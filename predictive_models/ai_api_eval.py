"""
ai_api_eval.py

RAG-LLM evaluation: retrieve similar train taxa per test row, predict log10 mass
with an LLM, optionally blend with a neighbor baseline, then evaluate vs test.csv.

Environment variables (recommended in `private/secrets.env`, git-ignored):
- AI_PROVIDER: "ollama" or "anthropic" (default "anthropic")

For Ollama:
- OLLAMA_BASE_URL (default http://localhost:11434)
- OLLAMA_MODEL (default llama3.1)
- OLLAMA_EMBED_MODEL (default nomic-embed-text)

For Anthropic:
- ANTHROPIC_API_KEY (required)
- ANTHROPIC_BASE_URL (default https://api.anthropic.com)
- ANTHROPIC_MODEL (default claude-sonnet-4-6)
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from predictive_models.llm_clients import (
    ChatConfig,
    EmbedConfig,
    chat_completion,
    embed_texts_ollama,
    load_private_secrets,
    validate_anthropic_api_key,
)
from predictive_models.rag_core import (
    TARGET_COL,
    TAXONOMY_COLS,
    HybridRetriever,
    finalize_log10_prediction,
    build_rag_system_prompt,
    build_rag_user_payload,
    features_to_text,
    parse_predictions_json,
    row_to_features,
)


TRAIN_CSV_DEFAULT = "./data/train.csv"
TEST_CSV_DEFAULT = "./data/test.csv"
DEFAULT_CACHE_PATH = "./data/ai_api_cache.jsonl"
PIPELINE_VERSION = "v2"


def _features_key(features: Dict[str, str]) -> str:
    parts = [f"{c}={features.get(c,'')}" for c in TAXONOMY_COLS]
    return "|".join(parts)


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - float(np.mean(y_true))) ** 2))
    if ss_tot == 0:
        return 0.0
    return float(1.0 - (ss_res / ss_tot))


@dataclass(frozen=True)
class ApiConfig:
    provider: str
    base_url: str
    model: str
    api_key: str
    timeout_s: int


@dataclass(frozen=True)
class CacheEntry:
    pred_log10_mass_g: float
    baseline_log10_mass_g: float
    llm_log10_mass_g: float
    pipeline_version: str = PIPELINE_VERSION


def load_cache(cache_path: str) -> Dict[str, CacheEntry]:
    cache: Dict[str, CacheEntry] = {}
    if not os.path.exists(cache_path):
        return cache
    with open(cache_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                k = obj.get("key")
                pred = obj.get("pred_log10_mass_g")
                baseline = obj.get("baseline_log10_mass_g")
                llm = obj.get("llm_log10_mass_g")
                version = str(obj.get("pipeline_version", "v1"))
                if (
                    not isinstance(k, str)
                    or not isinstance(pred, (int, float))
                    or not isinstance(baseline, (int, float))
                    or not isinstance(llm, (int, float))
                    or version != PIPELINE_VERSION
                ):
                    continue
                cache[k] = CacheEntry(
                    pred_log10_mass_g=float(pred),
                    baseline_log10_mass_g=float(baseline),
                    llm_log10_mass_g=float(llm),
                )
            except json.JSONDecodeError:
                continue
    return cache


def append_cache(
    cache_path: str,
    key: str,
    pred_log10_mass_g: float,
    baseline_log10_mass_g: float,
    llm_log10_mass_g: float,
    raw: Dict[str, Any],
) -> None:
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    rec = {
        "key": key,
        "pred_log10_mass_g": float(pred_log10_mass_g),
        "baseline_log10_mass_g": float(baseline_log10_mass_g),
        "llm_log10_mass_g": float(llm_log10_mass_g),
        "pipeline_version": PIPELINE_VERSION,
        "raw": raw,
        "ts": int(time.time()),
    }
    with open(cache_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def call_llm_batch(cfg: ApiConfig, user_payload: str) -> str:
    chat_cfg = ChatConfig(
        provider=cfg.provider,
        base_url=cfg.base_url,
        model=cfg.model,
        api_key=cfg.api_key,
        timeout_s=cfg.timeout_s,
    )
    last_err: Exception | None = None
    for attempt in range(8):
        try:
            return chat_completion(
                chat_cfg,
                system=build_rag_system_prompt(),
                user=user_payload,
                max_tokens=900,
            )
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(min(60, 2**attempt))
    raise RuntimeError(f"LLM batch call failed after retries: {last_err}") from last_err


def extract_predictions(content_text: str, expected_n: int) -> List[float]:
    try:
        return parse_predictions_json(content_text, expected_n=expected_n)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Could not parse predictions from model response: {e}") from e


def iter_batches(items: List[Any], batch_size: int) -> Iterable[List[Any]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RAG-LLM body mass prediction and evaluation (RMSE/R2)."
    )
    parser.add_argument("--train", default=TRAIN_CSV_DEFAULT)
    parser.add_argument("--test", default=TEST_CSV_DEFAULT)
    parser.add_argument("--cache", default=DEFAULT_CACHE_PATH)
    parser.add_argument("--top-k", type=int, default=12, help="Retrieved train examples per query")
    parser.add_argument("--alpha", type=float, default=0.65, help="Dense-vs-lexical blend weight")
    parser.add_argument(
        "--blend-weight",
        type=float,
        default=0.0,
        help="Weight on neighbor baseline (0=LLM only, 1=baseline only)",
    )
    parser.add_argument(
        "--use-embeddings",
        action="store_true",
        help="Use Ollama embeddings for dense retrieval (requires local Ollama)",
    )
    parser.add_argument("--batch-size", type=int, default=5, help="API batch size")
    parser.add_argument("--max-test", type=int, default=0, help="0 means all test rows")
    parser.add_argument("--timeout", type=int, default=60, help="API timeout in seconds")
    parser.add_argument(
        "--out-csv",
        default="./data/ai_api_predictions.csv",
        help="Write per-row predictions CSV",
    )
    args = parser.parse_args()

    load_private_secrets()

    provider = os.getenv("AI_PROVIDER", "anthropic").strip().lower()
    if provider not in {"ollama", "anthropic"}:
        raise SystemExit("AI_PROVIDER must be 'ollama' or 'anthropic'.")

    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
        model = os.getenv("OLLAMA_MODEL", "llama3.1").strip() or "llama3.1"
        api_key = ""
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        try:
            validate_anthropic_api_key(api_key)
        except ValueError as e:
            raise SystemExit(str(e)) from e
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip()
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"

    cfg = ApiConfig(provider=provider, base_url=base_url, api_key=api_key, model=model, timeout_s=args.timeout)

    train = pd.read_csv(args.train)
    test = pd.read_csv(args.test)

    missing_cols = [c for c in ([TARGET_COL] + TAXONOMY_COLS) if c not in train.columns]
    if missing_cols:
        raise SystemExit(f"Train CSV missing columns: {missing_cols}")

    missing_cols_test = [c for c in ([TARGET_COL] + TAXONOMY_COLS) if c not in test.columns]
    if missing_cols_test:
        raise SystemExit(f"Test CSV missing columns: {missing_cols_test}")

    train_mass = train[TARGET_COL].astype(float).to_numpy()
    train_log_mass = np.log10(train_mass)
    test_y_log = np.log10(test[TARGET_COL].astype(float).to_numpy())

    train_features = [row_to_features(row) for _, row in train.iterrows()]

    train_embeddings = None
    if args.use_embeddings:
        embed_cfg = EmbedConfig(
            provider="ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip(),
            model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text").strip() or "nomic-embed-text",
            timeout_s=int(args.timeout),
        )
        train_texts = [features_to_text(x) for x in train_features]
        train_embeddings = np.asarray(embed_texts_ollama(cfg=embed_cfg, texts=train_texts), dtype=float)

    retriever = HybridRetriever(
        train_features=train_features,
        train_log_mass=train_log_mass,
        train_mass=train_mass,
        train_embeddings=train_embeddings,
        alpha=float(args.alpha),
    )

    test_df = test.copy()
    if int(args.max_test) and int(args.max_test) > 0:
        test_df = test_df.iloc[: int(args.max_test)].copy()
        test_y_log = test_y_log[: len(test_df)]

    test_embeddings = None
    if args.use_embeddings and train_embeddings is not None:
        embed_cfg = EmbedConfig(
            provider="ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip(),
            model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text").strip() or "nomic-embed-text",
            timeout_s=int(args.timeout),
        )
        test_features_pre = [row_to_features(row) for _, row in test_df.iterrows()]
        test_texts = [features_to_text(x) for x in test_features_pre]
        test_embeddings = np.asarray(embed_texts_ollama(cfg=embed_cfg, texts=test_texts), dtype=float)

    cache = load_cache(args.cache)

    test_features: List[Dict[str, str]] = []
    test_keys: List[str] = []
    retrieved_per_row: List[Any] = []
    for i, (_, row) in enumerate(test_df.iterrows()):
        feats = row_to_features(row)
        k = _features_key(feats)
        test_features.append(feats)
        test_keys.append(k)
        q_emb = test_embeddings[i] if test_embeddings is not None else None
        retrieved_per_row.append(
            retriever.retrieve(query_features=feats, query_embedding=q_emb, top_k=int(args.top_k))
        )

    pred_log: List[float] = [np.nan] * len(test_df)
    baseline_log: List[float] = [np.nan] * len(test_df)
    llm_log: List[float] = [np.nan] * len(test_df)

    need_idx = [i for i, k in enumerate(test_keys) if k not in cache]
    for i, k in enumerate(test_keys):
        if k in cache:
            entry = cache[k]
            pred_log[i] = entry.pred_log10_mass_g
            baseline_log[i] = entry.baseline_log10_mass_g
            llm_log[i] = entry.llm_log10_mass_g

    if need_idx:
        for batch_idxs in iter_batches(need_idx, batch_size=max(1, int(args.batch_size))):
            batch_feats = [test_features[i] for i in batch_idxs]
            batch_retrieved = [retrieved_per_row[i] for i in batch_idxs]
            user_payload = build_rag_user_payload(batch_feats, batch_retrieved)

            content_text = call_llm_batch(cfg, user_payload)
            batch_llm_preds = extract_predictions(content_text, expected_n=len(batch_feats))

            for j, p in enumerate(batch_llm_preds):
                row_i = batch_idxs[j]
                final, base, llm_val = finalize_log10_prediction(
                    query=test_features[row_i],
                    retrieved=batch_retrieved[j],
                    llm_log10=float(p),
                    blend_weight=float(args.blend_weight),
                )
                baseline_log[row_i] = base
                llm_log[row_i] = llm_val
                pred_log[row_i] = final
                k = test_keys[row_i]
                cache[k] = CacheEntry(
                    pred_log10_mass_g=final,
                    baseline_log10_mass_g=base,
                    llm_log10_mass_g=llm_val,
                )
                append_cache(
                    args.cache,
                    key=k,
                    pred_log10_mass_g=final,
                    baseline_log10_mass_g=base,
                    llm_log10_mass_g=llm_val,
                    raw={"provider": cfg.provider, "content": content_text},
                )

    y_true_log = test_y_log
    y_pred_log = np.asarray(pred_log, dtype=float)

    log_rmse = rmse(y_true_log, y_pred_log)
    log_r2 = r2_score(y_true_log, y_pred_log)

    y_true_g = np.power(10.0, y_true_log)
    y_pred_g = np.power(10.0, y_pred_log)
    g_rmse = rmse(y_true_g, y_pred_g)
    g_r2 = r2_score(y_true_g, y_pred_g)

    print("Provider:", cfg.provider)
    print("Model:", cfg.model)
    print("Retrieval:", "hybrid+embeddings" if args.use_embeddings else "taxonomy+lexical")
    print("Top-k:", int(args.top_k))
    print("Blend weight (baseline):", float(args.blend_weight))
    print("Test rows:", len(test_df))
    print("Log10-space RMSE:", log_rmse)
    print("Log10-space R2:", log_r2)
    print("Gram-space RMSE:", g_rmse)
    print("Gram-space R2:", g_r2)

    out = test_df[TAXONOMY_COLS + [TARGET_COL]].copy()
    out["pred_log10_mass_g"] = y_pred_log
    out["true_log10_mass_g"] = y_true_log
    out["baseline_log10_mass_g"] = np.asarray(baseline_log, dtype=float)
    out["llm_log10_mass_g"] = np.asarray(llm_log, dtype=float)
    out["pred_mass_g"] = y_pred_g
    out["abs_error_g"] = np.abs(out["pred_mass_g"] - out[TARGET_COL].astype(float))
    out.to_csv(args.out_csv, index=False)
    print("Wrote:", args.out_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

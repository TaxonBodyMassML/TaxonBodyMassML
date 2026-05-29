"""
RAG-LLM predictor for taxonomy -> body mass prediction.

Pipeline:
1) Read train/test CSV data.
2) Retrieve top-k similar train rows (lexical + taxonomy match + optional embeddings).
3) Compute a neighbor baseline (weighted median log10 mass).
4) Ask an LLM using retrieved context, then blend LLM output with baseline.

Environment variables:
- AI_PROVIDER (optional, "ollama" or "anthropic", default "anthropic")

For Ollama:
- OLLAMA_BASE_URL (optional, default http://localhost:11434)
- OLLAMA_MODEL (optional, default llama3.1)
- OLLAMA_EMBED_MODEL (optional, default nomic-embed-text)

For Anthropic:
- ANTHROPIC_API_KEY (required)
- ANTHROPIC_BASE_URL (optional, default https://api.anthropic.com)
- ANTHROPIC_MODEL (optional, default claude-sonnet-4-6)
"""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Dict, List

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
    build_single_rag_prompt,
    features_to_text,
    parse_first_float,
    row_to_features,
)


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def load_checkpoint(path: str) -> Dict[int, Dict[str, float]]:
    done: Dict[int, Dict[str, float]] = {}
    if not os.path.exists(path):
        return done
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                idx = int(obj["idx"])
                done[idx] = {
                    "pred_log10_mass_g": float(obj["pred_log10_mass_g"]),
                    "baseline_log10_mass_g": float(obj["baseline_log10_mass_g"]),
                    "llm_log10_mass_g": float(obj["llm_log10_mass_g"]),
                }
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return done


def append_checkpoint(
    path: str,
    idx: int,
    pred_log10: float,
    baseline_log10: float,
    llm_log10: float,
) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    rec = {
        "idx": int(idx),
        "pred_log10_mass_g": float(pred_log10),
        "baseline_log10_mass_g": float(baseline_log10),
        "llm_log10_mass_g": float(llm_log10),
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def write_partial_csv(
    test: pd.DataFrame,
    done: Dict[int, Dict[str, float]],
    out_csv: str,
) -> None:
    if not done:
        return
    out = test.iloc[sorted(done.keys())][TAXONOMY_COLS + [TARGET_COL]].copy()
    out["pred_log10_mass_g"] = [done[i]["pred_log10_mass_g"] for i in sorted(done.keys())]
    out["true_log10_mass_g"] = np.log10(out[TARGET_COL].astype(float).to_numpy())
    out["baseline_log10_mass_g"] = [done[i]["baseline_log10_mass_g"] for i in sorted(done.keys())]
    out["llm_log10_mass_g"] = [done[i]["llm_log10_mass_g"] for i in sorted(done.keys())]
    out["pred_mass_g"] = np.power(10.0, out["pred_log10_mass_g"].to_numpy())
    out["abs_error_g"] = np.abs(out["pred_mass_g"] - out[TARGET_COL].astype(float))
    out.to_csv(out_csv, index=False)


def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - float(np.mean(y_true))) ** 2))
    if ss_tot == 0:
        return 0.0
    return float(1.0 - (ss_res / ss_tot))


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG-LLM predictor for body mass from taxonomy CSVs.")
    parser.add_argument("--train", default="./data/train.csv")
    parser.add_argument("--test", default="./data/test.csv")
    parser.add_argument("--out-csv", default="./data/hybrid_rag_predictions.csv")
    parser.add_argument("--max-test", type=int, default=0, help="0 means all rows")
    parser.add_argument("--top-k", type=int, default=12, help="Retrieved examples per query")
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
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument(
        "--checkpoint",
        default="./data/hybrid_rag_checkpoint.jsonl",
        help="Resume checkpoint (append-only JSONL)",
    )
    parser.add_argument(
        "--save-every",
        type=int,
        default=25,
        help="Write partial CSV every N completed rows",
    )
    args = parser.parse_args()

    load_private_secrets()

    provider = os.getenv("AI_PROVIDER", "anthropic").strip().lower()
    if provider not in {"ollama", "anthropic"}:
        raise SystemExit("AI_PROVIDER must be 'ollama' or 'anthropic'.")

    timeout_s = int(args.timeout)

    if provider == "ollama":
        chat_cfg = ChatConfig(
            provider="ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip(),
            model=os.getenv("OLLAMA_MODEL", "llama3.1").strip() or "llama3.1",
            api_key="",
            timeout_s=timeout_s,
        )
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        try:
            validate_anthropic_api_key(api_key)
        except ValueError as e:
            raise SystemExit(str(e)) from e
        chat_cfg = ChatConfig(
            provider="anthropic",
            base_url=os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip(),
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip() or "claude-sonnet-4-6",
            api_key=api_key,
            timeout_s=timeout_s,
        )

    train = pd.read_csv(args.train)
    test = pd.read_csv(args.test)

    required = [TARGET_COL] + TAXONOMY_COLS
    missing_train = [c for c in required if c not in train.columns]
    missing_test = [c for c in required if c not in test.columns]
    if missing_train:
        raise SystemExit(f"Train CSV missing columns: {missing_train}")
    if missing_test:
        raise SystemExit(f"Test CSV missing columns: {missing_test}")

    if int(args.max_test) > 0:
        test = test.iloc[: int(args.max_test)].copy()

    train_mass = train[TARGET_COL].astype(float).to_numpy()
    test_mass = test[TARGET_COL].astype(float).to_numpy()
    train_log_mass = np.log10(train_mass)
    test_log_mass = np.log10(test_mass)

    train_features = [row_to_features(row) for _, row in train.iterrows()]
    test_features = [row_to_features(row) for _, row in test.iterrows()]

    train_embeddings = None
    test_embeddings = None
    embed_model = None
    if args.use_embeddings:
        embed_cfg = EmbedConfig(
            provider="ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip(),
            model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text").strip() or "nomic-embed-text",
            timeout_s=timeout_s,
        )
        embed_model = embed_cfg.model
        train_texts = [features_to_text(x) for x in train_features]
        test_texts = [features_to_text(x) for x in test_features]
        train_embeddings = np.asarray(embed_texts_ollama(cfg=embed_cfg, texts=train_texts), dtype=float)
        test_embeddings = np.asarray(embed_texts_ollama(cfg=embed_cfg, texts=test_texts), dtype=float)

    retriever = HybridRetriever(
        train_features=train_features,
        train_log_mass=train_log_mass,
        train_mass=train_mass,
        train_embeddings=train_embeddings,
        alpha=float(args.alpha),
    )

    done = load_checkpoint(args.checkpoint)
    if done:
        print(f"Resuming from checkpoint: {len(done)} rows already done")

    preds_log: List[float] = [np.nan] * len(test_features)
    baseline_logs: List[float] = [np.nan] * len(test_features)
    llm_logs: List[float] = [np.nan] * len(test_features)

    for i in sorted(done.keys()):
        if 0 <= i < len(test_features):
            preds_log[i] = done[i]["pred_log10_mass_g"]
            baseline_logs[i] = done[i]["baseline_log10_mass_g"]
            llm_logs[i] = done[i]["llm_log10_mass_g"]

    completed_since_save = 0
    for idx, query_feats in enumerate(test_features):
        if idx in done:
            continue

        query_emb = test_embeddings[idx] if test_embeddings is not None else None
        retrieved = retriever.retrieve(
            query_features=query_feats,
            query_embedding=query_emb,
            top_k=int(args.top_k),
        )
        system, user = build_single_rag_prompt(query=query_feats, retrieved=retrieved)

        llm_raw = None
        last_err: Exception | None = None
        for attempt in range(8):
            try:
                llm_raw = parse_first_float(
                    chat_completion(chat_cfg, system=system, user=user, max_tokens=256)
                )
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(min(60, 2**attempt))
        if llm_raw is None:
            raise RuntimeError(f"Row {idx} failed after retries: {last_err}") from last_err

        final_log, baseline_log, llm_log = finalize_log10_prediction(
            query=query_feats,
            retrieved=retrieved,
            llm_log10=float(llm_raw),
            blend_weight=float(args.blend_weight),
        )
        baseline_logs[idx] = baseline_log
        llm_logs[idx] = llm_log
        preds_log[idx] = final_log
        done[idx] = {
            "pred_log10_mass_g": final_log,
            "baseline_log10_mass_g": baseline_log,
            "llm_log10_mass_g": llm_log,
        }
        append_checkpoint(args.checkpoint, idx, final_log, baseline_log, llm_log)

        completed_since_save += 1
        if completed_since_save >= max(1, int(args.save_every)):
            write_partial_csv(test, done, args.out_csv)
            print(f"Checkpoint progress: {len(done)}/{len(test_features)} rows")
            completed_since_save = 0

    if np.isnan(np.asarray(preds_log, dtype=float)).any():
        missing = int(np.sum(np.isnan(np.asarray(preds_log, dtype=float))))
        raise SystemExit(f"Incomplete run: {missing} rows missing predictions")

    y_pred_log = np.asarray(preds_log, dtype=float)
    y_true_log = test_log_mass

    log_rmse = rmse(y_true_log, y_pred_log)
    log_r2 = r2_score(y_true_log, y_pred_log)

    y_pred_g = np.power(10.0, y_pred_log)
    y_true_g = np.power(10.0, y_true_log)
    g_rmse = rmse(y_true_g, y_pred_g)
    g_r2 = r2_score(y_true_g, y_pred_g)

    print("Provider:", chat_cfg.provider)
    print("Chat model:", chat_cfg.model)
    print("Embeddings:", "enabled" if embed_model else "taxonomy-only")
    if embed_model:
        print("Embedding model:", embed_model)
    print("Top-k:", int(args.top_k))
    print("Blend weight (baseline):", float(args.blend_weight))
    print("Rows evaluated:", len(test))
    print("Log10-space RMSE:", log_rmse)
    print("Log10-space R2:", log_r2)
    print("Gram-space RMSE:", g_rmse)
    print("Gram-space R2:", g_r2)

    out = test[TAXONOMY_COLS + [TARGET_COL]].copy()
    out["pred_log10_mass_g"] = y_pred_log
    out["true_log10_mass_g"] = y_true_log
    out["baseline_log10_mass_g"] = np.asarray(baseline_logs, dtype=float)
    out["llm_log10_mass_g"] = np.asarray(llm_logs, dtype=float)
    out["pred_mass_g"] = y_pred_g
    out["abs_error_g"] = np.abs(out["pred_mass_g"] - out[TARGET_COL].astype(float))
    out.to_csv(args.out_csv, index=False)
    print("Wrote:", args.out_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
ai_api_eval.py
contributors: (added by Cursor agent)
purpose: call an AI API to predict body mass from taxonomy fields,
         then evaluate prediction quality vs. data/test.csv.

This script is designed to fit the existing project layout:
- Uses the same CSVs as predictive_models/decision_tree.py
- Evaluates with RMSE + R^2 (in log10 space by default)
- Uses requests (already used elsewhere in the repo)

API compatibility:
- OpenAI-compatible Chat Completions endpoint:
  POST {AI_API_BASE_URL}/chat/completions
  Authorization: Bearer {AI_API_KEY}

Environment variables:
- AI_API_BASE_URL (default: https://api.openai.com/v1)
- AI_API_KEY (required)
- AI_MODEL (default: gpt-4.1-mini)
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


TRAIN_CSV_DEFAULT = "./data/train.csv"
TEST_CSV_DEFAULT = "./data/test.csv"
DEFAULT_CACHE_PATH = "./data/ai_api_cache.jsonl"

TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
TARGET_COL = "mass_g"


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and np.isnan(x):
        return ""
    return str(x).strip()


def _row_to_features(row: pd.Series) -> Dict[str, str]:
    return {c: _safe_str(row.get(c, "")) for c in TAXONOMY_COLS}


def _features_key(features: Dict[str, str]) -> str:
    # stable cache key
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
    base_url: str
    api_key: str
    model: str
    timeout_s: int


def load_cache(cache_path: str) -> Dict[str, float]:
    cache: Dict[str, float] = {}
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
                v = obj.get("pred_log10_mass_g")
                if isinstance(k, str) and isinstance(v, (int, float)):
                    cache[k] = float(v)
            except json.JSONDecodeError:
                continue
    return cache


def append_cache(cache_path: str, key: str, pred_log10_mass_g: float, raw: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    rec = {
        "key": key,
        "pred_log10_mass_g": float(pred_log10_mass_g),
        "raw": raw,
        "ts": int(time.time()),
    }
    with open(cache_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def build_messages(
    fewshot_examples: List[Tuple[Dict[str, str], float]],
    batch_features: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """
    We ask the model to output strict JSON only:
    { "predictions": [<number>, ...] }
    Where each number is log10(mass_g) aligned to batch order.
    """
    system = (
        "You are a careful regression model. "
        "Given taxonomy fields (kingdom, phylum, class, order, family, genus, species), "
        "predict log10(body mass in grams). "
        "Return ONLY strict JSON with a top-level key 'predictions' mapping to an array of numbers. "
        "No prose, no markdown, no code fences."
    )

    ex_lines: List[str] = []
    for feats, log10_mass in fewshot_examples:
        ex_lines.append(
            json.dumps({"x": feats, "y_log10_mass_g": float(log10_mass)}, ensure_ascii=False)
        )

    user_payload = {
        "task": "predict_log10_mass_g",
        "fewshot": [json.loads(s) for s in ex_lines],
        "inputs": batch_features,
        "output_format": {"predictions": ["number (log10 mass_g) aligned to inputs"]},
    }

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def call_chat_completions(
    cfg: ApiConfig,
    messages: List[Dict[str, str]],
    max_retries: int = 5,
) -> Dict[str, Any]:
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": 0,
    }

    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            data = json.dumps(payload).encode("utf-8")
            req = Request(url, data=data, headers=headers, method="POST")
            with urlopen(req, timeout=cfg.timeout_s) as resp:
                status = getattr(resp, "status", 200)
                raw = resp.read().decode("utf-8", errors="replace")
                if status in (429, 500, 502, 503, 504):
                    time.sleep(min(30, 2**attempt))
                    continue
                return json.loads(raw)
        except HTTPError as e:
            # Retry on common transient errors
            if e.code in (429, 500, 502, 503, 504):
                last_err = e
                time.sleep(min(30, 2**attempt))
                continue
            last_err = e
            break
        except (URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(min(30, 2**attempt))
    raise RuntimeError(f"AI API request failed after {max_retries} attempts: {last_err}")


def extract_predictions(response_json: Dict[str, Any], expected_n: int) -> List[float]:
    try:
        content = response_json["choices"][0]["message"]["content"]
        obj = json.loads(content)
        preds = obj.get("predictions")
        if not isinstance(preds, list):
            raise ValueError("Missing 'predictions' list")
        out: List[float] = []
        for p in preds:
            if isinstance(p, (int, float)):
                out.append(float(p))
            elif isinstance(p, str):
                out.append(float(p.strip()))
            else:
                raise ValueError(f"Bad prediction type: {type(p)}")
        if len(out) != expected_n:
            raise ValueError(f"Expected {expected_n} predictions, got {len(out)}")
        return out
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Could not parse predictions from model response: {e}") from e


def iter_batches(items: List[Any], batch_size: int) -> Iterable[List[Any]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Call an AI API to predict body mass and evaluate RMSE/R2."
    )
    parser.add_argument("--train", default=TRAIN_CSV_DEFAULT)
    parser.add_argument("--test", default=TEST_CSV_DEFAULT)
    parser.add_argument("--cache", default=DEFAULT_CACHE_PATH)
    parser.add_argument("--fewshot", type=int, default=25, help="Number of train examples")
    parser.add_argument("--batch-size", type=int, default=20, help="API batch size")
    parser.add_argument("--max-test", type=int, default=0, help="0 means all test rows")
    parser.add_argument("--timeout", type=int, default=60, help="API timeout in seconds")
    parser.add_argument(
        "--out-csv",
        default="./data/ai_api_predictions.csv",
        help="Write per-row predictions CSV",
    )
    args = parser.parse_args()

    base_url = os.getenv("AI_API_BASE_URL", "https://api.openai.com/v1")
    api_key = os.getenv("AI_API_KEY", "").strip()
    model = os.getenv("AI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    if not api_key:
        raise SystemExit("Missing AI_API_KEY environment variable.")

    cfg = ApiConfig(base_url=base_url, api_key=api_key, model=model, timeout_s=args.timeout)

    train = pd.read_csv(args.train)
    test = pd.read_csv(args.test)

    missing_cols = [c for c in ([TARGET_COL] + TAXONOMY_COLS) if c not in train.columns]
    if missing_cols:
        raise SystemExit(f"Train CSV missing columns: {missing_cols}")

    missing_cols_test = [c for c in ([TARGET_COL] + TAXONOMY_COLS) if c not in test.columns]
    if missing_cols_test:
        raise SystemExit(f"Test CSV missing columns: {missing_cols_test}")

    # Log-transform target to match existing project's evaluation style.
    train_y_log = np.log10(train[TARGET_COL].astype(float).to_numpy())
    test_y_log = np.log10(test[TARGET_COL].astype(float).to_numpy())

    # Prepare few-shot examples from training set.
    n_fewshot = max(0, min(int(args.fewshot), len(train)))
    fewshot_idx = np.linspace(0, len(train) - 1, num=n_fewshot, dtype=int) if n_fewshot else []
    fewshot_examples: List[Tuple[Dict[str, str], float]] = [
        (_row_to_features(train.iloc[i]), float(train_y_log[i])) for i in fewshot_idx
    ]

    # Limit test rows if requested.
    test_df = test.copy()
    if int(args.max_test) and int(args.max_test) > 0:
        test_df = test_df.iloc[: int(args.max_test)].copy()
        test_y_log = test_y_log[: len(test_df)]

    cache = load_cache(args.cache)

    # Build list of rows needing API calls.
    test_features: List[Dict[str, str]] = []
    test_keys: List[str] = []
    for _, row in test_df.iterrows():
        feats = _row_to_features(row)
        k = _features_key(feats)
        test_features.append(feats)
        test_keys.append(k)

    pred_log: List[float] = [np.nan] * len(test_df)
    need_idx = [i for i, k in enumerate(test_keys) if k not in cache]
    for i, k in enumerate(test_keys):
        if k in cache:
            pred_log[i] = float(cache[k])

    # Call API in batches for missing predictions.
    if need_idx:
        idx_to_feats = [(i, test_features[i]) for i in need_idx]
        for batch in iter_batches(idx_to_feats, batch_size=max(1, int(args.batch_size))):
            batch_indices = [i for i, _ in batch]
            batch_feats = [feats for _, feats in batch]

            messages = build_messages(fewshot_examples=fewshot_examples, batch_features=batch_feats)
            resp = call_chat_completions(cfg, messages)
            batch_preds = extract_predictions(resp, expected_n=len(batch_feats))

            for j, p in enumerate(batch_preds):
                row_i = batch_indices[j]
                pred_log[row_i] = float(p)
                k = test_keys[row_i]
                cache[k] = float(p)
                append_cache(args.cache, key=k, pred_log10_mass_g=float(p), raw=resp)

    y_true_log = test_y_log
    y_pred_log = np.asarray(pred_log, dtype=float)

    # Evaluate in log space.
    log_rmse = rmse(y_true_log, y_pred_log)
    log_r2 = r2_score(y_true_log, y_pred_log)

    # Convert back to grams for an additional sanity check in original space.
    y_true_g = np.power(10.0, y_true_log)
    y_pred_g = np.power(10.0, y_pred_log)
    g_rmse = rmse(y_true_g, y_pred_g)
    g_r2 = r2_score(y_true_g, y_pred_g)

    print("AI API model:", cfg.model)
    print("Test rows:", len(test_df))
    print("Log10-space RMSE:", log_rmse)
    print("Log10-space R2:", log_r2)
    print("Gram-space RMSE:", g_rmse)
    print("Gram-space R2:", g_r2)

    out = test_df[TAXONOMY_COLS + [TARGET_COL]].copy()
    out["pred_log10_mass_g"] = y_pred_log
    out["true_log10_mass_g"] = y_true_log
    out["pred_mass_g"] = y_pred_g
    out["abs_error_g"] = np.abs(out["pred_mass_g"] - out[TARGET_COL].astype(float))
    out.to_csv(args.out_csv, index=False)
    print("Wrote:", args.out_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


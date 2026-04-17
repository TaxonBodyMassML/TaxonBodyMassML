"""
Hybrid RAG regressor for taxonomy -> body mass prediction.

Pipeline:
1) Read train/test CSV data.
2) Build a hybrid retriever over train rows:
   - lexical score from taxonomy token overlap
   - dense score from embeddings
3) For each test row, retrieve top-k similar train examples.
4) Ask an LLM for a numeric prediction using retrieved context.
5) Evaluate RMSE and R2 in both log10 and gram space.

Environment variables:
- AI_PROVIDER (optional, "ollama" or "openai", default "ollama")

For Ollama:
- OLLAMA_BASE_URL (optional, default http://localhost:11434)
- OLLAMA_MODEL (optional, default llama3.1)
- OLLAMA_EMBED_MODEL (optional, default nomic-embed-text)

For OpenAI-compatible endpoints:
- OPENAI_API_KEY (required)
- OPENAI_BASE_URL (optional, default https://api.openai.com/v1)
- OPENAI_MODEL (optional, default gpt-4.1-mini)
- OPENAI_EMBED_MODEL (optional, default text-embedding-3-small)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

TRAIN_CSV_DEFAULT = "./data/train.csv"
TEST_CSV_DEFAULT = "./data/test.csv"
OUT_CSV_DEFAULT = "./data/hybrid_rag_predictions.csv"

TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
TARGET_COL = "mass_g"


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


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and np.isnan(v):
        return ""
    return str(v).strip()


def row_to_features(row: pd.Series) -> Dict[str, str]:
    return {col: _safe_str(row.get(col, "")) for col in TAXONOMY_COLS}


def features_to_text(features: Dict[str, str]) -> str:
    return " | ".join(f"{col}:{features.get(col, '')}" for col in TAXONOMY_COLS)


def tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def lexical_score(a: Dict[str, str], b: Dict[str, str]) -> float:
    ta = set(tokenize(features_to_text(a)))
    tb = set(tokenize(features_to_text(b)))
    if not ta and not tb:
        return 0.0
    return float(len(ta & tb) / max(1, len(ta | tb)))


def cosine_sim(v1: np.ndarray, v2: np.ndarray) -> float:
    denom = float(np.linalg.norm(v1) * np.linalg.norm(v2))
    if denom == 0:
        return 0.0
    return float(np.dot(v1, v2) / denom)


@dataclass(frozen=True)
class ApiConfig:
    provider: str
    api_key: str
    base_url: str
    chat_model: str
    embed_model: str
    timeout_s: int


def _post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout_s: int) -> Dict[str, Any]:
    req = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body)


def call_with_retries(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout_s: int) -> Dict[str, Any]:
    last_err: Optional[Exception] = None
    for attempt in range(6):
        try:
            return _post_json(url=url, payload=payload, headers=headers, timeout_s=timeout_s)
        except HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                last_err = e
                time.sleep(min(30, 2**attempt))
                continue
            raise
        except (URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(min(30, 2**attempt))
    raise RuntimeError(f"Request failed after retries: {last_err}")


def _auth_headers(cfg: ApiConfig) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if cfg.provider == "openai":
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    return headers


def embed_texts_openai(cfg: ApiConfig, texts: Sequence[str], batch_size: int = 128) -> np.ndarray:
    all_embeddings: List[List[float]] = []
    url = cfg.base_url.rstrip("/") + "/embeddings"
    headers = _auth_headers(cfg)
    for i in range(0, len(texts), batch_size):
        chunk = list(texts[i : i + batch_size])
        payload = {
            "model": cfg.embed_model,
            "input": chunk,
        }
        response = call_with_retries(url=url, payload=payload, headers=headers, timeout_s=cfg.timeout_s)
        data = response.get("data", [])
        if not isinstance(data, list) or len(data) != len(chunk):
            raise ValueError("Unexpected embeddings response shape")
        for item in data:
            emb = item.get("embedding")
            if not isinstance(emb, list):
                raise ValueError("Missing embedding vector")
            all_embeddings.append([float(x) for x in emb])
    return np.asarray(all_embeddings, dtype=float)


def embed_texts_ollama(cfg: ApiConfig, texts: Sequence[str]) -> np.ndarray:
    all_embeddings: List[List[float]] = []
    url = cfg.base_url.rstrip("/") + "/api/embeddings"
    headers = _auth_headers(cfg)
    for text in texts:
        payload = {
            "model": cfg.embed_model,
            "prompt": text,
        }
        response = call_with_retries(url=url, payload=payload, headers=headers, timeout_s=cfg.timeout_s)
        emb = response.get("embedding")
        if not isinstance(emb, list):
            raise ValueError("Missing embedding vector from Ollama response")
        all_embeddings.append([float(x) for x in emb])
    return np.asarray(all_embeddings, dtype=float)


def embed_texts(cfg: ApiConfig, texts: Sequence[str], batch_size: int = 128) -> np.ndarray:
    if cfg.provider == "ollama":
        return embed_texts_ollama(cfg=cfg, texts=texts)
    return embed_texts_openai(cfg=cfg, texts=texts, batch_size=batch_size)


def parse_first_float(text: str) -> float:
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        raise ValueError(f"No numeric value found in response: {text[:200]}")
    return float(match.group(0))


def build_prompt(query: Dict[str, str], retrieved: List[Tuple[Dict[str, str], float, float]]) -> List[Dict[str, str]]:
    system = (
        "You predict log10(body_mass_g) from taxonomy. "
        "Use the retrieved examples as your grounded context. "
        "Return only one numeric value (no explanation)."
    )
    payload = {
        "query_taxonomy": query,
        "retrieved_examples": [
            {
                "taxonomy": feats,
                "mass_g": float(mass_g),
                "log10_mass_g": float(log_mass),
            }
            for feats, mass_g, log_mass in retrieved
        ],
        "task": "Predict log10_mass_g for query_taxonomy",
        "output": "single number only",
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def predict_with_chat_openai(cfg: ApiConfig, messages: List[Dict[str, str]]) -> float:
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    headers = _auth_headers(cfg)
    payload = {
        "model": cfg.chat_model,
        "messages": messages,
        "temperature": 0,
    }
    response = call_with_retries(url=url, payload=payload, headers=headers, timeout_s=cfg.timeout_s)
    content = response["choices"][0]["message"]["content"]
    return parse_first_float(str(content))


def predict_with_chat_ollama(cfg: ApiConfig, messages: List[Dict[str, str]]) -> float:
    url = cfg.base_url.rstrip("/") + "/api/chat"
    headers = _auth_headers(cfg)
    payload = {
        "model": cfg.chat_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0},
    }
    response = call_with_retries(url=url, payload=payload, headers=headers, timeout_s=cfg.timeout_s)
    content = response.get("message", {}).get("content", "")
    return parse_first_float(str(content))


def predict_with_chat(cfg: ApiConfig, messages: List[Dict[str, str]]) -> float:
    if cfg.provider == "ollama":
        return predict_with_chat_ollama(cfg=cfg, messages=messages)
    return predict_with_chat_openai(cfg=cfg, messages=messages)


class HybridRetriever:
    def __init__(
        self,
        train_features: List[Dict[str, str]],
        train_log_mass: np.ndarray,
        train_mass: np.ndarray,
        train_embeddings: np.ndarray,
        alpha: float = 0.65,
    ) -> None:
        self.train_features = train_features
        self.train_log_mass = np.asarray(train_log_mass, dtype=float)
        self.train_mass = np.asarray(train_mass, dtype=float)
        self.train_embeddings = np.asarray(train_embeddings, dtype=float)
        self.alpha = float(alpha)

    def retrieve(self, query_features: Dict[str, str], query_embedding: np.ndarray, top_k: int) -> List[Tuple[Dict[str, str], float, float]]:
        lexical = np.asarray([lexical_score(query_features, x) for x in self.train_features], dtype=float)
        dense = np.asarray([cosine_sim(query_embedding, e) for e in self.train_embeddings], dtype=float)

        # Normalize cosine from [-1, 1] -> [0, 1]
        dense01 = (dense + 1.0) / 2.0
        hybrid = self.alpha * dense01 + (1.0 - self.alpha) * lexical
        top_idx = np.argsort(-hybrid)[: max(1, top_k)]
        return [
            (
                self.train_features[int(i)],
                float(self.train_mass[int(i)]),
                float(self.train_log_mass[int(i)]),
            )
            for i in top_idx
        ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Hybrid RAG predictor for body mass from taxonomy CSVs.")
    parser.add_argument("--train", default=TRAIN_CSV_DEFAULT)
    parser.add_argument("--test", default=TEST_CSV_DEFAULT)
    parser.add_argument("--out-csv", default=OUT_CSV_DEFAULT)
    parser.add_argument("--max-test", type=int, default=0, help="0 means all rows")
    parser.add_argument("--top-k", type=int, default=8, help="Retrieved examples per query")
    parser.add_argument("--alpha", type=float, default=0.65, help="Dense-vs-lexical blend weight")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    provider = os.getenv("AI_PROVIDER", "ollama").strip().lower()
    if provider not in {"ollama", "openai"}:
        raise SystemExit("AI_PROVIDER must be 'ollama' or 'openai'.")

    if provider == "ollama":
        cfg = ApiConfig(
            provider="ollama",
            api_key="",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip(),
            chat_model=os.getenv("OLLAMA_MODEL", "llama3.1").strip() or "llama3.1",
            embed_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text").strip()
            or "nomic-embed-text",
            timeout_s=int(args.timeout),
        )
    else:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise SystemExit("Missing OPENAI_API_KEY environment variable.")
        cfg = ApiConfig(
            provider="openai",
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip(),
            chat_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
            embed_model=os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small").strip()
            or "text-embedding-3-small",
            timeout_s=int(args.timeout),
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

    train_texts = [features_to_text(x) for x in train_features]
    test_texts = [features_to_text(x) for x in test_features]
    train_embeddings = embed_texts(cfg=cfg, texts=train_texts)
    test_embeddings = embed_texts(cfg=cfg, texts=test_texts)

    retriever = HybridRetriever(
        train_features=train_features,
        train_log_mass=train_log_mass,
        train_mass=train_mass,
        train_embeddings=train_embeddings,
        alpha=float(args.alpha),
    )

    preds_log: List[float] = []
    for idx, query_feats in enumerate(test_features):
        retrieved = retriever.retrieve(
            query_features=query_feats,
            query_embedding=test_embeddings[idx],
            top_k=int(args.top_k),
        )
        messages = build_prompt(query=query_feats, retrieved=retrieved)
        pred_log = predict_with_chat(cfg=cfg, messages=messages)
        preds_log.append(pred_log)

    y_pred_log = np.asarray(preds_log, dtype=float)
    y_true_log = test_log_mass

    log_rmse = rmse(y_true_log, y_pred_log)
    log_r2 = r2_score(y_true_log, y_pred_log)

    y_pred_g = np.power(10.0, y_pred_log)
    y_true_g = np.power(10.0, y_true_log)
    g_rmse = rmse(y_true_g, y_pred_g)
    g_r2 = r2_score(y_true_g, y_pred_g)

    print("Provider:", cfg.provider)
    print("Chat model:", cfg.chat_model)
    print("Embedding model:", cfg.embed_model)
    print("Rows evaluated:", len(test))
    print("Log10-space RMSE:", log_rmse)
    print("Log10-space R2:", log_r2)
    print("Gram-space RMSE:", g_rmse)
    print("Gram-space R2:", g_r2)

    out = test[TAXONOMY_COLS + [TARGET_COL]].copy()
    out["pred_log10_mass_g"] = y_pred_log
    out["true_log10_mass_g"] = y_true_log
    out["pred_mass_g"] = y_pred_g
    out["abs_error_g"] = np.abs(out["pred_mass_g"] - out[TARGET_COL].astype(float))
    out.to_csv(args.out_csv, index=False)
    print("Wrote:", args.out_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

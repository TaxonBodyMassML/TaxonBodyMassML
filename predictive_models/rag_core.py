"""
Shared RAG utilities for taxonomy -> body mass prediction.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
TARGET_COL = "mass_g"

# Higher weight for more specific taxonomy levels.
TAXON_LEVEL_WEIGHTS: Dict[str, int] = {
    "species": 7,
    "genus": 6,
    "family": 5,
    "order": 4,
    "class": 3,
    "phylum": 2,
    "kingdom": 1,
}

RetrievedExample = Tuple[Dict[str, str], float, float, float]  # feats, mass_g, log10_mass_g, score


def safe_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and np.isnan(v):
        return ""
    return str(v).strip()


def row_to_features(row: pd.Series) -> Dict[str, str]:
    return {col: safe_str(row.get(col, "")) for col in TAXONOMY_COLS}


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


def taxonomy_match_score(a: Dict[str, str], b: Dict[str, str]) -> float:
    """Score exact matches at each taxonomy level (more specific levels weigh more)."""
    score = 0.0
    max_score = float(sum(TAXON_LEVEL_WEIGHTS.values()))
    for col in TAXONOMY_COLS:
        va = safe_str(a.get(col, "")).lower()
        vb = safe_str(b.get(col, "")).lower()
        if va and vb and va == vb:
            score += float(TAXON_LEVEL_WEIGHTS[col])
    return score / max_score if max_score else 0.0


def combined_lexical_score(a: Dict[str, str], b: Dict[str, str]) -> float:
    return max(lexical_score(a, b), taxonomy_match_score(a, b))


def cosine_sim(v1: np.ndarray, v2: np.ndarray) -> float:
    denom = float(np.linalg.norm(v1) * np.linalg.norm(v2))
    if denom == 0:
        return 0.0
    return float(np.dot(v1, v2) / denom)


def same_species(a: Dict[str, str], b: Dict[str, str]) -> bool:
    sa = safe_str(a.get("species", "")).lower()
    sb = safe_str(b.get("species", "")).lower()
    return bool(sa and sb and sa == sb)


def same_genus(a: Dict[str, str], b: Dict[str, str]) -> bool:
    ga = safe_str(a.get("genus", "")).lower()
    gb = safe_str(b.get("genus", "")).lower()
    return bool(ga and gb and ga == gb)


def _weighted_mean_log10(
    retrieved: Sequence[RetrievedExample],
    mask: np.ndarray,
) -> Optional[float]:
    if not np.any(mask):
        return None
    logs = np.asarray([float(r[2]) for r in retrieved], dtype=float)[mask]
    weights = np.asarray([max(float(r[3]), 1e-6) for r in retrieved], dtype=float)[mask]
    return float(np.sum(logs * weights) / np.sum(weights))


def species_anchor_log10(
    query: Dict[str, str],
    retrieved: Sequence[RetrievedExample],
) -> Optional[float]:
    mask = np.asarray([same_species(query, r[0]) for r in retrieved], dtype=bool)
    return _weighted_mean_log10(retrieved, mask)


def genus_anchor_log10(
    query: Dict[str, str],
    retrieved: Sequence[RetrievedExample],
) -> Optional[float]:
    mask = np.asarray([same_genus(query, r[0]) for r in retrieved], dtype=bool)
    return _weighted_mean_log10(retrieved, mask)


def hierarchical_baseline_log10(
    query: Dict[str, str],
    retrieved: Sequence[RetrievedExample],
) -> float:
    """Prefer same-species, then same-genus, then neighbor median."""
    species = species_anchor_log10(query, retrieved)
    if species is not None:
        return species
    genus = genus_anchor_log10(query, retrieved)
    if genus is not None:
        return genus
    return baseline_log10_from_retrieved(retrieved)


def baseline_log10_from_retrieved(
    retrieved: Sequence[RetrievedExample],
) -> float:
    """Weighted median log10 mass from retrieved neighbors."""
    if not retrieved:
        raise ValueError("No retrieved examples for baseline")

    logs = np.asarray([float(r[2]) for r in retrieved], dtype=float)
    weights = np.asarray([max(float(r[3]), 1e-6) for r in retrieved], dtype=float)
    order = np.argsort(logs)
    logs_sorted = logs[order]
    weights_sorted = weights[order]
    cum = np.cumsum(weights_sorted) / float(np.sum(weights_sorted))
    idx = int(np.searchsorted(cum, 0.5))
    idx = min(idx, len(logs_sorted) - 1)
    return float(logs_sorted[idx])


def soft_clamp_log10_to_neighbors(
    log10_value: float,
    retrieved: Sequence[RetrievedExample],
    margin: float = 2.0,
    extrapolation: float = 0.5,
) -> float:
    """Soft bounds: allow partial extrapolation beyond neighbor range."""
    logs = [float(r[2]) for r in retrieved]
    lo = float(min(logs) - margin)
    hi = float(max(logs) + margin)
    if log10_value < lo:
        return float(lo + extrapolation * (log10_value - lo))
    if log10_value > hi:
        return float(hi + extrapolation * (log10_value - hi))
    return float(log10_value)


def clamp_log10_to_neighbors(
    log10_value: float,
    retrieved: Sequence[RetrievedExample],
    margin: float = 1.5,
) -> float:
    """Keep predictions near retrieved neighbor mass range."""
    logs = [float(r[2]) for r in retrieved]
    lo = float(min(logs) - margin)
    hi = float(max(logs) + margin)
    return float(np.clip(log10_value, lo, hi))


def blend_log10_predictions(
    llm_log10: float,
    baseline_log10: float,
    blend_weight: float,
) -> float:
    """
    blend_weight in [0, 1]: 0 => LLM only, 1 => baseline only.
    """
    w = float(np.clip(blend_weight, 0.0, 1.0))
    return float((1.0 - w) * llm_log10 + w * baseline_log10)


def retrieval_bonus(query: Dict[str, str], candidate: Dict[str, str]) -> float:
    if same_species(query, candidate):
        return 0.35
    if same_genus(query, candidate):
        return 0.15
    return 0.0


def finalize_log10_prediction(
    query: Dict[str, str],
    retrieved: Sequence[RetrievedExample],
    llm_log10: float,
    blend_weight: float = 0.0,
) -> Tuple[float, float, float]:
    """
    Post-process LLM output with taxonomy-aware anchors.

    Returns (final_log10, hierarchical_baseline, refined_llm_log10).
    """
    baseline = hierarchical_baseline_log10(query, retrieved)
    species = species_anchor_log10(query, retrieved)

    llm_refined = soft_clamp_log10_to_neighbors(float(llm_log10), retrieved)
    if species is not None:
        llm_refined = 0.35 * llm_refined + 0.65 * species

    final = blend_log10_predictions(
        llm_log10=llm_refined,
        baseline_log10=baseline,
        blend_weight=float(blend_weight),
    )

    if species is not None:
        top_species_score = max(float(r[3]) for r in retrieved if same_species(query, r[0]))
        if top_species_score >= 0.85:
            final = 0.2 * final + 0.8 * species

    return final, baseline, llm_refined


class HybridRetriever:
    def __init__(
        self,
        train_features: List[Dict[str, str]],
        train_log_mass: np.ndarray,
        train_mass: np.ndarray,
        train_embeddings: Optional[np.ndarray] = None,
        alpha: float = 0.65,
    ) -> None:
        self.train_features = train_features
        self.train_log_mass = np.asarray(train_log_mass, dtype=float)
        self.train_mass = np.asarray(train_mass, dtype=float)
        self.train_embeddings = (
            np.asarray(train_embeddings, dtype=float) if train_embeddings is not None else None
        )
        self.alpha = float(alpha)

    def retrieve(
        self,
        query_features: Dict[str, str],
        query_embedding: Optional[np.ndarray] = None,
        top_k: int = 8,
    ) -> List[RetrievedExample]:
        lexical = np.asarray(
            [combined_lexical_score(query_features, x) for x in self.train_features],
            dtype=float,
        )

        if self.train_embeddings is not None and query_embedding is not None:
            dense = np.asarray(
                [cosine_sim(query_embedding, e) for e in self.train_embeddings],
                dtype=float,
            )
            dense01 = (dense + 1.0) / 2.0
            hybrid = self.alpha * dense01 + (1.0 - self.alpha) * lexical
        else:
            hybrid = lexical

        hybrid = hybrid + np.asarray(
            [retrieval_bonus(query_features, x) for x in self.train_features],
            dtype=float,
        )

        top_idx = np.argsort(-hybrid)[: max(1, top_k)]
        return [
            (
                self.train_features[int(i)],
                float(self.train_mass[int(i)]),
                float(self.train_log_mass[int(i)]),
                float(hybrid[int(i)]),
            )
            for i in top_idx
        ]


def build_rag_system_prompt() -> str:
    return (
        "You predict log10(body mass in grams) from taxonomy fields. "
        "Body mass spans many orders of magnitude; work in log10 space. "
        "If retrieved examples include the exact query species, treat those masses as primary evidence. "
        "Otherwise use same-genus neighbors, then broader taxonomic similarity. "
        "Return ONLY strict JSON with key 'predictions' as an array of numbers aligned to inputs. "
        "No prose, no markdown, no code fences."
    )


def _example_dict(
    feats: Dict[str, str],
    mass_g: float,
    log_mass: float,
    score: float,
) -> Dict[str, Any]:
    return {
        "taxonomy": feats,
        "mass_g": float(mass_g),
        "log10_mass_g": float(log_mass),
        "similarity": float(score),
    }


def build_rag_user_payload(
    queries: List[Dict[str, str]],
    retrieved_per_query: List[List[RetrievedExample]],
) -> str:
    inputs: List[Dict[str, Any]] = []
    for query, retrieved in zip(queries, retrieved_per_query):
        baseline = hierarchical_baseline_log10(query, retrieved)
        species = species_anchor_log10(query, retrieved)
        genus = genus_anchor_log10(query, retrieved)
        logs = [float(r[2]) for r in retrieved]
        species_examples = [_example_dict(*r) for r in retrieved if same_species(query, r[0])]
        inputs.append(
            {
                "query_taxonomy": query,
                "hierarchical_baseline_log10_mass_g": baseline,
                "same_species_anchor_log10_mass_g": species,
                "same_genus_anchor_log10_mass_g": genus,
                "retrieved_log10_range": [float(min(logs)), float(max(logs))],
                "same_species_examples": species_examples[:5],
                "retrieved_examples": [_example_dict(*r) for r in retrieved],
            }
        )

    payload = {
        "task": "predict_log10_mass_g",
        "inputs": inputs,
        "output_format": {"predictions": ["number (log10 mass_g) aligned to inputs"]},
    }
    return json.dumps(payload, ensure_ascii=False)


def build_single_rag_prompt(
    query: Dict[str, str],
    retrieved: List[RetrievedExample],
) -> Tuple[str, str]:
    """Prompt for one-query callers (hybrid_rag_predictor)."""
    baseline = hierarchical_baseline_log10(query, retrieved)
    species = species_anchor_log10(query, retrieved)
    logs = [float(r[2]) for r in retrieved]
    species_note = f" Same-species anchor: {species:.4f}." if species is not None else ""
    system = (
        "You predict log10(body_mass_g) from taxonomy. "
        "Body mass spans orders of magnitude; think in log10. "
        "Prioritize exact same-species retrieved examples when present. "
        f"Hierarchical baseline log10 mass: {baseline:.4f}.{species_note} "
        f"Neighbor log10 range: [{min(logs):.4f}, {max(logs):.4f}]. "
        "Return only one numeric value (no explanation)."
    )
    payload = {
        "query_taxonomy": query,
        "hierarchical_baseline_log10_mass_g": baseline,
        "same_species_anchor_log10_mass_g": species,
        "same_species_examples": [_example_dict(*r) for r in retrieved if same_species(query, r[0])][:5],
        "retrieved_examples": [_example_dict(*r) for r in retrieved],
        "task": "Predict log10_mass_g for query_taxonomy",
        "output": "single number only",
    }
    return system, json.dumps(payload, ensure_ascii=False)


def extract_json_object(content_text: str) -> Dict[str, Any]:
    """Parse JSON from raw LLM text, tolerating fences or leading prose."""
    text = content_text.strip()
    if not text:
        raise ValueError("Empty model response")

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        obj = json.loads(text[start : end + 1])
        if isinstance(obj, dict):
            return obj

    raise ValueError(f"Could not parse JSON object from response: {content_text[:200]}")


def parse_predictions_json(content_text: str, expected_n: int) -> List[float]:
    obj = extract_json_object(content_text)
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


def parse_first_float(text: str) -> float:
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        raise ValueError(f"No numeric value found in response: {text[:200]}")
    return float(match.group(0))

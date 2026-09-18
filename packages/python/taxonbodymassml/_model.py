"""
Artifact management: download, cache, load model/calibration/categories.
"""

import hashlib
import json
from pathlib import Path

import xgboost as xgb

from ._checksums import CHECKSUMS, HF_REPO_ID, MODEL_ARTIFACT_VERSION

# ---------------------------------------------------------------------------
# Cache location
# ---------------------------------------------------------------------------
try:
    from platformdirs import user_cache_dir

    _CACHE_DIR = Path(user_cache_dir("TaxonBodyMassML"))
except ImportError:  # pragma: no cover — platformdirs is a required dep
    _CACHE_DIR = Path.home() / ".cache" / "TaxonBodyMassML"

_ARTIFACT_FILES = list(CHECKSUMS.keys())
_ARTIFACTS_VERIFIED: bool = False


# ---------------------------------------------------------------------------
# Integrity check
# ---------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify(path: Path, filename: str) -> bool:
    return path.exists() and _sha256(path) == CHECKSUMS[filename]


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def download_model(version: str = "latest", force: bool = False) -> None:
    """Download model artifacts from Hugging Face Hub to the local cache.

    Parameters
    ----------
    version:
        Hugging Face revision to download.  ``"latest"`` resolves to the
        default branch of the repository (typically ``main``).
    force:
        Re-download and overwrite even if a valid cached copy already exists.
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "huggingface_hub is required to download model artifacts. "
            "Install it with: pip install huggingface_hub"
        ) from exc

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    revision = f"py-v{MODEL_ARTIFACT_VERSION}" if version == "latest" else version

    for filename in _ARTIFACT_FILES:
        cached = _CACHE_DIR / filename
        if not force and _verify(cached, filename):
            continue
        print(
            f"TaxonBodyMassML: downloading {filename} from {HF_REPO_ID} on Hugging Face..."  # noqa: E501
        )  # noqa: E501
        local_path = Path(
            hf_hub_download(
                repo_id=HF_REPO_ID,
                filename=filename,
                repo_type="model",
                revision=revision,
                local_dir=str(_CACHE_DIR),
            )
        )
        if not _verify(local_path, filename):
            raise RuntimeError(
                f"SHA256 mismatch for {filename}. The downloaded file may be "
                "corrupt. Re-run download_model(force=True) to retry."
            )


def _ensure_artifacts() -> None:
    """Download artifacts on first use if they are absent or corrupt."""
    global _ARTIFACTS_VERIFIED
    if _ARTIFACTS_VERIFIED:
        return
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    missing = [f for f in _ARTIFACT_FILES if not _verify(_CACHE_DIR / f, f)]
    if missing:
        print(
            f"TaxonBodyMassML: downloading model artifacts on first use "
            f"(files: {', '.join(missing)})..."
        )
        download_model()
    _ARTIFACTS_VERIFIED = True


# ---------------------------------------------------------------------------
# Loaders (called after _ensure_artifacts)
# ---------------------------------------------------------------------------
_MODEL_CACHE: xgb.Booster | None = None
_CALIBRATION_CACHE: list[float] | None = None
_CALIBRATION_BY_RANK_CACHE: dict[str, list[float]] | None = None
_CALIBRATION_BY_RANK_EE_CACHE: dict[str, list[float]] | None = None
_CATEGORIES_CACHE: dict[str, list[str]] | None = None
_LOOKUP_CACHE: dict[str, dict] | None = None
_EMBEDDINGS_CACHE: dict | None = None
_MODEL_EE_CACHE: xgb.Booster | None = None
_CALIBRATION_EE_CACHE: list[float] | None = None


def load_model() -> xgb.Booster:
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        m = xgb.Booster()
        m.load_model(str(_CACHE_DIR / "model.ubj"))
        _MODEL_CACHE = m
    return _MODEL_CACHE


def load_calibration() -> list[float]:
    global _CALIBRATION_CACHE
    if _CALIBRATION_CACHE is None:
        with open(_CACHE_DIR / "calibration.json") as f:
            _CALIBRATION_CACHE = json.load(f)["residuals"]
    return _CALIBRATION_CACHE


def load_calibration_by_rank() -> dict[str, list[float]]:
    global _CALIBRATION_BY_RANK_CACHE
    if _CALIBRATION_BY_RANK_CACHE is None:
        with open(_CACHE_DIR / "calibration_by_rank.json") as f:
            _CALIBRATION_BY_RANK_CACHE = json.load(f)
    return _CALIBRATION_BY_RANK_CACHE


def load_calibration_by_rank_ee() -> dict[str, list[float]]:
    global _CALIBRATION_BY_RANK_EE_CACHE
    if _CALIBRATION_BY_RANK_EE_CACHE is None:
        with open(_CACHE_DIR / "calibration_by_rank_ee.json") as f:
            _CALIBRATION_BY_RANK_EE_CACHE = json.load(f)
    return _CALIBRATION_BY_RANK_EE_CACHE


def load_categories() -> dict[str, list[str]]:
    global _CATEGORIES_CACHE
    if _CATEGORIES_CACHE is None:
        with open(_CACHE_DIR / "categories.json") as f:
            _CATEGORIES_CACHE = json.load(f)
    return _CATEGORIES_CACHE


def load_lookup() -> dict[str, dict]:
    global _LOOKUP_CACHE
    if _LOOKUP_CACHE is None:
        with open(_CACHE_DIR / "lookup.json") as f:
            _LOOKUP_CACHE = json.load(f)
    return _LOOKUP_CACHE


def _require_file(filename: str, method: str, training_script: str) -> None:
    path = _CACHE_DIR / filename
    if not path.exists():
        raise RuntimeError(
            f"Artifacts for method={method!r} are not yet available ({filename!r} "
            f"not found in cache). "
            f"Generate them first:\n"
            f"  python predictive_models/{training_script}\n"
            f"Then run scripts/export_artifacts.py and copy the new SHA-256 "
            f"checksums into packages/python/taxonbodymassml/_checksums.py."
        )


def load_embeddings() -> dict:
    global _EMBEDDINGS_CACHE
    if _EMBEDDINGS_CACHE is None:
        _require_file(
            "embeddings.json", "EntityEmbeddings", "entity_embeddings_model.py"
        )  # noqa: E501
        with open(_CACHE_DIR / "embeddings.json") as f:
            _EMBEDDINGS_CACHE = json.load(f)
    return _EMBEDDINGS_CACHE


def load_model_ee() -> xgb.Booster:
    global _MODEL_EE_CACHE
    if _MODEL_EE_CACHE is None:
        _require_file("model_ee.ubj", "EntityEmbeddings", "entity_embeddings_model.py")
        m = xgb.Booster()
        m.load_model(str(_CACHE_DIR / "model_ee.ubj"))
        _MODEL_EE_CACHE = m
    return _MODEL_EE_CACHE


def load_calibration_ee() -> list[float]:
    global _CALIBRATION_EE_CACHE
    if _CALIBRATION_EE_CACHE is None:
        _require_file(
            "calibration_ee.json", "EntityEmbeddings", "entity_embeddings_model.py"
        )  # noqa: E501
        with open(_CACHE_DIR / "calibration_ee.json") as f:
            _CALIBRATION_EE_CACHE = json.load(f)["residuals"]
    return _CALIBRATION_EE_CACHE

"""
Artifact management: download, cache, load model/calibration/categories.

Model versions live in sub-folders of the local cache and of the HuggingFace
Hub repo.  A bundled manifest.json is the single source of truth for which
(method, version) pairs exist, their per-file SHA-256 checksums, and the DB
snapshot they were trained on.
"""

from __future__ import annotations

import hashlib
import json
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import xgboost as xgb

HF_REPO_ID = "marknovak/TaxonBodyMassML"

_DEFAULT_METHOD = "EntityEmbeddings"

# ---------------------------------------------------------------------------
# Cache location
# ---------------------------------------------------------------------------
try:
    from platformdirs import user_cache_dir

    _CACHE_DIR = Path(user_cache_dir("TaxonBodyMassML"))
except ImportError:  # pragma: no cover — platformdirs is a required dep
    _CACHE_DIR = Path.home() / ".cache" / "TaxonBodyMassML"

# ---------------------------------------------------------------------------
# Manifest loading (bundled with the package)
# ---------------------------------------------------------------------------
_MANIFEST_CACHE: dict | None = None


def _manifest() -> dict:
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is None:
        try:
            from importlib.resources import files as _res_files

            data = (
                _res_files("taxonbodymassml")
                .joinpath("data/manifest.json")
                .read_text(encoding="utf-8")
            )
        except Exception:  # pragma: no cover — fallback for older Python
            import importlib.resources as _ir

            data = _ir.read_text("taxonbodymassml.data", "manifest.json", encoding="utf-8")
        _MANIFEST_CACHE = json.loads(data)
    return _MANIFEST_CACHE


# ---------------------------------------------------------------------------
# ModelSpec: identifies one (method, version) pair
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ModelSpec:
    method: str
    version: int
    path: str  # hub-relative folder, e.g. "models/XGBoost/v1"
    files: dict  # {name: {"sha256": "...", "size": int}}
    db_version: str


# ---------------------------------------------------------------------------
# Version resolution helpers
# ---------------------------------------------------------------------------
def _version_keys(manifest: dict, method: str) -> list[int]:
    """Sorted integer version numbers for method (may be empty)."""
    result = []
    for k in manifest.get("models", {}).get(method, {}):
        m = re.fullmatch(r"v(\d+)", k)
        if m:
            result.append(int(m.group(1)))
    return sorted(result)


def _newest_version(manifest: dict, method: str) -> int | None:
    keys = _version_keys(manifest, method)
    return keys[-1] if keys else None


def _cached_versions_for(manifest: dict, method: str) -> list[int]:
    """Sorted version numbers that are locally cached and checksum-valid."""
    result = []
    for v in _version_keys(manifest, method):
        entry = manifest["models"][method][f"v{v}"]
        folder = _CACHE_DIR / entry["path"]
        if all(
            (folder / name).exists() and _sha256(folder / name) == info["sha256"]
            for name, info in entry["files"].items()
        ):
            result.append(v)
    return result


def _normalise_version(raw) -> int | str:
    """Normalise "v2", "2", 2 → 2 (int); pass "newest"/"cached" through."""
    if isinstance(raw, int):
        return raw
    s = str(raw).strip()
    low = s.lower()
    if low in ("newest", "cached"):
        return low
    try:
        return int(s.lstrip("vV"))
    except ValueError:
        return s  # will raise a clear error downstream


# Tracks which (method, version) pairs have already triggered the
# "newer version available" note this session.
_NEWER_VERSION_NOTED: set[str] = set()


def resolve_model(method: str, method_version=None) -> ModelSpec:
    """Resolve (method, method_version) to a concrete ModelSpec.

    Parameters
    ----------
    method : str
        ``"XGBoost"`` or ``"EntityEmbeddings"``.
    method_version : str, int, or None
        ``None`` → read from ``tbm_options()["method_version"]`` (default ``"newest"``).
        ``"newest"`` → highest version in the bundled manifest (downloaded on demand).
        ``"cached"`` → highest locally-cached valid version; falls back to ``"newest"``
        with a printed message if nothing is cached.
        ``"v2"``, ``"2"``, ``2`` → that exact version.
    """
    from ._lookup import tbm_options

    mfest = _manifest()

    if method_version is None:
        method_version = tbm_options().get("method_version", "newest")

    v_raw = _normalise_version(method_version)

    avail = _version_keys(mfest, method)
    if not avail:
        raise RuntimeError(
            f"No versions of {method!r} found in the bundled manifest. "
            "Upgrade the package to access the latest models."
        )

    if v_raw == "newest":
        v_int = avail[-1]
    elif v_raw == "cached":
        cached = _cached_versions_for(mfest, method)
        if cached:
            v_int = cached[-1]
            newest_v = avail[-1]
            if v_int < newest_v:
                note_key = f"{method}:v{v_int}"
                if note_key not in _NEWER_VERSION_NOTED:
                    _NEWER_VERSION_NOTED.add(note_key)
                    print(
                        f"TaxonBodyMassML: using cached {method} v{v_int}; "
                        f"v{newest_v} is available "
                        f"(method_version='newest' or download_model() to upgrade)."
                    )
        else:
            print(
                f"TaxonBodyMassML: no cached {method} version; "
                f"falling back to newest (v{avail[-1]})."
            )
            v_int = avail[-1]
    elif isinstance(v_raw, int):
        v_int = v_raw
        if v_int not in avail:
            raise ValueError(
                f"Version {v_int!r} of {method!r} is not in the bundled manifest. "
                f"Available: {avail}."
            )
    else:
        raise ValueError(
            f"Invalid method_version {method_version!r}. "
            "Expected 'newest', 'cached', or an integer version (1, 2, 'v2', '2')."
        )

    entry = mfest["models"][method][f"v{v_int}"]
    return ModelSpec(
        method=method,
        version=v_int,
        path=entry["path"],
        files=entry["files"],
        db_version=entry["db_version"],
    )


# ---------------------------------------------------------------------------
# Integrity check
# ---------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_ok(path: Path, sha: str) -> bool:
    return path.exists() and _sha256(path) == sha


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def _fetch(hub_path: str, dest: Path) -> None:
    """Download one file from the pinned HuggingFace revision into dest."""
    try:
        from huggingface_hub import hf_hub_download
        from huggingface_hub.utils import EntryNotFoundError
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "huggingface_hub is required to download model artifacts. "
            "Install it with: pip install huggingface_hub"
        ) from exc

    mfest = _manifest()
    release = mfest.get("release", 1)
    revision = f"artifacts-{release}"

    print(f"TaxonBodyMassML: downloading {hub_path} from {HF_REPO_ID}...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        hf_hub_download(
            repo_id=HF_REPO_ID,
            filename=hub_path,
            repo_type="model",
            revision=revision,
            local_dir=str(_CACHE_DIR),
        )
    except EntryNotFoundError:
        raise RuntimeError(
            f"{hub_path!r} was not found in {HF_REPO_ID} at revision {revision!r}. "
            "The installed package may be newer than the published artifacts."
        )


def _ensure_files(
    rel_dir: str,
    files: dict,
    *,
    download: bool = True,
    force: bool = False,
    optional: bool = False,
) -> bool:
    """Verify and optionally download all files in a model folder.

    Returns True when every file is present and valid.  With ``download=False``
    returns False on the first missing/corrupt file without fetching.
    """
    folder = _CACHE_DIR / rel_dir
    for name, info in files.items():
        path = folder / name
        if not force and _file_ok(path, info["sha256"]):
            continue
        if not download:
            return False
        if optional:
            try:
                _fetch(f"{rel_dir}/{name}", path)
            except RuntimeError:
                warnings.warn(
                    f"{rel_dir}/{name} is not available in the current artifact revision.",
                    UserWarning,
                    stacklevel=4,
                )
                continue
        else:
            _fetch(f"{rel_dir}/{name}", path)
        if not _file_ok(path, info["sha256"]):
            raise RuntimeError(
                f"SHA-256 mismatch for {name} after download. "
                "The file may be corrupt. Re-run download_model(force=True) to retry."
            )
    return True


# Tracks specs and provenance entries that have been verified this session.
_VERIFIED: set[tuple] = set()


def _ensure_model(spec: ModelSpec, force: bool = False) -> None:
    """Ensure all model files for spec are cached and checksum-valid."""
    key = (spec.method, spec.version)
    if not force and key in _VERIFIED:
        return
    _VERIFIED.discard(key)
    missing = [
        name
        for name, info in spec.files.items()
        if not _file_ok(_CACHE_DIR / spec.path / name, info["sha256"])
    ]
    if missing or force:
        if missing:
            print(
                f"TaxonBodyMassML: downloading {spec.method} v{spec.version} "
                f"({', '.join(missing)})..."
            )
        _ensure_files(spec.path, spec.files, download=True, force=force)
    _VERIFIED.add(key)


def _ensure_provenance(db_version: str, force: bool = False) -> None:
    """Ensure provenance artifacts for db_version are cached."""
    mfest = _manifest()
    prov = mfest.get("provenance", {}).get(db_version)
    if prov is None:
        raise RuntimeError(
            f"No provenance entry for db_version={db_version!r} in the bundled manifest. "
            "Use get_citations()/create_bib() with level='source', or upgrade the package."
        )
    key = ("provenance", db_version)
    if not force and key in _VERIFIED:
        return
    _VERIFIED.discard(key)
    _ensure_files(prov["path"], prov["files"], download=True, force=force, optional=True)
    still_missing = [
        name
        for name, info in prov["files"].items()
        if not _file_ok(_CACHE_DIR / prov["path"] / name, info["sha256"])
    ]
    if still_missing:
        raise RuntimeError(
            "Provenance artifacts are not available: "
            + ", ".join(still_missing)
            + f" (db_version={db_version!r}). "
            "Use get_citations()/create_bib() with level='source', or upgrade the "
            "package once a revision with provenance artifacts is published."
        )
    _VERIFIED.add(key)


def provenance_path(filename: str, db_version: str | None = None) -> Path:
    """Return the path of a verified provenance artifact (downloads on first use).

    Parameters
    ----------
    filename : str
        File name within the provenance folder (e.g.
        ``"PrimaryCitations_BodyMass.bib"``).
    db_version : str or None
        Which provenance snapshot to use.  ``None`` uses the db_version of the
        newest version of the default method.
    """
    if db_version is None:
        spec = resolve_model(_DEFAULT_METHOD)
        db_version = spec.db_version
    _ensure_provenance(db_version)
    mfest = _manifest()
    prov_path = mfest["provenance"][db_version]["path"]
    return _CACHE_DIR / prov_path / filename


# ---------------------------------------------------------------------------
# Loaders: memoised by (method, version, artifact-name)
# ---------------------------------------------------------------------------
_LOADED: dict[tuple, Any] = {}


def _cache_key(spec: ModelSpec, name: str) -> tuple:
    return (spec.method, spec.version, name)


def load_model(spec: ModelSpec) -> xgb.Booster:
    k = _cache_key(spec, "model")
    if k not in _LOADED:
        _ensure_model(spec)
        m = xgb.Booster()
        m.load_model(str(_CACHE_DIR / spec.path / "model.ubj"))
        _LOADED[k] = m
    return _LOADED[k]


def load_calibration(spec: ModelSpec) -> list[float]:
    k = _cache_key(spec, "calibration")
    if k not in _LOADED:
        _ensure_model(spec)
        with open(_CACHE_DIR / spec.path / "calibration.json") as f:
            _LOADED[k] = json.load(f)["residuals"]
    return _LOADED[k]


def load_calibration_by_rank(spec: ModelSpec) -> dict[str, list[float]]:
    k = _cache_key(spec, "calibration_by_rank")
    if k not in _LOADED:
        _ensure_model(spec)
        with open(_CACHE_DIR / spec.path / "calibration_by_rank.json") as f:
            _LOADED[k] = json.load(f)
    return _LOADED[k]


def load_categories(spec: ModelSpec) -> dict[str, list[str]]:
    k = _cache_key(spec, "categories")
    if k not in _LOADED:
        _ensure_model(spec)
        with open(_CACHE_DIR / spec.path / "categories.json") as f:
            _LOADED[k] = json.load(f)
    return _LOADED[k]


def load_lookup(spec: ModelSpec) -> dict[str, dict]:
    k = _cache_key(spec, "lookup")
    if k not in _LOADED:
        _ensure_model(spec)
        with open(_CACHE_DIR / spec.path / "lookup.json") as f:
            _LOADED[k] = json.load(f)
    return _LOADED[k]


def load_embeddings(spec: ModelSpec) -> dict:
    k = _cache_key(spec, "embeddings")
    if k not in _LOADED:
        _ensure_model(spec)
        with open(_CACHE_DIR / spec.path / "embeddings.json") as f:
            _LOADED[k] = json.load(f)
    return _LOADED[k]


# ---------------------------------------------------------------------------
# Public API: download_model
# ---------------------------------------------------------------------------
_LEGACY_FLAT_FILES = [
    "model.ubj",
    "model_ee.ubj",
    "calibration.json",
    "calibration_ee.json",
    "calibration_by_rank.json",
    "calibration_by_rank_ee.json",
    "categories.json",
    "lookup.json",
    "embeddings.json",
    "PrimaryCitations_BodyMass.bib",
    "TaxonBodyMass_Provenance.csv.gz",
]


def download_model(
    method: str | None = None,
    method_version=None,
    force: bool = False,
    revision: str | None = None,
    prune: bool = False,
    version=None,
) -> None:
    """Download model and provenance artifacts from Hugging Face Hub.

    Parameters
    ----------
    method : str or None
        ``None`` → the default method (``"EntityEmbeddings"``).
        ``"all"`` → every method in the manifest.
    method_version :
        Which version to download.  Same semantics as ``predict_mass()``.
        ``None`` → package default (``"newest"``).  ``"all"`` → all versions
        in the manifest for the selected method(s).
    force :
        Re-download and re-verify even if a valid cached copy already exists.
    revision :
        HuggingFace revision override (e.g. ``"artifacts-2"``).  When set the
        manifest's pinned release is ignored for this call.
    prune :
        Remove flat legacy cache files (``model.ubj``, ``model_ee.ubj`` etc.)
        left by package versions older than 0.14.0.
    version :
        Deprecated alias for ``method_version``.
    """
    if version is not None:
        warnings.warn(
            "The 'version' argument of download_model() is deprecated; "
            "use 'method_version' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        if method_version is None:
            method_version = version

    mfest = _manifest()
    all_methods = list(mfest.get("models", {}).keys())

    if method == "all":
        methods = all_methods
    elif method is None:
        methods = [_DEFAULT_METHOD]
    else:
        if method not in mfest.get("models", {}):
            raise ValueError(
                f"Unknown method {method!r}. Available: {sorted(mfest.get('models', {}))}"
            )
        methods = [method]

    for meth in methods:
        avail = _version_keys(mfest, meth)
        if not avail:
            continue

        if method_version == "all":
            versions_to_dl = avail
        else:
            spec = resolve_model(meth, method_version)
            versions_to_dl = [spec.version]

        for v_int in versions_to_dl:
            entry = mfest["models"][meth].get(f"v{v_int}")
            if entry is None:
                continue
            spec = ModelSpec(
                method=meth,
                version=v_int,
                path=entry["path"],
                files=entry["files"],
                db_version=entry["db_version"],
            )
            _ensure_model(spec, force=force)

            db_ver = entry["db_version"]
            if db_ver in mfest.get("provenance", {}):
                try:
                    _ensure_provenance(db_ver, force=force)
                except RuntimeError:
                    pass  # provenance not yet published — not fatal

    if method == "all":
        for db_ver in mfest.get("provenance", {}):
            try:
                _ensure_provenance(db_ver, force=force)
            except RuntimeError:
                pass

    if prune:
        for name in _LEGACY_FLAT_FILES:
            p = _CACHE_DIR / name
            if p.exists():
                p.unlink()
                print(f"TaxonBodyMassML: pruned legacy cache file {p}")


# ---------------------------------------------------------------------------
# Public API: list_models
# ---------------------------------------------------------------------------
def list_models():
    """List all known model versions from the bundled manifest.

    Returns
    -------
    pd.DataFrame
        One row per (method, version) with columns: method, version, newest,
        db_version, trained, package_min, cached, size_mb, r2, mae.
    """
    import pandas as pd

    mfest = _manifest()
    rows = []
    for method, versions in mfest.get("models", {}).items():
        avail = _version_keys(mfest, method)
        newest_v = avail[-1] if avail else None
        cached_vs = _cached_versions_for(mfest, method)
        for v_key, entry in versions.items():
            m = re.fullmatch(r"v(\d+)", v_key)
            if not m:
                continue
            v_int = int(m.group(1))
            total_bytes = sum(f["size"] for f in entry["files"].values())
            metrics = entry.get("metrics", {})
            rows.append(
                {
                    "method": method,
                    "version": v_int,
                    "newest": v_int == newest_v,
                    "db_version": entry.get("db_version", ""),
                    "trained": entry.get("trained", ""),
                    "package_min": entry.get("package_min", ""),
                    "cached": v_int in cached_vs,
                    "size_mb": round(total_bytes / 1e6, 1) if total_bytes else 0.0,
                    "r2": metrics.get("r2"),
                    "mae": metrics.get("mae"),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "method",
            "version",
            "newest",
            "db_version",
            "trained",
            "package_min",
            "cached",
            "size_mb",
            "r2",
            "mae",
        ],
    )

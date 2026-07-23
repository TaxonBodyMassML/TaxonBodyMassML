"""
Shared HTTP layer: connection reuse, retry with backoff, NCBI rate limiting.

Environment variables
---------------------
TAXONBODYMASSML_EMAIL  Contact email appended to User-Agent (required by NCBI ToS).
NCBI_API_KEY           Optional NCBI API key; raises rate limit from 3 to 10 req/s.
"""

import os
import threading
import time

import requests

from . import __version__

# ---------------------------------------------------------------------------
# Session (connection reuse across all GBIF + NCBI calls)
# ---------------------------------------------------------------------------
_SESSION = requests.Session()
_EMAIL = os.environ.get("TAXONBODYMASSML_EMAIL", "").strip()
_USER_AGENT = f"TaxonBodyMassML/{__version__}" + (f" (contact: {_EMAIL})" if _EMAIL else "")
_SESSION.headers.update({"User-Agent": _USER_AGENT})

# ---------------------------------------------------------------------------
# NCBI rate limiter (slot reservation)
# ---------------------------------------------------------------------------
_NCBI_LOCK = threading.Lock()
_NCBI_NEXT_SLOT: float = 0.0


def _ncbi_rate() -> float:
    """Return the configured NCBI rate limit (requests/second)."""
    return 10.0 if os.environ.get("NCBI_API_KEY") else 3.0


def _ncbi_wait() -> None:
    """Reserve the next NCBI request slot and sleep until it arrives.

    Each thread gets an exclusive future slot assigned under the lock, so no
    two threads can ever wake at the same moment and fire simultaneous requests.
    """
    global _NCBI_NEXT_SLOT
    with _NCBI_LOCK:
        now = time.monotonic()
        rate = _ncbi_rate()
        if _NCBI_NEXT_SLOT < now:
            _NCBI_NEXT_SLOT = now
        wait_until = _NCBI_NEXT_SLOT
        _NCBI_NEXT_SLOT += 1.0 / rate
    sleep_for = wait_until - time.monotonic()
    if sleep_for > 0:
        time.sleep(sleep_for)


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------
_RETRY_DELAYS = (1.0, 2.0, 4.0)
_TRANSIENT = {429, 500, 502, 503, 504}


def _get(url: str, params: dict, *, ncbi: bool = False, timeout: int = 10) -> requests.Response:
    """GET with retry on transient failures. Set ncbi=True to apply rate limiting."""
    for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
        if ncbi:
            _ncbi_wait()
            api_key = os.environ.get("NCBI_API_KEY")
            if api_key:
                params = {**params, "api_key": api_key}
        try:
            resp = _SESSION.get(url, params=params, timeout=timeout)
            if resp.status_code not in _TRANSIENT:
                return resp
        except (requests.ConnectionError, requests.Timeout):
            if delay is None:
                raise
        if delay is not None:
            time.sleep(delay)
    return resp  # last attempt's response

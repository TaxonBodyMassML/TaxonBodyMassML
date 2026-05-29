from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def load_private_secrets(
    extra_paths: Optional[Sequence[str]] = None,
) -> None:
    """
    Loads key=value lines from local-only env files into os.environ.

    Later files override earlier ones. `private/secrets.env` wins over `.env`,
    and both override pre-existing process environment variables so local
    secrets stay authoritative during development.
    """
    paths: List[str] = []
    if extra_paths:
        paths.extend(extra_paths)
    paths.extend([".env", os.path.join("private", "secrets.env")])

    loaded: Dict[str, str] = {}
    for path in paths:
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k:
                        loaded[k] = v
        except OSError:
            continue

    for k, v in loaded.items():
        os.environ[k] = v


def validate_anthropic_api_key(api_key: str) -> None:
    key = api_key.strip()
    if not key:
        raise ValueError("Missing ANTHROPIC_API_KEY.")
    if not key.startswith("sk-ant-"):
        raise ValueError(
            "ANTHROPIC_API_KEY looks invalid (expected format: sk-ant-api03-...). "
            "Create a key at https://console.anthropic.com/settings/keys"
        )


@dataclass(frozen=True)
class ChatConfig:
    provider: str  # "ollama" | "anthropic"
    base_url: str
    model: str
    api_key: str = ""
    timeout_s: int = 60


@dataclass(frozen=True)
class EmbedConfig:
    provider: str  # "ollama"
    base_url: str
    model: str
    timeout_s: int = 60


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


def post_json_with_retries(
    *,
    url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout_s: int,
    max_retries: int = 8,
) -> Dict[str, Any]:
    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
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


def chat_completion(
    cfg: ChatConfig,
    *,
    system: str,
    user: str,
    max_tokens: int = 512,
) -> str:
    if cfg.provider == "ollama":
        url = cfg.base_url.rstrip("/") + "/api/chat"
        payload = {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": 0},
        }
        resp = post_json_with_retries(
            url=url,
            payload=payload,
            headers={"Content-Type": "application/json"},
            timeout_s=cfg.timeout_s,
        )
        return str(resp.get("message", {}).get("content", ""))

    if cfg.provider == "anthropic":
        validate_anthropic_api_key(cfg.api_key)
        base = cfg.base_url.rstrip("/")
        if base.endswith("/v1"):
            url = base + "/messages"
        else:
            url = base + "/v1/messages"
        payload = {
            "model": cfg.model,
            "max_tokens": int(max_tokens),
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": cfg.api_key,
            "anthropic-version": "2023-06-01",
        }
        resp = post_json_with_retries(url=url, payload=payload, headers=headers, timeout_s=cfg.timeout_s)
        content = resp.get("content", [])
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and "text" in first:
                return str(first["text"])
        # fallback
        return str(resp)

    raise ValueError(f"Unsupported chat provider: {cfg.provider}")


def embed_texts_ollama(cfg: EmbedConfig, texts: Sequence[str]) -> List[List[float]]:
    base = cfg.base_url.rstrip("/")
    out: List[List[float]] = []
    for text in texts:
        last_err: Optional[Exception] = None
        emb: Optional[List[float]] = None
        for path in ("/api/embeddings", "/api/embed"):
            try:
                payload = {"model": cfg.model, "prompt": str(text)}
                resp = post_json_with_retries(
                    url=base + path,
                    payload=payload,
                    headers={"Content-Type": "application/json"},
                    timeout_s=cfg.timeout_s,
                )
                raw = resp.get("embedding")
                if not isinstance(raw, list):
                    raw = resp.get("embeddings")
                    if isinstance(raw, list) and raw and isinstance(raw[0], list):
                        raw = raw[0]
                if isinstance(raw, list):
                    emb = [float(x) for x in raw]
                    break
            except Exception as e:  # noqa: BLE001
                last_err = e
        if emb is None:
            raise ValueError(f"Missing embedding vector from Ollama response: {last_err}")
        out.append(emb)
    return out


"""Disk-backed stand catalog cache."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .paths import profile_dir

CACHE_PATH = profile_dir() / "cache" / "stands.json"
TTL_SECONDS = 6 * 60 * 60


def _read() -> dict[str, Any] | None:
    if not CACHE_PATH.is_file():
        return None
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_fresh() -> list[dict[str, Any]] | None:
    payload = _read()
    if not payload:
        return None
    if time.time() - float(payload.get("saved_at") or 0) > TTL_SECONDS:
        return None
    stands = payload.get("stands")
    return stands if isinstance(stands, list) else None


def load_any() -> list[dict[str, Any]] | None:
    payload = _read()
    if not payload:
        return None
    stands = payload.get("stands")
    return stands if isinstance(stands, list) else None


def save(stands: list[dict[str, Any]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps({"saved_at": time.time(), "stands": stands}, ensure_ascii=False),
        encoding="utf-8",
    )

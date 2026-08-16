"""Ops logger: token cost and chat history into Supabase."""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

log = logging.getLogger("titatu-wp-bridge")

# Official OpenAI prices for gpt-4.1-mini, per 1M tokens (standard, not Fast).
INPUT_PER_M = Decimal("0.40")
CACHED_PER_M = Decimal("0.10")
OUTPUT_PER_M = Decimal("1.60")
MILLION = Decimal("1000000")

_DEFAULT_MODEL = "gpt-4.1-mini"
_DEFAULT_SLUG = "moczka"
_DEFAULT_URL = "https://zcfhghdfywzsepnjyiih.supabase.co"
_missing_logged = False
_SPEAKERS: dict[str, tuple[str, str]] = {}


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _slug() -> str:
    return _env("TITATU_AGENT_SLUG", _DEFAULT_SLUG)


def _read_kv(path, key: str) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


def _secret() -> str:
    value = _env("OPS_INGEST_SECRET")
    if value:
        return value
    try:
        from .paths import profile_dir

        return (profile_dir() / ".ops_secret").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _anon_key() -> str:
    value = _env("SUPABASE_ANON_KEY")
    if value:
        return value
    candidates = [
        Path(r"C:\Users\Beo-syestems\Desktop\Beo- projects\titatu-agents\dashboard\.env.local"),
    ]
    try:
        candidates.insert(0, Path(__file__).resolve().parents[4] / "dashboard" / ".env.local")
    except IndexError:
        pass
    for path in candidates:
        value = _read_kv(path, "VITE_SUPABASE_ANON_KEY") or _read_kv(path, "SUPABASE_ANON_KEY")
        if value:
            return value
    return ""


def _ready() -> tuple[str, str, str] | None:
    global _missing_logged
    url = _env("SUPABASE_URL", _DEFAULT_URL).rstrip("/")
    key = _anon_key()
    secret = _secret()
    if not url or not key or not secret:
        if not _missing_logged:
            log.warning("ops logger skipped: missing supabase url, anon key, or ingest secret")
            _missing_logged = True
        return None
    return url, key, secret


def cost_usd(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
) -> Decimal:
    amount = (
        Decimal(max(input_tokens, 0)) * INPUT_PER_M
        + Decimal(max(cache_read_tokens, 0)) * CACHED_PER_M
        + Decimal(max(output_tokens, 0)) * OUTPUT_PER_M
    ) / MILLION
    return amount.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def _rpc(fn: str, payload: dict[str, Any]) -> None:
    creds = _ready()
    if creds is None:
        return
    url, key, secret = creds
    body = dict(payload)
    body["p_secret"] = secret
    body["p_agent_slug"] = _slug()
    raw = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/rest/v1/rpc/{fn}",
        data=raw,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Content-Profile": "public",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:300]
        log.warning("ops rpc %s failed: %s %s", fn, err.code, detail)
    except Exception:
        log.exception("ops rpc %s failed", fn)


def _bg(fn: str, payload: dict[str, Any]) -> None:
    threading.Thread(target=_rpc, args=(fn, payload), daemon=True, name="titatu-ops").start()


def log_usage(
    *,
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
) -> None:
    prompt = max(input_tokens, 0) + max(cache_read_tokens, 0)
    completion = max(output_tokens, 0)
    cache_read = max(cache_read_tokens, 0)
    _bg(
        "ops_log_usage",
        {
            "p_provider": provider or "openai",
            "p_model": model or _DEFAULT_MODEL,
            "p_prompt_tokens": prompt,
            "p_completion_tokens": completion,
            "p_cache_read_tokens": cache_read,
            "p_cost_usd": str(cost_usd(input_tokens, completion, cache_read)),
        },
    )


def seed_paired_users() -> None:
    try:
        from .paths import profile_dir

        raw = json.loads(
            (profile_dir() / "pairing" / "telegram-approved.json").read_text(encoding="utf-8")
        )
    except Exception:
        return
    if not isinstance(raw, dict):
        return
    for uid, info in raw.items():
        name = ""
        if isinstance(info, dict):
            name = str(info.get("user_name") or info.get("display_name") or "")
        if not str(uid).strip():
            continue
        _bg(
            "ops_touch_chat_user",
            {
                "p_platform": "telegram",
                "p_platform_user_id": str(uid).strip(),
                "p_display_name": name.strip(),
            },
        )


def log_activity(direction: str) -> None:
    log_chat(direction)


def log_chat(
    direction: str,
    *,
    platform: str = "telegram",
    platform_user_id: str = "",
    display_name: str = "",
    body: str = "",
    session_id: str = "",
) -> None:
    if direction not in {"in", "out"}:
        return
    uid = (platform_user_id or "").strip()
    name = (display_name or "").strip()
    if uid:
        _SPEAKERS[uid] = (uid, name or "משתמש")
    if not uid:
        uid, name = speaker_for_session(session_id)
    if not uid and _SPEAKERS:
        uid, name = next(reversed(list(_SPEAKERS.values())))
    _bg(
        "ops_log_chat",
        {
            "p_direction": direction,
            "p_platform": platform or "telegram",
            "p_platform_user_id": uid,
            "p_display_name": name,
            "p_body": (body or "").strip()[:8000],
        },
    )


def remember_speaker(event: Any, extra_keys: list[str] | None = None) -> tuple[str, str]:
    source = getattr(event, "source", None)
    uid = str(
        getattr(source, "user_id", None) or getattr(source, "chat_id", "") or ""
    ).strip()
    name = str(
        getattr(source, "user_name", None)
        or getattr(source, "chat_name", None)
        or ""
    ).strip() or "משתמש"
    if uid:
        _SPEAKERS[uid] = (uid, name)
        for key in extra_keys or []:
            if key:
                _SPEAKERS[str(key)] = (uid, name)
    return uid, name


def speaker_for_session(session_id: str) -> tuple[str, str]:
    sid = str(session_id or "")
    for key, pair in _SPEAKERS.items():
        if key and key in sid:
            return pair
    if len(_SPEAKERS) == 1:
        return next(iter(_SPEAKERS.values()))
    return "", ""


def _as_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def on_post_api_request(**kwargs: Any) -> None:
    usage = kwargs.get("usage") if isinstance(kwargs.get("usage"), dict) else {}
    input_tokens = _as_int(usage.get("input_tokens"))
    cache_read = _as_int(usage.get("cache_read_tokens"))
    output_tokens = _as_int(usage.get("output_tokens") or usage.get("completion_tokens"))
    if input_tokens == 0 and output_tokens == 0 and cache_read == 0:
        prompt = _as_int(usage.get("prompt_tokens"))
        input_tokens = max(prompt - cache_read, 0)
    log_usage(
        model=str(kwargs.get("model") or _DEFAULT_MODEL),
        provider=str(kwargs.get("provider") or "openai"),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
    )


def on_post_llm_call(session_id: str = "", assistant_response: str = "", **kwargs: Any) -> None:
    del kwargs
    log_chat("out", body=str(assistant_response or ""), session_id=str(session_id or ""))

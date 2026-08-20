"""Run the quote questionnaire in the gateway, without the LLM."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import Any

from . import intake

log = logging.getLogger("titatu-wp-bridge")
_LOCK = threading.Lock()
_PENDING: dict[str, dict[str, str]] = {}
_RESTART = ("התחל מחדש", "התחילי מחדש")


def _sid(event) -> str:
    chat_id = str(getattr(getattr(event, "source", None), "chat_id", "") or "default")
    return f"tg-{chat_id}"


def _session_key(gateway, event) -> str:
    source = getattr(event, "source", None)
    fn = getattr(gateway, "_session_key_for_source", None)
    if callable(fn) and source is not None:
        try:
            key = fn(source)
            if key:
                return str(key)
        except Exception:
            pass
    return _sid(event)


def _authorized(gateway, event) -> bool:
    fn = getattr(gateway, "_is_user_authorized", None)
    source = getattr(event, "source", None)
    if not callable(fn) or source is None:
        return True
    try:
        return bool(fn(source))
    except Exception:
        return False


def _loop(gateway):
    return getattr(gateway, "_gateway_loop", None)


def _run_coro(gateway, coro) -> None:
    loop = _loop(gateway)
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        running.create_task(coro)
        return
    if loop is None:
        coro.close()
        return
    try:
        from agent.async_utils import safe_schedule_threadsafe
    except Exception:
        asyncio.run_coroutine_threadsafe(coro, loop)
        return
    safe_schedule_threadsafe(coro, loop, logger=log, log_message="intake send failed")


def _note(direction: str, event=None, text: str = "") -> None:
    try:
        from . import ops

        uid, name = "", ""
        if event is not None:
            extra = [_sid(event)]
            source = getattr(event, "source", None)
            chat_id = str(getattr(source, "chat_id", "") or "")
            if chat_id:
                extra.append(chat_id)
            uid, name = ops.remember_speaker(event, extra_keys=extra)
        ops.log_chat(direction, platform_user_id=uid, display_name=name, body=text)
    except Exception:
        log.exception("ops activity failed")


def _send_text(gateway, event, text: str) -> None:
    if not (text or "").strip():
        return
    adapter = gateway.adapters.get(event.source.platform)
    if adapter is None:
        return
    _run_coro(gateway, adapter.send(str(event.source.chat_id), text))


def _cancel_pending(sid: str, session_key: str) -> None:
    with _LOCK:
        pending = _PENDING.pop(sid, None)
    try:
        from tools import clarify_gateway
    except Exception:
        clarify_gateway = None
    if pending and clarify_gateway is not None:
        try:
            clarify_gateway.resolve_gateway_clarify(pending.get("clarify_id") or "", "")
        except Exception:
            pass
    if clarify_gateway is not None:
        try:
            clarify_gateway.clear_session(session_key)
        except Exception:
            pass


def _await_send(gateway, event, coro) -> bool:
    loop = _loop(gateway)
    try:
        from agent.async_utils import safe_schedule_threadsafe
    except Exception:
        safe_schedule_threadsafe = None
    if safe_schedule_threadsafe is not None:
        fut = safe_schedule_threadsafe(coro, loop, logger=log, log_message="intake send failed")
    elif loop is not None:
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
    else:
        coro.close()
        return False
    if fut is None:
        return False
    try:
        sent = fut.result(timeout=15)
        return bool(getattr(sent, "success", False)) or sent is None
    except Exception:
        log.exception("intake send failed")
        return False


def _choice_body(result: dict[str, Any]) -> str:
    parts = []
    preamble = str(result.get("preamble") or "").strip()
    say = str(result.get("say") or "").strip()
    if preamble:
        parts.append(preamble)
    if say:
        parts.append(say)
    choices = result.get("choices") or []
    if choices:
        parts.append("\n".join(f"• {item}" for item in choices))
    return "\n\n".join(parts)


def _deliver(gateway, event, sid: str, result: dict[str, Any]) -> None:
    _note("out", event, _choice_body(result) if result.get("use_clarify") else str(result.get("say") or ""))
    if result.get("use_clarify") and result.get("choices"):
        threading.Thread(
            target=_clarify_wait,
            args=(gateway, event, sid, result),
            daemon=True,
            name="titatu-intake-clarify",
        ).start()
        return
    _send_text(gateway, event, str(result.get("say") or ""))


def _clarify_wait(gateway, event, sid: str, result: dict[str, Any]) -> None:
    try:
        from tools import clarify_gateway
    except Exception:
        log.exception("clarify_gateway unavailable; sending text choices")
        _send_text(gateway, event, _choice_body(result))
        return

    adapter = gateway.adapters.get(event.source.platform)
    if adapter is None or not hasattr(adapter, "send_clarify"):
        _send_text(gateway, event, _choice_body(result))
        return

    preamble = str(result.get("preamble") or "").strip()
    if preamble:
        _await_send(gateway, event, adapter.send(str(event.source.chat_id), preamble))

    clarify_id = uuid.uuid4().hex[:10]
    session_key = _session_key(gateway, event)
    choices = list(result.get("choices") or [])
    question = str(result.get("say") or "")
    clarify_gateway.register(
        clarify_id=clarify_id,
        session_key=session_key,
        question=question,
        choices=choices,
    )
    with _LOCK:
        _PENDING[sid] = {"clarify_id": clarify_id, "session_key": session_key}

    loop = _loop(gateway)
    try:
        from agent.async_utils import safe_schedule_threadsafe
    except Exception:
        safe_schedule_threadsafe = None
    send_ok = False
    coro = adapter.send_clarify(
        chat_id=str(event.source.chat_id),
        question=question,
        choices=choices,
        clarify_id=clarify_id,
        session_key=session_key,
    )
    if safe_schedule_threadsafe is not None:
        fut = safe_schedule_threadsafe(coro, loop, logger=log, log_message="clarify send failed")
    elif loop is not None:
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
    else:
        fut = None
        coro.close()
    if fut is not None:
        try:
            sent = fut.result(timeout=15)
            send_ok = bool(getattr(sent, "success", False))
        except Exception:
            log.exception("send_clarify failed")
    if not send_ok:
        with _LOCK:
            _PENDING.pop(sid, None)
        try:
            clarify_gateway.clear_session(session_key)
        except Exception:
            pass
        _send_text(gateway, event, _choice_body(result))
        return

    timeout = float(clarify_gateway.get_clarify_timeout())
    answer = clarify_gateway.wait_for_response(clarify_id, timeout=timeout)
    with _LOCK:
        current = _PENDING.get(sid) or {}
        if current.get("clarify_id") == clarify_id:
            _PENDING.pop(sid, None)
    if not answer:
        return
    state = intake.load_state(sid)
    if not state or not intake.is_active(state):
        return
    nxt = intake.submit_intake(sid, answer)
    _deliver(gateway, event, sid, nxt)


def on_pre_gateway_dispatch(event, gateway, **kwargs):
    del kwargs
    if event is None or gateway is None:
        return None
    if not _authorized(gateway, event):
        return None
    text = str(getattr(event, "text", "") or "").strip()
    if not text or intake.looks_like_memory_nudge(text):
        return None
    _note("in", event, text)
    if text.startswith("/"):
        cmd = text.split()[0].split("@")[0]
        if cmd in {"/new", "/reset"}:
            sid = _sid(event)
            _cancel_pending(sid, _session_key(gateway, event))
            intake.clear_state(sid)
        return None

    sid = _sid(event)
    session_key = _session_key(gateway, event)

    if intake.looks_like_cancel(text) or intake.looks_like_delete(text):
        _cancel_pending(sid, session_key)
        result = intake.handle_ops_message(sid, text) or intake.cancel_intake(sid)
        if result.get("use_clarify") and result.get("choices"):
            _deliver(gateway, event, sid, result)
        else:
            _note("out", event, str(result.get("say") or ""))
            _send_text(gateway, event, str(result.get("say") or ""))
        return {"action": "skip", "reason": "intake-ops"}

    if text in _RESTART or intake.looks_like_new_quote(text):
        _cancel_pending(sid, session_key)
        intake.clear_state(sid)
        result = intake.start_intake(sid, force=True)
        _deliver(gateway, event, sid, result)
        return {"action": "skip", "reason": "intake-restart"}

    state = intake.load_state(sid)
    in_progress = intake.is_active(state)

    if in_progress and intake.looks_like_quote_intent(text):
        result = intake.start_intake(sid)
        _deliver(gateway, event, sid, result)
        return {"action": "skip", "reason": "intake-resume"}

    if in_progress:
        with _LOCK:
            pending = _PENDING.get(sid)
        state = state or intake.load_state(sid)
        if pending:
            if intake.is_structured_reply(state, text):
                try:
                    from tools import clarify_gateway

                    clarify_gateway.resolve_gateway_clarify(pending.get("clarify_id") or "", text)
                except Exception:
                    log.exception("failed to resolve pending clarify")
                return {"action": "skip", "reason": "intake-clarify-text"}
            _cancel_pending(sid, session_key)
        if intake.is_form_step(state) or intake.is_structured_reply(state, text):
            result = intake.submit_intake(sid, text)
            _deliver(gateway, event, sid, result)
            return {"action": "skip", "reason": "intake-submit"}
        return None

    if intake.looks_like_resume_last(text) and (
        intake.load_last_bid() or ((state or {}).get("wp_id") if state else None)
    ):
        result = intake.resume_working(sid)
        _deliver(gateway, event, sid, result)
        return {"action": "skip", "reason": "intake-resume-last"}

    if intake.looks_like_quote_intent(text) or intake.looks_like_intake_block(text):
        if intake.looks_like_intake_block(text):
            intake.start_intake(sid, force=True)
            result = intake.submit_intake(sid, text)
        else:
            result = intake.start_intake(sid, force=True)
        _deliver(gateway, event, sid, result)
        return {"action": "skip", "reason": "intake-start"}

    if (intake.looks_like_add_stands(text) or intake.looks_like_patch(text)) and (
        intake.load_last_bid() or ((state or {}).get("wp_id") if state else None)
    ):
        result = intake.apply_free_update(sid, text)
        _deliver(gateway, event, sid, result)
        return {"action": "skip", "reason": "free-update"}

    return None

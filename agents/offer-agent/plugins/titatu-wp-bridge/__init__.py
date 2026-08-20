"""Titatu WordPress + fixed quote intake tools for Hermes."""

from . import gateway_intake, intake, schemas, tools


def _inject(result: dict):
    say = str(result.get("say") or "").strip()
    if result.get("use_clarify") and result.get("choices"):
        choices = result.get("choices")
        preamble = str(result.get("preamble") or "").strip()
        extra = f"קודם השב את הסיכום הבא כלשונו:\n{preamble}\n" if preamble else ""
        return {
            "context": (
                "השאלון כבר עודכן אוטומטית. אל תקרא start_quote_intake ואל תקרא submit_intake_message. "
                f"{extra}"
                "חובה לקרוא עכשיו clarify עם השאלה והכפתורים הבאים בלבד, בלי טקסט נוסף.\n"
                f"question: {say}\n"
                f"choices: {choices}"
            )
        }
    if not say:
        return None
    return {
        "context": (
            "השאלון כבר עודכן אוטומטית. אל תקרא כלים. "
            "השב בדיוק את הטקסט הבא בלבד, בלי ציטוט של המשתמש, בלי הקדמה, בלי שינוי:\n"
            "<<<\n"
            f"{say}\n"
            ">>>"
        )
    }


def _brain_context(state: dict, text: str) -> dict:
    last = state.get("last_result") if isinstance(state.get("last_result"), dict) else {}
    last_say = str(last.get("say") or "").strip()
    awaiting = state.get("awaiting_field") or "אין"
    return {
        "context": (
            "אתה מוצ'קה — עוזר בינה מלאכותית להצעות מחיר, לא בוט אוטומציה. "
            "השאלון פתוח. אסור לקרוא start_quote_intake ואסור לאפס אותו.\n"
            f"שלב נוכחי: {state.get('step')}\n"
            f"שדה ממתין: {awaiting}\n"
            f"השאלה האחרונה שלך: {last_say or 'אין'}\n"
            "הבן כוונה ושגיאות כתיב כמו ChatGPT. אל תוסיף שגיאות לקוד — תנרמל בעברית בראש.\n"
            "אם זו תשובה לשאלון — קרא submit_intake_message עם ניסוח ברור (לא חיפוש קטלוג על משפט שיחה).\n"
            "אם זו שיחה/שאלה — ענה בעברית מעוצבת: כותרת מודגשת, נקודות, משפטים קצרים. "
            "טלגרם מציג עברית מימין לשמאל לבד.\n"
            "שאלות כן/לא בשאלון: כפתורים מאושר / לא מאושר בלבד דרך clarify.\n"
            "מחיקה: אל תקרא trash_bid. אם מבקשים למחוק — submit_intake_message עם המילה מחק, "
            "ואז לחכות לאישור מאושר/לא מאושר.\n"
            f"הודעת המשתמש: {text}"
        )
    }


def _on_pre_llm_call(session_id: str, user_message: str, **kwargs):
    del kwargs
    sid = str(session_id or "telegram-default")
    text = (user_message or "").strip()
    if intake.looks_like_memory_nudge(text):
        return None
    if not text or text.startswith("/"):
        if text.split()[0].split("@")[0] in {"/new", "/reset"}:
            intake.clear_state(sid)
        return None
    if intake.looks_like_cancel(text) or intake.looks_like_delete(text):
        return _inject(intake.handle_ops_message(sid, text) or intake.cancel_intake(sid))
    if intake.looks_like_new_quote(text):
        intake.clear_state(sid)
        return _inject(intake.start_intake(sid, force=True))
    if intake.looks_like_add_stands(text) or intake.looks_like_patch(text):
        last = intake.load_last_bid()
        state = intake.load_state(sid)
        if last or (state or {}).get("wp_id"):
            if intake.is_active(state) and (state or {}).get("step") not in {
                "working",
                "approved",
                "published",
                "corrections",
                "confirm",
                "ready",
            }:
                pass
            else:
                return _inject(intake.apply_free_update(sid, text))
    state = intake.load_state(sid)
    if intake.is_active(state):
        if intake.is_form_step(state) or intake.is_structured_reply(state, text):
            return _inject(intake.submit_intake(sid, text))
        return _brain_context(state, text)
    if intake.looks_like_intake_block(text):
        intake.start_intake(sid, force=True)
        return _inject(intake.submit_intake(sid, text))
    if intake.looks_like_resume_last(text):
        last = intake.load_last_bid()
        if last or (state or {}).get("wp_id"):
            return _inject(intake.resume_working(sid))
    if intake.looks_like_quote_intent(text):
        return _inject(intake.start_intake(sid, force=True))
    return None


def _on_session_reset(session_id: str, **kwargs):
    del kwargs
    intake.clear_state(str(session_id or "telegram-default"))


def register(ctx):
    pairs = [
        ("wp_bridge_health", schemas.WP_BRIDGE_HEALTH, tools.wp_bridge_health),
        ("get_bid", schemas.GET_BID, tools.get_bid),
        ("search_bids", schemas.SEARCH_BIDS, tools.search_bids),
        ("find_bids", schemas.FIND_BIDS, tools.find_bids),
        ("list_bids_by_quote_status", schemas.LIST_BIDS_BY_QUOTE_STATUS, tools.list_bids_by_quote_status),
        ("list_approved_today", schemas.LIST_APPROVED_TODAY, tools.list_approved_today),
        ("list_stands", schemas.LIST_STANDS, tools.list_stands),
        ("get_stand", schemas.GET_STAND, tools.get_stand),
        ("search_stands", schemas.SEARCH_STANDS, tools.search_stands),
        ("resolve_stands", schemas.RESOLVE_STANDS, tools.resolve_stands),
        ("start_quote_intake", schemas.START_QUOTE_INTAKE, tools.start_quote_intake),
        ("submit_intake_message", schemas.SUBMIT_INTAKE_MESSAGE, tools.submit_intake_message),
        ("get_last_bid", schemas.GET_LAST_BID, tools.get_last_bid),
        ("trash_bid", schemas.TRASH_BID, tools.trash_bid),
        ("update_quote", schemas.UPDATE_QUOTE, tools.update_quote),
    ]
    for name, schema, handler in pairs:
        ctx.register_tool(
            name=name,
            toolset=schemas.TOOLSET,
            schema=schema,
            handler=handler,
            description=schema["description"],
        )
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("on_session_reset", _on_session_reset)
    ctx.register_hook("pre_gateway_dispatch", gateway_intake.on_pre_gateway_dispatch)
    from . import ops

    ctx.register_hook("post_api_request", ops.on_post_api_request)
    ctx.register_hook("post_llm_call", ops.on_post_llm_call)
    ops.seed_paired_users()

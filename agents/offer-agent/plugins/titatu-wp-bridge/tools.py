"""Read-only WordPress handlers. Never write to WordPress from these tools."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from . import bid_write, fuzzy, intake, stands
from .wp_client import WpClient, WpError

ISRAEL = timezone(timedelta(hours=3))
SITE = "https://titatu.co.il"


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _err(message: str, **extra: Any) -> str:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _client() -> WpClient:
    return WpClient()


def _title(item: dict[str, Any]) -> str:
    title = item.get("title")
    if isinstance(title, dict):
        return str(title.get("raw") or title.get("rendered") or "")
    return str(title or "")


def _meta(item: dict[str, Any]) -> dict[str, Any]:
    meta = item.get("meta")
    return meta if isinstance(meta, dict) else {}


def _canonical(bid_id: int) -> str:
    return f"{SITE}/?p={int(bid_id)}"


def _admin_edit(bid_id: int) -> str:
    return f"{SITE}/wp-admin/post.php?post={int(bid_id)}&action=edit"


def _doc_kind(item: dict[str, Any]) -> str:
    status = str(item.get("status") or "")
    bid_status = str(_meta(item).get("bid_status") or "")
    if "אושר" in bid_status:
        return "approved"
    if status == "draft":
        return "draft"
    if "ממתין" in bid_status or status in ("publish", "pending", "private"):
        return "open_waiting"
    return status or "unknown"


def _summarize_bid(item: dict[str, Any]) -> dict[str, Any]:
    meta = _meta(item)
    bid_id = int(item.get("id") or 0)
    return {
        "id": bid_id,
        "wp_status": item.get("status"),
        "doc_kind": _doc_kind(item),
        "title": _title(item),
        "link": _canonical(bid_id),
        "edit_link": _admin_edit(bid_id),
        "modified": item.get("modified"),
        "date": item.get("date"),
        "bid_status": meta.get("bid_status") or "",
        "customer_name": meta.get("customer_name") or meta.get("for") or "",
        "phone": meta.get("customer_phone") or meta.get("phone") or "",
        "email": meta.get("email") or "",
        "event_date": meta.get("customer_date") or "",
        "guests": meta.get("customer_guests") or meta.get("participants") or "",
        "has_signature": bool(meta.get("e-signature")),
    }


def _summarize_stand(item: dict[str, Any]) -> dict[str, Any]:
    return stands.summarize(item)


def _iter_bids(client: WpClient, *, per_page: int = 50, max_pages: int = 6) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        try:
            batch = client.request(
                "GET",
                "/wp-json/wp/v2/bid",
                params={
                    "per_page": per_page,
                    "page": page,
                    "context": "edit",
                    "status": "publish,draft,private,pending",
                    "orderby": "modified",
                    "order": "desc",
                },
            )
        except WpError as exc:
            if exc.status in (400, 404):
                break
            raise
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < per_page:
            break
    return rows


def _load_stands(client: WpClient) -> tuple[list[dict[str, Any]], str]:
    return stands.load_catalog(client)


def wp_bridge_health(args: dict, **kwargs) -> str:
    del args, kwargs
    try:
        data = _client().health()
        return _ok(
            {
                "ok": True,
                "bridge": data.get("bridge"),
                "version": data.get("version"),
                "can_edit": data.get("can_edit"),
                "can_publish": data.get("can_publish"),
                "types": data.get("types"),
                "read_via": "wp/v2 (bridge v2 has health only)",
            }
        )
    except WpError as exc:
        return _err(str(exc), status=exc.status)


def get_bid(args: dict, **kwargs) -> str:
    del kwargs
    try:
        item = _client().get_bid(int(args.get("id") or 0))
        if not isinstance(item, dict):
            return _err("תשובה לא תקינה מ-WordPress")
        summary = _summarize_bid(item)
        meta = dict(_meta(item))
        meta.pop("e-signature", None)
        summary["meta"] = meta
        return _ok({"ok": True, "bid": summary})
    except WpError as exc:
        return _err(str(exc), status=exc.status)


def search_bids(args: dict, **kwargs) -> str:
    del kwargs
    query = str(args.get("query") or "").strip()
    if not query:
        return _err("חסר טקסט לחיפוש")
    try:
        rows = _client().search_bids(query, per_page=int(args.get("per_page") or 20))
        if not isinstance(rows, list):
            return _err("תשובה לא תקינה מ-WordPress")
        return _ok({"ok": True, "count": len(rows), "bids": [_summarize_bid(item) for item in rows if isinstance(item, dict)]})
    except WpError as exc:
        return _err(str(exc), status=exc.status)


def find_bids(args: dict, **kwargs) -> str:
    del kwargs
    name = str(args.get("name") or "").strip()
    phone = str(args.get("phone") or "").strip()
    email = str(args.get("email") or "").strip()
    if not (name or phone or email):
        return _err("צריך שם, טלפון או מייל")
    try:
        rows = _iter_bids(_client())
    except WpError as exc:
        return _err(str(exc), status=exc.status)

    scored: list[dict[str, Any]] = []
    for item in rows:
        meta = _meta(item)
        scores = []
        if name:
            scores.append(
                max(
                    fuzzy.score_text(name, _title(item)),
                    fuzzy.score_text(name, str(meta.get("customer_name") or "")),
                    fuzzy.score_text(name, str(meta.get("for") or "")),
                )
            )
        if phone:
            scores.append(
                max(
                    fuzzy.score_phone(phone, str(meta.get("customer_phone") or "")),
                    fuzzy.score_phone(phone, str(meta.get("phone") or "")),
                )
            )
        if email:
            scores.append(fuzzy.score_email(email, str(meta.get("email") or "")))
        score = min(scores) if scores else 0.0
        if score >= 0.72:
            summary = _summarize_bid(item)
            summary["match_score"] = round(score, 3)
            scored.append(summary)
    scored.sort(key=lambda row: row.get("match_score") or 0, reverse=True)
    top = scored[:8]
    needs_confirm = len([row for row in top if (row.get("match_score") or 0) >= 0.72]) > 1
    return _ok(
        {
            "ok": True,
            "count": len(top),
            "needs_confirmation": needs_confirm,
            "bids": top,
        }
    )


def _filter_quote_status(rows: list[dict[str, Any]], quote_status: str) -> list[dict[str, Any]]:
    out = []
    for item in rows:
        status = str(_meta(item).get("bid_status") or "")
        if quote_status == "approved" and "אושר" in status:
            out.append(item)
        elif quote_status == "waiting" and "ממתין" in status:
            out.append(item)
        elif quote_status == "not_approved" and "אושר" not in status:
            out.append(item)
    return out


def list_bids_by_quote_status(args: dict, **kwargs) -> str:
    del kwargs
    quote_status = str(args.get("quote_status") or "")
    if quote_status not in ("approved", "waiting", "not_approved"):
        return _err("quote_status חייב להיות approved / waiting / not_approved")
    days = int(args.get("days") or 31)
    cutoff = datetime.now(tz=ISRAEL) - timedelta(days=days)
    try:
        rows = _iter_bids(_client())
    except WpError as exc:
        return _err(str(exc), status=exc.status)
    filtered = []
    for item in _filter_quote_status(rows, quote_status):
        modified = str(item.get("modified") or "")
        try:
            when = datetime.fromisoformat(modified.replace("Z", "+00:00")).astimezone(ISRAEL)
        except ValueError:
            when = None
        if when is None or when >= cutoff:
            filtered.append(item)
    return _ok(
        {
            "ok": True,
            "quote_status": quote_status,
            "count": len(filtered),
            "bids": [_summarize_bid(item) for item in filtered[:40]],
        }
    )


def list_approved_today(args: dict, **kwargs) -> str:
    del args, kwargs
    today = datetime.now(tz=ISRAEL).date().isoformat()
    try:
        rows = _filter_quote_status(_iter_bids(_client()), "approved")
    except WpError as exc:
        return _err(str(exc), status=exc.status)
    matched = []
    for item in rows:
        modified = str(item.get("modified") or "")
        try:
            when = datetime.fromisoformat(modified.replace("Z", "+00:00")).astimezone(ISRAEL)
        except ValueError:
            continue
        if when.date().isoformat() == today:
            matched.append(item)
    return _ok({"ok": True, "date": today, "count": len(matched), "bids": [_summarize_bid(item) for item in matched]})


def list_stands(args: dict, **kwargs) -> str:
    del args, kwargs
    try:
        stands, source = _load_stands(_client())
        return _ok({"ok": True, "source": source, "count": len(stands), "stands": stands})
    except WpError as exc:
        return _err(str(exc), status=exc.status)


def get_stand(args: dict, **kwargs) -> str:
    del kwargs
    try:
        item = _client().get_stand(int(args.get("id") or 0))
        if not isinstance(item, dict):
            return _err("תשובה לא תקינה מ-WordPress")
        return _ok({"ok": True, "stand": _summarize_stand(item)})
    except WpError as exc:
        return _err(str(exc), status=exc.status)


def search_stands(args: dict, **kwargs) -> str:
    del kwargs
    query = str(args.get("query") or "").strip()
    if not query:
        return _err("חסר טקסט לחיפוש דוכן")
    try:
        stands, source = _load_stands(_client())
    except WpError as exc:
        return _err(str(exc), status=exc.status)
    hits = []
    for stand in stands:
        score = max(
            fuzzy.score_text(query, str(stand.get("title") or "")),
            fuzzy.score_text(query, str(stand.get("product_title") or "")),
        )
        if score >= 0.6:
            row = dict(stand)
            row["match_score"] = round(score, 3)
            hits.append(row)
    hits.sort(key=lambda row: row.get("match_score") or 0, reverse=True)
    return _ok({"ok": True, "source": source, "count": len(hits), "stands": hits[:20]})


def resolve_stands(args: dict, **kwargs) -> str:
    del kwargs
    names = args.get("names") or []
    if isinstance(names, str):
        names = [names]
    names = [str(name).strip() for name in names if str(name).strip()]
    if not names:
        return _err("חסרות שמות דוכנים")
    try:
        catalog, source = _load_stands(_client())
    except WpError as exc:
        return _err(str(exc), status=exc.status)

    resolved = stands.resolve_names(names, catalog)
    return _ok({"ok": True, "source": source, "results": resolved})


def _session_id(kwargs: dict) -> str:
    return str(kwargs.get("session_id") or kwargs.get("task_id") or "telegram-default")


def start_quote_intake(args: dict, **kwargs) -> str:
    del args
    return _ok(intake.start_intake(_session_id(kwargs)))


def submit_intake_message(args: dict, **kwargs) -> str:
    text = str(args.get("text") or "")
    return _ok(intake.submit_intake(_session_id(kwargs), text))


def get_last_bid(args: dict, **kwargs) -> str:
    del args, kwargs
    last = intake.load_last_bid()
    if not last:
        return _err("אין הצעה אחרונה בשיחה הזו")
    return _ok({"ok": True, "bid": last})


def trash_bid(args: dict, **kwargs) -> str:
    del kwargs
    bid_id = args.get("id")
    if bid_id:
        try:
            _client().trash_bid(int(bid_id))
        except WpError as exc:
            return _err(str(exc), status=exc.status)
        last = intake.load_last_bid()
        if last and int(last.get("id") or 0) == int(bid_id):
            intake.forget_last_bid()
        return _ok({"ok": True, "deleted_id": int(bid_id), "say": f"מחקתי את הצעה #{int(bid_id)}. היא בפח בוורדפרס."})
    result = intake.delete_last_quote()
    if not result.get("ok"):
        return _err(str(result.get("say") or "לא הצלחתי למחוק"))
    return _ok(result)


def update_quote(args: dict, **kwargs) -> str:
    del kwargs
    bid_id = args.get("id")
    if not bid_id:
        last = intake.load_last_bid()
        if not last:
            return _err("אין הצעה אחרונה. תגיד מזהה (#) או צור הצעה קודם.")
        bid_id = last["id"]
    add_stands = args.get("add_stands") or []
    if isinstance(add_stands, str):
        add_stands = [add_stands]
    try:
        updated = bid_write.update_live_quote(
            int(bid_id),
            title=str(args["title"]).strip() if args.get("title") else None,
            guests=args.get("guests"),
            show_price_per_participants=args.get("show_price_per_participants"),
            decorated_stands=args.get("decorated_stands"),
            add_stand_names=[str(name).strip() for name in add_stands if str(name).strip()] or None,
            phone=str(args["phone"]).strip() if args.get("phone") else None,
            event_date=str(args["event_date"]).strip() if args.get("event_date") else None,
            address=str(args["address"]).strip() if args.get("address") else None,
            serve_time=str(args["serve_time"]).strip() if args.get("serve_time") else None,
        )
    except WpError as exc:
        return _err(str(exc), status=exc.status)
    say = f"עדכנתי את הצעה #{updated['id']}.\n{updated['link']}"
    unmatched = updated.get("unmatched_stands") or []
    if unmatched:
        say += "\nלא מצאתי: " + ", ".join(unmatched)
    updated["say"] = say
    return _ok({"ok": True, **updated})

"""Map an approved intake draft to a WordPress bid POST. Field names from live JetEngine."""

from __future__ import annotations

import re
from typing import Any

from .wp_client import WpClient, WpError

SITE = "https://titatu.co.il"


def canonical(bid_id: int) -> str:
    return f"{SITE}/?p={int(bid_id)}"


def admin_edit(bid_id: int) -> str:
    return f"{SITE}/wp-admin/post.php?post={int(bid_id)}&action=edit"


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _guests(raw: Any) -> int | str:
    text = str(raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if digits:
        try:
            return int(digits)
        except ValueError:
            return text
    return text


def plain_notes(raw: str) -> str:
    """Strip HTML / bullets so notes stay one clean line per request."""
    text = (raw or "").replace("\r\n", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(?:li|p|div|h[1-6])>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    lines: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        item = re.sub(r"^[-•*]+\s*", "", line).strip()
        item = re.sub(r"^(?:הערות(?:\s*כלליות)?|הערה)\s*[:\-–]\s*", "", item).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        lines.append(item)
    return "\n".join(lines)


def format_notes(raw: str, fmt: str | None) -> str:
    items = [line for line in plain_notes(raw).splitlines() if line.strip()]
    if not items:
        return ""
    if fmt == "continuous" or len(items) == 1:
        return " · ".join(items) if fmt == "continuous" else items[0]
    return "<ul>\n" + "\n".join(f"<li>{item}</li>" for item in items) + "\n</ul>"


def _price100(stand: dict[str, Any]) -> float | None:
    raw = stand.get("price_per_hundred")
    try:
        value = float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _nis(value: float) -> int:
    return int(value + 0.5)


def _guest_n(guests: int | str) -> int:
    if isinstance(guests, int):
        return guests
    return int(re.sub(r"\D", "", str(guests) or "0") or 0)


def _stand_title(stand: dict[str, Any]) -> str:
    return str(stand.get("product_title") or stand.get("title") or "דוכן").strip() or "דוכן"


def food_stands(stands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Food catalog stands only. Decorated/custom (estimate_stand) are not part of 3+1."""
    return [stand for stand in stands if str(stand.get("type") or "") != "estimate_stand"]


def stand_price_for_guests(price100: float, guests: int) -> int:
    if guests > 0:
        return _nis(price100 * guests / 100.0)
    return _nis(price100)


def three_plus_one(stands: list[dict[str, Any]], guests: int | str) -> tuple[int, str]:
    """WordPress 3+1: 4+ food stands → cheapest stand is free. discount = that stand's price."""
    food = food_stands(stands)
    if len(food) < 4:
        return 0, ""
    guest_n = _guest_n(guests)
    priced: list[tuple[dict[str, Any], int]] = []
    for stand in food:
        unit = _price100(stand)
        if unit is None:
            continue
        priced.append((stand, stand_price_for_guests(unit, guest_n)))
    if not priced:
        return 0, ""
    cheapest, amount = min(priced, key=lambda pair: pair[1])
    title = _stand_title(cheapest)
    reason = f"3+1 — דוכן ללא עלות: {title} (הזול מבין {len(food)} הדוכנים)"
    return amount, reason


def quote_discount(draft: dict[str, Any]) -> tuple[int | float, str]:
    """3+1 plus any extra flat discount. Extra never replaces the house deal."""
    guests = _guests(draft.get("guests"))
    deal, reason = three_plus_one(list(draft.get("stands") or []), guests)
    manual = draft.get("extra_discount")
    try:
        extra = float(str(manual).replace(",", "").strip()) if manual not in (None, "") else 0.0
    except (TypeError, ValueError):
        extra = 0.0
    extra_reason = str(draft.get("extra_discount_reason") or "").strip()
    if extra > 0 and "3+1" in extra_reason:
        extra_reason = ""
    extra_n = int(extra) if extra == int(extra) else extra
    if deal and extra > 0:
        return deal + extra_n, f"{reason} + הנחה נוספת {extra_n:g} ש״ח"
    if deal:
        return deal, reason
    if extra > 0:
        return extra_n, extra_reason or f"הנחה — {extra_n:g} ₪ לפני מע״מ"
    return 0, ""


def bucket_stand_ids(stands: list[dict[str, Any]]) -> dict[str, list[int]]:
    food: list[int] = []
    custom: list[int] = []
    for stand in stands:
        stand_id = int(stand.get("id") or 0)
        if not stand_id:
            continue
        kind = str(stand.get("type") or "")
        if kind == "estimate_stand":
            custom.append(stand_id)
        else:
            food.append(stand_id)
    return {"food": food, "custom": custom}


def draft_to_meta(draft: dict[str, Any]) -> dict[str, Any]:
    guests = _guests(draft.get("guests"))
    stands = list(draft.get("stands") or [])
    discount, reason = quote_discount(draft)
    buckets = bucket_stand_ids(stands)
    customer_for = str(draft.get("customer_for") or "").strip()
    phone = str(draft.get("phone") or "").strip()
    notes = format_notes(str(draft.get("notes") or ""), draft.get("notes_format"))
    meta: dict[str, Any] = {
        "for": customer_for,
        "customer_for": customer_for,
        "customer_name": str(draft.get("customer_name") or "").strip(),
        "customer_phone": phone,
        "phone": phone,
        "email": str(draft.get("email") or "").strip(),
        "customer_date": str(draft.get("event_date") or "").strip(),
        "customer_address": str(draft.get("address") or "").strip(),
        "customer_serve_time": str(draft.get("serve_time") or "").strip(),
        "customer_guests": guests,
        "participants": guests,
        "no_packages": "true",
        "no_stands": _flag(bool(draft.get("no_stands"))),
        "show_price_per_participants": _flag(bool(draft.get("show_price_per_participants"))),
        "additional_notes": notes,
        "chosen_food_services": buckets["food"],
        "chosen_custom_services": buckets["custom"],
        "chosen_drink_services": [],
        "chosen_dessert_services": [],
        "discount": discount or 0,
        "discount_reason": reason or "",
    }
    return {
        key: value
        for key, value in meta.items()
        if value not in ("", None, []) or key in {"discount", "discount_reason"}
    }


def create_draft(draft: dict[str, Any]) -> dict[str, Any]:
    title = str(draft.get("title") or "").strip() or "הצעת מחיר"
    type_id = draft.get("bid_type_id")
    type_ids = [int(type_id)] if type_id else []
    meta = draft_to_meta(draft)
    client = WpClient()
    created = client.create_bid(title=title, meta=meta, bid_type_ids=type_ids)
    if not isinstance(created, dict) or not created.get("id"):
        raise WpError("WordPress החזיר תשובה בלי מזהה הצעה")
    bid_id = int(created["id"])
    status = str(created.get("status") or "draft")
    live = False
    try:
        published = client.publish_for_view(bid_id)
        if isinstance(published, dict):
            status = str(published.get("status") or status)
            live = status == "publish"
    except WpError as exc:
        raise WpError(
            f"ההצעה נוצרה (#{bid_id}) אבל הקישור החי לא נפתח: {exc}"
        ) from exc
    return {
        "id": bid_id,
        "title": title,
        "status": status,
        "live": live,
        "link": canonical(bid_id),
        "edit_link": admin_edit(bid_id),
        "discount": meta.get("discount") or 0,
        "discount_reason": meta.get("discount_reason") or "",
    }


def _meta_ids(value: Any) -> list[int]:
    if isinstance(value, list):
        out = []
        for item in value:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out
    if isinstance(value, str) and value.strip().isdigit():
        return [int(value.strip())]
    return []


def update_live_quote(
    bid_id: int,
    *,
    title: str | None = None,
    guests: Any = None,
    show_price_per_participants: bool | None = None,
    decorated_stands: bool | None = None,
    add_stand_names: list[str] | None = None,
    phone: str | None = None,
    event_date: str | None = None,
    address: str | None = None,
    serve_time: str | None = None,
) -> dict[str, Any]:
    from . import stands as stands_mod

    client = WpClient()
    current = client.get_bid(bid_id)
    if not isinstance(current, dict):
        raise WpError("לא מצאתי את ההצעה")
    meta = dict(current.get("meta") or {})
    body: dict[str, Any] = {}
    if title:
        body["title"] = title
    if guests is not None and str(guests).strip() != "":
        value = _guests(guests)
        meta["customer_guests"] = value
        meta["participants"] = value
    if show_price_per_participants is not None:
        meta["show_price_per_participants"] = _flag(show_price_per_participants)
    if decorated_stands is not None:
        meta["no_stands"] = _flag(not decorated_stands)
    if phone:
        meta["customer_phone"] = phone
        meta["phone"] = phone
    if event_date:
        meta["customer_date"] = event_date
    if address:
        meta["customer_address"] = address
    if serve_time:
        meta["customer_serve_time"] = serve_time
    if add_stand_names:
        resolved = stands_mod.resolve_names(add_stand_names)
        added: list[dict[str, Any]] = []
        unmatched: list[str] = []
        for row in resolved:
            if row.get("status") == "matched" and row.get("stand"):
                added.append(row["stand"])
            else:
                unmatched.append(str(row.get("query") or ""))
        if unmatched and not added:
            raise WpError("לא מצאתי דוכנים: " + ", ".join(unmatched))
        food = _meta_ids(meta.get("chosen_food_services"))
        custom = _meta_ids(meta.get("chosen_custom_services"))
        buckets = bucket_stand_ids(added)
        food.extend(buckets["food"])
        custom.extend(buckets["custom"])
        meta["chosen_food_services"] = list(dict.fromkeys(food))
        meta["chosen_custom_services"] = list(dict.fromkeys(custom))
        guest_n = meta.get("customer_guests") or meta.get("participants") or 0
        all_ids = list(dict.fromkeys(food + custom))
        catalog_stands = stands_mod.by_ids(all_ids) or added
        discount, reason = three_plus_one(catalog_stands, guest_n)
        extra = 0.0
        prev_reason = str(meta.get("discount_reason") or "")
        if "הנחה נוספת" in prev_reason or "ידנית" in prev_reason:
            try:
                extra = float(str(meta.get("discount") or 0))
                if discount:
                    extra = max(0.0, extra - float(discount))
            except (TypeError, ValueError):
                extra = 0.0
        if extra > 0:
            extra_n = int(extra) if extra == int(extra) else extra
            discount = (discount or 0) + extra_n
            reason = f"{reason} + הנחה נוספת {extra_n:g} ש״ח" if reason else f"הנחה — {extra_n:g} ₪ לפני מע״מ"
        meta["discount"] = discount or 0
        meta["discount_reason"] = reason or ""
        if unmatched:
            meta["_unmatched_stands"] = unmatched
    body["meta"] = meta
    updated = client.update_bid(bid_id, body)
    if not isinstance(updated, dict):
        raise WpError("עדכון וורדפרס נכשל")
    return {
        "id": bid_id,
        "title": title or (updated.get("title") or {}).get("rendered") or "",
        "status": updated.get("status"),
        "link": canonical(bid_id),
        "unmatched_stands": meta.get("_unmatched_stands") or [],
    }


def sync_quote(bid_id: int, draft: dict[str, Any]) -> dict[str, Any]:
    """Rewrite an existing quote from the current intake draft. Same ID, same link."""
    client = WpClient()
    meta = draft_to_meta(draft)
    body: dict[str, Any] = {"meta": meta}
    title = str(draft.get("title") or "").strip()
    if title:
        body["title"] = title
    type_id = draft.get("bid_type_id")
    if type_id:
        body["bid_type"] = [int(type_id)]
    updated = client.update_bid(int(bid_id), body)
    if not isinstance(updated, dict):
        raise WpError("עדכון וורדפרס נכשל")
    return {
        "id": int(bid_id),
        "title": title or str((updated.get("title") or {}).get("rendered") or ""),
        "status": updated.get("status"),
        "link": canonical(int(bid_id)),
        "discount": meta.get("discount") or 0,
        "discount_reason": meta.get("discount_reason") or "",
    }

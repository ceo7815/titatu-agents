"""Fixed quote-intake state machine. The model must paste `say` verbatim."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from . import bid_write, fuzzy, stands
from .paths import profile_dir
from .wp_client import WpClient, WpError

STATE_DIR = profile_dir() / "cache" / "intake"

OPENING = (
    "*מוצ׳קה* — עוזר להצעות מחיר\n"
    "\n"
    "אפשר לכתוב חופשי, גם עם שגיאות כתיב — אני מבין עניין.\n"
    "שלח את פרטי האירוע:\n"
    "\n"
    "1. שם לקוח\n"
    "2. שם המזמין\n"
    "3. מספר טלפון\n"
    "4. תאריך האירוע\n"
    "5. שעות ההגשה\n"
    "6. מיקום האירוע\n"
    "7. כמות אורחים\n"
    "8. אימייל _(לא חובה)_\n"
    "9. הערות כלליות _(לא חובה)_"
)

INTAKE_STEPS = {
    "block",
    "missing",
    "title",
    "event_type",
    "decorated",
    "price_per",
    "notes_format",
    "stands",
    "stand_choice",
    "confirm",
    "ready",
    "corrections",
    "working",
    "published",
}

REQUIRED = [
    ("customer_for", "שם לקוח"),
    ("customer_name", "שם המזמין"),
    ("phone", "מספר טלפון"),
    ("event_date", "תאריך האירוע"),
    ("serve_time", "שעות ההגשה"),
    ("address", "מיקום האירוע"),
    ("guests", "כמות אורחים"),
]
OPTIONAL = [
    ("email", "אמייל"),
    ("notes", "הערות כלליות"),
]
NUMBERED_FIELDS = [key for key, _label in REQUIRED] + [key for key, _label in OPTIONAL]
_NUMBERED_LINE = re.compile(r"^\s*(\d{1,2})(?:[\.\)\-–:]|\s)\s*(.+)$")
_FORM_STEPS = {
    "block",
    "missing",
    "title",
    "event_type",
    "decorated",
    "price_per",
    "notes_format",
    "stands",
    "stand_choice",
    "confirm",
    "confirm_delete",
    "ready",
}

FALLBACK_EVENT_TYPES = [
    {"id": 38, "label": "חתונה"},
    {"id": 41, "label": "אירוע עסקי"},
    {"id": 43, "label": "אירועים כלליים"},
    {"id": 39, "label": "בר מצווה"},
    {"id": 42, "label": "בת מצווה"},
    {"id": 45, "label": "יום הולדת"},
]

EVENT_TYPE_ORDER = [
    "חתונה",
    "אירוע עסקי",
    "אירועים כלליים",
    "בר מצווה",
    "בת מצווה",
    "יום הולדת",
]

LABEL_ALIASES = {
    "שם לקוח": "customer_for",
    "שם הלקוח": "customer_for",
    "לכבוד": "customer_for",
    "עבור": "customer_for",
    "לקוח": "customer_for",
    "שם המזמין": "customer_name",
    "שם מזמין": "customer_name",
    "מזמין": "customer_name",
    "מספר טלפון של איש קשר": "phone",
    "מספר טלפון": "phone",
    "טלפון של איש קשר": "phone",
    "טלפון איש קשר": "phone",
    "טלפון": "phone",
    "נייד": "phone",
    "תאריך האירוע": "event_date",
    "תאריך אירוע": "event_date",
    "שעות ההגשה": "serve_time",
    "זמני הגשת אוכל": "serve_time",
    "זמני הגשה": "serve_time",
    "שעת הגשה": "serve_time",
    "שעות הגשה": "serve_time",
    "הגשת אוכל": "serve_time",
    "מיקום האירוע": "address",
    "כתובת האירוע": "address",
    "כתובת אירוע": "address",
    "מיקום אירוע": "address",
    "מיקום": "address",
    "כתובת": "address",
    "כמות אורחים": "guests",
    "מספר אורחים": "guests",
    "מס אורחים": "guests",
    "אורחים": "guests",
    "אמייל": "email",
    "אימייל": "email",
    "מייל": "email",
    "דואל": "email",
    "דוא״ל": "email",
    'דוא"ל': "email",
    "הערות כלליות": "notes",
    "הערות": "notes",
    "כותרת ההצעה": "_title",
    "כותרת": "_title",
}

_PHONE_RE = re.compile(r"(?:\+972[\s-]?|0)5\d[\s-]?\d{7}")
_NOTE_LINE = re.compile(
    r"^(?:תוסי[ףפי]\s+|הוסי[ףפי]\s+)?הער(?:ה|ות)(?:\s*כלליות)?\s*[:\-–]?\s*(.+)$"
)
_NOTE_ADD = re.compile(r"^(?:תוסי[ףפי]|הוסי[ףפי])\b")
_EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
_TIME_RE = re.compile(r"(?:החל\s*מ-?\s*)?(\d{1,2}:\d{2})")
_EVENT_HINTS = [
    (r"מתחתנ|מתחתן|חתונה", 38, "חתונה"),
    (r"בר\s*מצוו", 39, "בר מצווה"),
    (r"בת\s*מצוו", 42, "בת מצווה"),
    (r"יום\s*הולדת", 45, "יום הולדת"),
    (r"עסקי|כנס", 41, "אירוע עסקי"),
]
_FINAL_LETTERS = str.maketrans("ךםןףץ", "כמנפצ")

QUOTE_INTENT = re.compile(
    r"(הצעת\s*מחיר|להוציא\s*הצעה|הצעה\s*חדשה|תיצרי?\s*הצעה|תוציא[י]?\s*הצעה|טיוטה)",
    re.I,
)
DELETE_INTENT = re.compile(
    r"(מחק|תמחק|למחוק|תזר[וקי]ק|לפח)",
    re.I,
)
CHANGE_INTENT = re.compile(
    r"(שנה|תשנה|עדכן|תעדכן|תוסי[ףפי]|תוסיף|תוריד|תיקון|תתקן|מחיר\s*לסועד|עמדות\s*מעוצבות)",
    re.I,
)
LAST_BID_PATH = STATE_DIR / "last_bid.json"


def looks_like_cancel(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if "saving to memory" in t or "Nothing to save" in t:
        return False
    return bool(re.match(r"^(בטל|ביטול|תבטל|cancel)(\s|$)", t, re.I))


def looks_like_delete(text: str) -> bool:
    t = (text or "").strip()
    if not t or looks_like_memory_nudge(t):
        return False
    if re.search(r"(אל תמחק|לא למחוק|בלי למחוק|לא תמחק)", t):
        return False
    if re.search(r"(מחק|תמחק|למחוק).{0,24}(דוכן|עמד)", t):
        return False
    return bool(DELETE_INTENT.search(t))


def looks_like_change(text: str) -> bool:
    t = (text or "").strip()
    if not t or looks_like_memory_nudge(t) or looks_like_delete(t) or looks_like_cancel(t):
        return False
    return bool(CHANGE_INTENT.search(t))


def looks_like_memory_nudge(text: str) -> bool:
    t = text or ""
    return "saving to memory" in t or "skill management tools" in t


def looks_like_intake_block(text: str) -> bool:
    if looks_like_cancel(text) or looks_like_memory_nudge(text) or looks_like_delete(text):
        return False
    return len(_parse_block(text)) >= 2


def _fold_label(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("״", "").replace("׳", "").replace('"', "").replace("'", "").replace("`", "")
    t = re.sub(r"\bמס[\s.]*", "מספר ", t)
    return re.sub(r"\s+", " ", t).strip()


def _label_key(left: str) -> str | None:
    n = _fold_label(left)
    if not n:
        return None
    if re.search(r"לידה", n) or re.search(r"(ת\.?\s*ז|תז\b|זהות)", n):
        if "אירוע" not in n:
            return "_ignore"
    if "הנחה" in n:
        return "_discount"
    if re.search(r"דוכנ", n):
        return "_stands"
    aliases = sorted(
        ((_fold_label(alias), key) for alias, key in LABEL_ALIASES.items()),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for alias, key in aliases:
        if not alias:
            continue
        if n == alias or n.startswith(alias):
            return key
        if len(alias) >= 5 and alias in n:
            return key
    return None


def _split_labeled(line: str) -> tuple[str, str] | None:
    parts = re.split(r"\s+[-–]\s+|\s*:\s+", line, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return None


def _clean_serve_time(value: str) -> str:
    text = (value or "").strip()
    match = _TIME_RE.search(text)
    if match and re.search(r"החל", text):
        return f"החל מ-{match.group(1)}"
    return text


def _parse_discount(value: str) -> tuple[float | None, str]:
    note = (value or "").strip()
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)", note)
    if not match:
        return None, note
    amount = float(match.group(1).replace(",", ""))
    return amount, note


def _numbered_field_values(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for raw_line in (text or "").splitlines():
        match = _NUMBERED_LINE.match((raw_line or "").strip())
        if not match:
            continue
        idx = int(match.group(1))
        value = match.group(2).strip()
        if not value or "לא חובה" in value:
            continue
        labeled = _split_labeled(value)
        key = _label_key(labeled[0]) if labeled else None
        if key in {"_stands", "_discount", "_ignore", "_title"}:
            continue
        if key and labeled and labeled[1].strip() and "לא חובה" not in labeled[1]:
            value = labeled[1].strip()
        elif 1 <= idx <= len(NUMBERED_FIELDS):
            key = NUMBERED_FIELDS[idx - 1]
        else:
            continue
        if key == "serve_time":
            value = _clean_serve_time(value)
        if key == "guests":
            value = re.sub(r"\s*אורחים\s*$", "", value).strip() or value
        if value:
            found[key] = value
    return found


def _positional_field_values(text: str) -> dict[str, str]:
    """Map unlabeled / '1 name' lines in list order when Sahar dumps details."""
    lines: list[str] = []
    for raw_line in (text or "").splitlines():
        clean = (raw_line or "").strip()
        if not clean:
            continue
        if re.search(r"(סוגי\s*דוכנ|רשימת\s*דוכנ|^דוכנים\s*$)", clean) and not _split_labeled(clean):
            break
        numbered = _NUMBERED_LINE.match(clean)
        if numbered and 1 <= int(numbered.group(1)) <= len(NUMBERED_FIELDS):
            clean = numbered.group(2).strip()
        labeled = _split_labeled(clean)
        if labeled and _label_key(labeled[0]):
            continue
        if clean:
            lines.append(clean)
    if len(lines) < 5:
        return {}
    found: dict[str, str] = {}
    for idx, line in enumerate(lines):
        if idx >= len(REQUIRED):
            break
        key = REQUIRED[idx][0]
        value = line
        if key == "serve_time":
            value = _clean_serve_time(value)
        if key == "guests":
            value = re.sub(r"\s*אורחים\s*$", "", value).strip() or value
        if value:
            found[key] = value
    return found


def _parse_message(text: str) -> dict[str, Any]:
    fields: dict[str, str] = {}
    stand_names: list[str] = []
    discount = None
    discount_note = ""
    pending: str | None = None
    numbered = _numbered_field_values(text)
    positional = _positional_field_values(text) if len(numbered) < 5 else {}
    for raw_line in (text or "").splitlines():
        numbered_hit = _NUMBERED_LINE.match((raw_line or "").strip())
        if numbered_hit and 1 <= int(numbered_hit.group(1)) <= len(NUMBERED_FIELDS):
            continue
        clean = re.sub(r"^[\-•*\d\.\)\s]+", "", re.sub(r"\s+", " ", raw_line)).strip()
        if not clean:
            pending = pending if pending == "_stands" else None
            continue
        labeled = _split_labeled(clean)
        key = None
        value = ""
        if labeled:
            key = _label_key(labeled[0])
            value = labeled[1]
        if key is None:
            for alias, alias_key in sorted(LABEL_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
                pattern = rf"^{re.escape(alias)}\s*[:\-–]?\s*(.*)$"
                match = re.match(pattern, _fold_label(clean), re.I)
                if match:
                    key = alias_key
                    value = match.group(1).strip()
                    break
            if key is None:
                key = _label_key(clean)
                if key in {"_stands", "_discount", "_ignore"} and not value:
                    pending = key if key == "_stands" else None
                    continue
        if key == "_ignore":
            pending = None
            continue
        if key == "_discount":
            discount, discount_note = _parse_discount(value)
            pending = None
            continue
        if key == "_stands":
            pending = "_stands"
            if value:
                stand_names.extend(_split_stand_names(value))
            continue
        if key == "_title" and value:
            fields["_title"] = value
            pending = None
            continue
        if key and key not in {"_stands", "_discount", "_ignore"}:
            if key == "serve_time" and value:
                value = _clean_serve_time(value)
            if value and "לא חובה" not in value:
                fields[key] = value
                pending = None
            else:
                pending = key
            continue
        if pending == "_stands":
            if _looks_like_stand_candidate(clean):
                stand_names.extend(_split_stand_names(clean))
            continue
        if pending and "לא חובה" not in clean:
            fields[pending] = clean
            pending = None
    for source in (numbered, positional):
        for key, val in source.items():
            if val and not str(fields.get(key) or "").strip():
                fields[key] = val
    if not fields.get("phone"):
        found = _PHONE_RE.search(text or "")
        if found:
            fields["phone"] = re.sub(r"\s+", "", found.group(0))
    if not fields.get("email"):
        found = _EMAIL_RE.search(text or "")
        if found:
            fields["email"] = found.group(0)
    if not fields.get("serve_time"):
        if re.search(r"(הגשה|החל\s*מ)", text or "") and _TIME_RE.search(text or ""):
            fields["serve_time"] = _clean_serve_time(_TIME_RE.search(text or "").group(0))
    stand_names = [name for name in stand_names if name and _looks_like_stand_candidate(name)]
    return {
        "fields": {key: val for key, val in fields.items() if key != "_title"},
        "title": fields.get("_title") or "",
        "stands": stand_names,
        "discount": discount,
        "discount_note": discount_note,
    }


def _merge_notes(previous: str, extra: str, *, append: bool) -> str:
    extra = bid_write.plain_notes(extra)
    if not extra:
        return bid_write.plain_notes(previous)
    if not append:
        return extra
    prev = bid_write.plain_notes(previous)
    if not prev:
        return extra
    existing = {line.strip() for line in prev.splitlines() if line.strip()}
    added = [line for line in extra.splitlines() if line.strip() and line.strip() not in existing]
    return "\n".join([prev] + added) if added else prev


def _extract_notes(raw: str) -> tuple[str, bool] | None:
    found: list[tuple[str, bool]] = []
    for line in (raw or "").splitlines():
        clean = re.sub(r"^[\-•*\d\.\)\s]+", "", line).strip()
        match = _NOTE_LINE.match(clean)
        if not match:
            continue
        extra = match.group(1).strip()
        if not extra or extra in {"כלליות", "כללית"}:
            continue
        found.append((extra, bool(_NOTE_ADD.match(clean))))
    if not found:
        return None
    append = any(item[1] for item in found)
    text = "\n".join(item[0] for item in found)
    return text, append


def _parse_block(text: str) -> dict[str, str]:
    parsed = _parse_message(text)
    found = dict(parsed["fields"])
    if parsed.get("title"):
        found["_title"] = parsed["title"]
    return found


def _absorb_message(state: dict[str, Any], raw: str) -> bool:
    parsed = _parse_message(raw)
    changed = False
    fields = dict(state.get("fields") or {})
    incoming_notes = (parsed["fields"] or {}).pop("notes", None)
    if parsed["fields"]:
        fields.update(parsed["fields"])
        changed = True
    if parsed.get("title"):
        state["title"] = parsed["title"]
        changed = True
    if parsed.get("discount") is not None:
        state["extra_discount"] = parsed["discount"]
        state["extra_discount_reason"] = parsed["discount_note"] or (
            f"הנחה ידנית — {int(parsed['discount']) if parsed['discount'] == int(parsed['discount']) else parsed['discount']} ₪ לפני מע״מ"
        )
        changed = True
    if parsed.get("stands"):
        existing = list(state.get("pending_stand_names") or [])
        for name in parsed["stands"]:
            if _looks_like_stand_candidate(name) and name not in existing:
                existing.append(name)
        state["pending_stand_names"] = existing
        changed = True
    elif "דוכן" in (raw or "") and (
        looks_like_add_stands(raw)
        or (not looks_like_intake_block(raw) and re.search(r"(דוכן|תוסי[ףפי])", raw))
    ):
        stand_names = _stand_names_from_text(raw)
        if stand_names:
            existing = list(state.get("pending_stand_names") or [])
            for name in stand_names:
                if name not in existing:
                    existing.append(name)
            state["pending_stand_names"] = existing
            changed = True
    guests = re.search(
        r"(?:כמות\s+|מספר\s+|מס['׳]?\s+)?(?:אורחים|משתתפים)\s*(?:ל-?|ל|:|-)?\s*(\d{1,5})",
        raw,
    ) or re.search(r"(\d{1,5})\s*(?:אורחים|משתתפים)", raw)
    if guests:
        fields["guests"] = guests.group(1)
        changed = True
    date = re.search(
        r"(?:תאריך(?:\s*האירוע)?)\s*(?:ל-?|:|-)?\s*(\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)",
        raw,
    )
    if date:
        fields["event_date"] = date.group(1)
        changed = True
    address = re.search(r"(?:כתובת|מיקום)(?:\s*האירוע)?\s*[:\-–]?\s*(.+)$", raw)
    if address and address.group(1).strip() and len(address.group(1).strip()) > 2:
        fields["address"] = address.group(1).strip()
        changed = True
    title = re.search(r"כותרת(?:\s*ההצעה)?\s*[:\-–]?\s*(.+)$", raw)
    if title and title.group(1).strip():
        state["title"] = title.group(1).strip()
        changed = True
    if re.search(r"מחיר\s*לסועד|מחיר\s*למשתתף", raw):
        state["show_price_per_participants"] = not bool(re.search(r"(בלי|לא|הסתר)", raw))
        changed = True
    if re.search(r"עמדות\s*מעוצבות", raw):
        state["no_stands"] = bool(re.search(r"(לא|בלי|ללא)", raw))
        changed = True
    extracted = _extract_notes(raw)
    extra = (extracted[0] if extracted else "") or (incoming_notes or "").strip()
    if extra:
        append = extracted[1] if extracted else bool(_NOTE_ADD.search((raw or "").strip()))
        fields["notes"] = _merge_notes(str(fields.get("notes") or ""), extra, append=append)
        changed = True
    state["fields"] = fields
    return changed


def _captured_preview(state: dict[str, Any]) -> str:
    fields = state.get("fields") or {}
    rows = [
        ("customer_for", "לקוח"),
        ("customer_name", "מזמין"),
        ("phone", "טלפון"),
        ("email", "מייל"),
        ("event_date", "תאריך"),
        ("serve_time", "הגשה"),
        ("address", "מיקום"),
        ("guests", "אורחים"),
    ]
    lines = []
    for key, label in rows:
        value = str(fields.get(key) or "").strip()
        if value:
            lines.append(f"• {label}: {value}")
    if state.get("title"):
        lines.append(f"• כותרת: {state['title']}")
    pending = list(state.get("pending_stand_names") or [])
    chosen = [_stand_label(row) for row in (state.get("stands") or [])]
    names = chosen or pending
    if names:
        lines.append("• דוכנים: " + ", ".join(names))
    if state.get("extra_discount") is not None:
        lines.append(f"• הנחה: {state.get('extra_discount_reason') or state.get('extra_discount')}")
    return "\n".join(lines)


def _infer_event_type(text: str) -> dict[str, Any] | None:
    blob = (text or "").translate(_FINAL_LETTERS)
    for pattern, type_id, label in _EVENT_HINTS:
        if re.search(pattern, blob):
            return {"id": type_id, "label": label}
    return None


def _continue_after_title(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    return _ask_event_type(session_id, state)


def _apply_loose_updates(state: dict[str, Any], raw: str) -> bool:
    return _absorb_message(state, raw)


def _normalize_choice(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^(or|או)\s*:\s*", "", t, flags=re.I)
    numbered = re.match(r"^([1-9])[\.\)\-]\s+(.+)$", t)
    if numbered:
        return numbered.group(2).strip()
    return t


def looks_like_approve(text: str) -> bool:
    t = (text or "").strip()
    return bool(re.match(r"^(מאושר|מאשר|אשר טיוטה|אשר)$", t, re.I))


def looks_like_skip_stands(text: str) -> bool:
    t = (text or "").strip()
    return bool(re.match(r"^(בלי דוכנים|אין דוכנים|בלי|דלג|אין)$", t))


_ADD_STAND_PREFIX = re.compile(
    r"^(?:בבקשה\s+)?(?:תוסי[ףפי]|תוסיפי|תוסיף|תוסיפו|שנה|תשנה|עדכן|תוסיף לי)\s+",
    re.I,
)
_FIELD_LINE = re.compile(
    r"(אורחים|משתתפים|תאריך|כתובת|מיקום|טלפון|מייל|דוא|הנחה|כותרת|הערות|מחיר\s*ל|מזמין|לקוח|הגשה|לידה)",
    re.I,
)
_JUNK_STAND = re.compile(
    r"(^היי$|^שלום$|^הל[וו]$|הצעה|מבנה הבא|ת\.?\s*ז|זהות|דוא|אימייל|טלפון|מזמין|לקוח|"
    r"לידה|אורחים|כתובת|הגשה|רשימה|צריך שתכין|במבנה)",
    re.I,
)


def _looks_like_stand_candidate(name: str) -> bool:
    t = (name or "").strip(" .:-,")
    if not t or len(t) < 2:
        return False
    if len(t) > 40 or len(t.split()) > 5:
        return False
    if _PHONE_RE.search(t) or _EMAIL_RE.search(t):
        return False
    if re.search(r"\d{6,}", t):
        return False
    if _JUNK_STAND.search(t):
        return False
    if _FIELD_LINE.search(t) and "דוכן" not in t:
        return False
    return True


def looks_like_add_stands(text: str) -> bool:
    t = (text or "").strip()
    if not t or looks_like_cancel(t) or looks_like_delete(t):
        return False
    if re.search(r"(תוסי[ףפי]|תוסיפי|תוסיף|תוסיפו).{0,24}דוכן", t):
        return True
    return bool(re.search(r"דוכן", t) and looks_like_change(t))


def _stand_names_from_text(text: str) -> list[str]:
    if looks_like_intake_block(text):
        return []
    names: list[str] = []
    parts = re.split(r"[\n,،]+|(?=תוסי[ףפי])", text or "")
    for part in parts:
        chunk = re.sub(r"\s+", " ", part).strip(" .,-")
        if not chunk:
            continue
        if _FIELD_LINE.search(chunk) and "דוכן" not in chunk:
            continue
        clean = _ADD_STAND_PREFIX.sub("", chunk)
        clean = re.sub(r"^את\s+", "", clean)
        clean = re.sub(r"דוכן(ים)?", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip(" .,-")
        if not clean or _FIELD_LINE.search(clean):
            continue
        for name in _split_stand_names(clean):
            name = name.strip(" .,-")
            if name and name not in names and _looks_like_stand_candidate(name):
                names.append(name)
    return names


def looks_like_new_quote(text: str) -> bool:
    t = (text or "").strip()
    return bool(re.search(r"(הצעה חדשה|התחל מחדש|התחילי מחדש|/new)", t, re.I))


def looks_like_publish(text: str) -> bool:
    t = (text or "").strip()
    return bool(re.match(r"^(לפרסם|פרסם|פרסמי|מאושר|מאשר)$", t, re.I))


def looks_like_want_edit(text: str) -> bool:
    t = (text or "").strip()
    return bool(re.match(r"^(לשנות משהו|לשנות|לא מאושר|לא)$", t, re.I))


def looks_like_patch(text: str) -> bool:
    t = (text or "").strip()
    if not t or looks_like_cancel(t) or looks_like_delete(t) or looks_like_publish(t):
        return False
    if looks_like_add_stands(t) or looks_like_change(t):
        return True
    parsed = _parse_message(t)
    if parsed.get("fields") or parsed.get("stands") or parsed.get("discount") is not None:
        return True
    return bool(re.search(r"(אורחים|תאריך|כתובת|טלפון|מייל|הנחה|כותרת|הגשה|לקוח|מזמין|הערות|משתתף)", t))


def looks_like_reject(text: str) -> bool:
    t = (text or "").strip()
    return bool(re.match(r"^(לא מאושר|לא לאשר|לא)$", t, re.I))


def _is_yes(text: str) -> bool:
    t = (text or "").strip()
    return t in {"כן", "yes", "1"} or looks_like_approve(t)


def _is_no(text: str) -> bool:
    t = (text or "").strip()
    return t in {"לא מאושר", "לא", "no", "2"} or looks_like_reject(t)


def is_active(state: dict[str, Any] | None) -> bool:
    step = (state or {}).get("step")
    return bool(step) and step not in {None, "cancelled"}


_CONVO_MARK = re.compile(
    r"(תמשיך|תמשיל|תשנה|שנה|מחק|בטל|תוסיף|דלג|רק עם|רשימה|איך|למה|מה זה|תסביר)",
    re.I,
)


def is_form_step(state: dict[str, Any] | None) -> bool:
    return str((state or {}).get("step") or "") in _FORM_STEPS


def looks_like_resume_last(text: str) -> bool:
    t = (text or "").strip()
    return bool(re.search(r"(הטיוטה|ההצעה האחרונה|ההצעה הקודמת|תחזיר את ההצעה)", t))


def is_structured_reply(state: dict[str, Any] | None, text: str) -> bool:
    """True when the message is a form answer, not free conversation."""
    raw = (text or "").strip()
    if not raw:
        return False
    if is_form_step(state):
        return True
    if looks_like_approve(raw) or looks_like_reject(raw) or looks_like_cancel(raw):
        return True
    if looks_like_publish(raw) or looks_like_want_edit(raw):
        return True
    if re.match(r"^[1-9]$", raw) or re.match(r"^[1-9][\.\)]\s*", raw):
        return True
    if looks_like_intake_block(raw):
        return True
    step = (state or {}).get("step")
    if step == "event_type":
        labels = [str(row.get("label") or "") for row in (state or {}).get("event_types") or []]
        return raw in labels or any(raw in label or label in raw for label in labels if label)
    if looks_like_add_stands(raw) and step in {
        "confirm",
        "ready",
        "corrections",
        "stands",
        "stand_choice",
        "working",
        "approved",
    }:
        return True
    if looks_like_patch(raw) and step in {
        "working",
        "approved",
        "published",
        "corrections",
        "confirm",
        "ready",
    }:
        return True
    if step in {"working", "approved", "published"}:
        return looks_like_publish(raw) or looks_like_want_edit(raw)
    if step in {"decorated", "price_per", "confirm", "confirm_delete"}:
        return raw in {"כן", "לא", "מאושר", "לא מאושר", "yes", "no", "1", "2"}
    if step == "stand_choice":
        pending = (state or {}).get("stand_pending") or {}
        labels = [_stand_label(row) for row in (pending.get("candidates") or [])]
        return raw in labels or raw in {"אף אחד מאלה", "אף אחד"}
    if step == "notes_format":
        return "רציף" in raw or "סעיף" in raw or "נקוד" in raw
    if step == "stands":
        if looks_like_stand_list(raw):
            return True
        if _CONVO_MARK.search(raw) or looks_like_stand_talk(raw):
            return False
        return bool(_split_stand_names(raw))
    if _CONVO_MARK.search(raw):
        return False
    if step in {"missing", "title", "block"} and len(raw.split()) <= 8:
        return True
    return False


def looks_like_quote_intent(text: str) -> bool:
    t = (text or "").strip()
    if not t or looks_like_cancel(t) or looks_like_memory_nudge(t):
        return False
    if looks_like_delete(t) or looks_like_change(t) or looks_like_publish(t) or looks_like_want_edit(t):
        return False
    if re.search(r"(חפש|מצא|סטטוס|שאושר|שאושרו|רשימת\s*הצעות)", t):
        return False
    if looks_like_new_quote(t):
        return True
    if re.search(r"^(תוציא[י]?|תיצרי?|צרי|צור)\s", t) and QUOTE_INTENT.search(t):
        return True
    return bool(QUOTE_INTENT.search(t)) and not re.search(r"(מחק|שנה|עדכן|בטל|טיוטה)", t)


def _path(session_id: str) -> Path:
    safe = re.sub(r"[^\w.-]+", "_", session_id or "default")
    return STATE_DIR / f"{safe}.json"


def load_state(session_id: str | None = None) -> dict[str, Any] | None:
    paths = [STATE_DIR / "active.json"]
    if session_id:
        paths.append(_path(session_id))
    for path in paths:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("step"):
            return data
    return None


def save_state(session_id: str, state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, indent=2)
    _path(session_id).write_text(payload, encoding="utf-8")
    (STATE_DIR / "active.json").write_text(payload, encoding="utf-8")


def clear_state(session_id: str) -> None:
    del session_id
    if not STATE_DIR.is_dir():
        return
    for path in STATE_DIR.glob("*.json"):
        if path.name == "last_bid.json":
            continue
        try:
            path.unlink()
        except OSError:
            pass


def remember_bid(payload: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LAST_BID_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_last_bid() -> dict[str, Any] | None:
    if not LAST_BID_PATH.is_file():
        return None
    try:
        data = json.loads(LAST_BID_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("id") else None


def forget_last_bid() -> None:
    try:
        LAST_BID_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def current_quote(session_id: str | None = None) -> dict[str, Any] | None:
    last = load_last_bid()
    if last:
        return last
    state = load_state(session_id) if session_id else load_state()
    if state and state.get("wp_id"):
        return {
            "id": state["wp_id"],
            "title": state.get("title") or "",
            "link": state.get("wp_link") or "",
            "status": state.get("wp_status") or "",
        }
    return None


def quote_is_live(bid_id: Any) -> bool:
    try:
        item = WpClient().get_bid(int(bid_id))
    except (WpError, TypeError, ValueError):
        return False
    if not isinstance(item, dict) or not item.get("id"):
        return False
    return str(item.get("status") or "") not in {"trash", "deleted"}


def close_working_session(session_id: str) -> None:
    forget_last_bid()
    clear_state(session_id)


def _meta_ids(value: Any) -> list[int]:
    if isinstance(value, list):
        out: list[int] = []
        for item in value:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out
    if isinstance(value, str) and value.strip().isdigit():
        return [int(value.strip())]
    return []


def _wp_title(item: dict[str, Any]) -> str:
    title = item.get("title")
    if isinstance(title, dict):
        return str(title.get("raw") or title.get("rendered") or "").strip()
    return str(title or "").strip()


def _needs_hydrate(state: dict[str, Any]) -> bool:
    fields = state.get("fields") or {}
    has_core = any(str(fields.get(key) or "").strip() for key, _label in REQUIRED)
    has_stands = bool(state.get("stands"))
    return not has_core or not has_stands


def _hydrate_from_wp(state: dict[str, Any]) -> dict[str, Any]:
    """Fill empty intake fields from the live WordPress quote so a patch cannot wipe it."""
    bid_id = state.get("wp_id")
    if not bid_id or not _needs_hydrate(state):
        return state
    try:
        item = WpClient().get_bid(int(bid_id))
    except (WpError, TypeError, ValueError):
        return state
    if not isinstance(item, dict):
        return state
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    fields = dict(state.get("fields") or {})

    def take(key: str, *meta_keys: str) -> None:
        if str(fields.get(key) or "").strip():
            return
        for meta_key in meta_keys:
            value = meta.get(meta_key)
            if value not in (None, "", [], 0, "0"):
                fields[key] = str(value).strip()
                return

    take("customer_for", "customer_for", "for")
    take("customer_name", "customer_name")
    take("phone", "customer_phone", "phone")
    take("email", "email")
    take("event_date", "customer_date")
    take("serve_time", "customer_serve_time")
    take("address", "customer_address")
    take("guests", "customer_guests", "participants")
    take("notes", "additional_notes")
    if str(fields.get("notes") or "").strip():
        fields["notes"] = bid_write.plain_notes(str(fields["notes"]))
    state["fields"] = fields
    if not str(state.get("title") or "").strip():
        state["title"] = _wp_title(item)
    if state.get("no_stands") is None and meta.get("no_stands") not in (None, ""):
        state["no_stands"] = str(meta.get("no_stands")).lower() in {"true", "1", "yes"}
    if state.get("show_price_per_participants") is None and meta.get("show_price_per_participants") not in (None, ""):
        state["show_price_per_participants"] = str(meta.get("show_price_per_participants")).lower() in {
            "true",
            "1",
            "yes",
        }
    reason = str(meta.get("discount_reason") or "")
    if state.get("extra_discount") in (None, "", 0) and "ידנית" in reason:
        state["extra_discount"] = meta.get("discount")
        state["extra_discount_reason"] = reason
    if not list(state.get("stands") or []):
        ids = _meta_ids(meta.get("chosen_food_services")) + _meta_ids(meta.get("chosen_custom_services"))
        if ids:
            try:
                state["stands"] = stands.by_ids(ids)
            except WpError:
                pass
    if not state.get("wp_link"):
        state["wp_link"] = bid_write.canonical(int(bid_id))
    state["wp_status"] = item.get("status") or state.get("wp_status")
    return state


def attach_last_bid(state: dict[str, Any]) -> dict[str, Any]:
    last = load_last_bid()
    if last and not state.get("wp_id"):
        state["wp_id"] = last["id"]
        state["wp_link"] = last.get("link") or ""
        state.setdefault("title", last.get("title") or "")
    return state


def _sort_event_types(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {label: index for index, label in enumerate(EVENT_TYPE_ORDER)}
    rank["אירועים כללים"] = rank["אירועים כלליים"]

    def key(row: dict[str, Any]) -> tuple[int, str]:
        label = str(row.get("label") or "").strip()
        return (rank.get(label, 100), label)

    return sorted(rows, key=key)


def _event_types() -> list[dict[str, Any]]:
    try:
        rows = WpClient().list_bid_types()
        if rows:
            return _sort_event_types(rows)
    except WpError:
        pass
    return list(FALLBACK_EVENT_TYPES)


def _missing(fields: dict[str, str]) -> list[tuple[str, str]]:
    missing = []
    for key, label in REQUIRED:
        if not str(fields.get(key) or "").strip():
            missing.append((key, label))
    return missing


def _reply(session_id: str, state: dict[str, Any], say: str, **extra: Any) -> dict[str, Any]:
    payload = {"ok": True, "say": say, "step": state.get("step"), **extra}
    state["last_processed"] = state.get("_incoming")
    state["last_processed_step"] = state.get("_incoming_step")
    state["last_result"] = payload
    save_state(session_id, state)
    return payload


def _ask_missing(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    missing = _missing(state.get("fields") or {})
    if missing:
        key, label = missing[0]
        state["step"] = "missing"
        state["awaiting_field"] = key
        remain = " · ".join(item[1] for item in missing)
        preview = _captured_preview(state)
        if not state.get("recap_sent") and preview:
            state["recap_sent"] = True
            say = (
                "*קלטו לי את הפרטים:*\n"
                f"{preview}\n"
                f"\n*עוד חסר:* {remain}\n"
                f"עכשיו צריך *{label}*. אפשר לשלוח את כל החסר בבת אחת."
            )
        elif len(missing) > 1:
            say = (
                f"*חסר לי עוד {label}*\n"
                f"נשארו גם: {remain}\n"
                "אפשר לשלוח הכל בבת אחת, לא רק מילה אחת."
            )
        else:
            say = f"*חסר לי עוד {label}*\nאפשר לכתוב חופשי."
        return _reply(session_id, state, say)
    return _ask_title(session_id, state)


def _ask_title(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    state["step"] = "title"
    state.pop("awaiting_field", None)
    return _reply(session_id, state, "*כותרת ההצעה*\nאיזה כותרת לשים על ההצעה?")


def _ask_event_type(session_id: str, state: dict[str, Any], page: int = 0) -> dict[str, Any]:
    del page
    types = _event_types()
    state["event_types"] = types
    state["step"] = "event_type"
    state.pop("event_type_page", None)
    choices = [str(row["label"]) for row in types]
    say = "*סוג האירוע*\nבחר מהכפתורים:"
    return _reply(session_id, state, say, use_clarify=True, choices=choices)


def _ask_decorated(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    state["step"] = "decorated"
    return _reply(
        session_id,
        state,
        "*עמדות מעוצבות*\nלתת ללקוח אפשרות לבחור עמדות מעוצבות בהצעה?",
        use_clarify=True,
        choices=["מאושר", "לא מאושר"],
    )


def _ask_price_per(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    state["step"] = "price_per"
    return _reply(
        session_id,
        state,
        "*מחיר למשתתף*\nלהציג בהצעה מחיר למשתתף?",
        use_clarify=True,
        choices=["מאושר", "לא מאושר"],
    )


def _continue_after_price_per(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    notes = str((state.get("fields") or {}).get("notes") or "").strip()
    if notes:
        return _ask_notes_format(session_id, state)
    return _ask_stands(session_id, state)


def _continue_after_decorated(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    if state.get("show_price_per_participants") is not None:
        return _continue_after_price_per(session_id, state)
    return _ask_price_per(session_id, state)


def _ask_stands(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    pending = [
        name
        for name in (state.get("pending_stand_names") or [])
        if name and _looks_like_stand_candidate(name)
    ]
    if pending:
        state["pending_stand_names"] = []
        return _ingest_stand_names(session_id, state, ", ".join(pending))
    state["step"] = "stands"
    state.setdefault("stands", [])
    return _reply(
        session_id,
        state,
        "*דוכני אוכל*\n"
        "חובה לפחות דוכן אחד — בלי דוכנים אין הצעת מחיר.\n"
        "\n"
        "כתוב שמות מהקטלוג, מופרדים בפסיק.\n"
        "אפשר גם לבקש רשימה מלאה.",
    )


_GENERIC_STAND_TITLE = re.compile(r"^שם דוכן")


def _stand_label(stand: dict[str, Any]) -> str:
    title = str(stand.get("title") or "").strip()
    product = str(stand.get("product_title") or "").strip()
    if title and not _GENERIC_STAND_TITLE.match(title):
        return title
    return product or title


def _split_stand_names(text: str) -> list[str]:
    parts = re.split(r"[,،\n]+|\s+וגם\s+|\s+ו\s+", text or "")
    return [part.strip(" .") for part in parts if part.strip(" .")]


def looks_like_stand_talk(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(
        re.search(
            r"(תמשיך|תמשיל|תמשכי|תמשיכי|רק עם|רק את|דלג|שכח מ|השאר רק|בלי ה|יאללה|אוקיי|בסדר,?\s*תמשיך)",
            t,
        )
    ) or bool(re.match(r"^(רק|יאללה|אוקיי|בסדר|תמשיך|תמשיל)\b", t))


def _fold_he(value: str) -> str:
    text = re.sub(r"דוכן(ים)?", "", value or "", flags=re.I)
    text = re.sub(r"\s+", "", text)
    if text.startswith("ה") and len(text) > 2:
        text = text[1:]
    return text


def _topic_matches(topic: str, text: str) -> bool:
    if fuzzy.related_stand(topic, text):
        return True
    a, b = _fold_he(topic), _fold_he(text)
    return bool(a) and bool(b) and (a in b or b in a)


def _stand_topic(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^(תמשיך|תמשיל|תמשכי|תמשיכי|יאללה|אוקיי|בסדר)\s*", "", t)
    t = re.sub(r"^(רק\s+עם|רק\s+את|רק|עם)\s*", "", t)
    t = re.sub(r"^(את\s+)?(ה)?דוכן(ים)?\s*", "", t)
    t = t.strip(" .,-")
    return t


def _format_closest(rows: list[dict[str, Any]], limit: int = 5) -> str:
    labels = []
    for row in rows[:limit]:
        label = _stand_label(row)
        if label and label not in labels:
            labels.append(label)
    if not labels:
        return ""
    return "הקרובים ביותר מהקטלוג:\n" + "\n".join(f"• {item}" for item in labels)


def _format_unmatched(items: list[dict[str, Any]]) -> str:
    parts = []
    for item in items:
        query = str(item.get("query") or "").strip()
        closest = list(item.get("closest") or item.get("candidates") or [])
        line = f"לא מצאתי בקטלוג את השם «{query}»."
        extra = _format_closest(closest)
        parts.append(line + (("\n" + extra) if extra else ""))
    return "\n\n".join(parts)


def _ask_stand_choice(session_id: str, state: dict[str, Any], query: str, candidates: list[dict[str, Any]], *, preamble: str = "") -> dict[str, Any]:
    candidates = _unique_candidates(candidates)
    state["step"] = "stand_choice"
    state["stand_pending"] = {
        "query": query,
        "candidates": candidates,
    }
    choices: list[str] = []
    for row in candidates:
        label = _stand_label(row)
        if label and label not in choices:
            choices.append(label)
    choices.append("אף אחד מאלה")
    return _reply(
        session_id,
        state,
        f"*כמה דוכנים מתאימים ל«{query}»*\nבחר מהרשימה, או כתוב את השם המדויק.",
        use_clarify=True,
        choices=choices[:6],
        preamble=preamble or None,
    )


def _is_stand_query(query: str) -> bool:
    return _looks_like_stand_candidate(str(query or "").strip())


def _sanitize_stand_queries(state: dict[str, Any]) -> None:
    state["stand_confirm_queue"] = [
        row
        for row in (state.get("stand_confirm_queue") or [])
        if _is_stand_query(str(row.get("query") or ""))
    ]
    state["stand_unmatched_info"] = [
        row
        for row in (state.get("stand_unmatched_info") or [])
        if _is_stand_query(str(row.get("query") or ""))
    ]
    pending = state.get("stand_pending") or {}
    if pending and not _is_stand_query(str(pending.get("query") or "")):
        state.pop("stand_pending", None)


def _next_stand_step(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    _sanitize_stand_queries(state)
    _drop_resolved_stand_queries(state)
    confirm = list(state.get("stand_confirm_queue") or [])
    leftover: list[dict[str, Any]] = []
    for item in (state.get("stand_unmatched_info") or []):
        cands = _unique_candidates(list(item.get("candidates") or item.get("closest") or []))
        if cands:
            confirm.append({"query": item.get("query"), "candidates": cands[:5]})
        else:
            leftover.append(item)
    state["stand_confirm_queue"] = confirm
    state["stand_unmatched_info"] = leftover
    unmatched = leftover
    chosen = list(state.get("stands") or [])
    if confirm:
        first = confirm[0]
        return _ask_stand_choice(
            session_id,
            state,
            str(first.get("query") or ""),
            list(first.get("candidates") or []),
        )
    if unmatched:
        state["step"] = "stands"
        chosen_names = [_stand_label(row) for row in chosen if _stand_label(row)]
        lines = [_format_unmatched(unmatched)]
        if chosen_names:
            lines.append("כבר נבחרו: " + ", ".join(chosen_names))
        lines.append("כתוב שוב את השמות שלא זוהו, או בקש רשימה מלאה.")
        return _reply(session_id, state, "\n".join(lines))
    if chosen:
        return _finish(session_id, state)
    return _ask_stands(session_id, state)


def _pop_current_confirm(state: dict[str, Any]) -> None:
    pending = state.get("stand_pending") or {}
    query = str(pending.get("query") or "")
    confirm = list(state.get("stand_confirm_queue") or [])
    if confirm and str(confirm[0].get("query") or "") == query:
        confirm = confirm[1:]
    elif confirm:
        confirm = [row for row in confirm if str(row.get("query") or "") != query]
    state["stand_confirm_queue"] = confirm
    state.pop("stand_pending", None)


def looks_like_stand_list(text: str) -> bool:
    t = (text or "").strip()
    return bool(re.search(r"(רשימה מלאה|כל הדוכנים|רשימת הדוכנים|תראה דוכנים)", t))


def _send_stand_catalog(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    try:
        catalog, _source = stands.load_catalog()
    except WpError:
        return _reply(session_id, state, "לא הצלחתי למשוך את קטלוג הדוכנים מוורדפרס.")
    labels: list[str] = []
    for row in catalog:
        label = _stand_label(row)
        if label and label not in labels:
            labels.append(label)
    labels.sort()
    shown = labels[:90]
    body = "רשימת הדוכנים מהקטלוג:\n" + "\n".join(f"• {item}" for item in shown)
    if len(labels) > len(shown):
        body += f"\n… ועוד {len(labels) - len(shown)}"
    body += "\n\nכתוב שמות מדויקים מהרשימה, מופרדים בפסיק."
    state["step"] = state.get("step") or "stands"
    return _reply(session_id, state, body)


def _stand_id(stand: dict[str, Any]) -> int:
    try:
        return int(stand.get("id") or 0)
    except (TypeError, ValueError):
        return 0


def _auto_stand(result: dict[str, Any]) -> dict[str, Any] | None:
    if result.get("status") == "matched" and isinstance(result.get("stand"), dict):
        return result["stand"]
    return None


def _unique_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        stand_id = _stand_id(row)
        if stand_id and stand_id in seen:
            continue
        if stand_id:
            seen.add(stand_id)
        out.append(row)
    return out


def _query_satisfied(query: str, stand: dict[str, Any]) -> bool:
    if not query:
        return False
    return any(
        fuzzy.related_stand(query, str(stand.get(key) or ""))
        for key in ("title", "product_title")
    ) or fuzzy.related_stand(query, _stand_label(stand))


def _drop_resolved_stand_queries(state: dict[str, Any]) -> None:
    chosen = list(state.get("stands") or [])
    chosen_ids = {_stand_id(row) for row in chosen if _stand_id(row)}

    def still_open(item: dict[str, Any]) -> bool:
        query = str(item.get("query") or "")
        if any(_query_satisfied(query, row) for row in chosen):
            return False
        nearby = list(item.get("candidates") or []) + list(item.get("closest") or [])
        if any(_stand_id(row) in chosen_ids for row in nearby if _stand_id(row)):
            return False
        return True

    state["stand_confirm_queue"] = [
        row for row in (state.get("stand_confirm_queue") or []) if still_open(row)
    ]
    state["stand_unmatched_info"] = [
        row for row in (state.get("stand_unmatched_info") or []) if still_open(row)
    ]
    pending = state.get("stand_pending") or {}
    if pending and not still_open(pending):
        state.pop("stand_pending", None)


def _ingest_stand_names(session_id: str, state: dict[str, Any], raw: str, *, append: bool = False) -> dict[str, Any]:
    if looks_like_skip_stands(raw):
        return _reply(
            session_id,
            state,
            "בלי דוכנים אין הצעת מחיר. כתוב לפחות דוכן אחד מהקטלוג, למשל: פסטה, בר יין.",
        )
    if looks_like_stand_talk(raw) and not looks_like_add_stands(raw):
        return _handle_stand_talk(session_id, state, raw)
    names = _stand_names_from_text(raw)
    if not names:
        names = [
            part
            for part in _split_stand_names(raw)
            if part and _looks_like_stand_candidate(part)
        ]
    if not names:
        return _ask_stands(session_id, state)
    try:
        results = stands.resolve_names(names)
    except WpError:
        return _reply(session_id, state, "לא הצלחתי לקרוא את קטלוג הדוכנים. נסה שוב עם שמות דוכנים.")
    if not append:
        state["stands"] = []
        state["stand_confirm_queue"] = []
        state["stand_unmatched_info"] = []
    chosen = list(state.get("stands") or [])
    confirm = list(state.get("stand_confirm_queue") or [])
    unmatched = list(state.get("stand_unmatched_info") or [])
    seen = {_stand_id(row) for row in chosen if _stand_id(row)}
    for result in results:
        closest = _unique_candidates(list(result.get("closest") or result.get("candidates") or []))
        picked = _auto_stand(result)
        stand_id = _stand_id(picked) if picked else 0
        if picked and stand_id and stand_id not in seen:
            chosen.append(picked)
            seen.add(stand_id)
        elif picked and stand_id in seen:
            continue
        elif result.get("status") == "needs_confirmation" or closest:
            confirm.append(
                {
                    "query": result.get("query"),
                    "candidates": _unique_candidates(
                        list(result.get("candidates") or closest)
                    )[:5],
                }
            )
        else:
            unmatched.append({"query": result.get("query"), "closest": closest})
    state["stands"] = chosen
    state["stand_confirm_queue"] = confirm
    state["stand_unmatched_info"] = unmatched
    state["stand_queue"] = []
    _drop_resolved_stand_queries(state)
    return _next_stand_step(session_id, state)


def _handle_stand_talk(session_id: str, state: dict[str, Any], raw: str) -> dict[str, Any]:
    _sanitize_stand_queries(state)
    _drop_resolved_stand_queries(state)
    topic = _stand_topic(raw)
    pending = state.get("stand_pending") or {}
    confirm = list(state.get("stand_confirm_queue") or [])
    unmatched = list(state.get("stand_unmatched_info") or [])
    chosen = list(state.get("stands") or [])

    def matches_topic(text: str) -> bool:
        if not topic:
            return True
        return _topic_matches(topic, text)

    if pending:
        query = str(pending.get("query") or "")
        cands = list(pending.get("candidates") or [])
        if topic and not matches_topic(query) and not any(matches_topic(_stand_label(row)) for row in cands):
            pass
        else:
            keep_q = [row for row in confirm if matches_topic(str(row.get("query") or ""))]
            if pending not in keep_q:
                keep_q = [{"query": query, "candidates": cands}] + keep_q
            state["stand_confirm_queue"] = keep_q
            state["stand_unmatched_info"] = [row for row in unmatched if matches_topic(str(row.get("query") or ""))]
            if topic:
                filtered = [row for row in cands if matches_topic(_stand_label(row))] or cands
                if len(filtered) == 1:
                    chosen.append(filtered[0])
                    state["stands"] = chosen
                    state["stand_confirm_queue"] = keep_q[1:]
                    state.pop("stand_pending", None)
                    return _next_stand_step(session_id, state)
                return _ask_stand_choice(session_id, state, query, filtered)

    if topic:
        state["stand_unmatched_info"] = [row for row in unmatched if matches_topic(str(row.get("query") or ""))]
        kept_confirm = [row for row in confirm if matches_topic(str(row.get("query") or ""))]
        state["stand_confirm_queue"] = kept_confirm
        if chosen or kept_confirm:
            return _next_stand_step(session_id, state)
        return _ingest_stand_names(session_id, state, topic, append=True)

    if chosen:
        state["stand_confirm_queue"] = []
        state["stand_unmatched_info"] = []
        state.pop("stand_pending", None)
        return _finish(session_id, state)
    return _next_stand_step(session_id, state)


def _ask_notes_format(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    state["step"] = "notes_format"
    return _reply(
        session_id,
        state,
        "*הערות כלליות*\nאיך להציג אותן בהצעה?",
        use_clarify=True,
        choices=["סעיפים ונקודות (תוכן יורד)", "תוכן רציף"],
    )


def _draft_from_state(state: dict[str, Any]) -> dict[str, Any]:
    fields = state.get("fields") or {}
    return {
        "title": state.get("title") or "",
        "customer_for": fields.get("customer_for") or "",
        "customer_name": fields.get("customer_name") or "",
        "phone": fields.get("phone") or "",
        "email": fields.get("email") or "",
        "event_date": fields.get("event_date") or "",
        "serve_time": fields.get("serve_time") or "",
        "address": fields.get("address") or "",
        "guests": fields.get("guests") or "",
        "notes": fields.get("notes") or "",
        "notes_format": state.get("notes_format"),
        "bid_type_id": state.get("bid_type_id"),
        "bid_type_label": state.get("bid_type_label"),
        "no_stands": state.get("no_stands"),
        "show_price_per_participants": bool(state.get("show_price_per_participants")),
        "extra_discount": state.get("extra_discount"),
        "extra_discount_reason": state.get("extra_discount_reason") or "",
        "stands": list(state.get("stands") or []),
        "source_message": state.get("source_message") or "",
    }


def _summary_lines(state: dict[str, Any]) -> list[str]:
    draft = state.get("draft") or _draft_from_state(state)
    lines = [
        "*סיכום לפני יצירה*",
        f"• לקוח: {draft['customer_for']}",
        f"• מזמין: {draft['customer_name']}",
        f"• טלפון: {draft['phone']}",
        f"• תאריך: {draft['event_date']}",
        f"• הגשה: {draft['serve_time']}",
        f"• מיקום: {draft['address']}",
        f"• אורחים: {draft['guests']}",
        f"• כותרת: {draft['title']}",
        f"• סוג אירוע: {draft['bid_type_label']}",
        f"• עמדות מעוצבות: {'כן' if draft['no_stands'] is False else 'לא'}",
        f"• מחיר לסועד: {'כן' if draft.get('show_price_per_participants') else 'לא'}",
    ]
    if draft.get("email"):
        lines.append(f"• מייל: {draft['email']}")
    if draft.get("notes"):
        fmt = "סעיפים ונקודות" if draft.get("notes_format") == "headed_lines" else "תוכן רציף"
        lines.append(f"• הערות ({fmt}): {draft['notes']}")
    stand_names = [
        str(row.get("product_title") or row.get("title") or "")
        for row in (draft.get("stands") or [])
        if row
    ]
    if stand_names:
        lines.append("• דוכנים: " + ", ".join(name for name in stand_names if name))
    else:
        lines.append("• דוכנים: חסר — חובה לבחור")
    deal, reason = bid_write.quote_discount(draft)
    if deal:
        lines.append(f"• הנחה: {deal:g} ₪ — {reason}")
    return lines


def _ask_confirm(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    return _open_working_draft(session_id, state)


def _ask_what_to_change(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    state["step"] = "corrections"
    return _reply(
        session_id,
        state,
        "*מה לשנות בטיוטה?*\n"
        "אפשר כמה שינויים בהודעה אחת, למשל:\n"
        "• תוסיף דוכן פסטה\nתוסיף דוכן קורטוש\n"
        "• כמות אורחים 150\n"
        "• להציג מחיר למשתתף\n"
        "• הערות: צריך חשמל",
    )


def _working_payload(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": state.get("wp_id"),
        "title": state.get("title") or "",
        "link": state.get("wp_link") or "",
        "status": state.get("wp_status") or "draft",
    }


def _present_working(session_id: str, state: dict[str, Any], *, updated: bool = False) -> dict[str, Any]:
    state["step"] = "working"
    bid_id = state.get("wp_id")
    link = state.get("wp_link") or (bid_write.canonical(int(bid_id)) if bid_id else "")
    title = state.get("title") or "הצעת מחיר"
    headline = "*הטיוטה עודכנה*" if updated else "*טיוטה מוכנה*"
    amount, reason = bid_write.quote_discount(state.get("draft") or _draft_from_state(state))
    lines = [
        headline,
        f"#{bid_id} — {title}",
        link,
        "רענן את הקישור כדי לראות את המצב העדכני.",
        "עדיין לא פורסם ללקוח — בלי מייל.",
    ]
    stand_names = [_stand_label(row) for row in (state.get("stands") or []) if _stand_label(row)]
    if stand_names:
        lines.append("דוכנים: " + ", ".join(stand_names))
    if amount:
        lines.append(f"הנחה: {amount:g} ₪ לפני מע״מ")
        if reason:
            lines.append(reason)
    note = state.pop("stand_note", None)
    if note:
        lines.append(str(note))
    lines.append("כתוב חופשי מה לשנות — אפשר כמה שינויים בהודעה אחת.")
    return _reply(
        session_id,
        state,
        "\n".join(lines),
        use_clarify=True,
        choices=["לפרסם", "לשנות משהו"],
        ready=True,
        draft=state.get("draft") or _draft_from_state(state),
        created=_working_payload(state),
    )


def _sync_and_present(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    if not state.get("wp_id"):
        return _open_working_draft(session_id, state)
    _hydrate_from_wp(state)
    if _needs_hydrate(state) and not list(state.get("stands") or []):
        return _reply(
            session_id,
            state,
            "*לא הצלחתי לטעון את הטיוטה מוורדפרס*\nכתוב שוב מה לשנות, בלי לפתוח הצעה חדשה.",
        )
    state["draft"] = _draft_from_state(state)
    try:
        synced = bid_write.sync_quote(int(state["wp_id"]), state["draft"])
    except WpError as exc:
        return _reply(
            session_id,
            state,
            f"*השינוי נקלט אצלי, אבל וורדפרס לא עודכן*\n{exc}\nכתוב שוב מה לשנות, או לחץ לשנות משהו.",
        )
    state["wp_link"] = synced["link"]
    state["wp_status"] = synced.get("status") or state.get("wp_status")
    remember_bid(
        {
            "id": synced["id"],
            "title": synced.get("title") or state.get("title"),
            "link": synced["link"],
            "status": synced.get("status"),
        }
    )
    return _present_working(session_id, state, updated=True)


def _open_working_draft(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    if not list(state.get("stands") or []):
        return _ask_stands(session_id, state)
    if state.get("wp_id"):
        return _sync_and_present(session_id, state)
    state["draft"] = _draft_from_state(state)
    try:
        created = bid_write.create_draft(state["draft"])
    except WpError as exc:
        state["step"] = "confirm"
        return _reply(
            session_id,
            state,
            f"*לא הצלחתי ליצור טיוטה בוורדפרס*\n{exc}\nכתוב מאושר כדי לנסות שוב.",
            ready=True,
            draft=state["draft"],
        )
    state["wp_id"] = created["id"]
    state["wp_link"] = created["link"]
    state["wp_status"] = created.get("status")
    remember_bid(
        {
            "id": created["id"],
            "title": created["title"],
            "link": created["link"],
            "status": created.get("status"),
        }
    )
    return _present_working(session_id, state, updated=False)


def _apply_working_patch(session_id: str, state: dict[str, Any], raw: str) -> dict[str, Any]:
    attach_last_bid(state)
    _hydrate_from_wp(state)
    changed = _absorb_message(state, raw)
    names = [
        name
        for name in (state.pop("pending_stand_names", None) or [])
        if name and _looks_like_stand_candidate(name)
    ]
    if not looks_like_intake_block(raw):
        for name in _stand_names_from_text(raw):
            if name not in names:
                names.append(name)
    if names and not (_extract_notes(raw) and "דוכן" not in (raw or "")):
        return _ingest_stand_names(session_id, state, ", ".join(names), append=True)
    if not changed:
        return _ask_what_to_change(session_id, state)
    return _sync_and_present(session_id, state)


def _mark_published(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    if not state.get("wp_id"):
        return _open_working_draft(session_id, state)
    state["step"] = "published"
    link = state.get("wp_link") or bid_write.canonical(int(state["wp_id"]))
    lines = [
        "*הטיוטה פורסמה לצפייה*",
        f"#{state.get('wp_id')} — {state.get('title') or ''}",
        link,
        "לא נשלח מייל ללקוח.",
        "אפשר עדיין לשנות בשפה חופשית — זה יעדכן את אותו קישור.",
    ]
    return _reply(session_id, state, "\n".join(lines), approved=True, created=_working_payload(state))


def _approve(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    return _open_working_draft(session_id, state)


def delete_last_quote(session_id: str | None = None) -> dict[str, Any]:
    last = current_quote(session_id)
    if not last:
        return {"ok": False, "say": "*אין הצעה אחרונה למחוק*\nאם זו הצעה ישנה, תגיד את המזהה (#)."}
    bid_id = int(last["id"])
    try:
        WpClient().trash_bid(bid_id)
    except WpError as exc:
        return {"ok": False, "say": f"*לא הצלחתי למחוק*\n#{bid_id}: {exc}"}
    if session_id:
        close_working_session(session_id)
    else:
        forget_last_bid()
    return {
        "ok": True,
        "say": (
            "*נמחקה*\n"
            f"#{bid_id} — {last.get('title') or 'בלי כותרת'}\n"
            "ההצעה בפח בוורדפרס.\n"
            "אפשר להתחיל הצעה חדשה — כתוב «הצעת מחיר»."
        ),
        "deleted_id": bid_id,
    }


def _with_prefix(result: dict[str, Any], prefix: str) -> dict[str, Any]:
    text = (prefix or "").strip()
    if not text:
        return result
    if result.get("use_clarify"):
        old = str(result.get("preamble") or "").strip()
        result["preamble"] = text + (("\n\n" + old) if old else "")
    else:
        say = str(result.get("say") or "").strip()
        result["say"] = text + (("\n\n" + say) if say else "")
    return result


def _close_delete(session_id: str, state: dict[str, Any], *, do_delete: bool) -> dict[str, Any]:
    pending = dict(state.get("pending_delete") or {})
    return_step = state.get("return_step")
    state.pop("pending_delete", None)
    state.pop("return_step", None)
    prefix = ""
    if do_delete:
        bid_id = pending.get("id")
        if bid_id:
            try:
                WpClient().trash_bid(int(bid_id))
                prefix = (
                    "*נמחקה*\n"
                    f"#{bid_id} — {pending.get('title') or 'בלי כותרת'}\n"
                    "ההצעה בפח בוורדפרס.\n"
                    "אפשר להתחיל הצעה חדשה — כתוב «הצעת מחיר»."
                )
            except WpError as exc:
                prefix = f"*לא נמחקה*\n#{bid_id}: {exc}"
        else:
            result = delete_last_quote(session_id)
            prefix = str(result.get("say") or "")
        if prefix.startswith("*נמחקה*"):
            close_working_session(session_id)
            return {
                "ok": True,
                "say": prefix,
                "step": "cancelled",
                "cancelled": True,
            }
    else:
        title = pending.get("title") or "ההצעה"
        bid = pending.get("id")
        prefix = "*לא מחקתי*\n"
        if bid:
            prefix += f"#{bid} — {title}\n"
        prefix += "ההצעה נשארת."
    if return_step in INTAKE_STEPS:
        state["step"] = return_step
        result = _with_prefix(_replay(session_id, state), prefix)
        loaded = load_state(session_id) or state
        loaded["last_result"] = result
        save_state(session_id, loaded)
        return result
    state["step"] = "cancelled"
    return _reply(session_id, state, prefix)


def propose_delete(session_id: str) -> dict[str, Any]:
    last = current_quote(session_id)
    if not last:
        return {
            "ok": False,
            "say": "*אין הצעה אחרונה למחוק*\nאם זו הצעה ישנה, תגיד את המזהה (#).",
        }
    state = load_state(session_id) or {"fields": {}}
    current = state.get("step")
    if current != "confirm_delete":
        state["return_step"] = current
    state["step"] = "confirm_delete"
    state["pending_delete"] = last
    say = (
        "*למחוק את ההצעה?*\n"
        f"#{last.get('id')} — {last.get('title') or 'בלי כותרת'}\n"
        f"{last.get('link') or ''}"
    )
    return _reply(
        session_id,
        state,
        say,
        use_clarify=True,
        choices=["מאושר", "לא מאושר"],
    )


def handle_ops_message(session_id: str, text: str) -> dict[str, Any] | None:
    """Cancel / delete / start-new. None = not an ops command."""
    raw = (text or "").strip()
    if looks_like_cancel(raw):
        return cancel_intake(session_id)
    if looks_like_delete(raw):
        return propose_delete(session_id)
    return None


def resume_working(session_id: str) -> dict[str, Any]:
    state = load_state(session_id) or {"fields": {}, "step": "working"}
    attach_last_bid(state)
    bid_id = state.get("wp_id")
    if bid_id and not quote_is_live(bid_id):
        close_working_session(session_id)
        return start_intake(session_id, force=True)
    if not bid_id:
        return start_intake(session_id, force=True)
    _hydrate_from_wp(state)
    return _present_working(session_id, state)


def apply_free_update(session_id: str, text: str) -> dict[str, Any]:
    state = load_state(session_id) or {"fields": {}, "step": "working"}
    attach_last_bid(state)
    if state.get("wp_id"):
        return _apply_working_patch(session_id, state, text)
    if is_active(state):
        return submit_intake(session_id, text)
    return {"ok": False, "say": "*אין טיוטה פתוחה*\nקודם נוציא הצעת מחיר."}


def add_stands_command(session_id: str, text: str) -> dict[str, Any]:
    return apply_free_update(session_id, text)


def _apply_corrections(session_id: str, state: dict[str, Any], raw: str) -> dict[str, Any]:
    parsed = _parse_block(raw)
    if not parsed and ":" in raw:
        parsed = _parse_block(raw.replace(":", " "))
    if not parsed:
        return _reply(
            session_id,
            state,
            "*לא זיהיתי מה לשנות*\nכתוב למשל:\n• כמות אורחים 150\n• תאריך האירוע 22.1.27",
        )
    fields = dict(state.get("fields") or {})
    title = parsed.pop("_title", None)
    if title:
        state["title"] = title
    fields.update(parsed)
    state["fields"] = fields
    return _ask_confirm(session_id, state)


def _finish(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    if not list(state.get("stands") or []):
        return _ask_stands(session_id, state)
    state["draft"] = _draft_from_state(state)
    return _ask_confirm(session_id, state)


def _replay(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    step = state.get("step")
    if step == "missing":
        return _ask_missing(session_id, state)
    if step == "title":
        return _ask_title(session_id, state)
    if step == "event_type":
        return _ask_event_type(session_id, state)
    if step == "decorated":
        return _ask_decorated(session_id, state)
    if step == "price_per":
        return _ask_price_per(session_id, state)
    if step == "notes_format":
        return _ask_notes_format(session_id, state)
    if step in {"stands", "stand_choice"}:
        return _next_stand_step(session_id, state)
    if step in {"confirm", "ready", "corrections"}:
        return _ask_confirm(session_id, state)
    if step in {"working", "approved", "published"}:
        return _present_working(session_id, state)
    if step == "confirm_delete":
        return propose_delete(session_id)
    return _reply(session_id, state, OPENING)


def start_intake(session_id: str, *, force: bool = False) -> dict[str, Any]:
    existing = None if force else load_state(session_id)
    step = (existing or {}).get("step")
    if existing and is_active(existing):
        if step == "event_type":
            return _ask_event_type(session_id, existing)
        if step in {"confirm", "ready", "corrections", "working", "approved", "published"}:
            if existing.get("wp_id"):
                if not quote_is_live(existing.get("wp_id")):
                    close_working_session(session_id)
                    return start_intake(session_id, force=True)
                return _present_working(session_id, existing)
            return _ask_confirm(session_id, existing)
        if step in {"stands", "stand_choice"}:
            return _next_stand_step(session_id, existing)
        last = existing.get("last_result")
        if isinstance(last, dict) and (last.get("say") or last.get("use_clarify")):
            return last
        return _replay(session_id, existing)
    state = {"step": "block", "fields": {}, "source_message": ""}
    return _reply(session_id, state, OPENING)


def cancel_intake(session_id: str) -> dict[str, Any]:
    clear_state(session_id)
    return {
        "ok": True,
        "say": "*ביטלתי*\nשאלון הצעת המחיר נסגר. אפשר להתחיל מחדש מתי שתרצה.",
        "step": "cancelled",
        "cancelled": True,
    }


def submit_intake(session_id: str, text: str) -> dict[str, Any]:
    raw = _normalize_choice((text or "").strip())
    if looks_like_memory_nudge(raw):
        existing = load_state(session_id)
        if existing and isinstance(existing.get("last_result"), dict):
            return existing["last_result"]
        return {"ok": True, "say": "", "step": (existing or {}).get("step")}
    ops = handle_ops_message(session_id, raw)
    if ops is not None:
        return ops
    state = load_state(session_id) or {"step": "block", "fields": {}}
    incoming_step = state.get("step") or "block"
    if (
        raw
        and raw == state.get("last_processed")
        and incoming_step == state.get("last_processed_step")
        and isinstance(state.get("last_result"), dict)
    ):
        return state["last_result"]
    state["_incoming"] = raw
    state["_incoming_step"] = incoming_step
    step = incoming_step

    if step == "confirm_delete":
        if _is_yes(raw):
            return _close_delete(session_id, state, do_delete=True)
        if _is_no(raw):
            return _close_delete(session_id, state, do_delete=False)
        return propose_delete(session_id)

    if step == "block":
        _absorb_message(state, raw)
        if not state.get("source_message"):
            state["source_message"] = raw
        return _ask_missing(session_id, state)

    if step == "missing":
        parsed = _parse_message(raw)
        _absorb_message(state, raw)
        key = state.get("awaiting_field")
        fields = dict(state.get("fields") or {})
        if key and not str(fields.get(key) or "").strip() and not parsed["fields"] and not parsed["stands"]:
            fields[key] = raw
            state["fields"] = fields
        return _ask_missing(session_id, state)

    if step == "title":
        if looks_like_change(raw) or _parse_block(raw):
            _absorb_message(state, raw)
            if state.get("title"):
                return _continue_after_title(session_id, state)
            return _ask_title(session_id, state)
        state["title"] = raw
        return _continue_after_title(session_id, state)

    if step == "event_type":
        types = state.get("event_types") or _event_types()
        if raw.strip() in {"עוד סוגים", "עוד", "אחר"}:
            return _ask_event_type(session_id, state)
        match = None
        for row in types:
            if str(row.get("label") or "").strip() == raw.strip():
                match = row
                break
        if match is None:
            for row in types:
                label = str(row.get("label") or "")
                if label and (label in raw or raw in label):
                    match = row
                    break
        if match is None:
            return _ask_event_type(session_id, state)
        state["bid_type_id"] = match.get("id")
        state["bid_type_label"] = match.get("label")
        return _ask_decorated(session_id, state)

    if step == "decorated":
        yes = _is_yes(raw)
        no = _is_no(raw)
        if not yes and not no:
            if looks_like_change(raw):
                _apply_loose_updates(state, raw)
                if state.get("no_stands") is not None:
                    return _continue_after_decorated(session_id, state)
            return _ask_decorated(session_id, state)
        state["no_stands"] = False if yes else True
        return _continue_after_decorated(session_id, state)

    if step == "price_per":
        yes = _is_yes(raw)
        no = _is_no(raw)
        if not yes and not no:
            if looks_like_change(raw) or re.search(r"מחיר\s*ל(סועד|משתתף)", raw):
                _apply_loose_updates(state, raw)
                if state.get("show_price_per_participants") is not None:
                    return _continue_after_price_per(session_id, state)
            return _ask_price_per(session_id, state)
        state["show_price_per_participants"] = bool(yes)
        return _continue_after_price_per(session_id, state)

    if step == "notes_format":
        if "רציף" in raw:
            state["notes_format"] = "continuous"
        elif "סעיף" in raw or "נקוד" in raw or "יורד" in raw:
            state["notes_format"] = "headed_lines"
        else:
            return _ask_notes_format(session_id, state)
        return _ask_stands(session_id, state)

    if step == "stands":
        if looks_like_stand_list(raw):
            return _send_stand_catalog(session_id, state)
        if looks_like_stand_talk(raw):
            return _handle_stand_talk(session_id, state, raw)
        return _ingest_stand_names(session_id, state, raw, append=bool(state.get("stands")))

    if step == "stand_choice":
        _sanitize_stand_queries(state)
        if looks_like_stand_list(raw):
            return _send_stand_catalog(session_id, state)
        if looks_like_stand_talk(raw):
            return _handle_stand_talk(session_id, state, raw)
        pending = state.get("stand_pending") or {}
        if not pending:
            return _next_stand_step(session_id, state)
        candidates = list(pending.get("candidates") or [])
        if raw.strip() in {"אף אחד מאלה", "אף אחד"}:
            _pop_current_confirm(state)
            return _next_stand_step(session_id, state)
        match = None
        ordinal = {"הראשון": 0, "השני": 1, "השלישי": 2, "הרביעי": 3, "החמישי": 4}
        if raw.strip() in ordinal and ordinal[raw.strip()] < len(candidates):
            match = candidates[ordinal[raw.strip()]]
        elif re.match(r"^[1-6]([\.\)]\s*|$)", raw.strip()):
            idx = int(raw.strip()[0]) - 1
            if 0 <= idx < len(candidates):
                match = candidates[idx]
        if match is None:
            for row in candidates:
                label = _stand_label(row)
                title = str(row.get("title") or "").strip()
                if raw.strip() in {label, title} or fuzzy.related_stand(raw, label, threshold=0.88):
                    match = row
                    break
        if match is None:
            names = _stand_names_from_text(raw)
            if not names:
                names = [
                    part
                    for part in _split_stand_names(raw)
                    if part and _looks_like_stand_candidate(part)
                ]
            if names:
                return _ingest_stand_names(session_id, state, raw, append=True)
            return _ask_stand_choice(session_id, state, str(pending.get("query") or ""), candidates)
        chosen = list(state.get("stands") or [])
        chosen.append(match)
        state["stands"] = chosen
        _pop_current_confirm(state)
        _drop_resolved_stand_queries(state)
        return _next_stand_step(session_id, state)

    if step in {"working", "approved", "published"}:
        if looks_like_publish(raw) and step != "published":
            return _mark_published(session_id, state)
        if looks_like_want_edit(raw):
            return _ask_what_to_change(session_id, state)
        if looks_like_patch(raw) or looks_like_add_stands(raw):
            return _apply_working_patch(session_id, state, raw)
        if step == "published":
            return _reply(
                session_id,
                state,
                "*הטיוטה כבר פורסמה לצפייה*\nכתוב מה לשנות כדי לעדכן את אותו קישור.",
            )
        return _present_working(session_id, state)

    if step in {"confirm", "ready"}:
        if looks_like_publish(raw) or _is_yes(raw):
            return _open_working_draft(session_id, state)
        if looks_like_want_edit(raw) or _is_no(raw):
            return _ask_what_to_change(session_id, state)
        if looks_like_patch(raw) or looks_like_add_stands(raw):
            return _apply_working_patch(session_id, state, raw)
        return _open_working_draft(session_id, state)

    if step == "corrections":
        if looks_like_publish(raw) or _is_yes(raw):
            return _open_working_draft(session_id, state)
        if looks_like_want_edit(raw) or _is_no(raw):
            return _ask_what_to_change(session_id, state)
        return _apply_working_patch(session_id, state, raw)

    return start_intake(session_id)

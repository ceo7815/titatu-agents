"""Hebrew-aware fuzzy matching for names, phones, emails, stand titles."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

_FINAL = str.maketrans("ךםןףץ", "כמנפצ")
_NIKUD = re.compile(r"[\u0591-\u05C7]")
_FILLER = re.compile(
    r"\b(דוכן|דוכנים|לאירועים|עמדה|עמדות|מעוצב|מעוצבות|בעיצוב|מיוחד)\b",
    re.I,
)
_STOP = {"על", "של", "עם", "ה", "ב", "ל", "ו", "את", "השל", "בכלים", "אישיים", "אישיות"}


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = _NIKUD.sub("", text).translate(_FINAL)
    text = text.replace("׳", "").replace("'", "").replace("`", "").replace("״", "")
    text = re.sub(r"[^\w\s@.+-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip().casefold()


def phone_digits(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    return digits


def stand_core(value: str | None) -> str:
    text = normalize_text(value)
    text = _FILLER.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(value: str | None) -> list[str]:
    return [tok for tok in stand_core(value).split() if tok and tok not in _STOP]


def _fold_token(value: str) -> str:
    text = normalize_text(value)
    if text.startswith("ה") and len(text) > 3:
        text = text[1:]
    if text.startswith("ו") and len(text) > 3:
        text = text[1:]
    text = text.replace("א", "")
    text = re.sub(r"ו+", "ו", text)
    text = re.sub(r"י+", "י", text)
    return text


def _stem(value: str) -> str:
    text = _fold_token(value)
    for suffix in ("יות", "ים", "ות", "ה", "ת"):
        if text.endswith(suffix) and len(text) - len(suffix) >= 3:
            return text[: -len(suffix)]
    return text


def token_sim(left: str, right: str) -> float:
    """Similarity of a query token (`left`) to a catalog token (`right`)."""
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    stem_left, stem_right = _stem(left), _stem(right)
    if stem_left and stem_left == stem_right and len(stem_left) >= 3:
        return 0.96
    folded_left, folded_right = _fold_token(left), _fold_token(right)
    if folded_left and folded_left == folded_right and min(len(folded_left), len(folded_right)) >= 3:
        return 0.97
    mapped = _latin_form(left)
    if mapped and mapped == right.casefold():
        return 0.96
    if left in right:
        if len(left) >= 4:
            return 0.94
        if right.startswith(left) and len(left) >= 2:
            return 0.9
    if folded_left and folded_right and len(folded_left) >= 4:
        if folded_left in folded_right:
            return 0.92
    ratio = max(
        SequenceMatcher(None, left, right).ratio(),
        SequenceMatcher(None, folded_left, folded_right).ratio() if folded_left and folded_right else 0.0,
        SequenceMatcher(None, mapped, right.casefold()).ratio() if mapped else 0.0,
    )
    return ratio if ratio >= 0.9 else ratio * 0.7


_LATIN_ALIASES = {
    "ניו": "new",
    "יורק": "york",
    "דלי": "deli",
}


def _latin_form(token: str) -> str:
    folded = _fold_token(token)
    if token.casefold() in _LATIN_ALIASES:
        return _LATIN_ALIASES[token.casefold()]
    if folded in _LATIN_ALIASES:
        return _LATIN_ALIASES[folded]
    return ""


def token_threshold(token: str) -> float:
    if len(token) >= 5:
        return 0.78
    if len(token) >= 4:
        return 0.82
    if len(token) == 3:
        return 0.88
    return 0.89


def score_stand_title(query: str, title: str) -> float:
    q = stand_core(query)
    c = stand_core(title)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    scores = [SequenceMatcher(None, q, c).ratio()]
    if q in c or c in q:
        scores.append(0.93)
    q_tokens, c_tokens = tokens(query), tokens(title)
    if q_tokens and c_tokens:
        hits = [max(token_sim(token, other) for other in c_tokens) for token in q_tokens]
        coverage = sum(hits) / len(hits)
        if min(hits) >= 0.5:
            scores.append(0.9 * coverage if q != c else 1.0)
    return max(scores)


def score_stand(query: str, stand: dict[str, Any] | None) -> float:
    row = stand or {}
    return max(
        score_stand_title(query, str(row.get("title") or "")),
        score_stand_title(query, str(row.get("product_title") or "")),
    )


def related_stand(query: str, title: str, *, threshold: float = 0.72) -> bool:
    return score_stand_title(query, title) >= threshold


def score_text(query: str, candidate: str) -> float:
    q = normalize_text(query)
    c = normalize_text(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    if q in c or c in q:
        return 0.92
    return SequenceMatcher(None, q, c).ratio()


def score_phone(query: str, candidate: str) -> float:
    q = phone_digits(query)
    c = phone_digits(candidate)
    if not q or not c:
        return 0.0
    if q == c or q.endswith(c) or c.endswith(q):
        return 1.0
    if q[-7:] == c[-7:] and min(len(q), len(c)) >= 7:
        return 0.9
    return 0.0


def score_email(query: str, candidate: str) -> float:
    q = normalize_text(query)
    c = normalize_text(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    if q in c or c in q:
        return 0.88
    return SequenceMatcher(None, q, c).ratio()

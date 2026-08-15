"""Stand catalog load + fuzzy resolve. Used by tools and the intake questionnaire."""

from __future__ import annotations

from typing import Any

from . import fuzzy, stands_cache
from .wp_client import WpClient, WpError


def _title(item: dict[str, Any]) -> str:
    title = item.get("title")
    if isinstance(title, dict):
        return str(title.get("raw") or title.get("rendered") or "")
    return str(title or "")


def summarize(item: dict[str, Any]) -> dict[str, Any]:
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    return {
        "id": item.get("id"),
        "type": item.get("type"),
        "status": item.get("status"),
        "title": _title(item),
        "product_title": meta.get("product_title") or "",
        "price_per_hundred": meta.get("price_per_hundred"),
        "price_per_fifty": meta.get("price_per_fifty"),
        "ordernumber": meta.get("ordernumber"),
    }


def by_ids(ids: list[int], catalog: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if catalog is None:
        catalog, _source = load_catalog()
    index = {int(row["id"]): row for row in catalog if row.get("id") is not None}
    found: list[dict[str, Any]] = []
    for stand_id in ids:
        try:
            key = int(stand_id)
        except (TypeError, ValueError):
            continue
        row = index.get(key)
        if row:
            found.append(row)
    return found


def load_catalog(client: WpClient | None = None) -> tuple[list[dict[str, Any]], str]:
    cached = stands_cache.load_fresh()
    if cached is not None:
        return cached, "memory_or_disk_fresh"
    client = client or WpClient()
    try:
        collected: list[dict[str, Any]] = []
        for post_type in ("services", "estimate_stand"):
            for page in range(1, 8):
                try:
                    batch = client.request(
                        "GET",
                        f"/wp-json/wp/v2/{post_type}",
                        params={
                            "per_page": 100,
                            "page": page,
                            "context": "edit",
                            "status": "publish,draft,private",
                        },
                    )
                except WpError as exc:
                    if exc.status in (400, 404):
                        break
                    raise
                if not isinstance(batch, list) or not batch:
                    break
                collected.extend(item for item in batch if isinstance(item, dict))
                if len(batch) < 100:
                    break
        compact = [summarize(item) for item in collected]
        stands_cache.save(compact)
        return compact, "wordpress"
    except WpError:
        stale = stands_cache.load_any()
        if stale is not None:
            return stale, "disk_stale"
        raise


def _pack(stand: dict[str, Any], score: float) -> dict[str, Any]:
    return {**stand, "match_score": round(score, 3)}


def _stand_id(stand: dict[str, Any]) -> int:
    try:
        return int(stand.get("id") or 0)
    except (TypeError, ValueError):
        return 0


def _stand_tokens(stand: dict[str, Any]) -> list[str]:
    return fuzzy.tokens(f"{stand.get('title') or ''} {stand.get('product_title') or ''}")


def _is_placeholder(stand: dict[str, Any]) -> bool:
    title = str(stand.get("title") or "").strip()
    return title.startswith("שם דוכן")


def _token_hits(query_token: str, catalog: list[tuple[dict[str, Any], list[str]]]) -> list[dict[str, Any]]:
    def collect(min_score: float) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        seen: set[int] = set()
        for stand, catalog_tokens in catalog:
            if _is_placeholder(stand):
                continue
            if not any(fuzzy.token_sim(query_token, token) >= min_score for token in catalog_tokens):
                continue
            stand_id = _stand_id(stand)
            if stand_id and stand_id in seen:
                continue
            if stand_id:
                seen.add(stand_id)
            hits.append(stand)
        return hits

    exact = collect(0.965)
    if exact:
        return exact
    return collect(fuzzy.token_threshold(query_token))


def _covering_stands(query: str, catalog: list[tuple[dict[str, Any], list[str]]]) -> list[dict[str, Any]]:
    query_tokens = [token for token in fuzzy.tokens(query) if token]
    if not query_tokens:
        return []
    covering: set[int] | None = None
    by_id: dict[int, dict[str, Any]] = {}
    for token in query_tokens:
        hits = _token_hits(token, catalog)
        if len(token) < 3 and len(hits) > 4:
            continue
        hit_ids = set()
        for stand in hits:
            stand_id = _stand_id(stand) or id(stand)
            hit_ids.add(stand_id)
            by_id[stand_id] = stand
        if covering is None:
            covering = hit_ids
        else:
            covering &= hit_ids
    if not covering:
        return []
    return [by_id[stand_id] for stand_id in covering]


def resolve_names(names: list[str], catalog: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if catalog is None:
        catalog, _source = load_catalog()
    indexed = [(stand, _stand_tokens(stand)) for stand in catalog]
    resolved: list[dict[str, Any]] = []
    for name in names:
        ranked = [(fuzzy.score_stand(name, stand), stand) for stand in catalog]
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        closest = [_pack(stand, score) for score, stand in ranked[:5] if score > 0]
        best_score = ranked[0][0] if ranked else 0.0
        second_score = ranked[1][0] if len(ranked) > 1 else 0.0
        covering = _covering_stands(name, indexed)
        covering_ranked = sorted(
            ((_score, stand) for _score, stand in ranked if _stand_id(stand) in {_stand_id(row) for row in covering}),
            key=lambda pair: pair[0],
            reverse=True,
        )
        unique_cover = [_pack(stand, score) for score, stand in covering_ranked]
        unique_win = best_score >= 0.82 and (best_score - second_score) >= 0.08
        if len(unique_cover) == 1:
            resolved.append(
                {
                    "query": name,
                    "status": "matched",
                    "stand": unique_cover[0],
                    "match_score": unique_cover[0]["match_score"],
                    "closest": closest,
                }
            )
            continue
        if len(unique_cover) >= 2:
            resolved.append(
                {
                    "query": name,
                    "status": "needs_confirmation",
                    "candidates": unique_cover[:6],
                    "closest": closest,
                }
            )
            continue
        if best_score >= 0.999 and (best_score - second_score) >= 0.02:
            resolved.append(
                {
                    "query": name,
                    "status": "matched",
                    "stand": ranked[0][1],
                    "match_score": 1.0,
                    "closest": closest,
                }
            )
            continue
        if unique_win:
            resolved.append(
                {
                    "query": name,
                    "status": "matched",
                    "stand": ranked[0][1],
                    "match_score": round(best_score, 3),
                    "closest": closest,
                }
            )
            continue
        tied = [
            _pack(stand, score)
            for score, stand in ranked
            if score >= 0.78 and score >= best_score - 0.05
        ][:6]
        if len(tied) >= 2:
            resolved.append(
                {
                    "query": name,
                    "status": "needs_confirmation",
                    "candidates": tied,
                    "closest": closest,
                }
            )
            continue
        resolved.append(
            {
                "query": name,
                "status": "unmatched",
                "candidates": closest,
                "closest": closest,
            }
        )
    return resolved

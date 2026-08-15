"""WordPress REST client for Titatu (application password, no guessing)."""

from __future__ import annotations

import http.client
import json
import os
import socket
import ssl
import urllib.parse
from base64 import b64encode
from pathlib import Path
from typing import Any


from .paths import profile_dir

PROFILE_DIR = profile_dir()
BOT_UA = "TitatuOfferAgent/1.0 (hermes; WordPress Application Password)"


def _env_files() -> list[Path]:
    files: list[Path] = []
    home = os.environ.get("HERMES_HOME")
    if home:
        files.append(Path(home) / ".env")
        files.append(Path(home) / "wp.env")
    files.append(PROFILE_DIR / ".env")
    files.append(PROFILE_DIR / "wp.env")
    return files


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def load_wp_env() -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in _env_files():
        merged.update(_parse_env_file(path))
    for key in ("WP_URL", "WP_USERNAME", "WP_APP_PASSWORD", "WP_ORIGIN_URL", "WP_ORIGIN_HOST"):
        if os.environ.get(key):
            merged[key] = os.environ[key]
    return merged


def _is_ipv4(host: str) -> bool:
    parts = host.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


def _is_cloudflare_block(status: int, text: str) -> bool:
    body = text or ""
    lowered = body.lower()
    return (
        "Just a moment..." in body
        or "cf-browser-verification" in body
        or "challenge-platform" in body
        or "Attention Required" in body
        or ("cloudflare" in lowered and "<!doctype html>" in lowered)
        or (status == 403 and body.strip().startswith("<"))
    )


def _parse_json_body(text: str) -> Any:
    trimmed = (text or "").lstrip("\ufeff").strip()
    if not trimmed:
        return None
    lowered = trimmed.lower()
    junk = "please unsubscribe me!"
    if lowered.startswith(junk):
        trimmed = trimmed[len(junk) :].strip()
    decoder = json.JSONDecoder()
    last_exc: json.JSONDecodeError | None = None
    for index, char in enumerate(trimmed):
        if char not in "{[":
            continue
        try:
            data, _end = decoder.raw_decode(trimmed[index:])
            return data
        except json.JSONDecodeError as exc:
            last_exc = exc
            continue
    if last_exc is not None:
        raise last_exc
    raise json.JSONDecodeError("No JSON object", trimmed, 0)


class WpError(Exception):
    def __init__(self, message: str, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


class WpClient:
    def __init__(self) -> None:
        env = load_wp_env()
        self.base = (env.get("WP_URL") or "").rstrip("/")
        if self.base.endswith("/wp-login.php"):
            self.base = self.base.rsplit("/", 1)[0]
        self.username = env.get("WP_USERNAME") or ""
        self.password = (env.get("WP_APP_PASSWORD") or "").replace(" ", "")
        self.origin = (env.get("WP_ORIGIN_URL") or "").rstrip("/")
        self.origin_host = env.get("WP_ORIGIN_HOST") or urllib.parse.urlparse(self.base).hostname or ""
        if not self.base or not self.username or not self.password:
            raise WpError("חסר WP_URL / WP_USERNAME / WP_APP_PASSWORD בפרופיל")

    def _auth_header(self) -> str:
        token = b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
        return f"Basic {token}"

    def _targets(self, rel: str, query: str) -> list[tuple[str, str, str | None]]:
        """Prefer origin IP (no Cloudflare), then the public hostname."""
        suffix = rel + query
        out: list[tuple[str, str, str | None]] = []
        if self.origin:
            out.append((self.origin + suffix, "origin", self.origin_host or None))
        out.append((self.base + suffix, "public", None))
        return out

    def _once(
        self,
        method: str,
        url: str,
        *,
        label: str,
        host_header: str | None,
        data: bytes | None,
        timeout: int,
    ) -> tuple[int, str, str]:
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        headers = {
            "Authorization": self._auth_header(),
            "Accept": "application/json",
            "User-Agent": BOT_UA,
            "Connection": "close",
        }
        if host_header:
            headers["Host"] = host_header
        if data is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
            headers["Content-Length"] = str(len(data))

        if parsed.scheme != "https":
            conn = http.client.HTTPConnection(hostname, port, timeout=timeout)
            try:
                conn.request(method, path, body=data, headers=headers)
                res = conn.getresponse()
                text = res.read().decode("utf-8", errors="replace")
                return res.status, text, res.getheader("content-type") or ""
            finally:
                conn.close()

        ctx = ssl.create_default_context()
        sni = host_header or hostname
        if label == "origin" and _is_ipv4(hostname):
            # Origin certs are issued for the public hostname, not the IP.
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        sock = socket.create_connection((hostname, port), timeout=timeout)
        try:
            ssock = ctx.wrap_socket(sock, server_hostname=sni)
        except Exception:
            sock.close()
            raise

        conn = http.client.HTTPSConnection(hostname, port, timeout=timeout, context=ctx)
        conn.sock = ssock
        try:
            conn.request(method, path, body=data, headers=headers)
            res = conn.getresponse()
            text = res.read().decode("utf-8", errors="replace")
            return res.status, text, res.getheader("content-type") or ""
        finally:
            conn.close()

    def _error(self, status: int, rel: str, body: str) -> WpError:
        if _is_cloudflare_block(status, body):
            return WpError(
                "Cloudflare חסם את WordPress. אפשר ללחוץ מאושר שוב אחרי רגע.",
                status=status,
                body=body[:200],
            )
        code = ""
        message = ""
        try:
            parsed = _parse_json_body(body)
            if isinstance(parsed, dict):
                code = str(parsed.get("code") or "")
                message = str(parsed.get("message") or "")
        except Exception:
            pass
        extra = f" ({code})" if code else ""
        hint = f" — {message}" if message else ""
        return WpError(f"WordPress HTTP {status} על {rel}{extra}{hint}", status=status, body=body[:500])

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> Any:
        query = ""
        if params:
            query = "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None and v != ""}
            )
        rel = path if path.startswith("/") else "/" + path
        data = json.dumps(body).encode("utf-8") if body is not None else None

        last_error: WpError | None = None
        last_cf: WpError | None = None
        for round_n in range(2):
            for url, label, host_header in self._targets(rel, query):
                try:
                    status, text, content_type = self._once(
                        method,
                        url,
                        label=label,
                        host_header=host_header,
                        data=data,
                        timeout=timeout,
                    )
                except Exception as exc:  # noqa: BLE001 — origin TLS/network can fail; try public next
                    last_error = WpError(f"שגיאת רשת ל-WordPress ({label}): {exc}")
                    continue
                if _is_cloudflare_block(status, text):
                    last_cf = self._error(status, rel, text)
                    continue
                if status < 200 or status >= 300:
                    # Real WP REST errors (capability/auth) must surface — not fall through to Cloudflare.
                    raise self._error(status, rel, text)
                if not text.strip():
                    return None
                if "json" not in content_type.lower() and text.strip().startswith("<"):
                    last_error = WpError("WordPress החזיר HTML במקום JSON — כנראה חסימת אבטחה.")
                    continue
                try:
                    return _parse_json_body(text)
                except json.JSONDecodeError:
                    preview = (text or "").replace("\n", " ").strip()[:80]
                    last_error = WpError(
                        f"WordPress {rel}: תשובה לא-JSON ({preview})",
                        body=text[:300] if text else "",
                    )
                    continue
            if round_n == 0 and last_cf:
                continue
            break
        raise last_cf or last_error or WpError("חיבור ל-WordPress נכשל")

    def health(self) -> Any:
        return self.request("GET", "/wp-json/titatu-bridge/v1/health")

    def get_bid(self, bid_id: int) -> Any:
        return self.request("GET", f"/wp-json/wp/v2/bid/{int(bid_id)}", params={"context": "edit"})

    def search_bids(self, query: str, per_page: int = 20) -> Any:
        return self.request(
            "GET",
            "/wp-json/wp/v2/bid",
            params={
                "search": query,
                "per_page": min(int(per_page), 100),
                "context": "edit",
                "status": "publish,draft,private,pending",
            },
        )

    def list_bids(
        self,
        quote_status: str = "any",
        days: int = 31,
        date_field: str = "modified",
        per_page: int = 50,
        page: int = 1,
    ) -> Any:
        return self.request(
            "GET",
            "/wp-json/titatu-bridge/v1/bids",
            params={
                "quote_status": quote_status,
                "days": days,
                "date_field": date_field,
                "per_page": per_page,
                "page": page,
            },
        )

    def staff_link(self, bid_id: int) -> Any:
        return self.request(
            "GET",
            "/wp-json/titatu-bridge/v1/staff-link",
            params={"id": int(bid_id)},
        )

    def list_stands(self, per_page: int = 300) -> Any:
        return self.request(
            "GET",
            "/wp-json/titatu-bridge/v1/stands",
            params={"per_page": min(int(per_page), 500)},
        )

    def get_stand(self, stand_id: int) -> Any:
        for post_type in ("services", "estimate_stand"):
            try:
                return self.request(
                    "GET",
                    f"/wp-json/wp/v2/{post_type}/{int(stand_id)}",
                    params={"context": "edit"},
                )
            except WpError as exc:
                if exc.status != 404:
                    raise
        raise WpError(f"דוכן {stand_id} לא נמצא", status=404)

    def list_bid_types(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/wp-json/wp/v2/bid_type", params={"per_page": 100})
        if not isinstance(data, list):
            return []
        types: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or ""
            if isinstance(name, dict):
                name = name.get("rendered") or ""
            types.append({"id": item.get("id"), "label": str(name).strip()})
        return [row for row in types if row.get("label")]

    def create_bid(self, title: str, meta: dict[str, Any], bid_type_ids: list[int] | None = None) -> Any:
        return self.request(
            "POST",
            "/wp-json/wp/v2/bid",
            body={
                "title": title,
                "status": "draft",
                "bid_type": bid_type_ids or [],
                "meta": meta,
            },
        )

    def update_bid(self, bid_id: int, body: dict[str, Any]) -> Any:
        return self.request("POST", f"/wp-json/wp/v2/bid/{int(bid_id)}", body=body)

    def publish_for_view(self, bid_id: int) -> Any:
        """WP publish so ?p=ID is public. Does not set bid_status (no customer email)."""
        return self.update_bid(bid_id, {"status": "publish"})

    def trash_bid(self, bid_id: int) -> Any:
        return self.request("DELETE", f"/wp-json/wp/v2/bid/{int(bid_id)}")

from __future__ import annotations

import json
import sqlite3
import threading
import time
import asyncio
from datetime import date, datetime
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .safehtml import rich_html_has_payload, sanitize_rich_html
from .config import load_config
from .fetcher import PoliteFetcher
from .sharing import (
    DEFAULT_SHARE_BASE_URL,
    cloud_snapshot_hash,
    last_pulled_snapshot_hash,
    pull_snapshot,
    remember_pulled_snapshot_hash,
)
from .textutils import decode_html_entities
from .store import Store
from .sync import sync_source

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = ROOT / "dashboard"
DEFAULT_CONFIG = ROOT / "config" / "sources.json"


def _new_check_state() -> dict:
    return {
        "status": "ready",
        "started_at": None,
        "finished_at": None,
        "report": None,
        "error": None,
    }


def _run_website_check(server) -> None:
    state = server.website_check_state  # type: ignore[attr-defined]
    try:
        config, sources = load_config(DEFAULT_CONFIG)
        selected = [source for source in sources if source.enabled]
        reports = []
        store = Store(server.db_path)  # type: ignore[attr-defined]
        try:
            async def run():
                async with PoliteFetcher(
                    user_agent=config.get("user_agent", "HCMUSHub/0.1"),
                    timeout=float(config.get("request_timeout_seconds", 20)),
                    delay=float(config.get("delay_between_requests_seconds", 0.8)),
                    max_bytes=int(config.get("max_response_bytes", 5_000_000)),
                    respect_robots=True,
                ) as fetcher:
                    for source in selected:
                        reports.append(await sync_source(source, fetcher, store))
                    return list(fetcher.warnings)

            fetcher_warnings = asyncio.run(run())
        finally:
            store.close()
        failed_sources = [
            {"source_id": report["source_id"], "source_name": report["source_name"], "errors": report["errors"]}
            for report in reports if report["errors"]
        ]
        with server.website_check_lock:  # type: ignore[attr-defined]
            state.update({
                "status": "completed",
                "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "report": {
                    "sources_checked": len(reports),
                    "articles_discovered": sum(report["articles_discovered"] for report in reports),
                    "upsert_events": sum(report["upsert_events"] for report in reports),
                    "new_articles": sum(report["new_articles"] for report in reports),
                    "updated_content": sum(report["updated_content"] for report in reports),
                    "linked_duplicate": sum(report["linked_duplicate"] for report in reports),
                    "unchanged": sum(report["unchanged"] for report in reports),
                    "listings_not_modified": sum(report["listings_not_modified"] for report in reports),
                    "failed_sources": failed_sources,
                    "fetcher_warnings": fetcher_warnings,
                },
                "error": None,
            })
    except Exception as exc:
        with server.website_check_lock:  # type: ignore[attr-defined]
            state.update({
                "status": "error",
                "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "report": None,
                "error": f"{type(exc).__name__}: {exc}",
            })


def _start_website_check(server) -> bool:
    with server.website_check_lock:  # type: ignore[attr-defined]
        if server.website_check_state["status"] == "running":  # type: ignore[attr-defined]
            return False
        server.website_check_state.update(  # type: ignore[attr-defined]
            {
                "status": "running",
                "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "finished_at": None,
                "report": None,
                "error": None,
            }
        )
    threading.Thread(
        target=_run_website_check,
        args=(server,),
        name="hcmus-hub-website-check",
        daemon=True,
    ).start()
    return True


def _connect(db_path: Path):
    con = sqlite3.connect(db_path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _is_safe_http_url(value: str | None) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def _row_article(row: sqlite3.Row, *, include_body: bool = False) -> dict:
    item = dict(row)
    item["summary"] = decode_html_entities(item.get("summary") or "")
    try:
        item["attachments"] = json.loads(item.pop("attachments_json", "[]") or "[]")
    except (json.JSONDecodeError, TypeError):
        item["attachments"] = []
    if not include_body:
        body = decode_html_entities(item.pop("content", "") or "")
        # Rich markup is sent only when a single article is opened, not for every row
        # in a paginated feed.
        item.pop("content_html", None)
        item["content_preview"] = body[:260]
    else:
        item["content"] = decode_html_entities(item.get("content") or "")
    return item


def _article_select_sql() -> str:
    return """SELECT a.*, GROUP_CONCAT(DISTINCT s.name) AS source_names,
        GROUP_CONCAT(DISTINCT ars.source_id) AS source_ids,
        GROUP_CONCAT(DISTINCT ars.source_url) AS source_urls,
        GROUP_CONCAT(DISTINCT ars.category) AS source_categories,
        COUNT(DISTINCT ars.source_id) AS source_count
        FROM articles a JOIN article_sources ars ON ars.article_id=a.id
        JOIN sources s ON s.id=ars.source_id"""


_NEEDS_REVIEW_SQL = """(
    (COALESCE(a.content,'')='' AND COALESCE(a.summary,'')='' AND
     COALESCE(a.content_html,'')='' AND COALESCE(a.attachments_json,'[]') IN ('[]',''))
    OR a.published_at IS NULL
    OR a.published_at_source IN ('legacy_unverified','unknown')
    OR a.title LIKE '[CHƯA LẤY CHI TIẾT]%'
    OR a.title LIKE 'Thong bao %'
)"""


def _academic_year_bounds(value: str | None) -> tuple[str, str] | None:
    """Return inclusive start / exclusive end dates for an academic year.

    Academic years run from 1 September through 31 August. An empty value means
    all history, including items whose publication date is unknown.
    """
    value = (value or "").strip()
    if not value:
        return None
    match = re.fullmatch(r"(\d{4})-(\d{4})", value)
    if not match or int(match.group(2)) != int(match.group(1)) + 1:
        raise ValueError("Năm học không hợp lệ; ví dụ hợp lệ: 2026-2027.")
    start_year = int(match.group(1))
    return f"{start_year:04d}-09-01", f"{start_year + 1:04d}-09-01"


def _academic_year_filter(value: str | None, alias: str = "a") -> tuple[str, list[str]]:
    bounds = _academic_year_bounds(value)
    if not bounds:
        return "", []
    return f"{alias}.published_at >= ? AND {alias}.published_at < ?", [bounds[0], bounds[1]]


def _available_academic_years(con: sqlite3.Connection) -> list[str]:
    today = date.today()
    current_start = today.year if today.month >= 9 else today.year - 1
    earliest_start = current_start
    row = con.execute("""SELECT MIN(substr(published_at,1,10)) FROM articles
        WHERE published_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'""").fetchone()
    min_text = row[0] if row else None
    if min_text:
        try:
            oldest = date.fromisoformat(min_text)
            oldest_start = oldest.year if oldest.month >= 9 else oldest.year - 1
            earliest_start = min(current_start, oldest_start)
        except ValueError:
            pass
    return [f"{year}-{year + 1}" for year in range(current_start, earliest_start - 1, -1)]


def _where_sql(conditions: list[str]) -> str:
    return " WHERE " + " AND ".join(f"({condition})" for condition in conditions) if conditions else ""


def _api_stats(db: Path, academic_year: str | None = None) -> dict:
    con = _connect(db)
    try:
        date_condition, date_args = _academic_year_filter(academic_year, "a")
        base_conditions = [date_condition] if date_condition else []
        base_where = _where_sql(base_conditions)
        total = con.execute("SELECT COUNT(*) FROM articles a" + base_where, date_args).fetchone()[0]

        def count_for(extra: str) -> int:
            conditions = [*base_conditions, extra]
            return int(con.execute(
                "SELECT COUNT(*) FROM articles a" + _where_sql(conditions), date_args
            ).fetchone()[0])

        unread = count_for("a.read_at IS NULL")
        favorites = count_for("a.is_favorite=1")
        needs_review = count_for(_NEEDS_REVIEW_SQL)

        # Keep every configured source in the sidebar, but show zero when it has no
        # articles in the selected academic year.
        if date_condition:
            sources = con.execute(f"""SELECT s.id,s.name,s.last_checked_at,s.last_success_at,s.last_error,
                COUNT(DISTINCT a.id) AS articles
                FROM sources s LEFT JOIN article_sources ars ON ars.source_id=s.id
                LEFT JOIN articles a ON a.id=ars.article_id AND {date_condition}
                GROUP BY s.id ORDER BY s.name""", date_args).fetchall()
            categories = [r[0] for r in con.execute(f"""SELECT DISTINCT ars.category
                FROM article_sources ars JOIN articles a ON a.id=ars.article_id
                WHERE COALESCE(ars.category,'')<>'' AND {date_condition.replace('a.', 'a.')}
                ORDER BY ars.category COLLATE NOCASE""", date_args).fetchall()]
        else:
            sources = con.execute("""SELECT s.id,s.name,s.last_checked_at,s.last_success_at,s.last_error,
                COUNT(DISTINCT ars.article_id) AS articles
                FROM sources s LEFT JOIN article_sources ars ON ars.source_id=s.id
                GROUP BY s.id ORDER BY s.name""").fetchall()
            categories = [r[0] for r in con.execute("SELECT DISTINCT category FROM article_sources WHERE COALESCE(category,'')<>'' ORDER BY category COLLATE NOCASE")]

        return {"articles": total, "unread": unread, "favorites": favorites,
                "needs_review": needs_review, "categories": categories,
                "sources": [dict(r) for r in sources],
                "academic_years": _available_academic_years(con),
                "academic_year": (academic_year or "").strip()}
    finally:
        con.close()


def _api_version(db: Path) -> dict:
    con = _connect(db)
    try:
        row = con.execute(
            "SELECT data_revision FROM data_metadata WHERE key='data_revision'"
        ).fetchone()
        return {"data_revision": int(row[0]) if row else 0}
    finally:
        con.close()


def _api_articles(db: Path, params: dict[str, list[str]]) -> dict:
    q = (params.get("q", [""])[0] or "").strip()[:200]
    source = (params.get("source", [""])[0] or "").strip()
    category = (params.get("category", [""])[0] or "").strip()
    mode = (params.get("mode", ["all"])[0] or "all").strip()
    academic_year = (params.get("academic_year", [""])[0] or "").strip()
    page = max(1, min(int((params.get("page", ["1"])[0] or "1")), 100000))
    limit = max(5, min(int((params.get("limit", ["30"])[0] or "30")), 100))
    where, args = [], []
    date_condition, date_args = _academic_year_filter(academic_year, "a")
    if date_condition:
        where.append(date_condition)
        args.extend(date_args)
    if q:
        where.append("(a.title LIKE ? OR a.summary LIKE ? OR a.content LIKE ?)")
        needle = f"%{q}%"
        args.extend([needle, needle, needle])
    if source:
        where.append("EXISTS (SELECT 1 FROM article_sources ax WHERE ax.article_id=a.id AND ax.source_id=?)")
        args.append(source)
    if category:
        where.append("EXISTS (SELECT 1 FROM article_sources ac WHERE ac.article_id=a.id AND ac.category=?)")
        args.append(category)
    if mode == "unread":
        where.append("a.read_at IS NULL")
    elif mode == "favorites":
        where.append("a.is_favorite=1")
    elif mode == "review":
        where.append(_NEEDS_REVIEW_SQL)
    where_sql = _where_sql(where)
    con = _connect(db)
    try:
        total = con.execute("SELECT COUNT(*) FROM articles a" + where_sql, args).fetchone()[0]
        sql = _article_select_sql() + where_sql + " GROUP BY a.id ORDER BY CASE WHEN a.published_at IS NULL OR a.published_at_source IN ('legacy_unverified','unknown') THEN 1 ELSE 0 END, a.published_at DESC, a.first_seen_at DESC LIMIT ? OFFSET ?"
        rows = con.execute(sql, [*args, limit, (page - 1) * limit]).fetchall()
        items = [_row_article(row) for row in rows]
        return {"items": items, "total": total, "page": page, "limit": limit,
                "academic_year": academic_year,
                "pages": max(1, (total + limit - 1) // limit)}
    finally:
        con.close()

def _api_article_detail(db: Path, article_id: int) -> dict | None:
    con = _connect(db)
    try:
        row = con.execute(_article_select_sql() + " WHERE a.id=? GROUP BY a.id", (article_id,)).fetchone()
        if not row:
            return None
        item = _row_article(row, include_body=True)
        item["sources"] = [dict(r) for r in con.execute("""SELECT s.id AS source_id,s.name AS source_name,
            ars.source_url,ars.category,ars.last_detail_attempt_at,ars.last_detail_status,ars.last_detail_chars,ars.last_detail_error
            FROM article_sources ars JOIN sources s ON s.id=ars.source_id WHERE ars.article_id=? ORDER BY s.name,ars.category""", (article_id,)).fetchall()]
        for source in item["sources"]:
            if not _is_safe_http_url(source.get("source_url")):
                source["source_url"] = ""
        item["attachments"] = [u for u in item.get("attachments", []) if _is_safe_http_url(u)]
        base_url = item["sources"][0]["source_url"] if item["sources"] else None
        # Sanitize again at the API boundary before the browser renders the fragment.
        item["content_html"] = sanitize_rich_html(item.get("content_html") or "", base_url)
        item["has_rich_payload"] = rich_html_has_payload(item["content_html"])
        return item
    finally:
        con.close()


def _mark_all_unread_read(db: Path, academic_year: str | None = None) -> int:
    """Mark unread articles as read, optionally limited to one academic year."""
    con = _connect(db)
    try:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        date_condition, date_args = _academic_year_filter(academic_year, "articles")
        where = "read_at IS NULL"
        args: list[object] = [now]
        if date_condition:
            where += f" AND {date_condition}"
            args.extend(date_args)
        cur = con.execute(f"UPDATE articles SET read_at=? WHERE {where}", args)
        con.commit()
        return int(cur.rowcount)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


class _HubHandler(BaseHTTPRequestHandler):
    server_version = "HCMUSHub/0.8"

    @property
    def db_path(self) -> Path:
        return self.server.db_path  # type: ignore[attr-defined]

    def log_message(self, format, *args):
        # Keep terminal logs useful without leaking query contents.
        print(f"[WEB] {self.address_string()} {self.command} {self.path.split('?')[0]}")

    def _send(self, body: bytes, status: int = 200, content_type: str = "application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, status: int = 200):
        self._send(json.dumps(payload, ensure_ascii=False).encode("utf-8"), status)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        try:
            if path == "/api/version":
                self._json(_api_version(self.db_path)); return
            if path == "/api/website-check":
                with self.server.website_check_lock:  # type: ignore[attr-defined]
                    self._json(dict(self.server.website_check_state))  # type: ignore[attr-defined]
                return
            if path == "/api/stats":
                self._json(_api_stats(self.db_path, (params.get("academic_year", [""])[0] or "").strip())); return
            if path == "/api/articles":
                self._json(_api_articles(self.db_path, params)); return
            if path.startswith("/api/articles/"):
                try: article_id = int(path.rsplit("/", 1)[-1])
                except ValueError: self._json({"error": "ID bài viết không hợp lệ"}, 400); return
                item = _api_article_detail(self.db_path, article_id)
                self._json(item if item else {"error": "Không tìm thấy bài viết"}, 200 if item else 404); return
            if path == "/health":
                self._json({"status": "ok", "database_exists": self.db_path.exists()}); return
            rel = "index.html" if path in {"/", "/index.html"} else path.lstrip("/")
            target = (DASHBOARD_DIR / rel).resolve()
            if DASHBOARD_DIR.resolve() not in target.parents and target != (DASHBOARD_DIR / "index.html").resolve():
                self._json({"error": "Không tìm thấy"}, 404); return
            if not target.is_file():
                self._json({"error": "Không tìm thấy"}, 404); return
            content_type = "text/html; charset=utf-8" if target.suffix == ".html" else "text/javascript; charset=utf-8" if target.suffix == ".js" else "text/css; charset=utf-8" if target.suffix == ".css" else "application/octet-stream"
            self._send(target.read_bytes(), 200, content_type)
        except Exception as exc:
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/website-check":
            if not _start_website_check(self.server):
                self._json({"error": "Đang có lượt kiểm tra website chạy"}, 409)
            else:
                self._json({"status": "running"}, 202)
            return
        if parsed.path == "/api/read-all":
            try:
                length = min(int(self.headers.get("Content-Length", "0")), 10000)
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}") if length else {}
                updated = _mark_all_unread_read(self.db_path, payload.get("academic_year"))
                self._json({"action": "read_all", "updated": updated})
            except (ValueError, json.JSONDecodeError) as exc:
                self._json({"error": f"Yêu cầu không hợp lệ: {exc}"}, 400)
            except Exception as exc:
                self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
            return
        match = re_match_action(parsed.path)
        if not match:
            self._json({"error": "Endpoint không hợp lệ"}, 404); return
        article_id, action = match
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 10000)
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            con = _connect(self.db_path)
            try:
                if action == "read":
                    value = bool(payload.get("read", True))
                    read_at = datetime.now().astimezone().isoformat(timespec="seconds") if value else None
                    cur = con.execute("UPDATE articles SET read_at=? WHERE id=?", (read_at, article_id))
                else:
                    value = bool(payload.get("favorite", True))
                    cur = con.execute("UPDATE articles SET is_favorite=? WHERE id=?", (int(value), article_id))
                con.commit()
                if not cur.rowcount:
                    self._json({"error": "Không tìm thấy bài viết"}, 404); return
                self._json({"id": article_id, "action": action, "value": value})
            finally:
                con.close()
        except (ValueError, json.JSONDecodeError) as exc:
            self._json({"error": f"Yêu cầu không hợp lệ: {exc}"}, 400)
        except Exception as exc:
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)


def re_match_action(path: str):
    import re
    match = re.fullmatch(r"/api/articles/(\d+)/(read|favorite)", path)
    return (int(match.group(1)), match.group(2)) if match else None


def _share_poll_loop(db_path: Path, base_url: str) -> None:
    while True:
        try:
            cloud_hash = cloud_snapshot_hash(base_url)
            if cloud_hash != last_pulled_snapshot_hash(db_path):
                report = pull_snapshot(db_path, base_url, apply=True)
                imported_hash = report["snapshot_sha256"]
                remember_pulled_snapshot_hash(db_path, imported_hash)
                print(f"[SHARE] Đã nhập snapshot mới: {imported_hash}")
        except (ValueError, OSError, sqlite3.Error, KeyError, TypeError):
            pass
        time.sleep(60)


def serve_dashboard(db_path: str | Path, host: str = "127.0.0.1", port: int = 8787):
    database = Path(db_path).expanduser().resolve()
    if not database.exists():
        raise FileNotFoundError(f"Không tìm thấy CSDL: {database}. Hãy chạy sync hoặc run-all trước.")
    # Apply additive SQLite schema migrations before serving API queries.
    from .store import Store
    migrated_store = Store(database)
    migrated_store.close()
    # Bind to loopback by default to keep student data local. Explicit public bind is not supported by default.
    server = ThreadingHTTPServer((host, port), _HubHandler)
    server.db_path = database  # type: ignore[attr-defined]
    server.website_check_lock = threading.Lock()  # type: ignore[attr-defined]
    server.website_check_state = _new_check_state()  # type: ignore[attr-defined]
    threading.Thread(
        target=_share_poll_loop,
        args=(database, DEFAULT_SHARE_BASE_URL),
        name="hcmus-hub-share-poll",
        daemon=True,
    ).start()
    print(f"HCMUS Hub dashboard: http://{host}:{port}")
    print(f"CSDL: {database}")
    print("Nhấn Ctrl+C để dừng. Mặc định chỉ máy này truy cập được.")
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\nĐã dừng HCMUS Hub dashboard.")
    finally:
        server.server_close()

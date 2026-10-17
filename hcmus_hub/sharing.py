from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .store import Store
from .textutils import content_digest, normalize_title

SCHEMA_VERSION = 1


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_snapshot(snapshot_path: str | Path, manifest_path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = Path(snapshot_path).expanduser().resolve()
    manifest_file = Path(manifest_path).expanduser().resolve()
    if not snapshot.is_file() or not manifest_file.is_file():
        raise ValueError("Không tìm thấy snapshot hoặc manifest.")
    raw = snapshot.read_bytes()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    expected = manifest.get("snapshot", {})
    actual_hash = hashlib.sha256(raw).hexdigest()
    if expected.get("filename") != snapshot.name or expected.get("sha256") != actual_hash or expected.get("size") != len(raw):
        raise ValueError("Manifest không khớp tên file, kích thước hoặc SHA-256 snapshot.")
    try:
        payload = json.loads(gzip.decompress(raw).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Snapshot gzip/JSON không hợp lệ: {exc}") from exc
    _validate_snapshot(payload, manifest)
    return payload, manifest


def _validate_snapshot(payload: Any, manifest: Any) -> None:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Manifest không hợp lệ hoặc không được hỗ trợ.")
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Không hỗ trợ schema snapshot: {payload.get('schema_version') if isinstance(payload, dict) else None}")
    for key in ("exported_at", "data_revision", "sources", "articles"):
        if key not in payload:
            raise ValueError(f"Snapshot thiếu trường bắt buộc: {key}")
    if not isinstance(payload["data_revision"], int) or payload["data_revision"] < 0:
        raise ValueError("data_revision không hợp lệ.")
    if not isinstance(payload["sources"], list) or not isinstance(payload["articles"], list):
        raise ValueError("sources/articles phải là danh sách.")
    counts = manifest.get("records", {}) if isinstance(manifest, dict) else {}
    if counts.get("sources") != len(payload["sources"]) or counts.get("articles") != len(payload["articles"]):
        raise ValueError("Manifest không khớp số lượng nguồn/bài viết.")
    source_ids: set[str] = set()
    for source in payload["sources"]:
        if not isinstance(source, dict) or not all(isinstance(source.get(k), str) and source[k] for k in ("id", "name", "owner", "base_url", "kind")):
            raise ValueError("Nguồn trong snapshot không hợp lệ.")
        if source["id"] in source_ids:
            raise ValueError("Snapshot chứa source_id trùng.")
        source_ids.add(source["id"])
    link_count = 0
    for article in payload["articles"]:
        required = ("title", "fingerprint", "content_hash", "links")
        if not isinstance(article, dict) or any(key not in article for key in required):
            raise ValueError("Bài viết trong snapshot thiếu trường bắt buộc.")
        if not all(isinstance(article[key], str) for key in ("title", "fingerprint", "content_hash")):
            raise ValueError("Trường định danh bài viết không hợp lệ.")
        if not isinstance(article["links"], list) or not article["links"]:
            raise ValueError("Mỗi bài viết phải có ít nhất một liên kết nguồn.")
        for link in article["links"]:
            if not isinstance(link, dict) or not all(isinstance(link.get(k), str) and link[k] for k in ("source_id", "source_url", "category")):
                raise ValueError("Liên kết nguồn trong snapshot không hợp lệ.")
            if link["source_id"] not in source_ids:
                raise ValueError("Liên kết trỏ tới nguồn không tồn tại.")
            link_count += 1
    if counts.get("links") != link_count:
        raise ValueError("Manifest không khớp số lượng liên kết.")


def export_snapshot(db_path: str | Path, snapshot_path: str | Path, manifest_path: str | Path) -> dict[str, Any]:
    store = Store(Path(db_path).expanduser().resolve())
    try:
        sources = [dict(row) for row in store.conn.execute(
            "SELECT id,name,owner,base_url,kind FROM sources ORDER BY id"
        ).fetchall()]
        articles: list[dict[str, Any]] = []
        rows = store.conn.execute("SELECT * FROM articles ORDER BY id").fetchall()
        for row in rows:
            links = [dict(link) for link in store.conn.execute(
                "SELECT source_id,source_url,category FROM article_sources WHERE article_id=? ORDER BY id",
                (row["id"],),
            ).fetchall()]
            articles.append({
                "title": row["title"], "published_at": row["published_at"],
                "published_at_source": row["published_at_source"],
                "category": row["category"], "summary": row["summary"],
                "content": row["content"], "content_html": row["content_html"],
                "attachments": json.loads(row["attachments_json"] or "[]"),
                "fingerprint": row["fingerprint"], "content_hash": row["content_hash"],
                "links": links,
            })
        payload = {
            "schema_version": SCHEMA_VERSION,
            "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "data_revision": store.data_revision(),
            "sources": sources,
            "articles": articles,
        }
    finally:
        store.close()
    compressed = gzip.compress(_json_bytes(payload), mtime=0)
    snapshot = Path(snapshot_path).expanduser().resolve()
    manifest = Path(manifest_path).expanduser().resolve()
    _atomic_bytes(snapshot, compressed)
    manifest_payload = {
        "schema_version": SCHEMA_VERSION,
        "snapshot": {"filename": snapshot.name, "sha256": hashlib.sha256(compressed).hexdigest(), "size": len(compressed)},
        "records": {"sources": len(sources), "articles": len(articles), "links": sum(len(a["links"]) for a in articles)},
    }
    _atomic_bytes(manifest, _json_bytes(manifest_payload))
    return {"snapshot": str(snapshot), "manifest": str(manifest), **manifest_payload["records"], "data_revision": payload["data_revision"]}


def _merge_article(con: sqlite3.Connection, incoming: dict[str, Any], article_id: int) -> None:
    current = con.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
    attachments = sorted(set(json.loads(current["attachments_json"] or "[]") + (incoming.get("attachments") or [])))
    content = incoming.get("content") or ""
    if len(current["content"] or "") > len(content):
        content = current["content"]
    content_html = incoming.get("content_html") or ""
    if len(current["content_html"] or "") > len(content_html):
        content_html = current["content_html"]
    summary = incoming.get("summary") or current["summary"]
    title = current["title"] if len(current["title"] or "") > len(incoming.get("title") or "") else incoming["title"]
    published_at = incoming.get("published_at") or current["published_at"]
    published_source = incoming.get("published_at_source") or current["published_at_source"]
    digest = content_digest(title, summary, content, attachments, content_html or None)
    con.execute("""UPDATE articles SET fingerprint=?, normalized_title=?, title=?, published_at=?,
        published_at_source=?, category=?, summary=?, content=?, content_html=?, attachments_json=?,
        content_hash=? WHERE id=?""", (
        incoming["fingerprint"], normalize_title(title), title, published_at, published_source,
        current["category"], summary, content, content_html, json.dumps(attachments, ensure_ascii=False),
        digest, article_id,
    ))


def _import_rows(con: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, int]:
    for source in payload["sources"]:
        con.execute("""INSERT INTO sources(id,name,owner,base_url,kind) VALUES(?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name, owner=excluded.owner,
            base_url=excluded.base_url, kind=excluded.kind""",
            tuple(source[key] for key in ("id", "name", "owner", "base_url", "kind")))
    result = {"sources": len(payload["sources"]), "articles_added": 0, "articles_updated": 0, "links_added": 0}
    for incoming in payload["articles"]:
        article_id = None
        for link in incoming["links"]:
            row = con.execute(
                "SELECT article_id FROM article_sources WHERE source_id=? AND source_url=? ORDER BY id LIMIT 1",
                (link["source_id"], link["source_url"]),
            ).fetchone()
            if row:
                article_id = int(row[0])
                break
        if article_id is None:
            row = con.execute("SELECT id FROM articles WHERE fingerprint=? ORDER BY id LIMIT 1", (incoming["fingerprint"],)).fetchone()
            article_id = int(row[0]) if row else None
        if article_id is None:
            attachments = incoming.get("attachments") or []
            con.execute("""INSERT INTO articles(fingerprint,normalized_title,title,published_at,published_at_source,
                category,summary,content,content_html,attachments_json,content_hash,first_seen_at,last_seen_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))""", (
                incoming["fingerprint"], normalize_title(incoming["title"]), incoming["title"],
                incoming.get("published_at"), incoming.get("published_at_source"), incoming.get("category") or "Chưa phân loại",
                incoming.get("summary") or "", incoming.get("content") or "", incoming.get("content_html") or "",
                json.dumps(attachments, ensure_ascii=False), incoming["content_hash"],
            ))
            article_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
            result["articles_added"] += 1
        else:
            _merge_article(con, incoming, article_id)
            result["articles_updated"] += 1
        for link in incoming["links"]:
            cur = con.execute("""INSERT OR IGNORE INTO article_sources(article_id,source_id,source_url,category,first_seen_at,last_seen_at)
                VALUES(?,?,?,?,datetime('now'),datetime('now'))""",
                (article_id, link["source_id"], link["source_url"], link["category"]))
            result["links_added"] += int(cur.rowcount > 0)
    return result


def import_snapshot(db_path: str | Path, snapshot_path: str | Path, manifest_path: str | Path, *, apply: bool = False) -> dict[str, Any]:
    payload, manifest = _read_snapshot(snapshot_path, manifest_path)
    db = Path(db_path).expanduser().resolve()
    if not apply:
        return {
            "apply": False, "data_revision": payload["data_revision"],
            "sources": len(payload["sources"]), "articles": len(payload["articles"]),
            "links": manifest["records"]["links"],
        }
    store = Store(db)
    try:
        con = store.conn
        con.execute("BEGIN")
        result = _import_rows(con, payload)
        con.commit()
        return {"apply": True, **result, "data_revision": store.data_revision()}
    except BaseException:
        store.conn.rollback()
        raise
    finally:
        store.close()

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from .store import Store
from .textutils import content_digest, normalize_title

SCHEMA_VERSION = 1
DEFAULT_SHARE_BASE_URL = "https://hcmus-hub-sync.sanphamsangtao2020.workers.dev"
SHARE_SYNC_METADATA_TABLE = "share_sync_metadata"


class _SnapshotManifestMismatch(ValueError):
    pass


class _NoCloudManifest(ValueError):
    pass


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


def _shared_fingerprint(payload: dict[str, Any]) -> str:
    shared = {
        "schema_version": payload["schema_version"],
        "sources": payload["sources"],
        "articles": payload["articles"],
    }
    return hashlib.sha256(_json_bytes(shared)).hexdigest()


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
        raise _SnapshotManifestMismatch("Manifest không khớp tên file, kích thước hoặc SHA-256 snapshot.")
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
    if len(current["summary"] or "") > len(summary):
        summary = current["summary"]
    title = current["title"] if len(current["title"] or "") > len(incoming.get("title") or "") else incoming["title"]
    published_at = current["published_at"] or incoming.get("published_at")
    published_source = current["published_at_source"] or incoming.get("published_at_source")
    digest = content_digest(title, summary, content, attachments, content_html or None)
    con.execute("""UPDATE articles SET fingerprint=?, normalized_title=?, title=?, published_at=?,
        published_at_source=?, category=?, summary=?, content=?, content_html=?, attachments_json=?,
        content_hash=? WHERE id=?""", (
        current["fingerprint"] or incoming["fingerprint"], normalize_title(title), title, published_at, published_source,
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


def _share_metadata_connection(db_path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(Path(db_path).expanduser().resolve(), timeout=10)
    con.execute(f"""CREATE TABLE IF NOT EXISTS {SHARE_SYNC_METADATA_TABLE} (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""")
    con.commit()
    return con


def last_pulled_snapshot_hash(db_path: str | Path) -> str | None:
    con = _share_metadata_connection(db_path)
    try:
        row = con.execute(
            f"SELECT value FROM {SHARE_SYNC_METADATA_TABLE} WHERE key='snapshot_sha256'"
        ).fetchone()
        return str(row[0]) if row else None
    finally:
        con.close()


def remember_pulled_snapshot_hash(db_path: str | Path, snapshot_hash: str) -> None:
    con = _share_metadata_connection(db_path)
    try:
        con.execute(
            f"""INSERT INTO {SHARE_SYNC_METADATA_TABLE}(key,value) VALUES('snapshot_sha256',?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (snapshot_hash,),
        )
        con.commit()
    finally:
        con.close()


def cloud_snapshot_hash(base_url: str = DEFAULT_SHARE_BASE_URL) -> str:
    try:
        manifest = json.loads(_request_bytes(_share_url(base_url, "/api/manifest")).decode("utf-8"))
        snapshot_hash = manifest["snapshot"]["sha256"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("Manifest từ Worker không hợp lệ.") from exc
    if (not isinstance(snapshot_hash, str) or
            not re.fullmatch(r"[0-9a-f]{64}", snapshot_hash, re.IGNORECASE)):
        raise ValueError("SHA-256 trong manifest Worker không hợp lệ.")
    return snapshot_hash.lower()


def _share_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def _request_bytes(url: str, *, method: str = "GET", data: bytes | None = None,
                   headers: dict[str, str] | None = None) -> bytes:
    request_headers = {"User-Agent": "HCMUS-Hub/1.0"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise ValueError(f"Worker trả HTTP {exc.code}: {detail or 'không có chi tiết.'}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Không thể kết nối Worker: {exc.reason}") from exc


def _request_with_headers(url: str) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "HCMUS-Hub/1.0"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read(), {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise ValueError(f"Worker trả HTTP {exc.code}: {detail or 'không có chi tiết.'}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Không thể kết nối Worker: {exc.reason}") from exc


def _fetch_cloud_snapshot(base_url: str, directory: Path, max_attempts: int) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    last_mismatch: _SnapshotManifestMismatch | None = None
    for _ in range(max_attempts):
        try:
            manifest_bytes, response_headers = _request_with_headers(_share_url(base_url, "/api/manifest"))
        except ValueError as exc:
            if "HTTP 404" in str(exc):
                raise _NoCloudManifest("Cloud chưa có manifest.") from exc
            raise
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            filename = manifest["snapshot"]["filename"]
            if not isinstance(filename, str) or not filename or Path(filename).name != filename:
                raise ValueError("Manifest snapshot filename không hợp lệ.")
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError("Manifest từ Worker không hợp lệ.") from exc
        manifest_path = directory / "cloud-manifest.json"
        snapshot_path = directory / filename
        manifest_path.write_bytes(manifest_bytes)
        try:
            snapshot_path.write_bytes(_request_bytes(_share_url(base_url, "/api/snapshot")))
        except ValueError as exc:
            if "HTTP 404" not in str(exc):
                raise
            last_mismatch = _SnapshotManifestMismatch("Snapshot tạm thời không tồn tại theo manifest vừa đọc.")
            continue
        try:
            payload, validated_manifest = _read_snapshot(snapshot_path, manifest_path)
            return payload, validated_manifest, response_headers.get("etag")
        except _SnapshotManifestMismatch as exc:
            last_mismatch = exc
    raise ValueError(f"Manifest và snapshot thay đổi đồng thời sau {max_attempts} lần thử.") from last_mismatch


def _multipart_form(snapshot: bytes, snapshot_name: str, manifest: bytes, manifest_name: str) -> tuple[bytes, str]:
    boundary = "----HcmusHubShareBoundary"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"snapshot\"; filename=\"{snapshot_name}\"\r\n"
        "Content-Type: application/gzip\r\n\r\n".encode("utf-8") + snapshot + b"\r\n",
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"manifest\"; filename=\"{manifest_name}\"\r\n"
        "Content-Type: application/json\r\n\r\n".encode("utf-8") + manifest + b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def pull_snapshot(db_path: str | Path, base_url: str = DEFAULT_SHARE_BASE_URL, *, apply: bool = False,
                  max_attempts: int = 3) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="hcmus-hub-share-pull-") as temp_dir:
        directory = Path(temp_dir)
        payload, manifest, _ = _fetch_cloud_snapshot(base_url, directory, max_attempts)
        del payload
        report = import_snapshot(
            db_path, directory / manifest["snapshot"]["filename"],
            directory / "cloud-manifest.json", apply=apply,
        )
        return {**report, "snapshot_sha256": manifest["snapshot"]["sha256"].lower()}


def publish_snapshot(db_path: str | Path, base_url: str = DEFAULT_SHARE_BASE_URL,
                     token: str | None = None, max_attempts: int = 3) -> dict[str, Any]:
    if not token:
        raise ValueError("Thiếu HUB_WRITE_TOKEN trong biến môi trường.")
    with tempfile.TemporaryDirectory(prefix="hcmus-hub-share-publish-") as temp_dir:
        directory = Path(temp_dir)
        snapshot_path = directory / "snapshot.json.gz"
        manifest_path = directory / "manifest.json"
        for attempt in range(max_attempts):
            try:
                cloud_payload, manifest, baseline_etag = _fetch_cloud_snapshot(base_url, directory, max_attempts)
                cloud_manifest = directory / "cloud-manifest.json"
                cloud_snapshot = directory / manifest["snapshot"]["filename"]
                import_snapshot(db_path, cloud_snapshot, cloud_manifest, apply=True)
                cloud_fingerprint = _shared_fingerprint(cloud_payload)
            except _NoCloudManifest:
                baseline_etag = None
                cloud_fingerprint = None
            export_snapshot(db_path, snapshot_path, manifest_path)
            local_payload, _ = _read_snapshot(snapshot_path, manifest_path)
            if baseline_etag and _shared_fingerprint(local_payload) == cloud_fingerprint:
                return {"ok": True, "published": False, "reason": "shared_data_unchanged"}
            body, content_type = _multipart_form(snapshot_path.read_bytes(), snapshot_path.name, manifest_path.read_bytes(), manifest_path.name)
            headers = {"Authorization": f"Bearer {token}", "Content-Type": content_type}
            headers["If-Match" if baseline_etag else "If-None-Match"] = baseline_etag or "*"
            try:
                response = _request_bytes(_share_url(base_url, "/api/publish"), method="POST", data=body, headers=headers)
                return {**json.loads(response.decode("utf-8")), "published": True}
            except ValueError as exc:
                if "HTTP 409" not in str(exc) or attempt + 1 >= max_attempts:
                    raise ValueError(f"Xung đột publish chưa giải quyết được sau {max_attempts} lần thử.") from exc
        raise ValueError(f"Xung đột publish chưa giải quyết được sau {max_attempts} lần thử.")

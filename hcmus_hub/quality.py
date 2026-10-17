from __future__ import annotations

import html
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .safehtml import rich_html_has_payload
from .textutils import article_fingerprint, content_digest, normalize_title

ENTITY_RE = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);?")


def _decode(value: str | None) -> str:
    return html.unescape(value or "")


def _looks_like_slug(title: str, urls: str | None) -> bool:
    if not title:
        return True
    if "[CHƯA LẤY CHI TIẾT]" in title.upper():
        return True
    for url in (urls or "").split(","):
        path = urlparse(url.strip()).path.rstrip("/")
        if not path:
            continue
        slug = path.split("/")[-1]
        slug_title = re.sub(r"[-_]+", " ", slug).strip()
        if slug_title and normalize_title(title) == normalize_title(slug_title):
            return True
    # CTSV's sitemap slug titles are ASCII-transliterated and commonly start with these words.
    if re.match(r"^(thong bao|so tay|ke hoach|chuong trinh|quy dinh|huong dan|trien khai)\b", title.casefold()):
        if not re.search(r"[À-ỹĐđ]", title):
            return True
    return False


def normalize_database_text(db_path: str | Path) -> dict[str, int]:
    """Decode HTML entities in existing SQLite text fields without deleting records."""
    path = Path(db_path).expanduser().resolve()
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    counts = {"articles_changed": 0, "article_sources_changed": 0, "revisions_changed": 0, "fields_changed": 0}
    try:
        con.execute("BEGIN")
        articles = con.execute("SELECT * FROM articles").fetchall()
        for row in articles:
            title = _decode(row["title"])
            summary = _decode(row["summary"])
            content = _decode(row["content"])
            category = _decode(row["category"])
            fields_changed = sum([
                title != (row["title"] or ""), summary != (row["summary"] or ""),
                content != (row["content"] or ""), category != (row["category"] or ""),
            ])
            if not fields_changed:
                continue
            attachments = json.loads(row["attachments_json"] or "[]")
            fingerprint = article_fingerprint(title, row["published_at"])
            rich_markup = (row["content_html"] or "") if "content_html" in row.keys() else ""
            digest = content_digest(title, summary, content, attachments, rich_markup or None)
            con.execute("""UPDATE articles SET title=?, normalized_title=?, category=?, summary=?, content=?,
                        fingerprint=?, content_hash=? WHERE id=?""",
                        (title, normalize_title(title), category, summary, content, fingerprint, digest, row["id"]))
            counts["articles_changed"] += 1
            counts["fields_changed"] += fields_changed
        links = con.execute("SELECT id,category FROM article_sources").fetchall()
        for row in links:
            category = _decode(row["category"])
            if category != (row["category"] or ""):
                con.execute("UPDATE article_sources SET category=? WHERE id=?", (category, row["id"]))
                counts["article_sources_changed"] += 1
        revisions = con.execute("SELECT id,title,summary,content FROM article_revisions").fetchall()
        for row in revisions:
            title, summary, content = _decode(row["title"]), _decode(row["summary"]), _decode(row["content"])
            if (title, summary, content) != (row["title"], row["summary"], row["content"]):
                con.execute("UPDATE article_revisions SET title=?,summary=?,content=? WHERE id=?", (title, summary, content, row["id"]))
                counts["revisions_changed"] += 1
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return counts


def build_quality_report(db_path: str | Path) -> dict[str, Any]:
    path = Path(db_path).expanduser().resolve()
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("""SELECT a.*, GROUP_CONCAT(DISTINCT s.name) source_names,
            GROUP_CONCAT(DISTINCT ars.source_id) source_ids,
            GROUP_CONCAT(DISTINCT ars.source_url) source_urls,
            GROUP_CONCAT(DISTINCT ars.category) source_categories
            FROM articles a JOIN article_sources ars ON ars.article_id=a.id
            JOIN sources s ON s.id=ars.source_id GROUP BY a.id ORDER BY a.id DESC""").fetchall()
        per_source: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        article_records: list[dict[str, Any]] = []
        normalized_groups: dict[str, list[dict]] = defaultdict(list)
        url_groups: dict[str, list[dict]] = defaultdict(list)
        total = len(rows)
        metrics = {
            "articles": total, "empty_content": 0, "empty_summary": 0,
            "neither_content_nor_summary": 0, "missing_published_at": 0,
            "unverified_date": 0, "slug_placeholder_title": 0,
            "html_entities": 0, "very_short_content": 0,
        }
        for row in rows:
            a = dict(row)
            sources = (a.get("source_ids") or "unknown").split(",")
            title = a.get("title") or ""
            summary = a.get("summary") or ""
            content = a.get("content") or ""
            source_urls = a.get("source_urls") or ""
            placeholder = _looks_like_slug(title, source_urls)
            entity_found = bool(ENTITY_RE.search(title + "\n" + summary + "\n" + content))
            if not content.strip(): metrics["empty_content"] += 1
            if not summary.strip(): metrics["empty_summary"] += 1
            has_rich_payload = rich_html_has_payload(a.get("content_html") or "")
            try:
                has_attachments = bool(json.loads(a.get("attachments_json") or "[]"))
            except (TypeError, json.JSONDecodeError):
                has_attachments = False
            if not content.strip() and not summary.strip() and not has_rich_payload and not has_attachments: metrics["neither_content_nor_summary"] += 1
            if not a.get("published_at"): metrics["missing_published_at"] += 1
            if a.get("published_at") and a.get("published_at_source") in {"legacy_unverified", "unknown", ""}:
                metrics["unverified_date"] += 1
            if placeholder: metrics["slug_placeholder_title"] += 1
            if entity_found: metrics["html_entities"] += 1
            if content.strip() and len(content.strip()) < 100: metrics["very_short_content"] += 1
            record = {
                "id": a["id"], "title": title, "source_ids": sources,
                "source_names": a.get("source_names"), "source_urls": source_urls,
                "published_at": a.get("published_at"), "published_at_source": a.get("published_at_source"),
                "content_chars": len(content), "summary_chars": len(summary),
                "rich_html_chars": len(a.get("content_html") or ""), "has_rich_payload": has_rich_payload,
                "has_attachments": has_attachments,
                "placeholder_title": placeholder, "html_entities": entity_found,
            }
            article_records.append(record)
            normalized = normalize_title(title)
            if normalized:
                normalized_groups[normalized].append(record)
            for url in source_urls.split(","):
                url = url.strip()
                if url:
                    url_groups[url].append(record)
            for source_id in sources:
                bucket = per_source[source_id]
                bucket["articles"] += 1
                bucket["empty_content"] += int(not content.strip())
                bucket["empty_summary"] += int(not summary.strip())
                bucket["neither_content_nor_summary"] += int(not content.strip() and not summary.strip())
                bucket["missing_published_at"] += int(not a.get("published_at"))
                bucket["unverified_date"] += int(bool(a.get("published_at") and a.get("published_at_source") in {"legacy_unverified", "unknown", ""}))
                bucket["placeholder_title"] += int(placeholder)
        title_duplicates = []
        for normalized, group in normalized_groups.items():
            source_ids = set(sid for item in group for sid in item["source_ids"])
            if len(group) > 1 and len(source_ids) > 1:
                title_duplicates.append({"normalized_title": normalized, "records": group})
        title_duplicates.sort(key=lambda g: (-len(g["records"]), g["normalized_title"]))
        canonical_url_duplicates = []
        for url, group in url_groups.items():
            ids = {item["id"] for item in group}
            if len(ids) > 1:
                canonical_url_duplicates.append({"url": url, "records": group})
        return {
            "db_path": str(path),
            "metrics": metrics,
            "per_source": {key: dict(value) for key, value in sorted(per_source.items())},
            "cross_source_title_duplicate_groups": title_duplicates,
            "canonical_url_multiple_article_groups": canonical_url_duplicates,
            "records_needing_enrichment": [
                item for item in article_records
                if item["placeholder_title"] or item["content_chars"] == 0 or item["summary_chars"] == 0
                or not item["published_at"] or item["published_at_source"] in {"legacy_unverified", "unknown", ""}
            ],
        }
    finally:
        con.close()


def write_quality_report(report: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "quality-report.json"
    md_path = target / "quality-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    metrics = report["metrics"]
    md = [
        "# HCMUS Hub — Báo cáo chất lượng dữ liệu", "",
        f"- CSDL: `{report['db_path']}`", f"- Tổng số bài: {metrics['articles']}", "",
        "## Các chỉ số", "", "| Chỉ số | Số bài |", "|---|---:|",
        f"| Thiếu nội dung đầy đủ | {metrics['empty_content']} |",
        f"| Thiếu tóm tắt | {metrics['empty_summary']} |",
        f"| Thiếu cả nội dung lẫn tóm tắt | {metrics['neither_content_nor_summary']} |",
        f"| Chưa có ngày đăng | {metrics['missing_published_at']} |",
        f"| Ngày đăng chưa xác minh | {metrics['unverified_date']} |",
        f"| Tiêu đề có vẻ dựng từ slug | {metrics['slug_placeholder_title']} |",
        f"| Còn HTML entity chưa giải mã | {metrics['html_entities']} |",
        f"| Nội dung rất ngắn (<100 ký tự) | {metrics['very_short_content']} |", "",
        "## Theo nguồn", "", "| Source ID | Bài | Thiếu body | Thiếu summary | Thiếu cả hai | Chưa ngày | Ngày chưa xác minh | Tiêu đề tạm |", "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for sid, value in report["per_source"].items():
        md.append(f"| {sid} | {value.get('articles',0)} | {value.get('empty_content',0)} | {value.get('empty_summary',0)} | {value.get('neither_content_nor_summary',0)} | {value.get('missing_published_at',0)} | {value.get('unverified_date',0)} | {value.get('placeholder_title',0)} |")
    md += ["", "## Nghi vấn thông báo trùng giữa các nguồn", ""]
    if report["cross_source_title_duplicate_groups"]:
        for group in report["cross_source_title_duplicate_groups"][:100]:
            md.append(f"- **{group['records'][0]['title']}** — " + "; ".join(f"ID {r['id']} ({','.join(r['source_ids'])})" for r in group["records"]))
    else:
        md.append("Không có nhóm tiêu đề trùng giữa các nguồn.")
    md += ["", "## Cùng URL nhưng nhiều bản ghi article", ""]
    if report["canonical_url_multiple_article_groups"]:
        for group in report["canonical_url_multiple_article_groups"]:
            md.append(f"- `{group['url']}` — IDs " + ", ".join(str(r["id"]) for r in group["records"]))
    else:
        md.append("Không phát hiện URL nào đang gắn với nhiều ID bài viết.")
    md += ["", "Ghi chú: nhóm tiêu đề trùng chỉ là gợi ý rà soát; báo cáo không tự gộp các bài này.", ""]
    md_path.write_text("\n".join(md), encoding="utf-8")
    return json_path, md_path

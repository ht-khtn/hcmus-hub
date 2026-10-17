#!/usr/bin/env python3
"""Export HCMUS Hub articles currently matching the dashboard's 'Cần kiểm tra' filter.

Read-only: opens SQLite in read-only URI mode and writes CSV/JSON reports only.
Place this file in the project root (next to the data/ folder), then run:
    python .\\export_review.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

HTML_PREVIEW_CHARS = 1200


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    try:
        return [row[1] for row in con.execute(f"PRAGMA table_info({quote_ident(table)})")]
    except sqlite3.Error:
        return []


def first_existing(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    lower = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in lower:
            return lower[candidate.lower()]
    return None


def find_database(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Không thấy database: {path}")
        return path

    here = Path(__file__).resolve().parent
    cwd = Path.cwd()
    candidates = [
        here / "data" / "hcmus_hub.sqlite3",
        cwd / "data" / "hcmus_hub.sqlite3",
        here.parent / "data" / "hcmus_hub.sqlite3",
        here / "hcmus_hub.sqlite3",
        cwd / "hcmus_hub.sqlite3",
    ]
    seen: set[Path] = set()
    for path in candidates:
        path = path.resolve()
        if path not in seen and path.is_file():
            return path
        seen.add(path)

    raise FileNotFoundError(
        "Không tự tìm thấy data\\hcmus_hub.sqlite3. Hãy chạy script ở thư mục gốc v0.8 "
        "hoặc truyền đường dẫn: python .\\export_review.py --db .\\data\\hcmus_hub.sqlite3"
    )


def review_reasons(article: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    content_empty = (article.get("content") is None or article.get("content") == "")
    summary_empty = (article.get("summary") is None or article.get("summary") == "")
    html_empty = (article.get("content_html") is None or article.get("content_html") == "")
    attachments = article.get("attachments_json")
    attachments_empty = ("[]" if attachments is None else str(attachments)) in ("[]", "")

    if content_empty and summary_empty and html_empty and attachments_empty:
        reasons.append("Không có content, summary, content_html hoặc attachments")
    if article.get("published_at") is None:
        reasons.append("Thiếu ngày đăng")
    if str(article.get("published_at_source") or "").lower() in ("legacy_unverified", "unknown"):
        reasons.append("Ngày đăng chưa xác minh")

    title = str(article.get("title") or "")
    # SQLite LIKE is case-insensitive for ASCII, matching the dashboard predicate.
    if title.startswith("[CHƯA LẤY CHI TIẾT]"):
        reasons.append("Tiêu đề placeholder [CHƯA LẤY CHI TIẾT]")
    if title[:10].lower() == "thong bao ":
        reasons.append("Tiêu đề dạng 'Thong bao ...'")
    return reasons


def get_source_links(con: sqlite3.Connection, article_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = {int(i): [] for i in article_ids}
    if not article_ids:
        return result

    link_cols = table_columns(con, "article_sources")
    source_cols = table_columns(con, "sources")
    if not link_cols or "article_id" not in link_cols:
        return result

    source_fk = first_existing(link_cols, ("source_id",))
    name_col = first_existing(source_cols, ("name", "source_name", "label", "title"))
    source_url_col = first_existing(source_cols, ("base_url", "url", "source_url"))
    article_url_col = first_existing(link_cols, ("url", "article_url", "canonical_url", "source_url", "link", "original_url"))
    category_col = first_existing(link_cols, ("category",))

    # Use small ID batches so this also works with SQLite's usual parameter limit.
    for start in range(0, len(article_ids), 400):
        batch = [int(v) for v in article_ids[start:start + 400]]
        placeholders = ",".join("?" for _ in batch)
        select = [f"l.{quote_ident('article_id')} AS article_id"]
        select.append(f"l.{quote_ident(source_fk)} AS source_id" if source_fk else "NULL AS source_id")
        select.append(f"l.{quote_ident(article_url_col)} AS article_url" if article_url_col else "NULL AS article_url")
        select.append(f"l.{quote_ident(category_col)} AS category" if category_col else "NULL AS category")

        join = ""
        if source_fk and source_cols and "id" in source_cols:
            if name_col:
                select.append(f"s.{quote_ident(name_col)} AS source_name")
            else:
                select.append("NULL AS source_name")
            if source_url_col:
                select.append(f"s.{quote_ident(source_url_col)} AS source_base_url")
            else:
                select.append("NULL AS source_base_url")
            join = f" LEFT JOIN sources s ON s.{quote_ident('id')} = l.{quote_ident(source_fk)}"
        else:
            select.extend(["NULL AS source_name", "NULL AS source_base_url"])

        sql = f"SELECT {', '.join(select)} FROM article_sources l{join} WHERE l.{quote_ident('article_id')} IN ({placeholders}) ORDER BY l.{quote_ident('article_id')}"
        for row in con.execute(sql, batch):
            item = dict(row)
            result.setdefault(int(item["article_id"]), []).append(item)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Xuất danh sách bài HCMUS Hub đang được đánh dấu Cần kiểm tra.")
    parser.add_argument("--db", help="Đường dẫn database SQLite; mặc định tự tìm data\\hcmus_hub.sqlite3")
    parser.add_argument("--out-dir", help="Thư mục lưu báo cáo; mặc định là thư mục data cạnh database")
    args = parser.parse_args()

    try:
        db_path = find_database(args.db)
    except FileNotFoundError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2

    uri = db_path.as_uri() + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
        con.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        print(f"Không mở được database ở chế độ chỉ đọc: {exc}", file=sys.stderr)
        return 2

    try:
        article_cols = table_columns(con, "articles")
        required = {"id", "title", "content", "summary", "content_html", "attachments_json", "published_at", "published_at_source"}
        missing = required - set(article_cols)
        if missing:
            print("Database không có đủ cột cần thiết trong bảng articles: " + ", ".join(sorted(missing)), file=sys.stderr)
            print("Các cột hiện có: " + ", ".join(article_cols), file=sys.stderr)
            return 3

        sql = """SELECT a.* FROM articles a WHERE
            (((COALESCE(a.content,'')='')
              AND (COALESCE(a.summary,'')='')
              AND (COALESCE(a.content_html,'')='')
              AND COALESCE(a.attachments_json,'[]') IN ('[]',''))
             OR a.published_at IS NULL
             OR a.published_at_source IN ('legacy_unverified','unknown')
             OR a.title LIKE '[CHƯA LẤY CHI TIẾT]%'
             OR a.title LIKE 'Thong bao %')
            ORDER BY CASE WHEN a.published_at IS NULL
                           OR a.published_at_source IN ('legacy_unverified','unknown') THEN 1 ELSE 0 END,
                     a.published_at DESC, a.first_seen_at DESC"""
        try:
            raw_rows = [dict(row) for row in con.execute(sql)]
        except sqlite3.Error as exc:
            print(f"Lỗi khi đọc danh sách review: {exc}", file=sys.stderr)
            return 3

        ids = [int(row["id"]) for row in raw_rows]
        sources_by_id = get_source_links(con, ids)
        records: list[dict[str, Any]] = []
        for row in raw_rows:
            sources = sources_by_id.get(int(row["id"]), [])
            reasons = review_reasons(row)
            # SQLite LIKE's prefix predicates are replicated above for the normal title values.
            row["review_reasons"] = reasons
            row["sources"] = sources
            row["primary_url"] = next((s.get("article_url") for s in sources if s.get("article_url")), None)
            records.append(row)
    finally:
        con.close()

    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else db_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "can-kiem-tra.csv"
    json_path = out_dir / "can-kiem-tra.json"
    metadata_path = out_dir / "can-kiem-tra-summary.txt"

    # Keep CSV easy to open in Excel. Full article data (including full HTML) is in JSON.
    csv_rows: list[dict[str, Any]] = []
    for row in records:
        sources = row.get("sources", [])
        csv_row: dict[str, Any] = {}
        for key, value in row.items():
            if key == "sources":
                continue
            if key == "content_html":
                csv_row["content_html_preview"] = str(value or "")[:HTML_PREVIEW_CHARS]
                csv_row["content_html_length"] = len(str(value or ""))
            elif isinstance(value, (dict, list)):
                csv_row[key] = json.dumps(value, ensure_ascii=False)
            else:
                csv_row[key] = value
        csv_row["source_links"] = "\n".join(
            " | ".join(str(x) for x in [s.get("source_name"), s.get("category"), s.get("article_url")] if x)
            for s in sources
        )
        csv_rows.append(csv_row)

    fieldnames: list[str] = []
    for row in csv_rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(csv_rows)

    payload = {
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "database": str(db_path),
        "filter": "Same article-level predicates used by the v0.8 dashboard review filter",
        "count": len(records),
        "articles": records,
    }
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    reason_counts: dict[str, int] = {}
    for row in records:
        for reason in row["review_reasons"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    with metadata_path.open("w", encoding="utf-8") as f:
        f.write(f"Database: {db_path}\nTổng bài được đánh dấu Cần kiểm tra: {len(records)}\n\nTheo lý do (một bài có thể thuộc nhiều nhóm):\n")
        for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0])):
            f.write(f"- {reason}: {count}\n")

    print("Xuất xong danh sách Cần kiểm tra (database chỉ được đọc, không bị sửa).")
    print(f"Database : {db_path}")
    print(f"Số bài   : {len(records)}")
    print(f"CSV      : {csv_path}")
    print(f"JSON     : {json_path}")
    print(f"Tóm tắt  : {metadata_path}")
    print("Gửi tui file CSV trước; nếu cần kiểm tra sâu phần HTML/metadata, gửi thêm JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

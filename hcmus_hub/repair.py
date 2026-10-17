from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

HCMUS_STATIC_PATHS = {
    "/tong-quan-hoat-dong-nghien-cuu",
    "/ho-so-nang-luc-nghien-cuu",
}


def _is_hcmus_navigation_link(row: sqlite3.Row) -> bool:
    """Identify known HCMUS archive/static pages even if another HCMUS unit found them.

    The university and Training Office share hcmus.edu.vn. A navigation URL can
    therefore have relations under both source IDs (``hcmus`` and ``pdt``). The
    classification must follow the URL's domain/path, not the discovery label.
    """
    if str(row["source_id"] or "") not in {"hcmus", "pdt"}:
        return False
    parsed = urlparse(str(row["source_url"] or ""))
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if host != "hcmus.edu.vn":
        return False
    path = parsed.path.rstrip("/").casefold() or "/"
    return path.startswith("/category/") or path in HCMUS_STATIC_PATHS


def _is_html_supplement(category: str | None) -> bool:
    return "html bổ sung" in str(category or "").casefold()


def _source_link_priority(row: sqlite3.Row) -> tuple[int, int]:
    """Lower is better; prefer canonical feed links over supplemental HTML links."""
    category = str(row["category"] or "").casefold()
    if _is_html_supplement(category):
        return (3, int(row["id"]))
    if "(rss)" in category or category.endswith(" rss"):
        return (1, int(row["id"]))
    if "(feed)" in category or "feed" in category:
        return (1, int(row["id"]))
    return (0, int(row["id"]))


def _load_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """SELECT ars.id, ars.article_id, ars.source_id, ars.source_url, ars.category,
                  a.title, a.read_at, a.is_favorite,
                  (SELECT COUNT(*) FROM article_revisions rev WHERE rev.article_id=a.id) AS revision_count
           FROM article_sources ars JOIN articles a ON a.id=ars.article_id
           ORDER BY ars.source_id, ars.source_url, ars.id"""
    ).fetchall()


def build_repair_plan(conn: sqlite3.Connection) -> dict:
    """Build a non-destructive plan. Different real categories for the same URL are valid."""
    rows = _load_rows(conn)
    to_remove: set[int] = set()
    navigation_rows: set[int] = set()
    protected_nav_rows: set[int] = set()
    navigation_article_ids: set[int] = set()

    # First, remove known false-positive HCMUS archive/category/navigation links.
    for row in rows:
        if not _is_hcmus_navigation_link(row):
            continue
        # If the user interacted with the item, or it has revision history, leave
        # it untouched for manual review rather than risk losing user data.
        if row["is_favorite"] or row["read_at"] or int(row["revision_count"] or 0) > 0:
            protected_nav_rows.add(int(row["id"]))
            continue
        navigation_rows.add(int(row["id"]))
        navigation_article_ids.add(int(row["article_id"]))
        to_remove.add(int(row["id"]))

    # Inspect relations sharing the same source URL. Keep separate genuine category
    # memberships, but remove transport-only HTML supplement rows where a canonical
    # RSS/feed/non-supplement relation exists for the same article and URL.
    by_identity: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in rows:
        if int(row["id"]) in to_remove:
            continue
        by_identity.setdefault((str(row["source_id"]), str(row["source_url"])), []).append(row)

    unresolved: list[dict] = []
    retained_multi_category_groups: list[dict] = []
    for (source_id, source_url), group in by_identity.items():
        if len(group) < 2:
            continue
        # Don't alter any duplicate group containing a protected navigation link.
        if any(int(row["id"]) in protected_nav_rows for row in group):
            continue

        article_ids = {int(row["article_id"]) for row in group}
        if len(article_ids) > 1:
            unresolved.append({
                "source_id": source_id,
                "source_url": source_url,
                "article_ids": sorted(article_ids),
                "link_ids": [int(r["id"]) for r in group],
                "reason": "same source URL points to different article IDs",
            })
            continue

        non_supplement = [r for r in group if not _is_html_supplement(r["category"])]
        supplement = [r for r in group if _is_html_supplement(r["category"])]
        if non_supplement and supplement:
            for row in supplement:
                to_remove.add(int(row["id"]))
            group = non_supplement

        # Preserve distinct categories (e.g. a FIT article listed in both general
        # notices and scholarships). Remove only exact duplicate relationships.
        by_category: dict[str, list[sqlite3.Row]] = {}
        for row in group:
            key = str(row["category"] or "").strip().casefold()
            by_category.setdefault(key, []).append(row)
        for same_category_rows in by_category.values():
            if len(same_category_rows) <= 1:
                continue
            keep = sorted(same_category_rows, key=_source_link_priority)[0]
            for row in same_category_rows:
                if int(row["id"]) != int(keep["id"]):
                    to_remove.add(int(row["id"]))

        surviving_categories = sorted({str(r["category"] or "") for r in group if int(r["id"]) not in to_remove})
        if len(surviving_categories) > 1:
            retained_multi_category_groups.append({
                "source_id": source_id,
                "source_url": source_url,
                "article_id": next(iter(article_ids)),
                "categories": surviving_categories,
                "reason": "different categories retained intentionally",
            })

    # A false-positive navigation article is eligible for deletion only if all its
    # source links are removed, and it has not been read/favorited or revised.
    candidate_article_deletes: list[int] = []
    articles_retained_due_to_other_links: list[dict] = []
    protected_navigation_articles: list[dict] = []
    for article_id in sorted(navigation_article_ids):
        article_rows = [r for r in rows if int(r["article_id"]) == article_id]
        remaining = [r for r in article_rows if int(r["id"]) not in to_remove]
        sample = article_rows[0]
        user_protected = bool(sample["is_favorite"] or sample["read_at"] or int(sample["revision_count"] or 0) > 0)
        if user_protected:
            protected_navigation_articles.append({
                "article_id": article_id,
                "title": sample["title"],
                "is_favorite": bool(sample["is_favorite"]),
                "read_at": sample["read_at"],
                "revision_count": int(sample["revision_count"] or 0),
                "remaining_link_count": len(remaining),
                "reason": "retained to preserve user state or revision history",
            })
        elif not remaining:
            candidate_article_deletes.append(article_id)
        else:
            articles_retained_due_to_other_links.append({
                "article_id": article_id,
                "title": sample["title"],
                "remaining_links": [
                    {
                        "link_id": int(link["id"]),
                        "source_id": link["source_id"],
                        "source_url": link["source_url"],
                        "category": link["category"],
                    }
                    for link in remaining
                ],
                "reason": "retained because it still has source links not classified as navigation false positives",
            })

    # Count exact duplicate relationships, not distinct categories of one article.
    remaining_rows = [row for row in rows if int(row["id"]) not in to_remove]
    exact_groups: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
    url_groups: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in remaining_rows:
        exact_groups.setdefault((str(row["source_id"]), str(row["source_url"]), str(row["category"] or "").strip().casefold()), []).append(row)
        url_groups.setdefault((str(row["source_id"]), str(row["source_url"])), []).append(row)
    exact_duplicate_groups = sum(1 for group in exact_groups.values() if len(group) > 1)
    remaining_url_groups_multiple_rows = sum(1 for group in url_groups.values() if len(group) > 1)

    return {
        "links_total": len(rows),
        "links_to_remove": sorted(to_remove),
        "navigation_links_to_remove": sorted(navigation_rows),
        "protected_navigation_links": sorted(protected_nav_rows),
        "articles_to_delete": candidate_article_deletes,
        "articles_retained_due_to_other_links": articles_retained_due_to_other_links,
        "protected_navigation_articles": protected_navigation_articles,
        "exact_duplicate_groups_remaining_after_plan": exact_duplicate_groups,
        "source_url_groups_with_multiple_rows_after_plan": remaining_url_groups_multiple_rows,
        "unresolved_duplicate_groups": unresolved,
        "retained_multi_category_groups": retained_multi_category_groups,
        "removal_details": [
            {
                "link_id": int(row["id"]),
                "article_id": int(row["article_id"]),
                "source_id": row["source_id"],
                "source_url": row["source_url"],
                "category": row["category"],
                "title": row["title"],
                "reason": (
                    "navigation/archive URL mistakenly collected as a notice"
                    if int(row["id"]) in navigation_rows
                    else "supplemental or exact duplicate source relationship"
                ),
            }
            for row in rows if int(row["id"]) in to_remove
        ],
    }


def repair_links(db_path: str | Path, apply: bool = False) -> dict:
    """Dry-run by default; --apply backs up the SQLite file before changing it."""
    path = Path(db_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy CSDL: {path}")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        plan = build_repair_plan(conn)
        result = {"database": str(path), "mode": "apply" if apply else "dry_run", **plan}
        if not apply:
            result["message"] = "Dry-run: chưa thay đổi CSDL. Xem kế hoạch rồi mới dùng --apply."
            return result

        backup_path = path.with_name(
            f"{path.stem}.before-repair-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}{path.suffix}"
        )
        backup = sqlite3.connect(backup_path)
        try:
            conn.backup(backup)
        finally:
            backup.close()

        conn.execute("BEGIN IMMEDIATE")
        if plan["links_to_remove"]:
            conn.executemany("DELETE FROM article_sources WHERE id=?", [(i,) for i in plan["links_to_remove"]])

        deleted_articles: list[int] = []
        for article_id in plan["articles_to_delete"]:
            remaining = conn.execute(
                "SELECT COUNT(*) FROM article_sources WHERE article_id=?", (article_id,)
            ).fetchone()[0]
            if remaining == 0:
                cur = conn.execute(
                    """DELETE FROM articles
                       WHERE id=? AND read_at IS NULL AND is_favorite=0
                         AND NOT EXISTS (SELECT 1 FROM article_revisions r WHERE r.article_id=articles.id)""",
                    (article_id,),
                )
                if cur.rowcount == 1:
                    deleted_articles.append(article_id)

        remaining_exact = conn.execute(
            """SELECT COUNT(*) FROM (
                   SELECT source_id, source_url, category FROM article_sources
                   GROUP BY source_id, source_url, category HAVING COUNT(*) > 1
               )""").fetchone()[0]
        remaining_url_groups = conn.execute(
            """SELECT COUNT(*) FROM (
                   SELECT source_id, source_url FROM article_sources
                   GROUP BY source_id, source_url HAVING COUNT(*) > 1
               )""").fetchone()[0]
        conn.commit()
        result.update({
            "backup_path": str(backup_path),
            "links_removed": len(plan["links_to_remove"]),
            "articles_deleted": deleted_articles,
            "exact_duplicate_groups_remaining": int(remaining_exact),
            "source_url_groups_with_multiple_rows_remaining": int(remaining_url_groups),
            "message": "Đã áp dụng sửa chữa và tạo bản sao lưu. Các liên kết đa danh mục hợp lệ được giữ lại.",
        })
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

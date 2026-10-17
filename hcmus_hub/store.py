from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import Article, SourceConfig
from .textutils import article_fingerprint, clean_text, content_digest, normalize_title, utc_now_iso


def _is_html_supplement_category(value: str | None) -> bool:
    return "html bổ sung" in str(value or "").casefold()

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  owner TEXT NOT NULL,
  base_url TEXT NOT NULL,
  kind TEXT NOT NULL,
  last_checked_at TEXT,
  last_success_at TEXT,
  last_error TEXT
);
CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT NOT NULL,
  normalized_title TEXT NOT NULL,
  title TEXT NOT NULL,
  published_at TEXT,
  published_at_source TEXT,
  category TEXT NOT NULL DEFAULT 'Chưa phân loại',
  summary TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  content_html TEXT NOT NULL DEFAULT '',
  attachments_json TEXT NOT NULL DEFAULT '[]',
  content_hash TEXT NOT NULL DEFAULT '',
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  read_at TEXT,
  is_favorite INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_fingerprint ON articles(fingerprint);
CREATE INDEX IF NOT EXISTS idx_articles_title ON articles(normalized_title);
CREATE TABLE IF NOT EXISTS article_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES sources(id),
  source_url TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'Chưa phân loại',
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  last_detail_attempt_at TEXT,
  last_detail_status TEXT,
  last_detail_chars INTEGER NOT NULL DEFAULT 0,
  last_detail_error TEXT,
  UNIQUE(source_id, source_url, category)
);
CREATE INDEX IF NOT EXISTS idx_article_sources_article ON article_sources(article_id);
CREATE TABLE IF NOT EXISTS article_revisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  revised_at TEXT NOT NULL,
  title TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  summary TEXT NOT NULL,
  content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS data_metadata (
  key TEXT PRIMARY KEY,
  data_revision INTEGER NOT NULL DEFAULT 0
);
"""


class Store:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate_schema()
        self.conn.commit()

    def _migrate_schema(self):
        """Add publish-date provenance without requiring users to recreate their DB."""
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(articles)").fetchall()}
        if "published_at_source" not in columns:
            self.conn.execute("ALTER TABLE articles ADD COLUMN published_at_source TEXT")
        if "content_html" not in columns:
            self.conn.execute("ALTER TABLE articles ADD COLUMN content_html TEXT NOT NULL DEFAULT ''")
        # Older rows have no provenance, so explicitly label their dates as unverified
        # instead of silently presenting them as authoritative publication dates.
        self.conn.execute("UPDATE articles SET published_at_source='legacy_unverified' WHERE published_at IS NOT NULL AND (published_at_source IS NULL OR published_at_source='')")
        link_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(article_sources)").fetchall()}
        if "last_detail_attempt_at" not in link_columns:
            self.conn.execute("ALTER TABLE article_sources ADD COLUMN last_detail_attempt_at TEXT")
        if "last_detail_status" not in link_columns:
            self.conn.execute("ALTER TABLE article_sources ADD COLUMN last_detail_status TEXT")
        if "last_detail_chars" not in link_columns:
            self.conn.execute("ALTER TABLE article_sources ADD COLUMN last_detail_chars INTEGER NOT NULL DEFAULT 0")
        if "last_detail_error" not in link_columns:
            self.conn.execute("ALTER TABLE article_sources ADD COLUMN last_detail_error TEXT")
        self.conn.execute(
            "INSERT OR IGNORE INTO data_metadata(key, data_revision) VALUES('data_revision', 0)"
        )
        self.conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS trg_data_revision_article_insert
            AFTER INSERT ON articles
            BEGIN
              UPDATE data_metadata SET data_revision=data_revision+1 WHERE key='data_revision';
            END;
            CREATE TRIGGER IF NOT EXISTS trg_data_revision_article_delete
            AFTER DELETE ON articles
            BEGIN
              UPDATE data_metadata SET data_revision=data_revision+1 WHERE key='data_revision';
            END;
            CREATE TRIGGER IF NOT EXISTS trg_data_revision_article_update
            AFTER UPDATE OF fingerprint, normalized_title, title, published_at,
              published_at_source, category, summary, content, content_html,
              attachments_json, content_hash ON articles
            WHEN OLD.fingerprint IS NOT NEW.fingerprint
              OR OLD.normalized_title IS NOT NEW.normalized_title
              OR OLD.title IS NOT NEW.title
              OR OLD.published_at IS NOT NEW.published_at
              OR OLD.published_at_source IS NOT NEW.published_at_source
              OR OLD.category IS NOT NEW.category
              OR OLD.summary IS NOT NEW.summary
              OR OLD.content IS NOT NEW.content
              OR OLD.content_html IS NOT NEW.content_html
              OR OLD.attachments_json IS NOT NEW.attachments_json
              OR OLD.content_hash IS NOT NEW.content_hash
            BEGIN
              UPDATE data_metadata SET data_revision=data_revision+1 WHERE key='data_revision';
            END;
            CREATE TRIGGER IF NOT EXISTS trg_data_revision_source_insert
            AFTER INSERT ON article_sources
            BEGIN
              UPDATE data_metadata SET data_revision=data_revision+1 WHERE key='data_revision';
            END;
            CREATE TRIGGER IF NOT EXISTS trg_data_revision_source_delete
            AFTER DELETE ON article_sources
            BEGIN
              UPDATE data_metadata SET data_revision=data_revision+1 WHERE key='data_revision';
            END;
            CREATE TRIGGER IF NOT EXISTS trg_data_revision_source_update
            AFTER UPDATE OF article_id, source_id, source_url, category ON article_sources
            WHEN OLD.article_id IS NOT NEW.article_id
              OR OLD.source_id IS NOT NEW.source_id
              OR OLD.source_url IS NOT NEW.source_url
              OR OLD.category IS NOT NEW.category
            BEGIN
              UPDATE data_metadata SET data_revision=data_revision+1 WHERE key='data_revision';
            END;
        """)

    def close(self):
        self.conn.close()

    def register_source(self, source: SourceConfig):
        self.conn.execute("""INSERT INTO sources(id,name,owner,base_url,kind) VALUES(?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name, owner=excluded.owner, base_url=excluded.base_url, kind=excluded.kind""",
            (source.id, source.name, source.owner, source.base_url, source.kind))
        self.conn.commit()

    def source_check_started(self, source_id: str):
        self.conn.execute("UPDATE sources SET last_checked_at=?, last_error=NULL WHERE id=?", (utc_now_iso(), source_id))
        self.conn.commit()

    def source_check_finished(self, source_id: str, error: str | None = None):
        now = utc_now_iso()
        self.conn.execute("UPDATE sources SET last_checked_at=?, last_success_at=CASE WHEN ? IS NULL THEN ? ELSE last_success_at END, last_error=? WHERE id=?",
                          (now, error, now, error, source_id))
        self.conn.commit()

    def upsert_article(self, article: Article) -> str:
        """Returns new, updated, linked_duplicate, unchanged, or updated_content."""
        now = utc_now_iso()
        source_url = article.source_url
        existing_sources = self.conn.execute(
            "SELECT id, article_id, category FROM article_sources WHERE source_id=? AND source_url=? ORDER BY id",
            (article.source_id, source_url),
        ).fetchall()
        incoming_category = str(article.category or "Chưa phân loại")
        incoming_is_supplement = _is_html_supplement_category(incoming_category)
        fingerprint = article_fingerprint(article.title, article.published_at)
        normalized = normalize_title(article.title)
        digest = article.content_hash or content_digest(article.title, article.summary, article.content, article.attachments, article.content_html or None)

        existing_source = None
        if existing_sources:
            exact = next((r for r in existing_sources if str(r["category"] or "") == incoming_category), None)
            canonical = [r for r in existing_sources if not _is_html_supplement_category(r["category"])]
            supplements = [r for r in existing_sources if _is_html_supplement_category(r["category"])]

            if incoming_is_supplement and canonical:
                # A discovery-method label must not create a second relation when
                # the same URL already has a canonical category relation.
                existing_source = canonical[0]
            elif exact is not None:
                existing_source = exact
            elif not incoming_is_supplement and supplements and not canonical:
                # Upgrade the only placeholder/supplement relation to the first
                # real category that discovers this URL.
                existing_source = supplements[0]
                self.conn.execute(
                    "UPDATE article_sources SET category=? WHERE id=?",
                    (incoming_category, existing_source["id"]),
                )
                existing_source = self.conn.execute(
                    "SELECT id, article_id, category FROM article_sources WHERE id=?",
                    (existing_source["id"],),
                ).fetchone()
            elif not incoming_is_supplement and canonical:
                # The same real article may belong to multiple legitimate categories
                # on a site (e.g. FIT). Preserve that association instead of silently
                # dropping the second category.
                article_id_for_link = int(canonical[0]["article_id"])
                cursor = self.conn.execute(
                    "INSERT INTO article_sources(article_id,source_id,source_url,category,first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?)",
                    (article_id_for_link, article.source_id, source_url, incoming_category, now, now),
                )
                # A real category is now present, so stale transport-only labels can
                # be removed; the database's existing UNIQUE triple remains respected.
                for row in supplements:
                    self.conn.execute("DELETE FROM article_sources WHERE id=?", (row["id"],))
                existing_source = self.conn.execute(
                    "SELECT id, article_id, category FROM article_sources WHERE id=?",
                    (cursor.lastrowid,),
                ).fetchone()
            else:
                # Repeated discovery through multiple non-canonical routes should
                # reuse the existing relation instead of manufacturing another row.
                existing_source = existing_sources[0]

        if existing_source:
            article_id = int(existing_source["article_id"])
            current = self.conn.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
            changed = False
            if current:
                # Do not overwrite long detail with a thin listing-card excerpt.
                summary = article.summary if article.summary else current["summary"]
                content = article.content if len(article.content) >= len(current["content"]) else current["content"]
                current_html = current["content_html"] or ""
                content_html = article.content_html if len(article.content_html or "") >= len(current_html) else current_html
                # Sitemap entries only expose URLs (and optional lastmod), not the
                # canonical article title. Never replace a title read from the detail
                # page with a slug-derived placeholder on the next sync.
                if article.raw_metadata.get("title_is_placeholder"):
                    title = current["title"] or article.title
                else:
                    title = article.title or current["title"]
                # Publication dates carry provenance. Prefer an authoritative date from
                # this fetch; clear old/unverified dates for sitemap entries when no
                # publication date can be found; otherwise preserve the stored date.
                if article.published_at:
                    published_at = article.published_at
                    published_at_source = article.published_at_source or current["published_at_source"] or "unknown"
                elif (article.raw_metadata.get("clear_unverified_published_date")
                      or current["published_at_source"] in {"legacy_unverified", "unknown"}):
                    published_at = None
                    published_at_source = None
                else:
                    published_at = current["published_at"]
                    published_at_source = current["published_at_source"]
                attachments = article.attachments if article.attachments else json.loads(current["attachments_json"] or "[]")
                final_digest = content_digest(title, summary, content, attachments, content_html or None)
                # First-time HTML enrichment is a presentation backfill, not a content revision.
                # Compare the legacy text digest while the current row has no rich markup;
                # after rich HTML exists, include it in later change detection.
                legacy_digest = content_digest(title, summary, content, attachments)
                changed = (bool(current_html) and final_digest != current["content_hash"]) or (not current_html and bool(current["content"]) and legacy_digest != current["content_hash"])
                # An initial listing -> detail enrichment is not a historical revision.
                if changed:
                    self.conn.execute("""INSERT INTO article_revisions(article_id,revised_at,title,content_hash,summary,content)
                        VALUES(?,?,?,?,?,?)""", (article_id, now, current["title"], current["content_hash"], current["summary"], current["content"]))
                self.conn.execute("""UPDATE articles SET fingerprint=?, normalized_title=?, title=?, published_at=?, published_at_source=?, category=?, summary=?, content=?, content_html=?, attachments_json=?, content_hash=?, last_seen_at=? WHERE id=?""",
                                  (article_fingerprint(title, published_at), normalize_title(title), title, published_at, published_at_source,
                                   article.category or current["category"], summary, content, content_html, json.dumps(attachments, ensure_ascii=False), final_digest, now, article_id))
            self.conn.execute("UPDATE article_sources SET last_seen_at=? WHERE id=?",
                              (now, existing_source["id"]))
            self.conn.commit()
            return "updated_content" if changed else "unchanged"

        # Cross-site duplicate detection based on normalized title + publish date.
        duplicate = self.conn.execute("SELECT id FROM articles WHERE fingerprint=? ORDER BY id LIMIT 1", (fingerprint,)).fetchone()
        if duplicate:
            article_id = int(duplicate["id"])
            existing_article = self.conn.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
            # Prefer richer content, retain a sensible category if one was already stored.
            summary = article.summary if len(article.summary) > len(existing_article["summary"]) else existing_article["summary"]
            content = article.content if len(article.content) > len(existing_article["content"]) else existing_article["content"]
            attachments = sorted(set(json.loads(existing_article["attachments_json"] or "[]") + article.attachments))
            content_html = article.content_html if len(article.content_html or "") > len(existing_article["content_html"] or "") else (existing_article["content_html"] or "")
            digest = content_digest(existing_article["title"], summary, content, attachments, content_html or None)
            self.conn.execute("UPDATE articles SET summary=?, content=?, content_html=?, attachments_json=?, content_hash=?, last_seen_at=? WHERE id=?",
                              (summary, content, content_html, json.dumps(attachments, ensure_ascii=False), digest, now, article_id))
            self.conn.execute("INSERT INTO article_sources(article_id,source_id,source_url,category,first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?)",
                              (article_id, article.source_id, source_url, article.category, now, now))
            self.conn.commit()
            return "linked_duplicate"

        published_at_source = article.published_at_source or ("unknown" if article.published_at else None)
        cursor = self.conn.execute("""INSERT INTO articles(fingerprint,normalized_title,title,published_at,published_at_source,category,summary,content,content_html,attachments_json,content_hash,first_seen_at,last_seen_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (fingerprint, normalized, article.title, article.published_at, published_at_source, article.category or "Chưa phân loại",
             article.summary, article.content, article.content_html or "", json.dumps(article.attachments, ensure_ascii=False), digest, now, now))
        article_id = int(cursor.lastrowid)
        self.conn.execute("INSERT INTO article_sources(article_id,source_id,source_url,category,first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?)",
                          (article_id, article.source_id, source_url, article.category, now, now))
        self.conn.commit()
        return "new"

    def list_articles(self, limit: int = 30, unread_only: bool = False) -> list[dict]:
        where = "WHERE a.read_at IS NULL" if unread_only else ""
        rows = self.conn.execute(f"""SELECT a.*, GROUP_CONCAT(DISTINCT s.name) AS source_names,
            GROUP_CONCAT(DISTINCT ars.source_url) AS source_urls,
            GROUP_CONCAT(DISTINCT ars.category) AS source_categories,
            COUNT(DISTINCT ars.source_id) AS source_count
            FROM articles a JOIN article_sources ars ON ars.article_id=a.id
            JOIN sources s ON s.id=ars.source_id
            {where}
            GROUP BY a.id
            ORDER BY CASE WHEN a.published_at IS NULL THEN 1 ELSE 0 END, a.published_at DESC, a.first_seen_at DESC
            LIMIT ?""", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def export_articles(self) -> list[dict]:
        rows = self.conn.execute("""SELECT a.*, GROUP_CONCAT(DISTINCT s.name) AS source_names,
            GROUP_CONCAT(DISTINCT ars.source_url) AS source_urls,
            GROUP_CONCAT(DISTINCT ars.category) AS source_categories
            FROM articles a JOIN article_sources ars ON ars.article_id=a.id
            JOIN sources s ON s.id=ars.source_id
            GROUP BY a.id ORDER BY a.first_seen_at DESC""").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["attachments"] = json.loads(item.pop("attachments_json") or "[]")
            result.append(item)
        return result

    def mark_read(self, article_id: int, read: bool = True) -> bool:
        read_at = utc_now_iso() if read else None
        cur = self.conn.execute("UPDATE articles SET read_at=? WHERE id=?", (read_at, article_id))
        self.conn.commit()
        return cur.rowcount > 0

    def mark_favorite(self, article_id: int, favorite: bool = True) -> bool:
        cur = self.conn.execute("UPDATE articles SET is_favorite=? WHERE id=?", (int(favorite), article_id))
        self.conn.commit()
        return cur.rowcount > 0

    def record_detail_attempt(self, source_id: str, source_url: str, *, status: str,
                              chars: int = 0, error: str | None = None):
        """Record extraction quality separately from HTTP fetch success."""
        now = utc_now_iso()
        self.conn.execute(
            "UPDATE article_sources SET last_detail_attempt_at=?, last_detail_status=?, last_detail_chars=?, last_detail_error=? WHERE source_id=? AND source_url=?",
            (now, status, max(0, int(chars)), error, source_id, source_url),
        )
        self.conn.commit()

    def detail_history(self, source_id: str, source_url: str) -> dict | None:
        row = self.conn.execute(
            "SELECT last_detail_attempt_at,last_detail_status,last_detail_chars,last_detail_error FROM article_sources WHERE source_id=? AND source_url=? ORDER BY last_detail_attempt_at DESC LIMIT 1",
            (source_id, source_url),
        ).fetchone()
        return dict(row) if row else None

    def quality_candidate_rows(self, enabled_source_ids: list[str]) -> list[dict]:
        if not enabled_source_ids:
            return []
        marks = ",".join("?" for _ in enabled_source_ids)
        rows = self.conn.execute(f"""
            SELECT a.*, ars.id AS link_id, ars.source_id AS link_source_id,
                   ars.source_url AS link_source_url, ars.category AS link_category,
                   ars.last_detail_attempt_at, ars.last_detail_status, ars.last_detail_chars,
                   ars.last_detail_error, s.name AS link_source_name, s.base_url AS link_base_url
            FROM articles a
            JOIN article_sources ars ON ars.article_id=a.id
            JOIN sources s ON s.id=ars.source_id
            WHERE ars.source_id IN ({marks})
            ORDER BY a.id DESC, ars.id
        """, enabled_source_ids).fetchall()
        return [dict(row) for row in rows]

    def counts(self) -> dict[str, int]:
        articles = self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        unread = self.conn.execute("SELECT COUNT(*) FROM articles WHERE read_at IS NULL").fetchone()[0]
        sources = self.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        return {"articles": articles, "unread": unread, "sources": sources}

    def data_revision(self) -> int:
        row = self.conn.execute(
            "SELECT data_revision FROM data_metadata WHERE key='data_revision'"
        ).fetchone()
        return int(row[0]) if row else 0

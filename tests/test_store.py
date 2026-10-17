import tempfile
import unittest
import sqlite3
from pathlib import Path

from hcmus_hub.models import Article, ListingConfig, SourceConfig
from hcmus_hub.store import Store
from hcmus_hub.textutils import content_digest


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "test.sqlite3")
        self.source = SourceConfig("s", "Nguồn thử", "Đơn vị", "https://example.edu/", "announcements", True,
                                   [ListingConfig("https://example.edu/news", "Thông báo", [])])
        self.store.register_source(self.source)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def make_article(self, url, source_id="s", name="Nguồn thử", summary="Thông tin", date="2026-10-01"):
        item = Article("Thông báo lịch học kỳ mới", source_id, name, "Học vụ", url, date, summary, "", [])
        item.content_hash = content_digest(item.title, item.summary, item.content, item.attachments)
        return item

    def test_new_and_repeat_are_idempotent(self):
        a = self.make_article("https://example.edu/news/1")
        self.assertEqual(self.store.upsert_article(a), "new")
        revision = self.store.data_revision()
        self.assertEqual(self.store.upsert_article(a), "unchanged")
        self.assertEqual(self.store.counts()["articles"], 1)
        self.assertEqual(self.store.data_revision(), revision)

    def test_data_revision_changes_for_content_and_source_relationships(self):
        a = self.make_article("https://example.edu/news/1")
        before = self.store.data_revision()
        self.store.upsert_article(a)
        after_insert = self.store.data_revision()
        self.assertGreater(after_insert, before)

        changed = self.make_article("https://example.edu/news/1", summary="Nội dung mới")
        self.store.upsert_article(changed)
        self.assertGreater(self.store.data_revision(), after_insert)

        category = self.make_article("https://example.edu/news/1")
        category.category = "Hoạt động sinh viên"
        before_link = self.store.data_revision()
        self.store.upsert_article(category)
        self.assertGreater(self.store.data_revision(), before_link)

    def test_data_revision_ignores_personal_and_operational_metadata(self):
        a = self.make_article("https://example.edu/news/1")
        self.store.upsert_article(a)
        revision = self.store.data_revision()
        article_id = self.store.conn.execute("SELECT id FROM articles").fetchone()[0]
        self.store.conn.execute(
            "UPDATE articles SET read_at=?, is_favorite=1, last_seen_at=? WHERE id=?",
            ("2026-10-17T12:00:00+07:00", "2026-10-17T12:00:01+07:00", article_id),
        )
        self.store.conn.execute(
            """UPDATE article_sources SET last_seen_at=?, last_detail_attempt_at=?,
               last_detail_status=?, last_detail_chars=?, last_detail_error=?""",
            ("2026-10-17T12:00:02+07:00", "2026-10-17T12:00:03+07:00", "body_ok", 12, None),
        )
        self.store.conn.commit()
        self.assertEqual(self.store.data_revision(), revision)

    def test_data_revision_migration_preserves_existing_articles(self):
        path = Path(self.tmp.name) / "legacy.sqlite3"
        legacy = Store(path)
        legacy.register_source(self.source)
        article = self.make_article("https://example.edu/news/legacy")
        legacy.upsert_article(article)
        legacy.close()
        con = sqlite3.connect(path)
        con.execute("DROP TABLE data_metadata")
        con.commit()
        con.close()

        migrated = Store(path)
        try:
            self.assertEqual(migrated.counts()["articles"], 1)
            self.assertEqual(migrated.list_articles(limit=1)[0]["title"], article.title)
            self.assertEqual(migrated.data_revision(), 0)
        finally:
            migrated.close()

    def test_cross_source_duplicate_links_sources(self):
        self.store.register_source(SourceConfig("s2", "Nguồn hai", "Đơn vị 2", "https://other.edu/", "announcements", True, []))
        a = self.make_article("https://example.edu/news/1")
        b = self.make_article("https://other.edu/news/44", source_id="s2", name="Nguồn hai")
        self.assertEqual(self.store.upsert_article(a), "new")
        self.assertEqual(self.store.upsert_article(b), "linked_duplicate")
        self.assertEqual(self.store.counts()["articles"], 1)
        row = self.store.list_articles()[0]
        self.assertEqual(row["source_count"], 2)

    def test_export_includes_attachments_array(self):
        a = self.make_article("https://example.edu/news/1")
        a.attachments = ["https://example.edu/file.pdf"]
        a.content_hash = content_digest(a.title, a.summary, a.content, a.attachments)
        self.store.upsert_article(a)
        self.assertEqual(self.store.export_articles()[0]["attachments"], ["https://example.edu/file.pdf"])

    def test_detail_enrichment_is_not_saved_as_revision(self):
        a = self.make_article("https://example.edu/news/1", summary="Teaser")
        self.store.upsert_article(a)
        detail = self.make_article("https://example.edu/news/1", summary="Teaser", date="2026-10-01")
        detail.content = "Nội dung đầy đủ của bài thông báo. " * 20
        detail.content_hash = content_digest(detail.title, detail.summary, detail.content, detail.attachments)
        self.store.upsert_article(detail)
        count = self.store.conn.execute("SELECT COUNT(*) FROM article_revisions").fetchone()[0]
        self.assertEqual(count, 0)

    def test_real_content_change_creates_revision(self):
        a = self.make_article("https://example.edu/news/1")
        a.content = "Nội dung phiên bản đầu tiên. " * 20
        a.content_hash = content_digest(a.title, a.summary, a.content, a.attachments)
        self.store.upsert_article(a)
        changed = self.make_article("https://example.edu/news/1")
        changed.content = "Nội dung đã được gia hạn thời hạn đăng ký. " * 30
        changed.content_hash = content_digest(changed.title, changed.summary, changed.content, changed.attachments)
        self.assertEqual(self.store.upsert_article(changed), "updated_content")
        count = self.store.conn.execute("SELECT COUNT(*) FROM article_revisions").fetchone()[0]
        self.assertEqual(count, 1)

    def test_same_article_can_keep_two_categories_from_same_source(self):
        a = self.make_article("https://example.edu/news/1")
        self.assertEqual(self.store.upsert_article(a), "new")
        b = self.make_article("https://example.edu/news/1")
        b.category = "Hoạt động sinh viên"
        self.assertEqual(self.store.upsert_article(b), "unchanged")
        rows = self.store.conn.execute("SELECT COUNT(*) FROM article_sources WHERE source_id='s' AND source_url=?", (a.source_url,)).fetchone()[0]
        self.assertEqual(rows, 2)
        self.assertEqual(self.store.counts()["articles"], 1)


if __name__ == "__main__":
    unittest.main()

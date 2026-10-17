import tempfile
import unittest
from pathlib import Path

from hcmus_hub.models import Article, SourceConfig, ListingConfig
from hcmus_hub.quality import build_quality_report, normalize_database_text
from hcmus_hub.store import Store
from hcmus_hub.textutils import clean_text
from hcmus_hub.web_server import _api_article_detail, _api_articles, _api_stats, _api_version, _mark_all_unread_read


class QualityAndWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "hub.sqlite3"
        self.store = Store(self.db)
        self.source = SourceConfig(
            id="ctsv", name="CTSV", owner="HCMUS", base_url="https://ctsv.hcmus.edu.vn/",
            kind="announcements", enabled=True, listings=[ListingConfig(url="https://ctsv.hcmus.edu.vn/sitemap.xml", category="Học bổng")]
        )
        self.store.register_source(self.source)
        self.store.upsert_article(Article(
            title="Thông báo &ndash; học bổng", source_id="ctsv", source_name="CTSV",
            category="Học bổng", source_url="https://ctsv.hcmus.edu.vn/news/hoc-bong",
            published_at=None, summary="", content="", published_at_source=None,
        ))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_clean_text_decodes_entities(self):
        self.assertEqual(clean_text("Thông báo&nbsp;&ndash; sinh viên"), "Thông báo – sinh viên")

    def test_normalize_existing_sqlite_decodes_entities_without_deleting(self):
        report = normalize_database_text(self.db)
        self.assertEqual(report["articles_changed"], 1)
        rows = self.store.list_articles(limit=5)
        self.assertEqual(rows[0]["title"], "Thông báo – học bổng")
        self.assertEqual(self.store.counts()["articles"], 1)

    def test_quality_report_counts_missing_body_and_date(self):
        report = build_quality_report(self.db)
        self.assertEqual(report["metrics"]["articles"], 1)
        self.assertEqual(report["metrics"]["neither_content_nor_summary"], 1)
        self.assertEqual(report["metrics"]["missing_published_at"], 1)

    def test_dashboard_sanitizes_rich_html_before_returning_it(self):
        article_id = self.store.conn.execute("SELECT id FROM articles LIMIT 1").fetchone()[0]
        self.store.conn.execute("UPDATE articles SET content_html=? WHERE id=?", (
            '<p>Hướng dẫn</p><a href="https://ctsv.hcmus.edu.vn/form" onclick="alert(1)">Mở form</a>'
            '<table><tr><td>Hạn</td></tr></table><img src="https://ctsv.hcmus.edu.vn/a.jpg" onerror="alert(1)">'
            '<script>alert(1)</script><a href="javascript:alert(1)">x</a>', article_id))
        self.store.conn.execute("UPDATE articles SET attachments_json=? WHERE id=?", (
            '["javascript:alert(1)","https://ctsv.hcmus.edu.vn/manual.pdf"]', article_id))
        self.store.conn.execute("UPDATE article_sources SET source_url=? WHERE article_id=?", ("javascript:alert(1)", article_id))
        self.store.conn.commit()
        detail = _api_article_detail(self.db, article_id)
        self.assertIn("<table", detail["content_html"])
        self.assertIn("Mở form", detail["content_html"])
        self.assertNotIn("onclick", detail["content_html"])
        self.assertNotIn("onerror", detail["content_html"])
        self.assertNotIn("<script", detail["content_html"])
        self.assertNotIn("javascript:", detail["content_html"])
        self.assertTrue(detail["has_rich_payload"])
        self.assertEqual(detail["attachments"], ["https://ctsv.hcmus.edu.vn/manual.pdf"])
        self.assertEqual(detail["sources"][0]["source_url"], "")

    def test_link_only_rich_content_is_not_counted_as_missing_body(self):
        article_id = self.store.conn.execute("SELECT id FROM articles LIMIT 1").fetchone()[0]
        self.store.conn.execute("UPDATE articles SET content_html=? WHERE id=?", (
            '<p><a href="https://ctsv.hcmus.edu.vn/form">Mở biểu mẫu</a></p>', article_id))
        self.store.conn.commit()
        report = build_quality_report(self.db)
        self.assertEqual(report["metrics"]["neither_content_nor_summary"], 0)
        stats = _api_stats(self.db)
        self.assertEqual(stats["articles"], 1)
        # Still needs review for a missing publication date, not for bodylessness.
        self.assertEqual(stats["needs_review"], 1)

    def test_mark_all_unread_as_read_marks_only_unread(self):
        self.store.upsert_article(Article(
            title="Thông báo thứ hai", source_id="ctsv", source_name="CTSV", category="Tin",
            source_url="https://ctsv.hcmus.edu.vn/news/thu-hai", published_at="2026-10-16",
            summary="Nội dung", content="", published_at_source="rss_pubdate"))
        self.assertEqual(_mark_all_unread_read(self.db), 2)
        self.assertEqual(_mark_all_unread_read(self.db), 0)
        self.assertEqual(self.store.counts()["unread"], 0)

    def test_academic_year_filter_scopes_feed_stats_sources_and_bulk_read(self):
        self.store.upsert_article(Article(
            title="Thông báo năm học 2026-2027", source_id="ctsv", source_name="CTSV",
            category="Học vụ", source_url="https://ctsv.hcmus.edu.vn/news/2026-2027",
            published_at="2026-09-01", summary="Nội dung thông báo", content="Nội dung đầy đủ.",
            published_at_source="rss_pubdate",
        ))
        self.store.upsert_article(Article(
            title="Thông báo năm học 2025-2026", source_id="ctsv", source_name="CTSV",
            category="Học bổng", source_url="https://ctsv.hcmus.edu.vn/news/2025-2026",
            published_at="2026-08-31", summary="Nội dung thông báo", content="Nội dung đầy đủ.",
            published_at_source="rss_pubdate",
        ))

        params = {"academic_year": ["2026-2027"], "page": ["1"], "limit": ["30"], "mode": ["all"]}
        feed = _api_articles(self.db, params)
        self.assertEqual(feed["total"], 1)
        self.assertEqual(feed["items"][0]["title"], "Thông báo năm học 2026-2027")

        stats = _api_stats(self.db, "2026-2027")
        self.assertEqual(stats["articles"], 1)
        self.assertEqual(stats["unread"], 1)
        self.assertEqual(stats["favorites"], 0)
        ctsv = next(source for source in stats["sources"] if source["id"] == "ctsv")
        self.assertEqual(ctsv["articles"], 1)
        self.assertIn("2026-2027", stats["academic_years"])
        self.assertEqual(_api_stats(self.db)["articles"], 3)  # all-time includes unknown dates

        updated = _mark_all_unread_read(self.db, "2026-2027")
        self.assertEqual(updated, 1)
        # The older-year record and the undated original must remain unread.
        self.assertEqual(_api_stats(self.db)["unread"], 2)
        self.assertEqual(_api_stats(self.db, "2025-2026")["unread"], 1)

    def test_invalid_academic_year_is_rejected(self):
        with self.assertRaises(ValueError):
            _api_stats(self.db, "2026-2028")
        with self.assertRaises(ValueError):
            _api_articles(self.db, {"academic_year": ["2026/2027"]})

    def test_dashboard_api_lists_and_opens_article(self):
        payload = _api_articles(self.db, {"q": ["học bổng"], "page": ["1"], "limit": ["30"], "mode": ["all"]})
        self.assertEqual(payload["total"], 1)
        article_id = payload["items"][0]["id"]
        detail = _api_article_detail(self.db, article_id)
        self.assertEqual(detail["title"], "Thông báo &ndash; học bổng")
        self.assertEqual(detail["sources"][0]["source_id"], "ctsv")
        stats = _api_stats(self.db)
        self.assertEqual(stats["articles"], 1)
        self.assertEqual(stats["unread"], 1)

    def test_version_endpoint_returns_current_data_revision(self):
        revision = self.store.data_revision()
        self.assertEqual(_api_version(self.db), {"data_revision": revision})


if __name__ == "__main__":
    unittest.main()

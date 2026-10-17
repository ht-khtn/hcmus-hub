import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hcmus_hub.models import ListingConfig, SourceConfig
from hcmus_hub.store import Store
from hcmus_hub.sync import sync_source

ROOT = Path(__file__).resolve().parent


class FakeFetcher:
    warnings = []

    async def get(self, url, **kwargs):
        if "/beta/tin-tuc/c/" in url:
            body = (ROOT / "fixtures" / "fit_listing.html").read_text(encoding="utf-8")
        elif url.endswith("dang-ky-tham-quan-bosch"):
            body = (ROOT / "fixtures" / "fit_detail.html").read_text(encoding="utf-8")
        else:
            body = (ROOT / "fixtures" / "fit_detail.html").read_text(encoding="utf-8")
        return SimpleNamespace(url=url, status_code=200, content_type="text/html; charset=utf-8", text=body, headers={})


class SyncTests(unittest.TestCase):
    def test_sync_can_use_sitemap_as_listing(self):
        class SitemapFetcher:
            warnings = []

            async def get(self, url, **kwargs):
                if url.endswith("sitemap.xml"):
                    body = """<?xml version=\"1.0\"?><urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"><url><loc>https://ctsv.hcmus.edu.vn/news/thong-bao-moi</loc><lastmod>2026-10-14</lastmod></url></urlset>"""
                    ctype = "application/xml"
                else:
                    body = (ROOT / "fixtures" / "fit_detail.html").read_text(encoding="utf-8")
                    ctype = "text/html; charset=utf-8"
                return SimpleNamespace(url=url, status_code=200, content_type=ctype, text=body, headers={})

        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "hcmus.sqlite3")
            source = SourceConfig(
                id="ctsv", name="CTSV", owner="CTSV", base_url="https://ctsv.hcmus.edu.vn/",
                kind="announcements", enabled=True,
                listings=[ListingConfig(
                    "https://ctsv.hcmus.edu.vn/sitemap.xml", "Thông báo CTSV", [],
                    mode="sitemap", link_patterns=["/news/"]
                )],
                max_pages=1, max_details_per_sync=1,
            )
            try:
                report = asyncio.run(sync_source(source, SitemapFetcher(), store, max_details=0))
                self.assertEqual(report["articles_discovered"], 1)
                rows = store.list_articles(limit=10)
                self.assertEqual(rows[0]["source_urls"], "https://ctsv.hcmus.edu.vn/news/thong-bao-moi")
            finally:
                store.close()

    def test_sitemap_sync_does_not_replace_detail_title_with_slug(self):
        class SitemapAndDetailFetcher:
            warnings = []

            async def get(self, url, **kwargs):
                if url.endswith("sitemap.xml"):
                    body = """<?xml version=\"1.0\"?><urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"><url><loc>https://ctsv.hcmus.edu.vn/news/thong-bao-hoc-bong-moi</loc><lastmod>2026-10-14</lastmod></url></urlset>"""
                    ctype = "application/xml"
                else:
                    body = """<html><head><title>Thông báo học bổng mới</title></head><body><main><article><h1>Thông báo học bổng mới</h1><div class=\"entry-content\">Thông tin chính thức về chương trình học bổng dành cho sinh viên. Nội dung chi tiết gồm điều kiện đăng ký, hồ sơ cần chuẩn bị, thời gian nhận hồ sơ và cách nộp đơn trực tuyến.</div></article></main></body></html>"""
                    ctype = "text/html; charset=utf-8"
                return SimpleNamespace(url=url, status_code=200, content_type=ctype, text=body, headers={})

        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "hcmus.sqlite3")
            source = SourceConfig(
                id="ctsv", name="CTSV", owner="CTSV", base_url="https://ctsv.hcmus.edu.vn/",
                kind="announcements", enabled=True,
                listings=[ListingConfig("https://ctsv.hcmus.edu.vn/sitemap.xml", "Thông báo CTSV", [],
                                        mode="sitemap", link_patterns=["/news/"])],
                max_pages=1, max_details_per_sync=1,
            )
            try:
                first = asyncio.run(sync_source(source, SitemapAndDetailFetcher(), store, max_details=1))
                first_row = store.list_articles(limit=10)[0]
                self.assertEqual(first_row["title"], "Thông báo học bổng mới")
                self.assertEqual(first["articles_discovered"], 1)
                self.assertEqual(first["upsert_events"], 2)

                second = asyncio.run(sync_source(source, SitemapAndDetailFetcher(), store, max_details=1))
                second_row = store.list_articles(limit=10)[0]
                self.assertEqual(second_row["title"], "Thông báo học bổng mới")
                self.assertEqual(second["listing_outcomes"]["updated_content"], 0)
                self.assertEqual(second["detail_outcomes"]["updated_content"], 0)
                self.assertEqual(second["upsert_events"], 2)
            finally:
                store.close()

    def test_one_detail_parse_error_does_not_stop_the_source(self):
        class OneItemFetcher:
            warnings = []

            async def get(self, url, **kwargs):
                if url.endswith("sitemap.xml"):
                    body = """<?xml version=\"1.0\"?><urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://ctsv.hcmus.edu.vn/news/bad-page</loc></url><url><loc>https://ctsv.hcmus.edu.vn/news/good-page</loc></url></urlset>"""
                    ctype = "application/xml"
                else:
                    body = (ROOT / "fixtures" / "fit_detail.html").read_text(encoding="utf-8")
                    ctype = "text/html; charset=utf-8"
                return SimpleNamespace(url=url, status_code=200, content_type=ctype, text=body, headers={})

        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "hcmus.sqlite3")
            source = SourceConfig(
                id="ctsv", name="CTSV", owner="CTSV", base_url="https://ctsv.hcmus.edu.vn/",
                kind="announcements", enabled=True,
                listings=[ListingConfig("https://ctsv.hcmus.edu.vn/sitemap.xml", "Thông báo CTSV", [],
                                        mode="sitemap", link_patterns=["/news/"])],
                max_pages=1, max_details_per_sync=2,
            )
            real_parser = __import__("hcmus_hub.sync", fromlist=["parse_detail_html"]).parse_detail_html
            calls = {"count": 0}

            def parser(html, article):
                calls["count"] += 1
                if "bad-page" in article.source_url:
                    raise RuntimeError("fixture parser failure")
                return real_parser(html, article)

            try:
                with patch("hcmus_hub.sync.parse_detail_html", side_effect=parser):
                    report = asyncio.run(sync_source(source, OneItemFetcher(), store, max_details=2))
                self.assertEqual(report["articles_discovered"], 2)
                self.assertEqual(report["details_http_fetched"], 2)
                self.assertEqual(report["details_parse_errors"], 1)
                self.assertEqual(report["details_fetched"], 1)
                self.assertTrue(any("fixture parser failure" in item for item in report["errors"]))
                bad = store.conn.execute("SELECT last_detail_status,last_detail_error FROM article_sources WHERE source_url LIKE '%bad-page'").fetchone()
                self.assertEqual(bad["last_detail_status"], "parse_error")
                self.assertIn("fixture parser failure", bad["last_detail_error"])
            finally:
                store.close()

    def test_sync_listing_detail_and_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "hcmus.sqlite3")
            source = SourceConfig(
                id="fit", name="FIT", owner="FIT", base_url="https://www.fit.hcmus.edu.vn/",
                kind="announcements", enabled=True,
                listings=[ListingConfig(
                    "https://www.fit.hcmus.edu.vn/beta/tin-tuc/c/thong-bao-chung",
                    "Thông báo chung", ["a[href*='/beta/tin-tuc/d/']"]
                )],
                max_pages=1, max_details_per_sync=1,
            )
            try:
                report = asyncio.run(sync_source(source, FakeFetcher(), store, max_details=1))
                self.assertEqual(report["articles_discovered"], 2)
                self.assertEqual(report["details_fetched"], 1)
                self.assertEqual(store.counts()["articles"], 2)
                rows = store.list_articles(limit=10)
                detailed = next(row for row in rows if "Bosch" in row["title"])
                self.assertIn("Thời hạn đăng ký", detailed["content"])
                self.assertEqual(detailed["source_count"], 1)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()

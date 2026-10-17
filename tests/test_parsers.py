from pathlib import Path
import unittest

from hcmus_hub.parsers import parse_detail_html, parse_feed, parse_listing_html, parse_sitemap
from hcmus_hub.textutils import normalize_url, parse_date
from hcmus_hub.sync import next_page_url
from hcmus_hub.discovery import classify_response

ROOT = Path(__file__).resolve().parent


class ParserTests(unittest.TestCase):
    def test_fit_listing_extracts_articles_and_ignores_nav(self):
        html = (ROOT / "fixtures" / "fit_listing.html").read_text(encoding="utf-8")
        items = parse_listing_html(
            html,
            "https://www.fit.hcmus.edu.vn/beta/tin-tuc/c/thong-bao-chung",
            "fit", "FIT", "Thông báo chung",
            ["a[href*='/beta/tin-tuc/d/']"],
            ["/beta/tin-tuc/d/", "/tin-tuc/d/", "/news/"],
        )
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "Đăng ký tham quan công ty Bosch ngày 3/11")
        self.assertEqual(items[0].published_at, "2026-10-07")
        self.assertNotIn("Trang chủ", [item.title for item in items])

    def test_detail_extracts_content_and_pdf(self):
        html = (ROOT / "fixtures" / "fit_detail.html").read_text(encoding="utf-8")
        item = parse_listing_html(
            (ROOT / "fixtures" / "fit_listing.html").read_text(encoding="utf-8"),
            "https://www.fit.hcmus.edu.vn/beta/tin-tuc/c/thong-bao-chung", "fit", "FIT", "Thông báo",
            ["a[href*='/beta/tin-tuc/d/']"], ["/beta/tin-tuc/d/"],
        )[0]
        parse_detail_html(html, item)
        self.assertIn("Thời hạn đăng ký", item.content)
        self.assertIn("https://example.edu.vn/tailieu.pdf", item.attachments)
        self.assertEqual(item.published_at, "2026-10-07")

    def test_rss(self):
        feed = '''<?xml version="1.0"?><rss version="2.0"><channel><item><title>Thông báo lịch học mới</title><link>https://example.edu/news/123</link><pubDate>Wed, 07 Oct 2026 00:00:00 +0700</pubDate><description>Nội dung thông báo</description></item></channel></rss>'''
        items = parse_feed(feed, "https://example.edu/feed", "x", "X", "Thông báo")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_url, "https://example.edu/news/123")
        self.assertEqual(items[0].published_at, "2026-10-07")

    def test_sitemap_extracts_only_matching_same_host_news_urls_and_sorts_lastmod(self):
        sitemap = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://ctsv.hcmus.edu.vn/news/cu</loc><lastmod>2026-09-01</lastmod></url>
          <url><loc>https://ctsv.hcmus.edu.vn/news/moi-nhat</loc><lastmod>2026-10-14</lastmod></url>
          <url><loc>https://ctsv.hcmus.edu.vn/category/thong-bao</loc><lastmod>2026-10-15</lastmod></url>
          <url><loc>https://other.example/news/outside</loc><lastmod>2026-10-16</lastmod></url>
        </urlset>"""
        items = parse_sitemap(
            sitemap, "https://ctsv.hcmus.edu.vn/sitemap.xml",
            "ctsv", "CTSV", "Thông báo CTSV", ["/news/"]
        )
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].source_url, "https://ctsv.hcmus.edu.vn/news/moi-nhat")
        self.assertEqual(items[0].published_at, "2026-10-14")
        self.assertEqual(items[1].source_url, "https://ctsv.hcmus.edu.vn/news/cu")

    def test_sitemap_index_does_not_treat_child_sitemaps_as_articles(self):
        sitemap_index = """<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://example.edu/posts.xml</loc></sitemap></sitemapindex>"""
        items = parse_sitemap(sitemap_index, "https://example.edu/sitemap.xml", "x", "X", "Tin", ["/news/"])
        self.assertEqual(items, [])

    def test_date_formats(self):
        self.assertEqual(parse_date("07/10/2026"), "2026-10-07")
        self.assertEqual(parse_date("2026-10-07T09:00:00+07:00"), "2026-10-07")
        self.assertEqual(parse_date("15 Th1", reference_year=2026), "2026-01-15")

    def test_url_normalization(self):
        self.assertEqual(normalize_url("HTTPS://Example.COM/news/a/?utm_source=x#top"), "https://example.com/news/a")

    def test_next_page_url_fit(self):
        url = next_page_url("<a href='?p=2'>2</a>", "https://www.fit.hcmus.edu.vn/beta/tin-tuc/c/thong-bao-chung", 1)
        self.assertEqual(url, "https://www.fit.hcmus.edu.vn/beta/tin-tuc/c/thong-bao-chung?p=2")

    def test_audit_classifies_rss_and_wordpress_json(self):
        kind, _ = classify_response("https://example.edu/feed", 200, "application/rss+xml", "<rss version='2.0'><channel/></rss>")
        self.assertEqual(kind, "feed")
        kind, _ = classify_response("https://example.edu/wp-json/wp/v2/posts", 200, "application/json", '[{"id": 1, "title": {"rendered": "Tin mới"}, "link": "https://example.edu/tin-moi"}]')
        self.assertEqual(kind, "json_api")

    def test_audit_classifies_http_404(self):
        kind, note = classify_response("https://example.edu/feed", 404, "text/html", "not found")
        self.assertEqual(kind, "not_found")
        self.assertIn("404", note)


if __name__ == "__main__":
    unittest.main()

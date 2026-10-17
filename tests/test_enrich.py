import asyncio
import unittest
from types import SimpleNamespace

from hcmus_hub.enrich import enrich_weak_articles
from hcmus_hub.models import SourceConfig


class FakeStore:
    def __init__(self, count=3):
        self.rows = [
            {
                "id": i,
                "link_source_id": "demo",
                "link_source_url": f"https://example.edu/news/{i}",
                "link_category": "Thông báo",
                "category": "Thông báo",
                "title": f"Thông báo số {i}",
                "summary": "",
                "content": "",
                "content_html": "",
                "published_at": None,
                "published_at_source": "unknown",
                "attachments_json": "[]",
                "content_hash": "",
                "last_detail_attempt_at": None,
            }
            for i in range(1, count + 1)
        ]
        self.saved = 0
        self.attempts = 0

    def quality_candidate_rows(self, source_ids):
        return list(self.rows)

    def upsert_article(self, article):
        self.saved += 1

    def record_detail_attempt(self, *args, **kwargs):
        self.attempts += 1


class FakeFetcher:
    warnings = []

    def __init__(self):
        self.requests = 0

    async def get(self, url):
        self.requests += 1
        text = (
            "<html><body><main><article><h1>Thông báo</h1>"
            "<div class='entry-content'>Nội dung thông báo chính thức, thông tin chi tiết "
            "về điều kiện, thời hạn, hồ sơ và cách thức thực hiện dành cho sinh viên.</div>"
            "</article></main></body></html>"
        )
        return SimpleNamespace(url=url, text=text, headers={}, status_code=200, content_type="text/html")


class EnrichmentLimitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.source = SourceConfig(
            id="demo", name="Nguồn thử nghiệm", owner="Đơn vị thử nghiệm",
            base_url="https://example.edu/", kind="announcements", enabled=True, listings=[]
        )

    async def test_none_limit_processes_all_candidate_articles(self):
        store = FakeStore(count=7)
        fetcher = FakeFetcher()
        report = await enrich_weak_articles([self.source], fetcher, store, limit=None)
        self.assertEqual(report["candidate_records"], 7)
        self.assertEqual(report["limit"], "all")
        self.assertEqual(report["details_attempted"], 7)
        self.assertEqual(fetcher.requests, 7)

    async def test_numeric_limit_is_still_respected(self):
        store = FakeStore(count=7)
        fetcher = FakeFetcher()
        report = await enrich_weak_articles([self.source], fetcher, store, limit=2)
        self.assertEqual(report["candidate_records"], 7)
        self.assertEqual(report["limit"], 2)
        self.assertEqual(report["details_attempted"], 2)
        self.assertEqual(fetcher.requests, 2)


if __name__ == "__main__":
    unittest.main()

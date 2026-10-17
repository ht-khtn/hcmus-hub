from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from .fetcher import FetchError, PoliteFetcher

COMMON_CANDIDATES = [
    ("robots", "/robots.txt"),
    ("sitemap", "/sitemap.xml"),
    ("sitemap_index", "/sitemap_index.xml"),
    ("wordpress_sitemap", "/wp-sitemap.xml"),
    ("rss_feed", "/feed/"),
    ("rss_feed", "/news/feed/"),
    ("rss_feed", "/feed"),
    ("rss_feed", "/rss.xml"),
    ("atom_feed", "/atom.xml"),
    ("wordpress_api", "/wp-json/wp/v2/posts?per_page=1"),
]


def classify_response(url: str, status: int, content_type: str, body: str) -> tuple[str, str]:
    if status in (401, 403):
        return "blocked_or_auth_required", f"HTTP {status}; không thử vượt cơ chế chặn/xác thực."
    if status == 404:
        return "not_found", "HTTP 404."
    if status >= 400:
        return "http_error", f"HTTP {status}."
    stripped = body.lstrip()
    if "json" in content_type or stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(body)
            if isinstance(data, list) and (not data or any(isinstance(row, dict) and ("title" in row or "link" in row) for row in data)):
                return "json_api", f"JSON có cấu trúc danh sách, {len(data)} phần tử ở phản hồi thử nghiệm."
            if isinstance(data, dict) and ("routes" in data or "namespaces" in data):
                return "api_index", "Phản hồi giống chỉ mục API; cần tìm endpoint dữ liệu bài viết."
            return "json", "Trả JSON nhưng chưa nhận diện được schema bài viết."
        except json.JSONDecodeError:
            return "invalid_json", "Header/đầu phản hồi giống JSON nhưng parse không thành công."
    if "xml" in content_type or stripped.startswith("<?xml") or re.match(r"^<(rss|feed|urlset|sitemapindex)\b", stripped, re.I):
        try:
            root = ET.fromstring(body)
            tag = root.tag.lower().split("}")[-1]
            if tag in {"rss", "feed", "rdf"}:
                item_count = len(root.findall(".//item")) + len(root.findall(".//{http://www.w3.org/2005/Atom}entry"))
                return "feed", f"XML hợp lệ, root={tag}; khoảng {item_count} mục feed."
            if tag == "urlset":
                locations = [node.text.strip() for node in root.iter() if node.tag.lower().split("}")[-1] == "loc" and node.text and node.text.strip()]
                examples = "; ".join(locations[:3])
                note = f"XML hợp lệ, root=urlset; {len(locations)} URL."
                if examples:
                    note += f" Ví dụ: {examples}"
                return "sitemap", note
            if tag == "sitemapindex":
                locations = [node.text.strip() for node in root.iter() if node.tag.lower().split("}")[-1] == "loc" and node.text and node.text.strip()]
                examples = "; ".join(locations[:3])
                note = f"XML hợp lệ, root=sitemapindex; {len(locations)} sitemap con."
                if examples:
                    note += f" Ví dụ: {examples}"
                return "sitemap", note
            return "xml", f"XML hợp lệ, root={tag}."
        except ET.ParseError:
            return "invalid_xml", "Phản hồi XML không parse được."
    if "html" in content_type or "<html" in stripped[:1000].lower() or "<!doctype html" in stripped[:1000].lower():
        soup = BeautifulSoup(body, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        anchors = len(soup.find_all("a", href=True))
        feeds = []
        for link in soup.find_all("link", href=True):
            typ = str(link.get("type", "")).lower()
            rel = " ".join(link.get("rel", [])).lower() if isinstance(link.get("rel"), list) else str(link.get("rel", "")).lower()
            if "alternate" in rel and ("rss" in typ or "atom" in typ or "xml" in typ):
                feeds.append(urljoin(url, str(link["href"])))
        hint = f"HTML; title={title[:100]!r}; {anchors} liên kết." 
        if feeds:
            hint += " Feed khai báo: " + ", ".join(feeds[:5])
        return "html", hint
    return "other", f"Content-Type={content_type or '(không rõ)'}."


async def audit_source(source, fetcher: PoliteFetcher) -> dict:
    base = source.base_url.rstrip("/")
    origin = f"{urlparse(source.base_url).scheme}://{urlparse(source.base_url).netloc}"
    tested: list[dict] = []
    seen: set[str] = set()
    # Cache robots rules once per origin for all tested endpoints.
    await fetcher._get_robots(source.base_url)

    urls: list[tuple[str, str]] = [(name, urljoin(origin + "/", path.lstrip("/"))) for name, path in COMMON_CANDIDATES]
    urls.extend(("listing", listing.url) for listing in source.listings)
    cursor = 0
    while cursor < len(urls):
        label, url = urls[cursor]
        cursor += 1
        if url in seen:
            continue
        seen.add(url)
        try:
            # The audit must be able to read robots.txt itself, without recursively checking robots.
            result = await fetcher.get(url, check_robots=(label != "robots"), allow_http_errors=True)
            classification, note = classify_response(result.url, result.status_code, result.content_type, result.text)
            if label == "robots" and result.status_code == 200:
                lines = result.text.splitlines()
                sitemap_urls = [line.split(":", 1)[1].strip() for line in lines if line.lower().startswith("sitemap:") and ":" in line]
                disallow_rules = sum(1 for line in lines if line.strip().lower().startswith("disallow:"))
                classification = "robots_txt"
                note = f"robots.txt đọc được; {disallow_rules} dòng Disallow; {len(sitemap_urls)} Sitemap được khai báo."
                for sitemap_url in sitemap_urls:
                    urls.append(("sitemap_from_robots", sitemap_url))
            if label == "listing" and classification == "html":
                soup = BeautifulSoup(result.text, "html.parser")
                for link in soup.find_all("link", href=True):
                    rel = link.get("rel", [])
                    rel_text = " ".join(rel).lower() if isinstance(rel, list) else str(rel).lower()
                    typ = str(link.get("type", "")).lower()
                    if "alternate" in rel_text and any(word in typ for word in ("rss", "atom", "xml")):
                        feed_url = urljoin(result.url, str(link["href"]))
                        if feed_url not in seen:
                            urls.append(("alternate_feed", feed_url))
            tested.append({"label": label, "url": url, "final_url": result.url, "status": result.status_code,
                           "content_type": result.content_type, "bytes": len(result.text.encode("utf-8", errors="replace")),
                           "classification": classification, "note": note})
        except FetchError as exc:
            tested.append({"label": label, "url": url, "status": None, "classification": "fetch_error", "note": str(exc)})

    good_feeds = [row for row in tested if row["classification"] == "feed"]
    good_api = [row for row in tested if row["classification"] in {"json_api", "api_index"}]
    good_html = [row for row in tested if row["label"] == "listing" and row["classification"] == "html"]
    if good_feeds:
        recommendation = "rss_atom"
    elif good_api:
        recommendation = "api_json_review_schema"
    elif good_html:
        recommendation = "html_parser"
    else:
        recommendation = "manual_review_or_browser"
    return {
        "source_id": source.id,
        "source_name": source.name,
        "base_url": source.base_url,
        "tested_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        "recommendation": recommendation,
        "results": tested,
        "warnings": list(fetcher.warnings),
        "note": "Audit chỉ kiểm tra các endpoint phổ biến và URL danh mục đã cấu hình; không chứng minh rằng mọi endpoint có thể tìm thấy đã được liệt kê.",
    }

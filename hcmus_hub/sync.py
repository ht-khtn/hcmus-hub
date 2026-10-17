from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, urljoin
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from .fetcher import FetchError, PoliteFetcher
from .models import Article, ListingConfig, SourceConfig
from .parsers import parse_detail_html, parse_feed, parse_listing_html, parse_sitemap
from .store import Store
from .textutils import normalize_url


def next_page_url(html: str, current_url: str, page_number: int) -> str | None:
    """Find an explicit next-page link. Avoid guessing URLs on unknown CMSs."""
    soup = BeautifulSoup(html, "html.parser")
    next_node = soup.find("a", rel=lambda value: value and ("next" in value if isinstance(value, list) else "next" in str(value).lower()))
    if next_node and next_node.get("href"):
        return normalize_url(urljoin(current_url, str(next_node["href"])))
    for anchor in soup.find_all("a", href=True):
        label = " ".join(anchor.get("rel", [])) if isinstance(anchor.get("rel"), list) else str(anchor.get("rel", ""))
        text = (anchor.get_text(" ", strip=True) + " " + label).strip().lower()
        if re.search(r"^(next|older|sau|tiếp|trang sau|›|»|→)$", text):
            return normalize_url(urljoin(current_url, str(anchor["href"])))
    # A few known paging conventions. For FIT's custom listing, page 1 is the base URL;
    # older pages are query parameters p=2, p=3, ... .
    parsed = urlsplit(current_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "p" in query and query["p"].isdigit():
        query["p"] = str(int(query["p"]) + 1)
        return normalize_url(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), "")))
    if "/beta/tin-tuc/c/" in parsed.path or "/tin-tuc/c/" in parsed.path:
        query["p"] = str(max(2, page_number + 1))
        return normalize_url(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), "")))
    # WordPress convention, only for category/archive paths known to be WordPress-like.
    if "/danh-muc/" in parsed.path:
        path = parsed.path.rstrip("/") + f"/page/{page_number + 1}/"
        return normalize_url(urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, "")))
    return None


def _xml_root_tag(result) -> str | None:
    body = result.text.lstrip()
    if "xml" not in result.content_type.lower() and not body.startswith("<?xml") and not body.startswith("<rss") and not body.startswith("<feed") and not body.startswith("<urlset") and not body.startswith("<sitemapindex"):
        return None
    try:
        root = ET.fromstring(result.text)
        return root.tag.lower().split("}")[-1]
    except ET.ParseError:
        return None


def _looks_like_feed(result) -> bool:
    return _xml_root_tag(result) in {"rss", "feed", "rdf"}


def _looks_like_sitemap(result) -> bool:
    return _xml_root_tag(result) == "urlset"


async def sync_source(source: SourceConfig, fetcher: PoliteFetcher, store: Store,
                      max_details: int | None = None, max_items_per_listing: int = 30) -> dict:
    store.register_source(source)
    store.source_check_started(source.id)
    seen_urls: set[str] = set()
    discovered: list[Article] = []
    listing_errors: list[str] = []
    successful_listings = 0
    try:
        for listing in source.listings:
            url = listing.url
            visited_pages: set[str] = set()
            for page_no in range(1, max(1, source.max_pages) + 1):
                if url in visited_pages:
                    break
                visited_pages.add(url)
                try:
                    response = await fetcher.get(url)
                except FetchError as exc:
                    listing_errors.append(f"{url}: {exc}")
                    break
                successful_listings += 1
                mode = (listing.mode or "auto").lower()
                if mode == "sitemap" or (mode == "auto" and _looks_like_sitemap(response)):
                    page_articles = parse_sitemap(
                        response.text, response.url, source.id, source.name,
                        listing.category, listing.link_patterns or None,
                    )
                elif mode == "feed" or (mode == "auto" and _looks_like_feed(response)):
                    page_articles = parse_feed(response.text, response.url, source.id, source.name, listing.category)
                else:
                    page_articles = parse_listing_html(
                        response.text, response.url, source.id, source.name,
                        listing.category, listing.selectors,
                        link_patterns=["/beta/tin-tuc/d/", "/tin-tuc/d/", "/news/"],
                    )
                for article in page_articles:
                    if article.source_url not in seen_urls:
                        discovered.append(article)
                        seen_urls.add(article.source_url)
                    if len([a for a in discovered if a.category == listing.category]) >= max_items_per_listing:
                        break
                if page_no >= source.max_pages:
                    break
                more = None if mode in {"feed", "sitemap"} or _looks_like_feed(response) or _looks_like_sitemap(response) else next_page_url(response.text, response.url, page_no)
                if not more or more in visited_pages:
                    break
                url = more
        # Persist list-level metadata first. This means a detail failure still keeps the notification title/URL.
        outcome_keys = ("new", "updated_content", "linked_duplicate", "unchanged")
        listing_outcomes: dict[str, int] = {key: 0 for key in outcome_keys}
        detail_outcomes: dict[str, int] = {key: 0 for key in outcome_keys}
        for article in discovered:
            listing_outcomes[store.upsert_article(article)] += 1

        details_limit = source.max_details_per_sync if max_details is None else max_details
        detail_count = 0
        detail_title_extracted = 0
        detail_date_extracted = 0
        detail_body_extracted = 0
        detail_body_chars = 0
        detail_empty_body = 0
        detail_http_fetched = 0
        detail_fetch_errors = 0
        detail_parse_errors = 0
        detail_body_selectors: dict[str, int] = {}
        detail_errors: list[str] = []
        # Refresh a small number of detail pages on each run. HTTP success and content extraction
        # success are reported independently; weak historical records are handled by enrich.py.
        # it can detect deadline/content edits without redownloading the full historical archive.
        details_attempted = 0
        source_host = urlsplit(source.base_url).netloc.lower()
        for article in discovered:
            if details_attempted >= max(0, details_limit):
                break
            # Do not crawl arbitrary third-party pages linked from a feed/listing.
            if urlsplit(article.source_url).netloc.lower() != source_host:
                continue
            details_attempted += 1
            try:
                detail_response = await fetcher.get(article.source_url)
                detail_http_fetched += 1
                enriched = parse_detail_html(detail_response.text, article)
                detail_outcomes[store.upsert_article(enriched)] += 1
                detail_count += 1
                if enriched.raw_metadata.get("detail_title_extracted"):
                    detail_title_extracted += 1
                if enriched.raw_metadata.get("detail_date_extracted"):
                    detail_date_extracted += 1
                chars = int(enriched.raw_metadata.get("detail_body_chars") or 0)
                detail_body_chars += chars
                selector = str(enriched.raw_metadata.get("detail_body_selector") or "")
                if selector:
                    detail_body_selectors[selector] = detail_body_selectors.get(selector, 0) + 1
                if enriched.raw_metadata.get("detail_body_extracted"):
                    detail_body_extracted += 1
                    status = "body_ok"
                else:
                    detail_empty_body += 1
                    status = "fetched_no_body"
                error = None if status == "body_ok" else (
                    "HTTP tải trang thành công nhưng không tìm được vùng nội dung đủ điều kiện; "
                    f"selector={selector or 'none'}, text_chars={chars}, "
                    f"html_chars={enriched.raw_metadata.get('detail_body_html_chars') or 0}. "
                    "Có thể trang đổi cấu trúc hoặc nội dung được dựng bằng JavaScript."
                )
                store.record_detail_attempt(source.id, article.source_url, status=status, chars=chars, error=error)
            except FetchError as exc:
                detail_fetch_errors += 1
                message = f"{article.source_url}: {exc}"
                detail_errors.append(message)
                store.record_detail_attempt(source.id, article.source_url, status="fetch_error", error=str(exc))
            except Exception as exc:
                # A malformed page or parser/database error for one detail page should
                # not stop extraction of the remaining articles from this source.
                detail_parse_errors += 1
                message = f"{article.source_url}: {type(exc).__name__}: {exc}"
                detail_errors.append(message)
                store.record_detail_attempt(source.id, article.source_url, status="parse_error", error=message)

        all_errors = listing_errors + detail_errors
        if successful_listings and not discovered:
            all_errors.append("Đọc được trang danh mục nhưng không trích xuất được bài nào; cần kiểm tra selector/JavaScript và báo cáo audit.")
        store.source_check_finished(source.id, "; ".join(all_errors[:3]) if all_errors else None)
        outcomes = {key: listing_outcomes[key] + detail_outcomes[key] for key in outcome_keys}
        return {
            "source_id": source.id,
            "source_name": source.name,
            "listings_succeeded": successful_listings,
            "articles_discovered": len(discovered),
            "details_attempted": details_attempted,
            "details_fetched": detail_count,
            "details_http_fetched": detail_http_fetched,
            "details_fetch_errors": detail_fetch_errors,
            "details_parse_errors": detail_parse_errors,
            "details_body_selectors": detail_body_selectors,
            "details_title_extracted": detail_title_extracted,
            "details_date_extracted": detail_date_extracted,
            "details_body_extracted": detail_body_extracted,
            "details_empty_body_after_fetch": detail_empty_body,
            "details_body_chars_extracted": detail_body_chars,
            # Outcomes count database upsert events, not unique discovered URLs.
            # Listing persistence and detail enrichment are now shown separately.
            "upsert_events": len(discovered) + detail_count,
            "listing_outcomes": listing_outcomes,
            "detail_outcomes": detail_outcomes,
            "outcomes": outcomes,
            "errors": all_errors,
            "warnings": list(fetcher.warnings),
        }
    except Exception as exc:
        store.source_check_finished(source.id, str(exc))
        raise

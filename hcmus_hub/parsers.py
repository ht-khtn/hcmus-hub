from __future__ import annotations

import json
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup, Tag

from .models import Article
from .safehtml import sanitize_rich_html, rich_html_has_payload
from .textutils import clean_text, content_digest, normalize_url, parse_date

ATTACHMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar", ".png", ".jpg", ".jpeg")
NAV_WORDS = {"trang chủ", "home", "liên hệ", "contact", "đăng nhập", "login", "tìm kiếm", "search", "xem thêm", "read more", "1", "2", "3", "4", "5", "→", "←"}
EXCLUDED_PATH_BITS = ("/wp-login", "/wp-admin", "/tag/", "/author/", "/login", "/lien-he", "/contact", "/search", "/page/", "/danh-muc/", "/category/")


def _is_valid_title(title: str) -> bool:
    folded = clean_text(title).casefold()
    return len(folded) >= 9 and folded not in NAV_WORDS and len(folded.split()) >= 2


def _article_link_is_plausible(href: str, listing_url: str, allowed_patterns: list[str] | None = None) -> bool:
    full = normalize_url(urljoin(listing_url, href))
    candidate = urlparse(full)
    listing = urlparse(listing_url)
    if candidate.scheme not in {"http", "https"} or candidate.netloc != listing.netloc:
        return False
    if candidate.path.rstrip("/") == listing.path.rstrip("/"):
        return False
    path_lower = candidate.path.lower()
    candidate_host = (candidate.hostname or "").casefold().removeprefix("www.")
    # Known HCMUS static research pages are useful reference pages, not notices.
    if candidate_host == "hcmus.edu.vn" and path_lower.rstrip("/") in {
        "/tong-quan-hoat-dong-nghien-cuu",
        "/ho-so-nang-luc-nghien-cuu",
    }:
        return False
    if any(bit in path_lower for bit in EXCLUDED_PATH_BITS):
        # Categories can link to articles, but not article-like links themselves.
        if not any(pattern in path_lower for pattern in (allowed_patterns or [])):
            return False
    if any(path_lower.endswith(ext) for ext in ATTACHMENT_EXTENSIONS):
        return False
    if allowed_patterns and any(pattern in path_lower for pattern in allowed_patterns):
        return True
    # General article candidates should not be very short navigation paths.
    segments = [segment for segment in candidate.path.split("/") if segment]
    if len(segments) >= 2:
        return True
    if len(segments) == 1 and len(segments[0]) >= 18 and "-" in segments[0]:
        return True
    return False


def _anchor_context_text(anchor: Tag) -> str:
    parent = anchor.parent
    for _ in range(4):
        if parent is None:
            break
        if parent.name in {"article", "li", "div", "section"}:
            text = clean_text(parent.get_text(" ", strip=True))
            if len(text) >= len(clean_text(anchor.get_text(" ", strip=True))) + 4:
                return text[:1200]
        parent = parent.parent
    return clean_text(anchor.get_text(" ", strip=True))


def _parse_explicit_date(value: str | None, reference_year: int | None = None) -> str | None:
    """Parse a date only when the candidate itself looks like a date.

    Unlike parse_date(), this helper never searches inside arbitrary prose. That
    prevents dates in titles/deadlines (e.g. "03-04/2027") from becoming a
    publication date.
    """
    if not value:
        return None
    candidate = clean_text(value)
    patterns = [
        r"\d{4}-\d{1,2}-\d{1,2}(?:[T ]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?",
        r"\d{1,2}([/.\-])\d{1,2}\1\d{4}",
        r"\d{1,2}\s+(?:th\s*\d{1,2}|tháng\s+\d{1,2})(?:\s+\d{4})?",
    ]
    if any(re.fullmatch(pattern, candidate, re.I) for pattern in patterns):
        return parse_date(candidate, reference_year=reference_year)
    try:
        parsed = parsedate_to_datetime(candidate)
        return parsed.date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _nearest_card(anchor: Tag) -> Tag:
    parent = anchor.parent
    for _ in range(7):
        if not isinstance(parent, Tag):
            break
        classes = " ".join(parent.get("class", [])).casefold() if isinstance(parent.get("class"), list) else str(parent.get("class", "")).casefold()
        if parent.name in {"article", "li"} or any(token in classes for token in ("news-item", "post-item", "article-item", "blog-item", "listing-item", "card-item")):
            return parent
        parent = parent.parent
    return anchor.parent if isinstance(anchor.parent, Tag) else anchor


def _published_date_from_card(anchor: Tag) -> tuple[str | None, str | None]:
    """Read only date-shaped text from dedicated date nodes in a listing card."""
    card = _nearest_card(anchor)
    selectors = [
        "time[datetime]", "[itemprop='datePublished']", ".published", ".post-date",
        ".entry-date", ".news-date", ".publish-date", ".date-published",
        "[class*='published']", "[class*='post-date']", "[class*='entry-date']",
        "[class*='news-date']", "[class*='publish-date']", "[class*='date']",
    ]
    seen: set[int] = set()
    for selector in selectors:
        for node in card.select(selector):
            if id(node) in seen:
                continue
            seen.add(id(node))
            value = node.get("datetime") or node.get("content") or node.get_text(" ", strip=True)
            parsed = _parse_explicit_date(str(value or ""))
            if parsed:
                return parsed, "listing_date_element"
    # Some sites use a plain <span> for the card date. Accept it only when the
    # entire element text is a date, never when a date is embedded in prose.
    for node in card.find_all(["time", "span", "small", "p"]):
        if node.find("a"):
            continue
        parsed = _parse_explicit_date(node.get_text(" ", strip=True))
        if parsed:
            return parsed, "listing_date_element"
    return None, None


def _jsonld_published_dates(soup: BeautifulSoup) -> list[str]:
    found: list[str] = []

    def walk(value):
        if isinstance(value, dict):
            date_value = value.get("datePublished")
            if isinstance(date_value, str):
                found.append(date_value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        try:
            walk(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            continue
    return found


def _published_date_from_detail(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    # First: explicit machine-readable publication metadata.
    meta_selectors = [
        'meta[property="article:published_time"]',
        'meta[property="og:published_time"]',
        'meta[name="datePublished"]',
        'meta[itemprop="datePublished"]',
        'meta[name="pubdate"]',
        'meta[name="publish_date"]',
        'meta[name="publication_date"]',
    ]
    for selector in meta_selectors:
        for node in soup.select(selector):
            parsed = _parse_explicit_date(str(node.get("content", "")))
            if parsed:
                return parsed, "detail_meta"

    for raw in _jsonld_published_dates(soup):
        parsed = _parse_explicit_date(raw)
        if parsed:
            return parsed, "detail_jsonld"

    # Second: time/date nodes associated with the article header/meta region.
    for node in soup.select("time[datetime], [itemprop='datePublished']"):
        if node.find_parent(class_=re.compile(r"entry-content|article-content|news-content|post-content|content-body", re.I)):
            continue
        parsed = _parse_explicit_date(str(node.get("datetime") or node.get("content") or node.get_text(" ", strip=True)))
        if parsed:
            return parsed, "detail_date_element"

    # Some CMSs expose a date span in an article header but no <time> metadata.
    for selector in [
        ".entry-header .date", ".entry-header .published", ".post-meta .date",
        ".post-meta .published", ".posted-on", ".entry-date", ".post-date",
        ".news-date", ".publish-date", "header [class*='date']",
    ]:
        for node in soup.select(selector):
            if node.find_parent(class_=re.compile(r"entry-content|article-content|news-content|post-content|content-body", re.I)):
                continue
            parsed = _parse_explicit_date(node.get_text(" ", strip=True))
            if parsed:
                return parsed, "detail_date_element"
    return None, None

def parse_listing_html(html: str, listing_url: str, source_id: str, source_name: str,
                       category: str, selectors: list[str] | None = None,
                       link_patterns: list[str] | None = None) -> list[Article]:
    soup = BeautifulSoup(html, "html.parser")
    selected: list[Tag] = []
    used_selector = False
    for selector in selectors or []:
        try:
            matches = soup.select(selector)
        except Exception:
            continue
        if matches:
            used_selector = True
            selected.extend(a for a in matches if isinstance(a, Tag) and a.name == "a")
    if not selected:
        # Generic fallbacks; prefer semantic article-title nodes over arbitrary navigation links.
        preferred_selectors = [
            "article h1 a", "article h2 a", "article h3 a", "article h4 a",
            ".entry-title a", ".post-title a", ".news-title a", ".item-title a",
            ".news-item a[href]", ".post a[href]", ".blog-item a[href]",
        ]
        for selector in preferred_selectors:
            selected.extend(a for a in soup.select(selector) if isinstance(a, Tag) and a.name == "a")
        if not selected:
            selected = list(soup.find_all("a", href=True))

    output: list[Article] = []
    seen_urls: set[str] = set()
    for anchor in selected:
        href = str(anchor.get("href", "")).strip()
        title = clean_text(anchor.get_text(" ", strip=True) or anchor.get("title", ""))
        if not href or not _is_valid_title(title):
            continue
        absolute = normalize_url(urljoin(listing_url, href))
        if absolute in seen_urls or not _article_link_is_plausible(absolute, listing_url, link_patterns):
            continue
        seen_urls.add(absolute)
        context = _anchor_context_text(anchor)
        # Remove title from context to form a concise snippet where possible.
        summary = context.replace(title, "", 1).strip(" :-|·")
        if len(summary) > 500:
            summary = summary[:497].rstrip() + "..."
        published, published_source = _published_date_from_card(anchor)
        article = Article(
            title=title, source_id=source_id, source_name=source_name,
            category=category, source_url=absolute, published_at=published,
            summary=summary, content="", attachments=[],
            published_at_source=published_source,
        )
        article.content_hash = content_digest(article.title, article.summary, article.content)
        output.append(article)
    return output


def _candidate_body_text(node: Tag) -> tuple[str, int]:
    """Return cleaned body text and an approximate navigation/link ratio."""
    clone = BeautifulSoup(str(node), "html.parser")
    root = clone.find() or clone
    for unwanted in root.select(
        "script, style, noscript, nav, footer, header, aside, form, "
        ".share, .social, .related, .breadcrumb, .breadcrumbs, .pagination, "
        ".menu, .sidebar, .comments, .comment-respond, .post-navigation, "
        ".related-posts, .social-share, .elementor-location-header, .elementor-location-footer"
    ):
        unwanted.decompose()
    chunks = [clean_text(part) for part in root.stripped_strings]
    chunks = [part for part in chunks if part]
    text = "\n".join(chunks)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    link_chars = sum(len(clean_text(a.get_text(" ", strip=True))) for a in root.find_all("a"))
    ratio = int(100 * link_chars / max(1, len(text)))
    return text, ratio


def _body_node_for_source(soup: BeautifulSoup, source_url: str) -> tuple[Tag | None, str, str | None]:
    host = (urlparse(source_url).hostname or "").casefold()
    if host.endswith("ctsv.hcmus.edu.vn"):
        selectors = [
            "article .news-detail-content", "article .article-body", "article .content-detail",
            ".news-detail-content", ".news-detail__content", ".article-detail-content",
            ".single-news-content", ".post-detail-content", ".article-body", ".content-detail",
            ".entry-content", ".post-content", ".article-content", "[itemprop='articleBody']",
            "main article", "article", "main",
        ]
    elif host.endswith("tuyensinh.hcmus.edu.vn"):
        selectors = [
            "article .entry-content", ".entry-content", ".elementor-widget-theme-post-content",
            ".wp-block-post-content", ".post-content", ".single-post-content",
            ".article-content", "[itemprop='articleBody']", ".content-area article", "main article", "article", "main",
        ]
    elif host.endswith("fit.hcmus.edu.vn"):
        selectors = [
            ".news-detail-content", ".article-detail", ".news-content", ".article-content",
            ".detail-content", "[itemprop='articleBody']", "article .entry-content", ".entry-content",
            "main article", "article", "main",
        ]
    elif host.endswith("hcmus.edu.vn"):
        selectors = [
            "article .entry-content", ".entry-content", ".wp-block-post-content",
            ".elementor-widget-theme-post-content", ".td-post-content", ".post-content",
            ".single-post-content", ".article-content", ".article-body", ".news-content",
            "[itemprop='articleBody']", ".content-area article", "main article", "article", "main",
        ]
    else:
        selectors = [
            "article .entry-content", ".entry-content", ".wp-block-post-content",
            ".elementor-widget-theme-post-content", ".article-content", ".article-body",
            ".news-content", ".post-content", ".content-detail", "[itemprop='articleBody']",
            "main article", "article", "main",
        ]

    seen: set[int] = set()
    best: tuple[Tag, str, str, int] | None = None
    for selector in selectors:
        try:
            nodes = soup.select(selector)
        except Exception:
            continue
        for node in nodes:
            if not isinstance(node, Tag) or id(node) in seen:
                continue
            seen.add(id(node))
            text, link_ratio = _candidate_body_text(node)
            # A few notices genuinely consist of a short external link, image, or
            # small table. Keep those when found in a specific article-content
            # container, while still rejecting short navigation shells.
            selector_is_specific = selector not in {"main", "article", "main article", "body"}
            has_rich_payload = bool(node.select("a[href], img[src], img[data-src], img[data-lazy-src], table, ul, ol"))
            short_link_or_media_notice = selector_is_specific and has_rich_payload and (len(text) >= 3 or bool(node.select("img, table, ul, ol")))
            if len(text) < 100 and not short_link_or_media_notice:
                continue
            if link_ratio > 65 and len(text) < 1200 and not short_link_or_media_notice:
                continue
            # Select the first source-specific article container; for generic main/body
            # fallback, prefer a sufficiently long text with a lower navigation ratio.
            score = min(len(text), 30000) - max(0, link_ratio - 25) * 8
            if best is None or score > best[3]:
                best = (node, text, selector, score)
        # Prefer any candidate from more specific selectors before considering broad article/main.
        if best and selector not in {"main", "article", "main article"}:
            break
    if best:
        return best[0], best[1], best[2]
    return None, "", None


def parse_detail_html(html: str, article: Article) -> Article:
    soup = BeautifulSoup(html, "html.parser")
    host = (urlparse(article.source_url).hostname or "").casefold()
    # Prefer page-specific article title selectors before generic H1, which may be a site heading.
    title_selectors = [
        "article h1", ".entry-title", ".post-title", ".news-title", ".article-title",
        "h1", 'meta[property="og:title"]', 'meta[name="twitter:title"]',
    ]
    title_node = None
    for selector in title_selectors:
        try:
            title_node = soup.select_one(selector)
        except Exception:
            title_node = None
        if title_node:
            title_text = title_node.get("content") if title_node.name == "meta" else title_node.get_text(" ", strip=True)
            if len(clean_text(str(title_text or ""))) >= 5:
                break
            title_node = None
    title_extracted = False
    if title_node:
        title = clean_text(str(title_node.get("content") if title_node.name == "meta" else title_node.get_text(" ", strip=True)))
        if len(title) >= 5:
            if not article.raw_metadata.get("title_is_placeholder") or title.casefold() != article.title.casefold():
                article.title = title
            else:
                article.title = title
            article.raw_metadata.pop("title_is_placeholder", None)
            title_extracted = True

    # Read publication dates only from publication-specific metadata/date nodes.
    published_at, published_source = _published_date_from_detail(soup)
    date_extracted = bool(published_at)
    if published_at:
        article.published_at = published_at
        article.published_at_source = published_source
        article.raw_metadata.pop("clear_unverified_published_date", None)
    elif article.raw_metadata.get("clear_unverified_published_date"):
        article.published_at = None
        article.published_at_source = None

    body_node, content, body_selector = _body_node_for_source(soup, article.source_url)
    content_html = sanitize_rich_html(str(body_node) if body_node is not None else "", article.source_url)
    has_html_payload = rich_html_has_payload(content_html)
    article.raw_metadata["detail_title_extracted"] = title_extracted
    article.raw_metadata["detail_date_extracted"] = date_extracted
    article.raw_metadata["detail_body_extracted"] = bool(body_node is not None and (len(content) >= 100 or has_html_payload))
    article.raw_metadata["detail_body_chars"] = len(content)
    article.raw_metadata["detail_body_html_chars"] = len(content_html)
    article.raw_metadata["detail_body_selector"] = body_selector
    article.raw_metadata["detail_body_has_rich_payload"] = has_html_payload

    if body_node is not None and (len(content) >= 100 or has_html_payload):
        if len(content) > 30_000:
            content = content[:30_000].rstrip() + "\n[Đã cắt nội dung ở 30.000 ký tự trong bản thu thập.]"
        if len(content) > len(article.content):
            article.content = content
        if content_html and len(content_html) >= len(article.content_html or ""):
            article.content_html = content_html

    # Attachments are extracted only from the selected content area, avoiding site-wide menus.
    attachments: list[str] = []
    if body_node is not None:
        for anchor in body_node.find_all("a", href=True):
            href = normalize_url(urljoin(article.source_url, str(anchor.get("href", ""))))
            if urlparse(href).path.lower().endswith(ATTACHMENT_EXTENSIONS):
                attachments.append(href)
    article.attachments = sorted(set(attachments) | set(article.attachments))
    article.content_hash = content_digest(article.title, article.summary, article.content, article.attachments, article.content_html or None)
    return article


def parse_sitemap(xml_text: str, sitemap_url: str, source_id: str, source_name: str,
                  category: str, link_patterns: list[str] | None = None) -> list[Article]:
    """Parse a URL-set sitemap into lightweight articles for later detail-page enrichment.

    This is useful when a site exposes article URLs in its sitemap but its homepage/list
    is JavaScript-rendered or contains no article anchors. Sitemap <lastmod> is treated
    as a last-modified hint, not guaranteed publication date.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    root_tag = root.tag.lower().split("}")[-1]
    if root_tag != "urlset":
        # Sitemap indexes point to other sitemaps; don't mistake child sitemap URLs for articles.
        return []

    sitemap_host = urlparse(sitemap_url).netloc.lower()
    records: list[tuple[str, str | None]] = []
    for node in root:
        if node.tag.lower().split("}")[-1] != "url":
            continue
        loc_node = next((child for child in node if child.tag.lower().split("}")[-1] == "loc"), None)
        if loc_node is None or not (loc_node.text or "").strip():
            continue
        url = normalize_url(urljoin(sitemap_url, (loc_node.text or "").strip()))
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != sitemap_host:
            continue
        path = parsed.path.lower()
        if link_patterns and not any(pattern.lower() in path for pattern in link_patterns):
            continue
        lastmod_node = next((child for child in node if child.tag.lower().split("}")[-1] == "lastmod"), None)
        lastmod = parse_date((lastmod_node.text or "").strip()) if lastmod_node is not None else None
        records.append((url, lastmod))

    # Newer sitemap entries first when lastmod is available; keep stable order for ties.
    indexed = list(enumerate(records))
    indexed.sort(key=lambda pair: (pair[1][1] is not None, pair[1][1] or "", -pair[0]), reverse=True)
    output: list[Article] = []
    for _, (url, lastmod) in indexed:
        slug = urlparse(url).path.rstrip("/").split("/")[-1]
        # A sitemap has URL metadata, not the actual page title. Keep a clearly
        # marked placeholder until the detail page can supply the authoritative title.
        title = re.sub(r"[-_]+", " ", slug).strip().capitalize() or url
        article = Article(title=title, source_id=source_id, source_name=source_name,
                          category=category, source_url=url, published_at=None,
                          raw_metadata={"title_is_placeholder": True, "sitemap_lastmod": lastmod, "clear_unverified_published_date": True})
        article.content_hash = content_digest(article.title, "", "")
        output.append(article)
    return output


def parse_feed(xml_text: str, listing_url: str, source_id: str, source_name: str, category: str) -> list[Article]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    ns = {"atom": "http://www.w3.org/2005/Atom", "content": "http://purl.org/rss/1.0/modules/content/"}
    items = root.findall(".//item") or root.findall(".//atom:entry", ns)
    output: list[Article] = []
    for item in items:
        title_node = item.find("title")
        if title_node is None:
            title_node = item.find("atom:title", ns)
        title = clean_text("".join(title_node.itertext()) if title_node is not None else "")
        if not _is_valid_title(title):
            continue
        link_node = item.find("link")
        if link_node is not None and link_node.text:
            url = urljoin(listing_url, link_node.text.strip())
        else:
            atom_link = item.find("atom:link", ns)
            url = urljoin(listing_url, atom_link.attrib.get("href", "")) if atom_link is not None else ""
        if not url:
            continue
        date_node = item.find("pubDate")
        if date_node is None:
            date_node = item.find("dc:date", {"dc": "http://purl.org/dc/elements/1.1/"})
        if date_node is None:
            date_node = item.find("atom:published", ns)
        if date_node is None:
            date_node = item.find("atom:updated", ns)
        published = None
        if date_node is not None:
            date_text = clean_text("".join(date_node.itertext()))
            published = parse_date(date_text)
            if not published:
                try:
                    published = parsedate_to_datetime(date_text).date().isoformat()
                except (TypeError, ValueError, OverflowError):
                    pass
        desc_node = item.find("description")
        if desc_node is None:
            desc_node = item.find("atom:summary", ns)
        summary_raw = "".join(desc_node.itertext()) if desc_node is not None else ""
        summary_soup = BeautifulSoup(summary_raw, "html.parser")
        summary = clean_text(summary_soup.get_text(" ", strip=True))
        encoded_node = item.find("content:encoded", ns)
        if encoded_node is None:
            encoded_node = item.find("atom:content", ns)
        encoded_raw = "".join(encoded_node.itertext()) if encoded_node is not None else ""
        rich_raw = encoded_raw
        if not rich_raw and summary_soup.select_one("a[href], img, table"):
            rich_raw = summary_raw
        content_html = sanitize_rich_html(rich_raw, normalize_url(url)) if rich_raw else ""
        content_text = clean_text(BeautifulSoup(rich_raw, "html.parser").get_text(" ", strip=True)) if rich_raw else ""
        article = Article(title=title, source_id=source_id, source_name=source_name,
                          category=category, source_url=normalize_url(url), published_at=published,
                          summary=summary[:1000], content=content_text[:30_000],
                          published_at_source=("rss_pubdate" if published else None),
                          content_html=content_html)
        article.content_hash = content_digest(article.title, article.summary, article.content, [], article.content_html or None)
        output.append(article)
    return output

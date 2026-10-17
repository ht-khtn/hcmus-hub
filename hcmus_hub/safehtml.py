from __future__ import annotations

import html
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

# Keep a small formatting allowlist. Scripts, styles, forms, embedded documents,
# SVG and event handlers are intentionally excluded because this HTML is rendered
# inside the local dashboard.
ALLOWED_TAGS = {
    "a", "p", "br", "hr", "strong", "b", "em", "i", "u", "s", "del",
    "ul", "ol", "li", "blockquote", "pre", "code", "h2", "h3", "h4", "h5", "h6",
    "div", "span", "figure", "figcaption", "img", "table", "caption", "thead",
    "tbody", "tfoot", "tr", "th", "td", "dl", "dt", "dd", "sup", "sub",
}
DROP_WITH_CONTENT = {"script", "style", "noscript", "iframe", "object", "embed", "form", "input", "button", "textarea", "select", "option", "svg", "math", "canvas", "video", "audio", "source"}
ALLOWED_SCHEMES = {"http", "https"}


def _safe_url(value: str | None, base_url: str | None, *, allow_mailto: bool = False) -> str | None:
    raw = str(value or "").strip()
    if not raw or raw.startswith(("#", "javascript:", "data:", "vbscript:", "file:")):
        return None
    full = urljoin(base_url or "", raw)
    parsed = urlparse(full)
    allowed = ALLOWED_SCHEMES | ({"mailto"} if allow_mailto else set())
    if parsed.scheme.lower() not in allowed:
        return None
    if parsed.scheme.lower() in {"http", "https"} and not parsed.netloc:
        return None
    return full


def _numeric_attr(value: object) -> str | None:
    value = str(value or "").strip()
    return value if re.fullmatch(r"\d{1,4}", value) else None


def sanitize_rich_html(raw_html: str | None, base_url: str | None = None) -> str:
    """Sanitize a source body fragment and resolve links/images to absolute URLs."""
    raw = str(raw_html or "").strip()
    if not raw:
        return ""
    # Guard against pathological source pages. Parsing remains tolerant of fragments.
    raw = raw[:200_000]
    soup = BeautifulSoup(raw, "html.parser")

    for node in soup.find_all(string=lambda value: isinstance(value, Comment)):
        node.extract()

    for node in list(soup.find_all(True)):
        # A previous dangerous parent may already have decomposed this node.
        if node.name is None or node.parent is None:
            continue
        name = (node.name or "").lower()
        if name in DROP_WITH_CONTENT:
            node.decompose()
            continue
        if name not in ALLOWED_TAGS:
            node.unwrap()
            continue

        original = dict(node.attrs)
        node.attrs = {}
        if name == "a":
            href = _safe_url(original.get("href"), base_url, allow_mailto=True)
            if href:
                node["href"] = href
                node["target"] = "_blank"
                node["rel"] = "noopener noreferrer"
            title = str(original.get("title") or "").strip()
            if title:
                node["title"] = title[:300]
        elif name == "img":
            src = original.get("src")
            if not src or str(src).strip().lower().startswith("data:"):
                src = original.get("data-src") or original.get("data-lazy-src") or original.get("data-original")
            if not src and original.get("srcset"):
                first = str(original["srcset"]).split(",", 1)[0].strip().split(" ", 1)[0]
                src = first
            safe_src = _safe_url(src, base_url)
            if not safe_src:
                node.decompose()
                continue
            node["src"] = safe_src
            node["loading"] = "lazy"
            node["referrerpolicy"] = "no-referrer"
            alt = str(original.get("alt") or original.get("title") or "").strip()
            if alt:
                node["alt"] = alt[:500]
            for attr in ("width", "height"):
                val = _numeric_attr(original.get(attr))
                if val:
                    node[attr] = val
        elif name in {"td", "th"}:
            for attr in ("colspan", "rowspan"):
                val = _numeric_attr(original.get(attr))
                if val:
                    node[attr] = val
            scope = str(original.get("scope") or "").lower()
            if name == "th" and scope in {"row", "col", "rowgroup", "colgroup"}:
                node["scope"] = scope
        # All style/class/id/on* attributes are discarded by design.

    # Some pages store entity text twice escaped (for example a text node
    # becomes the literal string ``&nbsp;``). Decode text nodes only, never
    # markup or attributes, so URL/security sanitization remains unchanged.
    for text_node in list(soup.find_all(string=True)):
        if text_node.parent is None:
            continue
        original_text = str(text_node)
        decoded_text = original_text
        for _ in range(3):
            next_text = html.unescape(decoded_text)
            if next_text == decoded_text:
                break
            decoded_text = next_text
        decoded_text = decoded_text.replace("\xa0", " ").replace("\u200b", "")
        if decoded_text != original_text:
            text_node.replace_with(NavigableString(decoded_text))

    return "".join(str(child) for child in soup.contents).strip()


def rich_html_has_payload(value: str | None) -> bool:
    """True for readable text or useful link/image/table markup, including link-only notices."""
    soup = BeautifulSoup(str(value or ""), "html.parser")
    if soup.get_text(" ", strip=True):
        return True
    return bool(soup.select("a[href], img[src], table, ul, ol, dl"))


def plain_text_from_html(value: str | None) -> str:
    return BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)

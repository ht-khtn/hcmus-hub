from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import date, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def decode_html_entities(value: str | None, max_passes: int = 3) -> str:
    """Decode repeatedly escaped HTML entities without collapsing text layout.

    Some source pages double-escape entities (for example ``&amp;nbsp;``), which
    otherwise leaks the literal ``&nbsp;`` into the dashboard and stored content.
    """
    if not value:
        return ""
    decoded = str(value)
    for _ in range(max(1, min(int(max_passes), 5))):
        next_value = html.unescape(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded.replace("\xa0", " ").replace("\u200b", "")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = decode_html_entities(value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in TRACKING_KEYS]
    path = parts.path or "/"
    # Preserve explicit file paths; normalize ordinary website trailing slash.
    if path != "/" and not re.search(r"\.[A-Za-z0-9]{1,8}$", path):
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query, doseq=True), ""))


def normalize_title(title: str) -> str:
    title = unicodedata.normalize("NFKC", clean_text(title)).casefold()
    title = re.sub(r"[\W_]+", " ", title, flags=re.UNICODE)
    return clean_text(title)


def parse_date(text: str | None, reference_year: int | None = None) -> str | None:
    """Parse common Vietnamese/ISO dates without guessing ambiguous US dates."""
    if not text:
        return None
    s = clean_text(text).lower()
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})(?:[t\s].*)?\b", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})([/ .\-])\s*(\d{1,2})\2\s*(\d{4})\b", s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(3)), int(m.group(4))
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    # For Vietnamese archive dates like "15 Th1" or "15 tháng 1".
    month_words = {
        "th1": 1, "th2": 2, "th3": 3, "th4": 4, "th5": 5, "th6": 6,
        "th7": 7, "th8": 8, "th9": 9, "th10": 10, "th11": 11, "th12": 12,
    }
    m = re.search(r"\b(\d{1,2})\s+(th\s*\d{1,2}|tháng\s+\d{1,2})(?:\s+(\d{4}))?\b", s)
    if m:
        day = int(m.group(1))
        month_token = re.sub(r"\s+", "", m.group(2)).replace("tháng", "th")
        month = month_words.get(month_token)
        year = int(m.group(3)) if m.group(3) else reference_year
        if month and year:
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                return None
    return None


def utc_now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def article_fingerprint(title: str, published_at: str | None) -> str:
    key = normalize_title(title)
    if published_at:
        key = f"{key}|{published_at}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def content_digest(title: str, summary: str, content: str, attachments: list[str] | None = None,
                   content_html: str | None = None) -> str:
    payload_parts = [
        normalize_title(title), clean_text(summary), clean_text(content),
        "\n".join(sorted(attachments or [])),
    ]
    # Keep legacy hashes stable unless the caller explicitly supplies rich markup.
    if content_html is not None:
        payload_parts.append(clean_text(content_html))
    return hashlib.sha256("\n".join(payload_parts).encode("utf-8")).hexdigest()

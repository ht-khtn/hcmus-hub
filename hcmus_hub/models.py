from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ListingConfig:
    url: str
    category: str = "Chưa phân loại"
    selectors: list[str] = field(default_factory=list)
    # auto: detect RSS/sitemap/HTML; feed and sitemap force a specific parser.
    mode: str = "auto"
    # Optional path fragments used to restrict sitemap URLs to article pages.
    link_patterns: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SourceConfig:
    id: str
    name: str
    owner: str
    base_url: str
    kind: str
    enabled: bool
    listings: list[ListingConfig]
    max_pages: int = 1
    max_details_per_sync: int = 5
    notes: str = ""


@dataclass(slots=True)
class Article:
    title: str
    source_id: str
    source_name: str
    category: str
    source_url: str
    published_at: str | None = None
    summary: str = ""
    content: str = ""
    attachments: list[str] = field(default_factory=list)
    first_seen_at: str | None = None
    content_hash: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    # Provenance is tracked so an event/deadline date is not presented as a publish date.
    published_at_source: str | None = None
    # Sanitized source markup for rendering links, tables, and images in the dashboard.
    content_html: str = ""

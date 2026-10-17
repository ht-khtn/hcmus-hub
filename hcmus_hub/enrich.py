from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urlparse
from typing import Any

from .fetcher import FetchError, PoliteFetcher
from .models import Article, SourceConfig
from .parsers import parse_detail_html
from .store import Store
from .textutils import content_digest, normalize_title


def _placeholder_title(title: str, url: str) -> bool:
    if "[CHƯA LẤY CHI TIẾT]" in (title or "").upper():
        return True
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    readable = re.sub(r"[-_]+", " ", slug).strip()
    if readable and normalize_title(title) == normalize_title(readable):
        return True
    if re.match(r"^(thong bao|so tay|ke hoach|chuong trinh|quy dinh|huong dan|trien khai)\b", (title or "").casefold()) and not re.search(r"[À-ỹĐđ]", title or ""):
        return True
    return False


def _candidate_priority(row: dict[str, Any]) -> int | None:
    title = row.get("title") or ""
    url = row.get("link_source_url") or ""
    content = row.get("content") or ""
    summary = row.get("summary") or ""
    date_source = row.get("published_at_source")
    placeholder = _placeholder_title(title, url)
    if placeholder:
        return 0
    if not content.strip() and not summary.strip() and not (row.get("content_html") or "").strip():
        return 1
    # Existing plaintext was extracted by earlier versions; prioritize a rich-HTML
    # backfill so the dashboard can preserve source links, tables, and images.
    if not (row.get("content_html") or "").strip():
        return 2
    if not content.strip() and not summary.strip():
        return 3
    if not content.strip():
        return 4
    if not summary.strip():
        return 5
    if not row.get("published_at") or date_source in {"legacy_unverified", "unknown", ""}:
        return 6
    return None


def _make_article(row: dict[str, Any], source: SourceConfig) -> Article:
    attachments = json.loads(row.get("attachments_json") or "[]")
    unverified = row.get("published_at_source") in {"legacy_unverified", "unknown", ""}
    return Article(
        title=row.get("title") or "",
        source_id=source.id,
        source_name=source.name,
        category=row.get("link_category") or row.get("category") or "Chưa phân loại",
        source_url=row.get("link_source_url") or "",
        published_at=row.get("published_at"),
        summary=row.get("summary") or "",
        content=row.get("content") or "",
        attachments=attachments,
        content_hash=row.get("content_hash") or "",
        published_at_source=row.get("published_at_source"),
        content_html=row.get("content_html") or "",
        raw_metadata={"clear_unverified_published_date": bool(unverified),
                      "title_is_placeholder": _placeholder_title(row.get("title") or "", row.get("link_source_url") or "")},
    )


async def enrich_weak_articles(sources: list[SourceConfig], fetcher: PoliteFetcher, store: Store,
                               *, limit: int | None = None, source_ids: list[str] | None = None) -> dict[str, Any]:
    """Use remaining request budget on weak existing records, not only newest feed entries."""
    source_map = {s.id: s for s in sources if s.enabled and (not source_ids or s.id in source_ids)}
    rows = store.quality_candidate_rows(list(source_map))
    candidates: list[tuple[tuple, dict, SourceConfig, int]] = []
    seen_links: set[tuple[str, str]] = set()
    for row in rows:
        source = source_map.get(row.get("link_source_id"))
        if not source:
            continue
        url = row.get("link_source_url") or ""
        if not url or urlparse(url).netloc.casefold() != urlparse(source.base_url).netloc.casefold():
            continue
        link_key = (source.id, url)
        if link_key in seen_links:
            continue
        seen_links.add(link_key)
        priority = _candidate_priority(row)
        if priority is None:
            continue
        # First process the worst quality tier; within a tier, never-attempted and oldest-attempted first.
        last_attempt = row.get("last_detail_attempt_at") or ""
        sort_key = (priority, 1 if last_attempt else 0, last_attempt, row.get("published_at") or "", int(row.get("id") or 0))
        candidates.append((sort_key, row, source, priority))
    candidates.sort(key=lambda item: item[0])
    selected = candidates if limit is None else candidates[:max(0, limit)]
    result: dict[str, Any] = {
        "candidate_records": len(candidates), "limit": "all" if limit is None else max(0, limit), "details_attempted": 0,
        "http_fetched": 0, "title_extracted": 0, "date_extracted": 0,
        "body_extracted": 0, "body_chars_extracted": 0, "empty_body_after_fetch": 0,
        "errors": [], "by_source": {},
    }
    for _, row, source, priority in selected:
        result["details_attempted"] += 1
        bucket = result["by_source"].setdefault(source.id, {
            "source_name": source.name, "attempted": 0, "http_fetched": 0,
            "title_extracted": 0, "date_extracted": 0, "body_extracted": 0,
            "empty_body_after_fetch": 0, "errors": 0,
        })
        bucket["attempted"] += 1
        article = _make_article(row, source)
        try:
            response = await fetcher.get(article.source_url)
            result["http_fetched"] += 1
            bucket["http_fetched"] += 1
            enriched = parse_detail_html(response.text, article)
            if enriched.raw_metadata.get("detail_title_extracted"):
                result["title_extracted"] += 1
                bucket["title_extracted"] += 1
            if enriched.raw_metadata.get("detail_date_extracted"):
                result["date_extracted"] += 1
                bucket["date_extracted"] += 1
            chars = int(enriched.raw_metadata.get("detail_body_chars") or 0)
            result["body_chars_extracted"] += chars
            if enriched.raw_metadata.get("detail_body_extracted"):
                result["body_extracted"] += 1
                bucket["body_extracted"] += 1
                status = "body_ok"
            else:
                result["empty_body_after_fetch"] += 1
                bucket["empty_body_after_fetch"] += 1
                status = "fetched_no_body"
            enriched.content_hash = content_digest(enriched.title, enriched.summary, enriched.content, enriched.attachments, enriched.content_html or None)
            store.upsert_article(enriched)
            selector = str(enriched.raw_metadata.get("detail_body_selector") or "")
            error = None if status == "body_ok" else (
                "HTTP tải trang thành công nhưng không tìm được vùng nội dung đủ điều kiện; "
                f"selector={selector or 'none'}, text_chars={chars}, "
                f"html_chars={enriched.raw_metadata.get('detail_body_html_chars') or 0}. "
                "Có thể trang đổi cấu trúc hoặc nội dung được dựng bằng JavaScript."
            )
            store.record_detail_attempt(source.id, article.source_url, status=status, chars=chars, error=error)
        except FetchError as exc:
            msg = f"{source.id}: {article.source_url}: {exc}"
            result["errors"].append(msg)
            bucket["errors"] += 1
            store.record_detail_attempt(source.id, article.source_url, status="fetch_error", error=str(exc))
        except Exception as exc:  # keep the enrichment pass moving, but record the parser error
            msg = f"{source.id}: {article.source_url}: {type(exc).__name__}: {exc}"
            result["errors"].append(msg)
            bucket["errors"] += 1
            store.record_detail_attempt(source.id, article.source_url, status="parse_error", error=msg)
    return result


def run_enrichment(config: dict, sources: list[SourceConfig], store: Store, *, limit: int | None = None,
                   delay: float = 1.0, source_ids: list[str] | None = None) -> dict[str, Any]:
    import asyncio
    async def _run():
        async with PoliteFetcher(
            user_agent=config.get("user_agent", "HCMUSHub/0.8"),
            timeout=float(config.get("request_timeout_seconds", 20)),
            delay=max(0.0, delay),
            max_bytes=int(config.get("max_response_bytes", 5_000_000)),
            respect_robots=True,
        ) as fetcher:
            result = await enrich_weak_articles(sources, fetcher, store, limit=limit, source_ids=source_ids)
            result["fetcher_warnings"] = list(fetcher.warnings)
            return result
    return asyncio.run(_run())

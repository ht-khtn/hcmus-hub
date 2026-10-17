from __future__ import annotations

import json
from pathlib import Path

from .models import ListingConfig, SourceConfig


def load_config(path: str | Path) -> tuple[dict, list[SourceConfig]]:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    sources: list[SourceConfig] = []
    for raw in data.get("sources", []):
        listings = [ListingConfig(**item) for item in raw.get("listings", [])]
        sources.append(SourceConfig(
            id=raw["id"],
            name=raw["name"],
            owner=raw.get("owner", raw["name"]),
            base_url=raw["base_url"],
            kind=raw.get("kind", "announcements"),
            enabled=bool(raw.get("enabled", True)),
            listings=listings,
            max_pages=int(raw.get("max_pages", 1)),
            max_details_per_sync=int(raw.get("max_details_per_sync", 5)),
            notes=raw.get("notes", ""),
        ))
    return data, sources

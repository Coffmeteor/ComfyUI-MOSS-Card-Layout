"""Resolve clothing-only wardrobe entries into existing character-card captions."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG = Path(__file__).resolve().parent / "resources/costume-gallery.json"
OUTFIT = "{{outfit}}"
PORTRAIT = "{{outfit_portrait}}"


@lru_cache(maxsize=2)
def _read_catalog(path: str, modified: int, size: int) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_catalog() -> dict[str, Any]:
    """Use the same maintained catalog in the pipeline and native UI node."""
    stat = CATALOG.stat()
    return _read_catalog(str(CATALOG), stat.st_mtime_ns, stat.st_size)


def resolve(request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Replace explicit wardrobe slots; preserve character and layout instructions."""
    request = dict(request)
    identifier = request.pop("outfit_id", "")
    if not isinstance(identifier, str):
        raise ValueError("outfit_id must be a gallery ID such as SPR-0048")
    identifier = identifier.strip().upper()
    keys = ("summary_caption", "portrait_caption", "front_caption", "back_caption")
    if not identifier:
        if any(OUTFIT in str(request.get(k, "")) or PORTRAIT in str(request.get(k, "")) for k in keys):
            raise ValueError("Wardrobe caption slots require outfit_id")
        return request, None
    catalog = read_catalog()
    entry = next((x for x in catalog["entries"] if x["id"] == identifier), None)
    if entry is None:
        raise ValueError(f"Unknown outfit_id: {identifier}; select an ID from the costume gallery")
    for key, token in (("portrait_caption", PORTRAIT), ("front_caption", OUTFIT), ("back_caption", OUTFIT)):
        if token not in str(request.get(key, "")):
            raise ValueError(f"{key} requires the {token} wardrobe slot; use wardrobe-card-request.json")
    for key in keys:
        text = request.get(key)
        if isinstance(text, str):
            request[key] = text.replace(OUTFIT, entry["description"]).replace(PORTRAIT, entry["portrait_description"])
    provenance = {"id": identifier, "category": entry["category"], "catalog": str(CATALOG),
                  "catalog_sha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
                  "source_image": entry["image_url"], "source_image_sha256": entry["source_image_sha256"],
                  "description": entry["description"], "portrait_description": entry["portrait_description"]}
    return request, provenance


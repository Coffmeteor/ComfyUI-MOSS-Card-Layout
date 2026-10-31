"""Shared wardrobe resolution and bounded preview routes for the native card UI."""

from __future__ import annotations

import asyncio
from functools import lru_cache
import hashlib
import os
import tempfile
import threading
import urllib.request
from io import BytesIO
from pathlib import Path
from types import ModuleType
from .labels import describe
from . import user_library


def library() -> ModuleType:
    from . import catalog

    return catalog


def get_entry(identifier: str) -> dict:
    identifier = identifier.strip().upper()
    if identifier.startswith("USER-"):
        return user_library.get("outfits", identifier)
    entry = next(
        (e for e in library().read_catalog()["entries"] if e["id"] == identifier), None
    )
    if entry is None:
        raise ValueError(f"Unknown outfit_id: {identifier}")
    return entry


def public_catalog() -> dict:
    # Do not publish filesystem paths through the browser API.
    keys = ("id", "category", "keywords", "description", "portrait_description")
    return {
        "entries": [
            dict(e, facets=describe(e)["facets"])
            for e in user_library.entries("outfits")
        ]
        + [
            ({k: e[k] for k in keys} | describe(e))
            for e in library().read_catalog()["entries"]
        ]
    }


@lru_cache(maxsize=128)
def _thumbnail(path: str, modified: int, size: int) -> bytes:
    from PIL import Image, ImageOps

    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((240, 320))
        output = BytesIO()
        image.save(output, format="JPEG", quality=82)
        return output.getvalue()


_DOWNLOADS = threading.BoundedSemaphore(8)
_LOCKS = [threading.Lock() for _ in range(64)]


def image_path(identifier: str) -> Path:
    entry = get_entry(identifier)
    if entry["id"].startswith("USER-"):
        return user_library.image_path("outfits", entry["id"])
    import folder_paths

    root = Path(folder_paths.get_user_directory()) / "moss-card-layout/images"
    root.mkdir(parents=True, exist_ok=True)
    path = root / (entry["id"] + ".png")
    expected = entry["source_image_sha256"]
    with _LOCKS[int(expected[:8], 16) % len(_LOCKS)]:
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            return path
        with _DOWNLOADS:
            request = urllib.request.Request(
                entry["image_url"], headers={"User-Agent": "MOSS-Card-Layout/1.0"}
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                content = response.read(16 * 1024 * 1024 + 1)
            if (
                len(content) > 16 * 1024 * 1024
                or hashlib.sha256(content).hexdigest() != expected
            ):
                raise ValueError(
                    "Downloaded wardrobe image failed integrity verification"
                )
            name = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=root, suffix=".part", delete=False
                ) as handle:
                    name = handle.name
                    handle.write(content)
                os.replace(name, path)
            finally:
                if name and Path(name).exists():
                    Path(name).unlink()
    return path


def thumbnail(identifier: str) -> bytes:
    # The caller supplies a catalog identity, never a filesystem path.
    path = image_path(identifier)
    stat = path.stat()
    return _thumbnail(str(path), stat.st_mtime_ns, stat.st_size)


def register_routes() -> None:
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.get("/moss-card/wardrobe")
    async def catalog_route(request: web.Request) -> web.Response:
        try:
            return web.json_response(await asyncio.to_thread(public_catalog))
        except (OSError, RuntimeError, ValueError) as exc:
            return web.json_response({"error": str(exc)}, status=503)

    @PromptServer.instance.routes.get("/moss-card/wardrobe/{identifier}/thumbnail")
    async def thumbnail_route(request: web.Request) -> web.Response:
        try:
            content = await asyncio.to_thread(
                thumbnail, request.match_info["identifier"]
            )
            return web.Response(
                body=content,
                content_type="image/jpeg",
                headers={"Cache-Control": "no-cache"},
            )
        except (ValueError, OSError):
            raise web.HTTPNotFound(text="Wardrobe image not found")

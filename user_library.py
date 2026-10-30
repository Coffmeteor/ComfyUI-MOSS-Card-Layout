"""User-owned face/outfit assets, stored outside the updatable node package."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid
from io import BytesIO
from PIL import Image, ImageOps

_LOCK = threading.RLock()
KINDS = {'faces', 'outfits'}


def root() -> Path:
    import folder_paths
    return Path(folder_paths.get_user_directory()) / 'moss-card-layout/library'


def kind_root(kind: str) -> Path:
    if kind not in KINDS:
        raise ValueError('Unknown library type')
    return root() / kind


def valid_id(identifier: str) -> str:
    if not re.fullmatch(r'USER-[A-F0-9]{32}', identifier):
        raise ValueError('Invalid user asset identifier')
    return identifier


def entries(kind: str) -> list[dict]:
    directory = kind_root(kind)
    with _LOCK:
        return [json.loads(p.read_text()) for p in sorted(directory.glob('USER-*/entry.json'))]


def get(kind: str, identifier: str) -> dict:
    with _LOCK:
        return json.loads((kind_root(kind) / valid_id(identifier) / 'entry.json').read_text())


def image_path(kind: str, identifier: str) -> Path:
    get(kind, identifier)
    return kind_root(kind) / identifier / 'image.png'


def fields(data: dict, kind: str) -> dict:
    def text(key: str, maximum: int, required: bool = False) -> str:
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
            raise ValueError(f'Invalid {key}')
        return value.strip()
    label = text('label', 120, True)
    description = text('description', 6000, True)
    portrait = text('portrait_description', 3000)
    tags = data.get('tags', [])
    if isinstance(tags, str): tags = [x.strip() for x in tags.split(',') if x.strip()]
    if not isinstance(tags, list) or len(tags) > 24 or any(not isinstance(t, str) or len(t) > 60 for t in tags):
        raise ValueError('Use up to 24 short tags')
    if kind == 'outfits' and not portrait:
        raise ValueError('Describe upper-body clothing for the portrait separately')
    return {'label':label, 'description':description, 'portrait_description':portrait,
            'category':'My library', 'tags':list(dict.fromkeys(tags)), 'keywords':' '.join(tags),
            'hair_description':text('hair_description', 1000), 'source':'user', 'editable':True}


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + '.part')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    os.replace(temporary, path)


def create(kind: str, data: dict, image: bytes) -> dict:
    directory = kind_root(kind)
    entry = fields(data, kind)
    if not image or len(image) > 16 * 1024 * 1024:
        raise ValueError('Upload a PNG, JPEG or WebP image up to 16 MB')
    try:
        with Image.open(BytesIO(image)) as source:
            if source.format not in {'PNG','JPEG','WEBP'} or source.width * source.height > 32_000_000:
                raise ValueError('Unsupported image format or dimensions')
            normalized = ImageOps.exif_transpose(source).convert('RGB')
            buffer = BytesIO();normalized.save(buffer, format='PNG');content = buffer.getvalue()
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Upload a valid PNG, JPEG or WebP image') from exc
    identifier = 'USER-' + uuid.uuid4().hex.upper()
    entry.update(id=identifier, source_image_sha256=hashlib.sha256(content).hexdigest())
    with _LOCK:
        target = directory / identifier;target.mkdir(parents=True)
        (target/'image.png').write_bytes(content)
        atomic_json(target/'entry.json',entry)
    return entry


def update(kind: str, identifier: str, data: dict) -> dict:
    with _LOCK:
        original = get(kind, identifier)
        original.update(fields(data, kind))
        atomic_json(kind_root(kind)/identifier/'entry.json',original)
        return original


def trash(kind: str, identifier: str, restore: bool = False) -> None:
    directory = kind_root(kind);identifier = valid_id(identifier)
    active = directory/identifier;deleted = directory/'.trash'/identifier
    with _LOCK:
        source,target = (deleted,active) if restore else (active,deleted)
        if target.exists(): raise ValueError('Asset already exists at destination')
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)

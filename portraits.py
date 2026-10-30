"""Portrait index, on-demand reference images, and the face library node."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request
from io import BytesIO
from PIL import Image,ImageOps
from . import user_library
from .wardrobe import _DOWNLOADS,_LOCKS,_thumbnail

CATALOG=Path(__file__).parent/'resources/portrait-gallery.json'


def official_entries() -> list[dict]:
    return json.loads(CATALOG.read_text())['entries']


def entries() -> list[dict]:
    return user_library.entries('faces')+official_entries()


def get(identifier: str) -> dict:
    if identifier.startswith('USER-'):return user_library.get('faces',identifier)
    item=next((e for e in official_entries() if e['id']==identifier),None)
    if item is None:raise ValueError('Select a face from the library')
    return item


def image_path(identifier: str, preview: bool=False) -> Path:
    entry=get(identifier)
    if identifier.startswith('USER-'):return user_library.image_path('faces',identifier)
    import folder_paths
    cache=Path(folder_paths.get_user_directory())/'moss-card-layout/portraits';cache.mkdir(parents=True,exist_ok=True)
    kind='thumbnail' if preview else 'image'
    path=cache/(identifier+('.webp' if preview else '.png'))
    expected=entry.get(kind+'_sha256');expected_bytes=entry.get('image_bytes') if not preview else None
    def valid(content:bytes) -> bool:
        return bool(content) and (not expected or hashlib.sha256(content).hexdigest()==expected) and (not expected_bytes or len(content)==expected_bytes)
    with _LOCKS[int(hashlib.sha256(identifier.encode()).hexdigest()[:8],16)%len(_LOCKS)]:
        if path.is_file() and valid(path.read_bytes()):return path
        with _DOWNLOADS:
            req=urllib.request.Request(entry[kind+'_url'],headers={'User-Agent':'MOSS-Card-Layout/1.1'})
            with urllib.request.urlopen(req,timeout=45) as response:content=response.read(16*1024*1024+1)
            if len(content)>16*1024*1024 or not valid(content):raise ValueError('Portrait download failed integrity validation')
            with Image.open(BytesIO(content)) as image:
                if image.width*image.height>32_000_000:raise ValueError('Portrait image is too large')
                image.verify()
            name=None
            try:
                with tempfile.NamedTemporaryFile(dir=cache,suffix='.part',delete=False) as temp:
                    name=temp.name;temp.write(content)
                os.replace(name,path)
            finally:
                if name and Path(name).exists():Path(name).unlink()
    return path


def thumbnail(identifier:str) -> bytes:
    path=image_path(identifier,True);stat=path.stat()
    return _thumbnail(str(path),stat.st_mtime_ns,stat.st_size)


class MOSSFaceLibrary:
    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {'required':{'face_id':('STRING',{'default':'f71f980dde3'}),
                            'description_override':('STRING',{'default':'','multiline':True})}}
    RETURN_TYPES=('IMAGE','STRING','STRING');RETURN_NAMES=('reference_image','face_description','reference_hair')
    FUNCTION='build';CATEGORY='MOSS-Image/Character Studio'

    @classmethod
    def IS_CHANGED(cls,**kwargs) -> str:
        return json.dumps(get(kwargs['face_id']),sort_keys=True)

    def build(self,face_id:str,description_override:str):
        import numpy as np
        import torch
        entry=get(face_id)
        from .face_contract import validate_face
        profile=entry.get('face_spec')
        if profile:
            profile=validate_face(dict(profile,geometry=description_override.strip() or profile['geometry']))
            description=json.dumps(profile,ensure_ascii=False,separators=(',',':'))
        else:
            description=description_override.strip() or entry['description']
        if not description:raise ValueError('Add a face description for text generation')
        with Image.open(image_path(face_id)) as source:
            image=ImageOps.exif_transpose(source).convert('RGB')
            array=np.asarray(image,dtype=np.float32)/255.0
        return torch.from_numpy(array)[None,],description,entry.get('hair_description','')

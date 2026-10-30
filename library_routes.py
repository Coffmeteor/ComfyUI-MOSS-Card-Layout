"""Same-origin library editing API with bounded uploads and recoverable deletion."""
from __future__ import annotations
import asyncio,json
from . import user_library,portraits,wardrobe


def register_routes() -> None:
    from aiohttp import web
    from server import PromptServer
    routes=PromptServer.instance.routes

    @routes.get('/moss-card/library/{kind}')
    async def list_entries(request):
        kind=request.match_info['kind']
        try:
            user_library.kind_root(kind)
            items=await asyncio.to_thread(portraits.entries if kind=='faces' else lambda:wardrobe.public_catalog()['entries'])
            return web.json_response({'entries':items})
        except (ValueError,OSError) as exc:return web.json_response({'error':str(exc)},status=400)

    @routes.get('/moss-card/library/{kind}/{identifier}/thumbnail')
    async def image(request):
        kind=request.match_info['kind'];identifier=request.match_info['identifier']
        try:
            user_library.kind_root(kind)
            content=await asyncio.to_thread(portraits.thumbnail if kind=='faces' else wardrobe.thumbnail,identifier)
            return web.Response(body=content,content_type='image/jpeg',headers={'Cache-Control':'no-cache'})
        except (ValueError,OSError):raise web.HTTPNotFound(text='Library image unavailable')

    @routes.post('/moss-card/library/{kind}')
    async def create(request):
        try:
            kind=request.match_info['kind'];user_library.kind_root(kind)
            reader=await request.multipart();metadata=None;image=None
            async for part in reader:
                limit=16*1024*1024 if part.name=='image' else 24000
                chunks=[];size=0
                while chunk:=await part.read_chunk():
                    size+=len(chunk)
                    if size>limit:raise ValueError('Upload exceeds the allowed size')
                    chunks.append(chunk)
                value=b''.join(chunks)
                if part.name=='metadata':metadata=json.loads(value)
                elif part.name=='image':image=value
            if not isinstance(metadata,dict) or image is None:raise ValueError('Image and metadata are required')
            entry=await asyncio.to_thread(user_library.create,kind,metadata,image)
            return web.json_response(entry,status=201)
        except (ValueError,OSError) as exc:return web.json_response({'error':str(exc)},status=400)

    @routes.patch('/moss-card/library/{kind}/{identifier}')
    async def update(request):
        try:
            chunks=[];size=0
            async for chunk in request.content.iter_chunked(4096):
                size+=len(chunk)
                if size>24000:raise ValueError('Metadata is too large')
                chunks.append(chunk)
            content=b''.join(chunks)
            data=json.loads(content)
            if not isinstance(data,dict):raise ValueError('Metadata must be an object')
            entry=await asyncio.to_thread(user_library.update,request.match_info['kind'],request.match_info['identifier'],data)
            return web.json_response(entry)
        except (ValueError,OSError) as exc:return web.json_response({'error':str(exc)},status=400)

    @routes.delete('/moss-card/library/{kind}/{identifier}')
    async def delete(request):
        try:
            await asyncio.to_thread(user_library.trash,request.match_info['kind'],request.match_info['identifier'])
            return web.json_response({'status':'moved_to_trash'})
        except (ValueError,OSError) as exc:return web.json_response({'error':str(exc)},status=400)

    @routes.post('/moss-card/library/{kind}/{identifier}/restore')
    async def restore(request):
        try:
            await asyncio.to_thread(user_library.trash,request.match_info['kind'],request.match_info['identifier'],True)
            return web.json_response({'status':'restored'})
        except (ValueError,OSError) as exc:return web.json_response({'error':str(exc)},status=400)

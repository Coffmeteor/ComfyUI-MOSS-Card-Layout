"""Sample a card region locally, then decode one complete canvas from its latents."""
from __future__ import annotations
import json
import math

from .edit_region import REGIONS, edit_contract


def region_geometry(layout_json, width, height, latent_width, latent_height, region, context_pixels=0):
    if type(context_pixels) is not int or not 0 <= context_pixels <= 512:
        raise ValueError("Context padding must be an integer between0 and512 pixels")
    if width % latent_width or height % latent_height:
        raise ValueError("Source pixels and latent grid must have an exact integer scale")
    sx,sy=width//latent_width,height//latent_height
    _,boxes=edit_contract(layout_json,width,height,region,"Region geometry.")
    x0=max(0,min(b[0]for b in boxes)-context_pixels)//sx*sx;y0=max(0,min(b[1]for b in boxes)-context_pixels)//sy*sy
    x1=min(width,math.ceil((max(b[2]for b in boxes)+context_pixels)/sx)*sx)
    y1=min(height,math.ceil((max(b[3]for b in boxes)+context_pixels)/sy)*sy)
    return dict(canvas=[width,height],pixels=[x0,y0,x1,y1],latent=[x0//sx,y0//sy,x1//sx,y1//sy],scale=[sx,sy])


class MOSSLatentRegionCrop:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{
            "samples":("LATENT",),"source_image":("IMAGE",),"edit_mask":("MASK",),
            "layout_json":("STRING",{"forceInput":True}),
            "region":("STRING",{"forceInput":True}),"edit_instruction":("STRING",{"forceInput":True}),
        },"optional":{"context_pixels":("INT",{"default":0,"min":0,"max":512,"step":16,
            "tooltip":"Include protected neighboring pixels around the edit region for coherent boundaries. This does not expand the editable mask."})}}
    RETURN_TYPES=("LATENT","IMAGE","STRING","STRING")
    RETURN_NAMES=("region_latent","region_reference","region_json","region_coordinates")
    FUNCTION="build"
    CATEGORY="MOSS-Image/Layout"

    def build(self,samples,source_image,edit_mask,layout_json,region,edit_instruction,context_pixels=0):
        z=samples["samples"]
        if z.ndim!=4 or source_image.ndim!=4 or z.shape[0]!=1 or source_image.shape[0]!=1:
            raise ValueError("Region editing requires one image and one spatial latent")
        h,w=source_image.shape[1:3]
        if tuple(edit_mask.shape)!=(1,h,w):raise ValueError("Edit mask must match the full source image")
        info=region_geometry(layout_json,w,h,z.shape[-1],z.shape[-2],region,context_pixels)
        x0,y0,x1,y1=info['pixels'];lx0,ly0,lx1,ly1=info['latent']
        cropped=dict(samples,samples=z[:,:,ly0:ly1,lx0:lx1].clone(),noise_mask=edit_mask[:,y0:y1,x0:x1].clone())
        layout=json.loads(layout_json);items=[];cw,ch=x1-x0,y1-y0
        instruction=edit_instruction.replace('left portrait','portrait')
        for i in REGIONS[region]:
            by0,bx0,by1,bx1=layout['items'][i]['bbox']
            items.append(dict(label=layout['items'][i].get('label','character'),caption=instruction,
                bbox=[by0+h//2-y0-ch//2,bx0+w//2-x0-cw//2,by1+h//2-y0-ch//2,bx1+w//2-x0-cw//2]))
        local=dict(summary=dict(canvas='single'if len(items)==1 else'multi_panel',caption=instruction+' Keep the existing composition. No drawn borders, boxes or text.'),items=items,bbox_coord_space='abs_centralized',bbox_format='yxyx')
        return cropped,source_image[:,y0:y1,x0:x1,:].clone(),json.dumps(local,separators=(',',':')),json.dumps(info,separators=(',',':'))


class MOSSLatentRegionMerge:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{
            "original":("LATENT",),"edited_region":("LATENT",),"edit_mask":("MASK",),
            "region_coordinates":("STRING",{"forceInput":True}),
        }}
    RETURN_TYPES=("LATENT",)
    RETURN_NAMES=("complete_canvas",)
    FUNCTION="build"
    CATEGORY="MOSS-Image/Layout"

    def build(self,original,edited_region,edit_mask,region_coordinates):
        from comfy.utils import reshape_mask
        info=json.loads(region_coordinates);base=original['samples'];patch=edited_region['samples']
        w,h=info['canvas'];sx,sy=info['scale'];x0,y0,x1,y1=info['pixels'];lx0,ly0,lx1,ly1=info['latent']
        if (base.ndim!=4 or patch.ndim!=4 or tuple(edit_mask.shape)!=(base.shape[0],h,w)
                or base.shape[-2:]!=(h//sy,w//sx) or patch.shape!=base[:,:,ly0:ly1,lx0:lx1].shape
                or [x0,y0,x1,y1]!=[lx0*sx,ly0*sy,lx1*sx,ly1*sy]
                or not (0<=x0<x1<=w and 0<=y0<y1<=h)):
            raise ValueError("Region coordinates, edited latent and original canvas do not match")
        mask=reshape_mask(edit_mask[:,y0:y1,x0:x1],patch.shape).to(device=base.device,dtype=base.dtype)
        result=base.clone();old=base[:,:,ly0:ly1,lx0:lx1]
        result[:,:,ly0:ly1,lx0:lx1]=patch.to(device=base.device,dtype=base.dtype)*mask+old*(1-mask)
        output=dict(original,samples=result);output.pop('noise_mask',None)
        return(output,)

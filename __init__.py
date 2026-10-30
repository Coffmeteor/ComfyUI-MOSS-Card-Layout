"""Automatic text-only MOSS card geometry and optional wardrobe browsing."""
from .layout import build_layout, build_four_view_layout, CAPTIONS
from .wardrobe import library, register_routes


class MOSSAutoThreeViewCard:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "long_edge": ("INT", {"default": 1824, "min": 256, "max": 4096, "step": 16}),
            "short_edge": ("INT", {"default": 1024, "min": 256, "max": 4096, "step": 16}),
            **{key: ("STRING", {"forceInput": True}) for key in CAPTIONS},
        }}

    RETURN_TYPES = ("STRING", "INT", "INT")
    RETURN_NAMES = ("layout_json", "width", "height")
    FUNCTION = "build"
    CATEGORY = "MOSS-Image/Layout"

    def build(self, long_edge, short_edge, **captions):
        return build_layout(long_edge, short_edge, **captions), long_edge, short_edge


class MOSSAutoFourViewCard(MOSSAutoThreeViewCard):
    @classmethod
    def INPUT_TYPES(cls):
        required = dict(super().INPUT_TYPES()["required"])
        required["privacy_blocks"] = ("BOOLEAN", {
            "default": True, "label_on": "On", "label_off": "Off",
            "tooltip": "Request opaque privacy blocks in the adult body-reference panel. Changing this regenerates the card; it is not a postprocessing mask.",
        })
        required["body_caption"] = ("STRING", {"forceInput": True})
        return {"required": required}

    def build(self, long_edge, short_edge, privacy_blocks, **captions):
        return (build_four_view_layout(long_edge, short_edge, privacy_blocks, **captions),
                long_edge, short_edge)


class MOSSFourViewWardrobeCard(MOSSAutoFourViewCard):
    @classmethod
    def IS_CHANGED(cls, **kwargs) -> str:
        import hashlib
        return hashlib.sha256(library().CATALOG.read_bytes()).hexdigest()

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        required = dict(super().INPUT_TYPES()["required"])
        required["outfit_id"] = ("STRING", {
            "default": "SPR-0048",
            "tooltip": "Click Browse Wardrobe to select a preview. Clothing slots are filled without changing the character or body-reference panel.",
        })
        return {"required": required}

    def build(self, long_edge: int, short_edge: int, privacy_blocks: bool,
              outfit_id: str, **captions: str) -> tuple[str, int, int]:
        resolved, _ = library().resolve(dict(captions, outfit_id=outfit_id))
        return super().build(long_edge, short_edge, privacy_blocks, **resolved)


NODE_CLASS_MAPPINGS = {"MOSSAutoThreeViewCard": MOSSAutoThreeViewCard,
                       "MOSSAutoFourViewCard": MOSSAutoFourViewCard,
                       "MOSSFourViewWardrobeCard": MOSSFourViewWardrobeCard}
NODE_DISPLAY_NAME_MAPPINGS = {"MOSSAutoThreeViewCard": "MOSS Three-View Card - Auto Bbox",
                              "MOSSAutoFourViewCard": "MOSS Four-View Card - Privacy Control",
                              "MOSSFourViewWardrobeCard": "MOSS Four-View Card - Wardrobe Preview"}

WEB_DIRECTORY = "./web"
register_routes()

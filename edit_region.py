"""Use one validated rectangle definition for MOSS edit text and sampling masks."""

from __future__ import annotations

import json
import math

REGIONS = {
    "Portrait": (0,),
    "Body reference": (1,),
    "Clothed front": (2,),
    "Clothed back": (3,),
    "Clothed front and back": (2, 3),
    "All body panels": (1, 2, 3),
}
ROLES = ("portrait", "body reference", "clothed front view", "clothed back view")


def placement_face_box(metadata, source_width, source_height, panel, frame_height, top):
    """Map reviewed full-photo coordinates through the exact native center-crop transform."""
    data = json.loads(metadata) if metadata else {}
    framing = data.get("framing")
    x0, y0, x1, y1 = panel
    w = x1 - x0
    if framing is None:
        return [
            [
                dict(
                    x=x0,
                    y=y0,
                    width=w,
                    height=y1 - y0,
                    metadata={
                        "desc": "Draw a face protection box",
                        "reference_id": data.get("asset_id", "custom"),
                    },
                )
            ]
        ]
    b = framing.get("face_bbox_norm_xyxy")
    if (
        framing.get("schema_version") != 1
        or type(framing.get("crown_complete")) is not bool
        or not isinstance(b, list)
        or len(b) != 4
        or any(type(v) is not int for v in b)
        or not (0 <= b[0] < b[2] <= 1000 and 0 <= b[1] < b[3] <= 1000)
    ):
        raise ValueError("Invalid reviewed reference-face framing metadata")
    old_aspect = source_width / source_height
    new_aspect = w / frame_height
    dx = dy = 0
    if old_aspect > new_aspect:
        dx = round((source_width - source_width * (new_aspect / old_aspect)) / 2)
    elif old_aspect < new_aspect:
        dy = round((source_height - source_height * (old_aspect / new_aspect)) / 2)
    sx = w / (source_width - 2 * dx)
    sy = frame_height / (source_height - 2 * dy)
    a = x0 + (b[0] * source_width / 1000 - dx) * sx
    c = x0 + (b[2] * source_width / 1000 - dx) * sx
    d = y0 + top + (b[1] * source_height / 1000 - dy) * sy
    e = y0 + top + (b[3] * source_height / 1000 - dy) * sy
    if not (x0 <= a < c <= x1 and y0 <= d < e <= y1):
        raise ValueError(
            "Reference placement crops the protected face; reduce reference frame height"
        )
    # MOSS/Flux2 uses a16-pixel latent grid; round protection outward rather than trim facial features.
    a = max(x0, math.floor(a / 16) * 16)
    c = min(x1, math.ceil(c / 16) * 16)
    d = max(y0, math.floor(d / 16) * 16)
    e = min(y1, math.ceil(e / 16) * 16)
    return [
        [
            dict(
                x=a,
                y=d,
                width=c - a,
                height=e - d,
                metadata={
                    "desc": "Face protection",
                    "reference_id": data.get("asset_id", "custom"),
                },
            )
        ]
    ]


def edit_contract(
    layout_json, width, height, region, instruction, edit_boxes=None, protect_box=False
):
    if any(
        type(v) is not int or v < 256 or v > 4096 or v % 16 for v in (width, height)
    ):
        raise ValueError(
            "Canvas dimensions must be multiples of 16 between 256 and 4096"
        )
    if region not in REGIONS:
        raise ValueError("Choose a supported card region")
    if (
        not isinstance(instruction, str)
        or not instruction.strip()
        or len(instruction) > 4000
    ):
        raise ValueError("Enter a short, nonempty edit instruction")
    layout = json.loads(layout_json)
    if (
        layout.get("bbox_format") != "yxyx"
        or layout.get("bbox_coord_space") != "abs_centralized"
        or not isinstance(layout.get("items"), list)
        or len(layout["items"]) != 4
    ):
        raise ValueError(
            "Use the four-panel Character Studio JSON with absolute centralized yxyx boxes"
        )
    boxes = []
    for item in layout["items"]:
        b = item.get("bbox")
        if not isinstance(b, list) or len(b) != 4 or any(type(v) is not int for v in b):
            raise ValueError("Every card bbox must contain four integer coordinates")
        y0, x0, y1, x1 = b
        r = (x0 + width // 2, y0 + height // 2, x1 + width // 2, y1 + height // 2)
        if not (0 <= r[0] < r[2] <= width and 0 <= r[1] < r[3] <= height):
            raise ValueError("A card bbox lies outside the source canvas")
        boxes.append(r)
    selected = REGIONS[region]
    protected = None
    if type(protect_box) is not bool or (protect_box and edit_boxes is None):
        raise ValueError("Protect box requires one explicitly drawn rectangle")
    if edit_boxes is not None:
        # Native CreateBoundingBoxes emits one frame containing pixel-space boxes.
        if (
            len(selected) != 1
            or not isinstance(edit_boxes, list)
            or len(edit_boxes) != 1
            or not isinstance(edit_boxes[0], list)
            or len(edit_boxes[0]) != 1
        ):
            raise ValueError(
                "Draw exactly one edit box inside one selected card region"
            )
        box = edit_boxes[0][0]
        if not isinstance(box, dict) or any(
            type(box.get(k)) is not int for k in ("x", "y", "width", "height")
        ):
            raise ValueError("The edit box must use integer pixel coordinates")
        x, y, w, h = (box[k] for k in ("x", "y", "width", "height"))
        outer = boxes[selected[0]]
        if not (
            w > 0
            and h > 0
            and outer[0] <= x < x + w <= outer[2]
            and outer[1] <= y < y + h <= outer[3]
        ):
            raise ValueError(
                "The edit box must remain entirely inside its selected card region"
            )
        if protect_box:
            protected = (x, y, x + w, y + h)
        else:
            boxes[selected[0]] = (x, y, x + w, y + h)
    instruction = instruction.strip()
    layout["summary"] = {
        "canvas": "multi_panel",
        "caption": "Edit the existing canvas only inside the selected bounding boxes. "
        + instruction
        + " Preserve everything outside those boxes, including the four-panel arrangement, unchanged.",
    }
    if protected:
        x0, y0, x1, y1 = protected
        bbox = [y0 - height // 2, x0 - width // 2, y1 - height // 2, x1 - width // 2]
        layout["summary"]["caption"] += (
            f" Preserve the protected area at bbox {bbox} unchanged."
        )
    for i, item in enumerate(layout["items"]):
        if i in selected:
            x0, y0, x1, y1 = boxes[i]
            item["bbox"] = [
                y0 - height // 2,
                x0 - width // 2,
                y1 - height // 2,
                x1 - width // 2,
            ]
            item["caption"] = (
                instruction
                + f" Keep the existing scale and orientation of this {ROLES[i]}."
            )
        else:
            item["caption"] = (
                f"Preserve this {ROLES[i]} in the existing canvas unchanged."
            )
    mask_boxes = [boxes[i] for i in selected]
    if protected:
        x0, y0, x1, y1 = boxes[selected[0]]
        px0, py0, px1, py1 = protected
        mask_boxes = [
            r
            for r in (
                (x0, y0, x1, py0),
                (x0, py1, x1, y1),
                (x0, py0, px0, py1),
                (px1, py0, x1, py1),
            )
            if r[0] < r[2] and r[1] < r[3]
        ]
        if not mask_boxes:
            raise ValueError("The protected box leaves no editable area")
    return json.dumps(layout, ensure_ascii=False, separators=(",", ":")), mask_boxes


class MOSSCardEditRegion:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_image": ("IMAGE",),
                "layout_json": ("STRING", {"forceInput": True}),
                "canvas_width": ("INT", {"forceInput": True}),
                "canvas_height": ("INT", {"forceInput": True}),
                "region": (list(REGIONS),),
                "protect_box": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Off: edit inside the drawn box. On: preserve that box and edit the surrounding selected panel.",
                    },
                ),
                "edit_instruction": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "Change only the specified clothing. Keep all other details unchanged.",
                    },
                ),
            },
            "optional": {
                "edit_boxes": (
                    "BOUNDING_BOX",
                    {
                        "forceInput": True,
                        "tooltip": "Optional single rectangle from native Create Bounding Boxes, inside the selected panel. The same box controls the JSON and the sampling mask.",
                    },
                ),
                "instruction_mode": (
                    ["Custom edit", "Complete portrait framing", "Selected outfit"],
                    {"default": "Custom edit"},
                ),
                "outfit_description": ("STRING", {"forceInput": True}),
                "portrait_clothing": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING", "MASK", "STRING", "STRING")
    RETURN_NAMES = ("edit_json", "edit_mask", "edit_instruction", "selected_region")
    FUNCTION = "build"
    CATEGORY = "MOSS-Image/Layout"

    def build(
        self,
        source_image,
        layout_json,
        canvas_width,
        canvas_height,
        region,
        edit_instruction,
        edit_boxes=None,
        protect_box=False,
        instruction_mode="Custom edit",
        outfit_description=None,
        portrait_clothing=None,
    ):
        if tuple(source_image.shape[:3]) != (1, canvas_height, canvas_width):
            raise ValueError(
                "Use one source card whose dimensions exactly match the connected layout dimensions"
            )
        if instruction_mode == "Complete portrait framing":
            if region != "Portrait":
                raise ValueError("Portrait framing applies only to the portrait region")
            edit_instruction = (
                "Complete the portrait as one seamless photograph. Fill empty margins and complete the hair crown with a small margin above it. "
                "Use a neutral light-gray studio background. Keep the existing face, expression, hairstyle and natural head-to-shoulder proportions. Show only head, shoulders and upper chest."
            )
        elif instruction_mode == "Selected outfit":
            if not outfit_description or not portrait_clothing:
                raise ValueError(
                    "Connect the outfit library before using Selected outfit"
                )
            from .outfit_contract import parse_spec, render_view

            outfit = parse_spec(outfit_description, portrait_clothing)
            if region == "Portrait":
                edit_instruction = (
                    "Change the portrait clothing and accessories to: "
                    + outfit["portrait"]
                    + " Keep the face, expression, hairstyle and framing unchanged. Match the neutral light-gray studio background of the card. Show only the upper neckline; the garment continues below the frame."
                )
            elif region in ("Clothed front", "Clothed back", "Clothed front and back"):
                descriptions = []
                for view in ("front", "back"):
                    if (
                        region == "Clothed front and back"
                        or region == "Clothed " + view
                    ):
                        descriptions.append(
                            view.upper() + ": " + render_view(outfit, view)
                        )
                edit_instruction = (
                    "Change only the clothing. "
                    + " ".join(descriptions)
                    + " Preserve the existing body, pose, headless framing and background."
                )
            else:
                raise ValueError(
                    "Outfit edits cannot modify the independent anatomy-reference panel"
                )
        elif instruction_mode != "Custom edit":
            raise ValueError("Choose a supported edit instruction mode")
        prompt, boxes = edit_contract(
            layout_json,
            canvas_width,
            canvas_height,
            region,
            edit_instruction,
            edit_boxes,
            protect_box,
        )
        import torch

        mask = torch.zeros(
            (1, canvas_height, canvas_width), dtype=torch.float32, device="cpu"
        )
        for x0, y0, x1, y1 in boxes:
            mask[:, y0:y1, x0:x1] = 1.0
        return prompt, mask, edit_instruction, region


class MOSSCardPortraitSetup:
    """Initialize the portrait panel with a uniformly framed whole reference photo."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_card": ("IMAGE",),
                "reference_portrait": ("IMAGE",),
                "layout_json": ("STRING", {"forceInput": True}),
                "canvas_width": ("INT", {"forceInput": True}),
                "canvas_height": ("INT", {"forceInput": True}),
                "reference_frame_height": (
                    "FLOAT",
                    {
                        "default": 0.8,
                        "min": 0.5,
                        "max": 1.0,
                        "step": 0.01,
                        "tooltip": "Fraction of the portrait panel occupied by the complete reference frame. Uniform framing preserves facial proportions; surrounding space is completed by the editor.",
                    },
                ),
                "vertical_position": (
                    "FLOAT",
                    {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01},
                ),
            },
            "optional": {
                "reference_framing": ("STRING", {"forceInput": True}),
                "replace_portrait": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "BOUNDING_BOX")
    RETURN_NAMES = ("initialized_card", "suggested_face_box")
    FUNCTION = "build"
    CATEGORY = "MOSS-Image/Layout"

    def build(
        self,
        source_card,
        reference_portrait,
        layout_json,
        canvas_width,
        canvas_height,
        reference_frame_height=0.8,
        vertical_position=0.45,
        reference_framing="",
        replace_portrait=True,
    ):
        if (
            tuple(source_card.shape[:3]) != (1, canvas_height, canvas_width)
            or reference_portrait.shape[0] != 1
        ):
            raise ValueError(
                "Use one source card matching the layout dimensions and one reference portrait"
            )
        if not (0.5 <= reference_frame_height <= 1.0 and 0 <= vertical_position <= 1):
            raise ValueError("Invalid reference frame height or vertical position")
        _, boxes = edit_contract(
            layout_json,
            canvas_width,
            canvas_height,
            "Portrait",
            "Prepare reference framing.",
        )
        x0, y0, x1, y1 = boxes[0]
        h = math.ceil((y1 - y0) * reference_frame_height)
        top = round((y1 - y0 - h) * vertical_position)
        if not replace_portrait:
            return source_card, placement_face_box("", 1, 1, boxes[0], h, top)
        from comfy.utils import common_upscale

        portrait = common_upscale(
            reference_portrait.movedim(-1, 1), x1 - x0, h, "lanczos", "center"
        ).movedim(1, -1)
        result = source_card.clone()
        # A whole rectangular input frame, never a segmented foreground or final output repair.
        background = source_card[
            :, min(y0 + 9, y1 - 1), min(x0 + 9, x1 - 1), :3
        ].clone()
        result[:, y0:y1, x0:x1, :3] = background[:, None, None, :]
        result[:, y0 + top : y0 + top + h, x0:x1, :3] = portrait[:, :, :, :3]
        face_box = placement_face_box(
            reference_framing,
            reference_portrait.shape[2],
            reference_portrait.shape[1],
            boxes[0],
            h,
            top,
        )
        return result, face_box


class MOSSExistingCardLayout:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"source_card": ("IMAGE",)},
            "optional": {"layout_json": ("STRING", {"forceInput": True})},
        }

    RETURN_TYPES = ("STRING", "INT", "INT")
    RETURN_NAMES = ("layout_json", "width", "height")
    FUNCTION = "build"
    CATEGORY = "MOSS-Image/Layout"

    def build(self, source_card, layout_json=""):
        if source_card.shape[0] != 1:
            raise ValueError("Select one source character card")
        height, width = source_card.shape[1:3]
        if not layout_json:
            from .layout import build_four_view_layout

            layout = json.loads(
                build_four_view_layout(
                    width,
                    height,
                    False,
                    summary_caption="Existing card",
                    portrait_caption="Portrait",
                    body_caption="Body reference",
                    front_caption="Clothed front",
                    back_caption="Clothed back",
                )
            )
            layout["summary"] = {
                "canvas": "multi_panel",
                "caption": "Existing four-panel card. These boxes locate editable regions.",
            }
            for item, role in zip(layout["items"], ROLES):
                item["caption"] = "Existing " + role + "."
            layout_json = json.dumps(layout, separators=(",", ":"))
        edit_contract(
            layout_json, width, height, "Portrait", "Validate existing layout."
        )
        return layout_json, width, height

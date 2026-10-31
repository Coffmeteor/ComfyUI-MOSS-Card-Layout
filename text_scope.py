"""Token-exact four-panel scopes for the native MOSS/Qwen3.5 context."""

from __future__ import annotations

from functools import lru_cache
import json
import math
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from transformers import PreTrainedTokenizerBase

import torch

from comfy.text_encoders.moss_image import MOSSImageTokenizer
import comfy.text_encoders.qwen_vl


@lru_cache(maxsize=1)
def offset_tokenizer() -> PreTrainedTokenizerBase:
    return MOSSImageTokenizer().qwen35_9b.tokenizer


def json_fields(source: str, start: int = 0) -> dict:
    """Return exact value character ranges, including JSON escapes/whitespace."""
    decoder = json.JSONDecoder()
    pos = start + 1
    fields = {}
    while True:
        while source[pos].isspace() or source[pos] == ",":
            pos += 1
        if source[pos] == "}":
            return fields
        key, pos = decoder.raw_decode(source, pos)
        while source[pos].isspace():
            pos += 1
        if source[pos] != ":":
            raise ValueError("Expected JSON field separator")
        pos += 1
        while source[pos].isspace():
            pos += 1
        begin = pos
        _, pos = decoder.raw_decode(source, pos)
        fields[key] = (begin, pos)


def scoped_token_spans(tokens: dict, prompt: str) -> dict:
    """Map JSON ranges to the *actual* encoded context, expanding vision patches.

    Retokenization must exactly match native IDs; otherwise refuse to guess spans.
    Tokens intersecting a boundary belong to the scope on either side.
    """
    rows = next(iter(tokens.values()))
    if len(rows) != 1:
        raise ValueError("Panel scopes require one unchunked native token sequence")
    ids, lengths = [], []
    for token, *_ in rows[0]:
        if isinstance(token, dict):
            _, grid = comfy.text_encoders.qwen_vl.process_qwen2vl_images(
                token["data"], patch_size=16
            )
            ids.append(248056)
            lengths.append(int(grid[0, 1] * grid[0, 2]) // 4)
        else:
            ids.append(token)
            lengths.append(1)
    tokenizer = offset_tokenizer()
    rendered = tokenizer.decode(
        ids, skip_special_tokens=False, clean_up_tokenization_spaces=False
    )
    encoded = tokenizer(rendered, add_special_tokens=False, return_offsets_mapping=True)
    if encoded["input_ids"] != ids:
        raise ValueError(
            "Native token IDs differ from offset tokenizer; cannot safely scope text"
        )
    prompt = prompt.strip()
    base = rendered.find(prompt)
    if base < 0 or rendered.find(prompt, base + 1) >= 0:
        raise ValueError("Expected one exact JSON prompt in native context")
    layout = json.loads(prompt)
    if len(layout["items"]) != 4:
        raise ValueError("Panel text scoping requires exactly four JSON items")
    fields = json_fields(prompt)
    pos = fields["items"][0] + 1
    item_chars = []
    for _ in range(4):
        while prompt[pos].isspace() or prompt[pos] == ",":
            pos += 1
        _, end = json.JSONDecoder().raw_decode(prompt, pos)
        item_chars.append((base + pos, base + end))
        pos = end
    summary_begin, _ = fields["summary"]
    caption_begin, caption_end = json_fields(prompt, summary_begin)["caption"]
    # Native catalog and C3 used different privacy sentences. Scope the actual
    # summary sentence(s), not a hard-coded spelling or a reserialized JSON.
    privacy_chars = [
        (base + caption_begin + m.start(), base + caption_begin + m.end())
        for m in re.finditer(
            r'[^".!?]*\bprivacy\b[^".!?]*[.!?]?',
            prompt[caption_begin:caption_end],
            re.IGNORECASE,
        )
    ]
    body_chars = [
        (base + caption_begin + m.start(), base + caption_begin + m.end())
        for m in re.finditer(
            r'[^".!?]*\b(?:no head|headless|neckless)\b[^".!?]*[.!?]?',
            prompt[caption_begin:caption_end],
            re.IGNORECASE,
        )
    ]
    suffix_chars = (item_chars[3][1], len(rendered))
    picture = rendered.find("Picture 1: <|vision_start|>")
    vision_end = rendered.find("<|vision_end|>", picture)
    if picture < 0 or vision_end < 0:
        raise ValueError("Expected one Picture 1 vision span")
    vision_chars = (picture, vision_end + len("<|vision_end|>"))
    offsets = [
        span
        for span, length in zip(encoded["offset_mapping"], lengths)
        for _ in range(length)
    ]

    def intersect(ranges: list[tuple[int, int]]) -> torch.Tensor:
        return torch.tensor(
            [[any(a < end and b > begin for begin, end in ranges) for a, b in offsets]],
            dtype=torch.bool,
        )

    return {
        "vision_span": intersect([vision_chars]),
        "privacy_summary_span": intersect(privacy_chars),
        "body_summary_span": intersect(body_chars),
        "suffix_span": torch.tensor(
            [[a >= suffix_chars[0] for a, _ in offsets]], dtype=torch.bool
        ),
        "item_spans": [intersect([span]) for span in item_chars],
        "character_ranges": {
            "vision": vision_chars,
            "privacy": privacy_chars,
            "body": body_chars,
            "suffix": suffix_chars,
            "items": item_chars,
        },
        "text_len": len(offsets),
    }


def panel_text_masks(
    tokens: dict,
    prompt: str,
    width: int,
    height: int,
    mask_text_self_attention: bool = False,
) -> tuple:
    """Return cross-modal scopes and an optional, explicitly requested text scope.

    Phase 1.6 keeps body-summary and terminal attention-sink tokens shared and
    leaves both TextEmbedder and DiT text-to-text attention entirely native.
    The Phase 2A isolation experiment remains available only by explicit opt-in.
    """
    spans = scoped_token_spans(tokens, prompt)
    vision, privacy, items = (
        spans[k] for k in ("vision_span", "privacy_summary_span", "item_spans")
    )
    length = spans["text_len"]
    shared = ~(vision | privacy | torch.stack(items).any(0))
    # Compact JSON can merge `},{` across adjacent items into one BPE token.
    # Blocking the other item wins for these structural boundary tokens.
    exclusive = [
        item & ~(torch.stack(items[:i] + items[i + 1 :]).any(0))
        for i, item in enumerate(items)
    ]
    spans["item_exclusive_spans"] = exclusive
    body, suffix = spans["body_summary_span"], spans["suffix_span"]
    common = shared & ~(body | suffix) if mask_text_self_attention else shared
    p0_group = common | vision | exclusive[0]
    spans["common_prefix"] = common
    spans["text_to_ref_mask"] = p0_group
    text_allow = None
    if mask_text_self_attention:
        text_allow = common[:, None, :].expand(1, length, length).clone()
        text_allow[0, p0_group[0]] = p0_group
        for i in (1, 2, 3):
            text_allow[0, exclusive[i][0]] = (
                common | body | exclusive[i] | suffix | (privacy if i == 1 else False)
            )
        text_allow[0, (body | suffix)[0]] = (
            common | body | exclusive[1] | exclusive[2] | exclusive[3] | suffix
        )
        text_allow[0, privacy[0]] = common | body | privacy | exclusive[1] | suffix
    h, w = height // 16, width // 16
    image_allow = common[:, None, :].expand(1, h * w, length).clone()
    for i, item in enumerate(json.loads(prompt)["items"]):
        by0, bx0, by1, bx1 = item["bbox"]
        y0, x0 = int((by0 + height // 2) // 16), int((bx0 + width // 2) // 16)
        y1, x1 = math.ceil((by1 + height // 2) / 16), math.ceil((bx1 + width // 2) / 16)
        if not (0 <= y0 < y1 <= h and 0 <= x0 < x1 <= w):
            raise ValueError("Panel bbox must be inside the canvas")
        keys = (
            p0_group
            if i == 0
            else common | body | exclusive[i] | suffix | (privacy if i == 1 else False)
        )
        image_allow.reshape(1, h, w, length)[:, y0:y1, x0:x1] = keys
    return image_allow, text_allow, spans

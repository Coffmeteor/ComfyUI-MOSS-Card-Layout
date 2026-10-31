"""Experimental independent panel conditioning through Comfy's native area sampler.

No face pixels are inserted or frozen. Each area has separately encoded text and
reference conditions. The native sampler crops model inputs per area at every
step, accumulates their predictions on one canvas, and runs one Euler update.
"""

from __future__ import annotations

import json
import math


def make_plan(
    layout_json: str, width: int, height: int, latent_width: int, latent_height: int
) -> dict:
    if any(
        type(v) is not int or v <= 0
        for v in (width, height, latent_width, latent_height)
    ):
        raise ValueError("Canvas and latent dimensions must be positive integers")
    if width % latent_width or height % latent_height:
        raise ValueError("The canvas must have an integer pixel-to-latent scale")
    sx, sy = width // latent_width, height // latent_height
    layout = json.loads(layout_json)
    if (
        layout.get("bbox_format") != "yxyx"
        or layout.get("bbox_coord_space") != "abs_centralized"
    ):
        raise ValueError("Use absolute centralized yxyx JSON boxes")
    items = layout.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 16:
        raise ValueError("Use between one and sixteen independent regions")
    regions = []
    for i, item in enumerate(items):
        box = item.get("bbox")
        if (
            not isinstance(box, list)
            or len(box) != 4
            or any(type(v) is not int for v in box)
        ):
            raise ValueError("Every bbox must contain four integer coordinates")
        by0, bx0, by1, bx1 = box
        x0, y0, x1, y1 = (
            bx0 + width // 2,
            by0 + height // 2,
            bx1 + width // 2,
            by1 + height // 2,
        )
        if not 0 <= x0 < x1 <= width or not 0 <= y0 < y1 <= height:
            raise ValueError("A region lies outside the canvas")
        lx0, ly0 = x0 // sx, y0 // sy
        lx1, ly1 = math.ceil(x1 / sx), math.ceil(y1 / sy)
        for other in regions:
            ox0, oy0, ox1, oy1 = other["latent"]
            if max(lx0, ox0) < min(lx1, ox1) and max(ly0, oy0) < min(ly1, oy1):
                raise ValueError(
                    "Independent regions overlap on the latent grid; leave a gutter or align their edges"
                )
        caption = item.get("caption")
        if not isinstance(caption, str) or not caption.strip():
            raise ValueError("Each region needs its own nonempty caption")
        px0, py0, px1, py1 = lx0 * sx, ly0 * sy, lx1 * sx, ly1 * sy
        rw, rh = px1 - px0, py1 - py0
        local_item = dict(
            item,
            bbox=[
                y0 - py0 - rh // 2,
                x0 - px0 - rw // 2,
                y1 - py0 - rh // 2,
                x1 - px0 - rw // 2,
            ],
        )
        # Never inherit the full-card summary: it contains other regions' roles.
        local = dict(
            summary={"canvas": "single", "caption": caption.strip()},
            items=[local_item],
            bbox_format="yxyx",
            bbox_coord_space="abs_centralized",
        )
        regions.append(
            dict(
                index=i,
                latent=[lx0, ly0, lx1, ly1],
                pixels=[px0, py0, px1, py1],
                prompt=json.dumps(local, ensure_ascii=False, separators=(",", ":")),
            )
        )
    return dict(
        canvas=[width, height],
        latent_size=[latent_width, latent_height],
        scale=[sx, sy],
        regions=regions,
    )


def bind_area(conditioning: list, region: dict, latent_size: list[int]) -> list:
    import torch

    x0, y0, x1, y1 = region["latent"]
    w, h = latent_size
    result = []
    for tokens, metadata in conditioning:
        if any(k in metadata for k in ("area", "mask", "control", "gligen")):
            raise ValueError(
                "Region inputs must be unscoped conditions without spatial ControlNet/GLIGEN"
            )
        # An explicit unit mask prevents native area edge feathering. Disjoint
        # regions then have exact weight one, matching a standalone invocation.
        result.append(
            [
                tokens,
                dict(
                    metadata,
                    area=(y1 - y0, x1 - x0, y0, x0),
                    mask=torch.ones((1, h, w)),
                    mask_strength=1.0,
                    strength=1.0,
                    set_area_to_bounds=False,
                ),
            ]
        )
    return result


def group_plan(
    plan: dict, groups: list, caption: str, top_margin=0.0, bottom_margin=0.0
) -> dict:
    """Group related views without exposing them to unrelated region conditions.

    Panel frames stay fixed. Insets apply only to subject boxes inside a merged
    group, and are fractions of its height rounded to the actual latent grid.
    Singleton prompts and coordinates are preserved exactly.
    """
    source = plan["regions"]
    if (
        not isinstance(groups, list)
        or not groups
        or any(not isinstance(g, list) or not g for g in groups)
    ):
        raise ValueError("Groups must be nonempty lists of region indices")
    indices = [i for g in groups for i in g]
    if any(type(i) is not int for i in indices) or sorted(indices) != list(
        range(len(source))
    ):
        raise ValueError("Groups must partition every region exactly once")
    if not 0 <= top_margin <= 0.25 or not 0 <= bottom_margin <= 0.25:
        raise ValueError("Subject margins must be fractions between zero and 0.25")
    sx, sy = plan["scale"]
    result = []
    for group in groups:
        selected = [source[i] for i in group]
        x0 = min(r["latent"][0] for r in selected)
        y0 = min(r["latent"][1] for r in selected)
        x1 = max(r["latent"][2] for r in selected)
        y1 = max(r["latent"][3] for r in selected)
        if any(
            max(x0, r["latent"][0]) < min(x1, r["latent"][2])
            and max(y0, r["latent"][1]) < min(y1, r["latent"][3])
            for r in result
        ):
            raise ValueError(
                "Group envelopes overlap; keep unrelated regions outside each other"
            )
        px0, py0, px1, py1 = x0 * sx, y0 * sy, x1 * sx, y1 * sy
        if len(group) == 1:
            prompt = selected[0]["prompt"]
        else:
            if not isinstance(caption, str) or not caption.strip():
                raise ValueError("Describe the shared scene for the grouped views")
            items = []
            for region in selected:
                rx0, ry0, rx1, ry1 = region["pixels"]
                for original in json.loads(region["prompt"])["items"]:
                    item = dict(original)
                    by0, bx0, by1, bx1 = item["bbox"]
                    dx = rx0 + (rx1 - rx0) // 2 - px0 - (px1 - px0) // 2
                    dy = ry0 + (ry1 - ry0) // 2 - py0 - (py1 - py0) // 2
                    top = round((py1 - py0) * top_margin / sy) * sy
                    bottom = round((py1 - py0) * bottom_margin / sy) * sy
                    item["bbox"] = [
                        by0 + dy + top,
                        bx0 + dx,
                        by1 + dy - bottom,
                        bx1 + dx,
                    ]
                    if item["bbox"][0] >= item["bbox"][2]:
                        raise ValueError(
                            "Subject margins remove the complete subject box"
                        )
                    items.append(item)
            prompt = json.dumps(
                dict(
                    summary=dict(canvas="multi_panel", caption=caption.strip()),
                    items=items,
                    bbox_format="yxyx",
                    bbox_coord_space="abs_centralized",
                ),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        result.append(
            dict(
                index=len(result),
                latent=[x0, y0, x1, y1],
                pixels=[px0, py0, px1, py1],
                source_indices=group,
                prompt=prompt,
            )
        )
    return dict(plan, regions=result)


class MOSSRegionalGroupPlan:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "plan": ("MOSS_REGION_PLAN",),
                "groups_json": ("STRING", {"default": "[[0],[1,2,3]]"}),
                "shared_caption": ("STRING", {"default": "", "multiline": True}),
                "subject_top_margin": (
                    "FLOAT",
                    {"default": 0.06, "min": 0, "max": 0.25, "step": 0.01},
                ),
                "subject_bottom_margin": (
                    "FLOAT",
                    {"default": 0.04, "min": 0, "max": 0.25, "step": 0.01},
                ),
            }
        }

    RETURN_TYPES = ("MOSS_REGION_PLAN", "STRING")
    RETURN_NAMES = ("grouped_plan", "grouped_json_preview")
    FUNCTION = "build"
    CATEGORY = "MOSS-Image/Experimental Regional Sampling"

    def build(
        self,
        plan,
        groups_json,
        shared_caption,
        subject_top_margin,
        subject_bottom_margin,
    ):
        grouped = group_plan(
            plan,
            json.loads(groups_json),
            shared_caption,
            subject_top_margin,
            subject_bottom_margin,
        )
        return grouped, json.dumps(grouped, ensure_ascii=False, indent=2)


class MOSSRegionalPlaceLatent:
    """Place a whole newly generated region on its planned canvas, without resizing."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "canvas_latent": ("LATENT",),
                "region_samples": ("LATENT",),
                "plan": ("MOSS_REGION_PLAN",),
                "region_index": ("INT", {"default": 0, "min": 0, "max": 15}),
            }
        }

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "place"
    CATEGORY = "MOSS-Image/Experimental Regional Sampling"

    def place(self, canvas_latent, region_samples, plan, region_index):
        z = canvas_latent["samples"]
        patch = region_samples["samples"]
        if "noise_mask" in canvas_latent or "noise_mask" in region_samples:
            raise ValueError(
                "Place a complete generated region, without a protection mask"
            )
        if not 0 <= region_index < len(plan["regions"]):
            raise ValueError("Region index is outside the plan")
        x0, y0, x1, y1 = plan["regions"][region_index]["latent"]
        if (
            z.ndim != 4
            or list(z.shape[-2:]) != plan["latent_size"][::-1]
            or z.shape[0] != 1
        ):
            raise ValueError("Canvas must match the regional plan")
        if tuple(patch.shape) != (1, z.shape[1], y1 - y0, x1 - x0):
            raise ValueError("Generated region dimensions must match its box exactly")
        result = z.clone()
        result[:, :, y0:y1, x0:x1] = patch.to(device=z.device, dtype=z.dtype)
        return (dict(canvas_latent, samples=result),)


class MOSSRegionalPlan:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "layout_json": ("STRING", {"forceInput": True}),
                "canvas_width": ("INT", {"forceInput": True}),
                "canvas_height": ("INT", {"forceInput": True}),
                "canvas_latent": ("LATENT",),
            }
        }

    RETURN_TYPES = ("MOSS_REGION_PLAN", "STRING")
    RETURN_NAMES = ("region_plan", "region_json_preview")
    FUNCTION = "build"
    CATEGORY = "MOSS-Image/Experimental Regional Sampling"

    def build(self, layout_json, canvas_width, canvas_height, canvas_latent):
        z = canvas_latent["samples"]
        if z.ndim != 4 or z.shape[0] != 1 or "noise_mask" in canvas_latent:
            raise ValueError(
                "Use one unmasked canvas latent; face protection masks are not part of this route"
            )
        plan = make_plan(
            layout_json, canvas_width, canvas_height, z.shape[-1], z.shape[-2]
        )
        return plan, json.dumps(plan, ensure_ascii=False, indent=2)


class MOSSRegionalEncode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "plan": ("MOSS_REGION_PLAN",),
                "region_index": ("INT", {"default": 0, "min": 0, "max": 15}),
                "prompt_format": (["Region JSON", "Edit instruction"],),
            },
            "optional": {
                "reference_image": ("IMAGE",),
                "previous_regions": ("MOSS_REGION_CONDS",),
                "edit_instruction": ("STRING", {"multiline": True, "default": ""}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("MOSS_REGION_CONDS", "STRING")
    RETURN_NAMES = ("region_conditions", "exact_region_prompt")
    FUNCTION = "encode"
    CATEGORY = "MOSS-Image/Experimental Regional Sampling"

    def encode(
        self,
        clip,
        vae,
        plan,
        region_index,
        prompt_format,
        reference_image=None,
        previous_regions=None,
        edit_instruction="",
        negative_prompt="",
    ):
        from comfy_extras.nodes_moss_image import TextEncodeMOSSImageEdit

        if not 0 <= region_index < len(plan["regions"]):
            raise ValueError("Region index is outside the plan")
        prompt = (
            plan["regions"][region_index]["prompt"]
            if prompt_format == "Region JSON"
            else edit_instruction.strip()
        )
        if not prompt:
            raise ValueError("Enter the scoped edit instruction")
        if reference_image is not None:
            if reference_image.shape[0] != 1:
                raise ValueError("Use one reference for this region")
            pos, neg = [
                TextEncodeMOSSImageEdit.execute(
                    clip=clip,
                    prompt=p,
                    edit_format="ai-toolkit",
                    images={"image_0": reference_image},
                    vae=vae,
                    image_strength=1.0,
                )[0]
                for p in (prompt, negative_prompt)
            ]
        else:
            pos, neg = [
                clip.encode_from_tokens_scheduled(clip.tokenize(p))
                for p in (prompt, negative_prompt)
            ]
        previous = list(previous_regions or [])
        if any(r["index"] == region_index for r in previous):
            raise ValueError("A region was conditioned twice")
        # Compare geometry rather than captions so nuisance-prompt variants can
        # reuse exactly the same portrait conditions without cross-encoding.
        geometry = [plan["canvas"], [r["latent"] for r in plan["regions"]]]
        if any(r["geometry"] != geometry for r in previous):
            raise ValueError("All conditions must use the same region geometry")
        previous.append(
            dict(
                index=region_index,
                positive=pos,
                negative=neg,
                geometry=geometry,
                prompt=prompt,
                negative_prompt=negative_prompt,
            )
        )
        return previous, prompt


class MOSSRegionalSampler:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "canvas_latent": ("LATENT",),
                "plan": ("MOSS_REGION_PLAN",),
                "regions": ("MOSS_REGION_CONDS",),
                "mode": (["Canvas", "Single region"],),
                "trace_region": ("INT", {"default": 0, "min": 0, "max": 15}),
                "seed": ("INT", {"default": 42, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "steps": ("INT", {"default": 50, "min": 1, "max": 1000}),
                "cfg": ("FLOAT", {"default": 3.0, "min": 1, "max": 20}),
            }
        }

    RETURN_TYPES = ("LATENT", "MOSS_REGION_TRACE", "LATENT", "STRING")
    RETURN_NAMES = ("samples", "region_trace", "trace_tensors", "trace_metadata")
    FUNCTION = "sample"
    CATEGORY = "MOSS-Image/Experimental Regional Sampling"

    def sample(
        self, model, canvas_latent, plan, regions, mode, trace_region, seed, steps, cfg
    ):
        import torch
        import comfy.sample
        import comfy.samplers
        import latent_preview

        z = canvas_latent["samples"]
        if (
            "noise_mask" in canvas_latent
            or z.shape[0] != 1
            or list(z.shape[-2:]) != plan["latent_size"][::-1]
        ):
            raise ValueError("Use the unmasked canvas latent bound to this region plan")
        if not 0 <= trace_region < len(plan["regions"]):
            raise ValueError("Trace region is outside the plan")
        indexed = {r["index"]: r for r in regions}
        expected = (
            set(range(len(plan["regions"]))) if mode == "Canvas" else {trace_region}
        )
        if not expected <= indexed.keys() or len(indexed) != len(regions):
            raise ValueError(
                "Every sampled region needs exactly one independent condition pair"
            )
        geometry = [plan["canvas"], [r["latent"] for r in plan["regions"]]]
        if any(r["geometry"] != geometry for r in regions):
            raise ValueError("Condition geometry does not match the sampling plan")
        noise = comfy.sample.prepare_noise(z, seed)
        x0, y0, x1, y1 = plan["regions"][trace_region]["latent"]
        if mode == "Single region":
            noise = noise[:, :, y0:y1, x0:x1].contiguous()
            z = z[:, :, y0:y1, x0:x1].contiguous()
            positive, negative = (
                indexed[trace_region]["positive"],
                indexed[trace_region]["negative"],
            )
            mask = None
            trace_box = [0, 0, x1 - x0, y1 - y0]
        elif mode == "Canvas":
            positive, negative = [], []
            mask = torch.zeros((1, z.shape[-2], z.shape[-1]))
            for index in sorted(expected):
                region = plan["regions"][index]
                positive += bind_area(
                    indexed[index]["positive"], region, plan["latent_size"]
                )
                negative += bind_area(
                    indexed[index]["negative"], region, plan["latent_size"]
                )
                a, b, c, d = region["latent"]
                mask[:, b:d, a:c] = 1
            trace_box = [x0, y0, x1, y1]
        else:
            raise ValueError("Select Canvas or Single region")
        sigmas = comfy.samplers.calculate_sigmas(
            model.get_model_object("model_sampling"), "normal", steps
        ).cpu()
        frames = []
        preview = latent_preview.prepare_callback(model, steps)

        def callback(step, denoised, state, total_steps):
            a, b, c, d = trace_box
            frames.extend(
                (
                    state[:, :, b:d, a:c].detach().float().cpu().clone(),
                    denoised[:, :, b:d, a:c].detach().float().cpu().clone(),
                )
            )
            preview(step, denoised, state, total_steps)

        output = comfy.sample.sample_custom(
            model,
            noise,
            cfg,
            comfy.samplers.sampler_object("euler"),
            sigmas,
            positive,
            negative,
            z,
            noise_mask=mask,
            callback=callback,
            seed=seed,
        )
        a, b, c, d = trace_box
        frames.append(output[:, :, b:d, a:c].detach().float().cpu().clone())
        trace = torch.cat(frames, dim=0)
        metadata = dict(
            mode=mode,
            seed=seed,
            steps=steps,
            cfg=cfg,
            sampler="euler",
            scheduler="normal",
            sigmas=sigmas.tolist(),
            trace_region=trace_region,
            ordering="For each step: state before Euler update, then denoised prediction; final frame is the returned final latent",
            full_canvas=plan["canvas"],
            region_pixels=plan["regions"][trace_region]["pixels"],
        )
        return (
            {"samples": output},
            dict(tensors=trace, metadata=metadata),
            {"samples": trace},
            json.dumps(metadata),
        )


class MOSSCompareRegionTraces:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "baseline": ("MOSS_REGION_TRACE",),
                "candidate": ("MOSS_REGION_TRACE",),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "compare"
    CATEGORY = "MOSS-Image/Experimental Regional Sampling"

    def compare(self, baseline, candidate):
        import torch

        a, b = baseline["tensors"], candidate["tensors"]
        steps = baseline["metadata"]["steps"]
        if (
            a.shape != b.shape
            or a.shape[0] != 2 * steps + 1
            or baseline["metadata"]["sigmas"] != candidate["metadata"]["sigmas"]
        ):
            raise ValueError(
                "Compare matching region shapes and exact time coordinates"
            )
        diffs = (a - b).abs().flatten(1).amax(1)
        return (
            json.dumps(
                dict(
                    exact_equal=torch.equal(a, b),
                    max_abs=float(diffs.max()),
                    final_latent_max_abs=float(diffs[-1]),
                    step_count=steps,
                    per_step=[
                        dict(
                            step=i,
                            state_max_abs=float(diffs[2 * i]),
                            denoised_max_abs=float(diffs[2 * i + 1]),
                        )
                        for i in range(steps)
                    ],
                    baseline=baseline["metadata"],
                    candidate=candidate["metadata"],
                ),
                indent=2,
            ),
        )


class MOSSRegionalDecode:
    """Decode each logical photograph independently, including VAE attention/norms.

    This is region isolation, not memory-driven VAE tiling: each call uses the native
    full decoder at that photograph's dimensions. Only newly generated latents are
    decoded; no original identity photograph supplies output pixels.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "vae": ("VAE",),
                "samples": ("LATENT",),
                "plan": ("MOSS_REGION_PLAN",),
                "gutter_color": (
                    "INT",
                    {"default": 0xC8C8C8, "min": 0, "max": 0xFFFFFF},
                ),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "decode"
    CATEGORY = "MOSS-Image/Experimental Regional Sampling"

    def decode(self, vae, samples, plan, gutter_color):
        import torch

        z = samples["samples"]
        if list(z.shape[-2:]) != plan["latent_size"][::-1] or z.shape[0] != 1:
            raise ValueError(
                "Decode the complete latent canvas associated with this plan"
            )
        width, height = plan["canvas"]
        color = (
            torch.tensor(
                [(gutter_color >> shift) & 255 for shift in (16, 8, 0)],
                dtype=torch.float32,
            )
            / 255
        )
        canvas = color.reshape(1, 1, 1, 3).expand(1, height, width, 3).clone()
        for region in plan["regions"]:
            x0, y0, x1, y1 = region["latent"]
            px0, py0, px1, py1 = region["pixels"]
            image = vae.decode(z[:, :, y0:y1, x0:x1].contiguous()).cpu()
            if tuple(image.shape) != (1, py1 - py0, px1 - px0, 3):
                raise ValueError(
                    "The native VAE output dimensions differ from the region plan"
                )
            canvas[:, py0:py1, px0:px1] = image
        return (canvas,)

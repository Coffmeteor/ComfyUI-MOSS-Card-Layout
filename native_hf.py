"""Load an existing unquantized MOSS HF snapshot into ComfyUI's native models.

Only file packaging/key prefixes change. Reference encoding, transformer forward,
sampling and memory management remain the ComfyUI 0.43 implementations.
"""
from __future__ import annotations

import json
from pathlib import Path
import torch
from comfy import sd, utils


def read_component(root: Path, name: str, stem: str) -> dict:
    directory = (root / name).resolve()
    index = directory / f"{stem}.safetensors.index.json"
    if not index.exists():
        return utils.load_torch_file(str(directory / f"{stem}.safetensors"), safe_load=True)
    mapping = json.loads(index.read_text())["weight_map"]
    state = {}
    for filename in sorted(set(mapping.values())):
        path = (directory / filename).resolve()
        if not path.is_relative_to(directory):
            raise ValueError("Shard path escapes its component directory")
        shard = utils.load_torch_file(str(path), safe_load=True)
        if set(shard) != {key for key, value in mapping.items() if value == filename}:
            raise ValueError(f"Shard/index mismatch: {filename}")
        state.update(shard)
    return state


def load_model(root: str):
    state = read_component(Path(root), "transformer", "diffusion_pytorch_model")
    available = set(state)
    model = sd.load_diffusion_model_state_dict(state, model_options={"dtype": torch.bfloat16})
    if model is None or type(model.model.diffusion_model).__module__ != "comfy.ldm.moss_image.model":
        raise ValueError("ComfyUI 0.43+ native MOSS support is required")
    missing = set(dict(model.model.diffusion_model.named_parameters())) - available
    if missing:
        raise ValueError(f"Missing native transformer parameters: {sorted(missing)}")
    model.cached_patcher_init = (load_model, (root,))
    return model


def load_clip(root: str):
    state = read_component(Path(root), "text_encoder", "model")
    # The original MOSS snapshot stores Qwen's encoder without its unused
    # autoregressive vocabulary head/MTP. Do not synthesize absent weights.
    has_head = "lm_head.weight" in state
    available = {
        "model." + key[len("language_model."):] if key.startswith("language_model.")
        else key for key in state
    }
    native_state = {
        "model." + key if key.startswith(("language_model.", "visual.")) else key: value
        for key, value in state.items()
    }
    clip = sd.load_text_encoder_state_dicts(
        [native_state], clip_type=sd.CLIPType.MOSS_IMAGE,
        model_options={"qwen35_9b_model_config": {"lm_head": has_head}},
    )
    expected = {
        key.removeprefix("qwen35_9b.transformer.")
        for key, _ in clip.cond_stage_model.named_parameters()
        if key.startswith("qwen35_9b.transformer.")
    }
    if expected - available:
        raise ValueError(f"Missing native encoder parameters: {sorted(expected - available)}")
    clip.patcher.cached_patcher_init = (load_clip_patcher, (root,))
    return clip


def load_clip_patcher(root: str):
    return load_clip(root).patcher


class MOSSNativeHFLoader:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model_path": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("MODEL", "CLIP", "VAE")
    FUNCTION = "load"
    CATEGORY = "MOSS-Image/Native"

    def load(self, model_path: str):
        root = Path(model_path).expanduser().resolve(strict=True)
        config = json.loads((root / "transformer/config.json").read_text())
        if config.get("_class_name") not in {"MOSImageTransformer", "MOSSImageTransformer"}:
            raise ValueError("Expected an original MOSS HF snapshot")
        model = load_model(str(root))
        clip = load_clip(str(root))
        vae = sd.VAE(sd=read_component(root, "vae", "diffusion_pytorch_model"), dtype=torch.float32)
        vae.throw_exception_if_invalid()
        return model, clip, vae



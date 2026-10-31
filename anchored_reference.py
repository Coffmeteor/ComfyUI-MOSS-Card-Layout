"""Single-pass reference conditioning; canvas latents remain pure noise."""

from __future__ import annotations

import json
import math
import inspect
import logging
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

import torch
import comfy.utils
import comfy.text_encoders.qwen_vl
from comfy.ldm.moss_image.model import MOSSImage
from .text_scope import panel_text_masks
from .reference_assets import default_model_path, ensure_landmarker
import node_helpers
from comfy_api.latest import io
from comfy_extras.nodes_moss_image import TextEncodeMOSSImageEdit


_FRAMING_LOCK = threading.Lock()

LANDMARK_MODEL = default_model_path()


def detect_portrait_landmarks(rgb):
    """MediaPipe IMAGE mode; return original-pixel coordinates or no detection.

    The shared model is fetched once with pinned size and SHA-256 verification.
    """
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions

    ensure_landmarker(LANDMARK_MODEL)
    options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(LANDMARK_MODEL)), num_faces=1
    )
    with FaceLandmarker.create_from_options(options) as detector:
        result = detector.detect(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        )
    if not result.face_landmarks:
        return None
    return np.array(
        [(p.x * rgb.shape[1], p.y * rgb.shape[0]) for p in result.face_landmarks[0]]
    )


def portrait_color_evidence(rgb: np.ndarray, points: np.ndarray, d: float) -> dict:
    """Learn background, skin and hair colors from this image; no named hues.

    Landmark 10 bounds the face, not necessarily the hairline. When the bangs
    strip is mostly skin, extend upward to find hair rather than fitting skin.
    Five brightness strata retain both hair shadows and highlights.
    """
    import cv2
    import numpy as np

    h, w = rgb.shape[:2]
    pixels = rgb.astype(np.float32)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    hue, sat, val = hsv.transpose(2, 0, 1)
    k = min(max(8, round(0.05 * min(h, w))), h, w)
    ks = max(3, int(round(0.01 * min(h, w))) | 1)
    corners = np.concatenate(
        (pixels[:k, :k].reshape(-1, 3), pixels[:k, -k:].reshape(-1, 3))
    )
    border_bg = np.median(corners, axis=0)
    mean = cv2.blur(pixels, (ks, ks))
    variance = np.maximum(cv2.blur(pixels * pixels, (ks, ks)) - mean * mean, 0).mean(2)
    border_match = np.linalg.norm(pixels - border_bg, axis=2) < 20
    studio_bg = border_match & (variance < 18**2) & (corners.std(axis=0).max() < 18)
    skin_like = np.zeros((h, w), dtype=bool)
    radius = max(1, round(0.035 * d))
    for index in (1, 4, 9):
        x, y = np.rint(points[index]).astype(int)
        sample = pixels[
            max(0, y - radius) : min(h, y + radius + 1),
            max(0, x - radius) : min(w, x + radius + 1),
        ]
        if sample.size:
            color = np.median(sample.reshape(-1, 3), axis=0)
            skin_like |= np.linalg.norm(pixels - color, axis=2) < 35
    # Blonde/light hair can share RGB values with skin. Skin-color exclusion is
    # meaningful only inside the detected face, not across the hair silhouette.
    facial_hull = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(facial_hull, cv2.convexHull(points[:468].astype(np.int32)), 1)
    skin_like &= facial_hull.astype(bool)
    eyes = points[[33, 133, 362, 263]].mean(0)
    forehead = points[10, 1]
    yy, xx = np.mgrid[:h, :w]
    strip = (
        (abs(xx - eyes[0]) < 0.35 * d)
        & (yy >= forehead - 0.08 * d)
        & (yy < forehead + 0.27 * d)
    )
    candidates = strip & ~skin_like & ~studio_bg
    if (skin_like & strip).sum() >= 0.25 * strip.sum() and (
        ~studio_bg & strip
    ).sum() >= 0.25 * strip.sum():
        strip = (
            (abs(xx - eyes[0]) < 0.35 * d)
            & (yy >= forehead - 0.35 * d)
            & (yy < forehead + 0.27 * d)
        )
        candidates = strip & ~skin_like & ~studio_bg
    samples = pixels[candidates]
    hair_match = np.zeros((h, w), dtype=bool)
    hair_core = np.zeros_like(hair_match)
    palette = []
    if len(samples):
        brightness = samples.max(1)
        edges = np.quantile(brightness, np.linspace(0, 1, 6))
        for lo, hi in zip(edges[:-1], edges[1:]):
            group = samples[(brightness >= lo) & (brightness <= hi)]
            if len(group):
                palette.append(np.median(group, axis=0))
        colors = cv2.cvtColor(
            np.rint(palette).astype(np.uint8).reshape(-1, 1, 3), cv2.COLOR_RGB2HSV
        )[:, 0]
        for hair_hue, hair_sat, hair_val in colors.astype(float):
            hue_distance = np.minimum(abs(hue - hair_hue), 180 - abs(hue - hair_hue))
            # Hue becomes unreliable at low saturation or near black.
            hue_reliable = (np.minimum(sat, hair_sat) >= 20) & (
                np.minimum(val, hair_val) >= 40
            )
            hair_match |= (
                (~hue_reliable | (hue_distance <= 18))
                & (abs(sat - hair_sat) <= 80)
                & (abs(val - hair_val) <= 75)
            )
            hair_core |= (
                (~hue_reliable | (hue_distance <= 10))
                & (abs(sat - hair_sat) <= 60)
                & (abs(val - hair_val) <= 50)
            )
        # Independent HSV boxes otherwise accept colors between the hair modes
        # (e.g. a pale occluder with a different channel correlation). Retain the
        # measured RGB covariance as well as shadows/highlights in the palette.
        center = np.median(samples, axis=0)
        covariance = np.cov(samples.T) if len(samples) > 1 else np.zeros((3, 3))
        inverse = np.linalg.inv(covariance + np.eye(3) * 8**2)
        delta = pixels - center
        color_score = np.einsum("...i,ij,...j->...", delta, inverse, delta)
        fit_delta = samples - center
        fit_score = np.einsum("ni,ij,nj->n", fit_delta, inverse, fit_delta)
        color_limit = max(9.0, 1.5 * float(np.quantile(fit_score, 0.99)))
        hair_match &= color_score <= color_limit
        hair_core &= color_score <= color_limit
    texture_limit = (
        max(18**2, 4 * float(np.quantile(variance[candidates], 0.95)))
        if candidates.any()
        else 18**2
    )
    foreign = ~studio_bg & (~hair_match | (variance > texture_limit))
    return dict(
        studio_bg=studio_bg,
        border_match=border_match,
        hair_match=hair_match,
        hair_core=hair_core,
        skin_like=skin_like,
        foreign=foreign,
        palette=palette,
        corner_patch=k,
        blur_kernel=ks,
    )


def suppress_portrait_headwear(rgb, points, eye_distance):
    """Feather only non-hair crown/background; the detected facial hull is protected.

    Image-derived color distributions are a heuristic, not semantic segmentation.
    Hair-colored pixels connected to the bangs survive beyond the crown ellipse.
    """
    import cv2
    import numpy as np

    h, w = rgb.shape[:2]
    d = eye_distance
    eyes = points[[33, 133, 362, 263]].mean(0)
    forehead = points[10, 1]
    yy, xx = np.mgrid[:h, :w]
    evidence = portrait_color_evidence(rgb, points, d)
    above_brow = yy < eyes[1] - 0.18 * d
    crown = ((xx - eyes[0]) / (1.18 * d)) ** 2 + (
        (yy - (eyes[1] - 0.15 * d)) / (1.22 * d)
    ) ** 2 < 1
    protected = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(protected, cv2.convexHull(points[:468].astype(np.int32)), 1)
    # GrabCut regularizes the color evidence into a continuous silhouette instead
    # of punching holes in blonde highlights or removing individual fine bangs.
    gc = np.full((h, w), cv2.GC_PR_FGD, np.uint8)
    gc[above_brow] = cv2.GC_PR_BGD
    gc[evidence["studio_bg"]] = cv2.GC_BGD
    gc[above_brow & evidence["foreign"]] = cv2.GC_BGD
    hair_seed = evidence["hair_core"] & ~evidence["skin_like"]
    hair_seed &= crown & (yy >= forehead - 0.55 * d) & (yy < eyes[1])
    gc[hair_seed] = cv2.GC_FGD
    gc[protected.astype(bool)] = cv2.GC_FGD
    with _FRAMING_LOCK:
        cv2.setRNGSeed(0)
        cv2.grabCut(
            rgb,
            gc,
            None,
            np.zeros((1, 65)),
            np.zeros((1, 65)),
            5,
            cv2.GC_INIT_WITH_MASK,
        )
    keep = ((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)).astype(np.uint8)
    # Fill enclosed highlight/forehead holes, without growing across the boundary.
    contours, _ = cv2.findContours(keep, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    solid = np.zeros_like(keep)
    cv2.drawContours(solid, contours, -1, 1, cv2.FILLED)
    # Retain only the silhouette attached to the face; isolated lace specks vanish.
    _, components = cv2.connectedComponents(solid)
    face_ids = np.unique(components[protected.astype(bool)])
    solid = np.isin(components, face_ids[face_ids != 0])
    # Preserve hair-matching fine curls beside the eyebrows, which the graph cut
    # can disconnect from the head. This zone starts below the crown decoration.
    fine_hair = evidence["hair_core"] & ~evidence["skin_like"]
    fine_hair &= yy > forehead + 0.25 * d
    _, detail_labels = cv2.connectedComponents((solid | fine_hair).astype(np.uint8))
    attached = np.unique(detail_labels[protected.astype(bool)])
    fine_hair &= np.isin(detail_labels, attached[attached != 0])
    remove = above_brow & ~solid & ~fine_hair
    # Outside the crown, only backdrop connected to an image border is removed.
    # This preserves source gloves, shoulders, clothing and the fine side curls.
    background = (
        evidence["border_match"] & ~evidence["hair_match"] & ~evidence["skin_like"]
    )
    _, bg_labels = cv2.connectedComponents(background.astype(np.uint8))
    border_ids = np.unique(
        np.concatenate((bg_labels[0], bg_labels[-1], bg_labels[:, 0], bg_labels[:, -1]))
    )
    remove |= np.isin(bg_labels, border_ids[border_ids != 0])
    remove[protected.astype(bool)] = False
    # Feather into the replaced side only: preserved facial/hair pixels stay exact.
    distance = cv2.distanceTransform(remove.astype(np.uint8), cv2.DIST_L2, 5)
    alpha = np.clip(distance / max(1.0, 0.022 * d), 0, 1)
    alpha[background & remove] = 1.0
    alpha[protected.astype(bool)] = 0
    neutral = np.array([218, 214, 208], dtype=np.float32)
    out = np.rint(rgb * (1 - alpha[..., None]) + neutral * alpha[..., None]).astype(
        np.uint8
    )
    return out, alpha


def eye_geometry(points: np.ndarray) -> list[dict]:
    """Viewer-left/right corner widths and mean vertical palpebral apertures."""
    return [
        {
            "center": points[[outer, inner]].mean(0),
            "width": float(abs(points[inner, 0] - points[outer, 0])),
            "height": float(points[lower, 1].mean() - points[upper, 1].mean()),
            "lid_mid_y": float((points[lower, 1].mean() + points[upper, 1].mean()) / 2),
        }
        for outer, inner, upper, lower in (
            (33, 133, [159, 158, 160], [145, 153, 144]),
            (263, 362, [386, 385, 387], [374, 380, 373]),
        )
    ]


def equalize_eye_symmetry(
    rgb: np.ndarray, points: np.ndarray, target_mid: np.ndarray, target_dist: float
) -> tuple[np.ndarray, dict]:
    """Inverse local affine maps with exact eye cores and smooth compact tails.

    OpenCV remap samples source coordinates for each destination pixel. A flat
    core is necessary: a Gaussian alone attenuates the corner/lid constraints.
    The Gaussian tails taper to zero before the nose and outside the eye band.
    Use the already transformed landmarks, avoiding a second detector's drift.
    """
    import cv2
    import numpy as np

    eyes = eye_geometry(points)
    if any(
        not np.isfinite([*e["center"], e["width"], e["height"], e["lid_mid_y"]]).all()
        or e["width"] < 1
        or e["height"] < 0.5
        for e in eyes
    ):
        return rgb, {"applied": False, "reason": "degenerate_eye_geometry"}
    width = sum(e["width"] for e in eyes) / 2
    height = max(e["height"] for e in eyes)
    yy, xx = np.mgrid[: rgb.shape[0], : rgb.shape[1]].astype(np.float32)
    map_x, map_y = xx.copy(), yy.copy()

    def window(distance: np.ndarray, core: float, extent: float) -> np.ndarray:
        t = np.clip((distance - core) / (extent - core), 0, 1)
        # C2 taper, modulated by a Gaussian; exactly one in the eye core.
        return (1 - (6 * t**5 - 15 * t**4 + 10 * t**3)) * np.exp(-2 * t * t)

    for i, eye in enumerate(eyes):
        cx = float(target_mid[0] + (i - 0.5) * target_dist)
        cy = float(target_mid[1])
        pad = max(1.0, 0.016 * target_dist)
        core_x = width / 2 + pad
        core_y = max(height, abs(eye["lid_mid_y"] - eye["center"][1]) + height) + pad
        # Unusual geometry must not make overlapping or folded support regions.
        if core_x >= 0.44 * target_dist or core_y >= 0.45 * target_dist:
            return rgb, {"applied": False, "reason": "eye_support_exceeds_band"}
        weight = window(abs(xx - cx), core_x, 0.44 * target_dist) * window(
            abs(yy - cy), core_y, 0.45 * target_dist
        )
        source_x = eye["center"][0] + (xx - cx) * eye["width"] / width
        # Keep the corner center fixed while centering the opening: the even
        # lid shift is zero at the eye line and one at/beyond either mean lid.
        lid_shift = (
            np.sin(0.5 * np.pi * np.clip(abs(yy - cy) / (height / 2), 0, 1)) ** 2
        )
        source_y = (
            eye["center"][1]
            + (yy - cy) * eye["height"] / height
            + (eye["lid_mid_y"] - eye["center"][1]) * lid_shift
        )
        map_x += weight * (source_x - xx)
        map_y += weight * (source_y - yy)
    out = cv2.remap(
        rgb, map_x, map_y, cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE
    )
    return out, {
        "applied": True,
        "source": [{**e, "center": e["center"].tolist()} for e in eyes],
        "target_width": width,
        "target_height": height,
        "target_centers": [
            [float(target_mid[0] + s * target_dist), float(target_mid[1])]
            for s in (-0.5, 0.5)
        ],
    }


def portrait_headwear_evidence(
    rgb: np.ndarray, points: np.ndarray, center_dist: float, angle: float, target_w: int
) -> tuple[bool, float]:
    """Exclude a smooth, matching top-corner studio backdrop from crown evidence."""
    import numpy as np

    mid = points[[33, 133, 362, 263]].mean(0)
    dist = float(np.linalg.norm(points[[362, 263]].mean(0) - points[[33, 133]].mean(0)))
    yy, xx = np.mgrid[: rgb.shape[0], : rgb.shape[1]]
    forehead = points[10, 1]
    probe = (
        (abs(xx - mid[0]) < 0.65 * dist)
        & (yy < forehead - 0.12 * dist)
        & (yy > forehead - 0.8 * dist)
    )
    evidence = portrait_color_evidence(rgb, points, dist)
    fraction = float(evidence["foreign"][probe].mean()) if probe.any() else 0.0
    return fraction >= 0.15, fraction


def studio_portrait_transform(
    source_shape: tuple, target_w: int, target_h: int, mid: np.ndarray, angle: float
) -> tuple[np.ndarray, dict]:
    """Level a covering crop, preferring the exact horizontal patch-grid axis.

    In source coordinates the four inverse-mapped output corners have a fixed
    extent. Their feasible center is an axis-aligned rectangle. Intersect that
    rectangle with the requested eye-x constraint, then choose the closest
    feasible natural eye-y position. Lanczos4's source footprint stays in bounds.
    """
    import cv2
    import numpy as np

    source_h, source_w = source_shape[:2]
    # One interpolation-table bin keeps roundoff/quantization away from the
    # conservative four-pixel footprint boundary (OpenCV uses 32 bins/pixel).
    padding = min(4.0 + 1.0 / cv2.INTER_TAB_SIZE, (min(source_w, source_h) - 1) / 4)
    theta = math.radians(angle)
    c, s = abs(math.cos(theta)), abs(math.sin(theta))
    cover_scale = max(target_w / source_w, target_h / source_h)
    # Projection of the output rectangle on each source axis after leveling.
    rotation_cover = max(
        (c * (target_w - 1) + s * (target_h - 1)) / (source_w - 1 - 2 * padding),
        (s * (target_w - 1) + c * (target_h - 1)) / (source_h - 1 - 2 * padding),
    )
    scale = max(cover_scale * 1.02, rotation_cover * (1 + 1e-9))
    matrix = cv2.getRotationMatrix2D(tuple(mid), angle, scale)
    rotation = matrix[:, :2]
    inverse = rotation.T / scale**2
    output_center = np.array([(target_w - 1) / 2, (target_h - 1) / 2])
    corners = np.array(
        [[0, 0], [target_w - 1, 0], [0, target_h - 1], [target_w - 1, target_h - 1]]
    )
    offsets = (corners - output_center) @ inverse.T
    low = padding - offsets.min(0)
    high = np.array([source_w - 1, source_h - 1]) - padding - offsets.max(0)
    natural_mid = np.array(
        [0.5 * target_w, mid[1] * scale + (target_h - source_h * scale) / 2]
    )
    desired_center = mid + inverse @ (output_center - natural_mid)
    # Preserve the desired eye x whenever the real source margin allows it.
    normal = rotation[0] / scale
    tangent = np.array([-normal[1], normal[0]])
    projection_low = np.where(normal >= 0, normal * low, normal * high).sum()
    projection_high = np.where(normal >= 0, normal * high, normal * low).sum()
    projection = np.clip(normal @ desired_center, projection_low, projection_high)
    base = normal * projection
    t_low, t_high = -np.inf, np.inf
    for axis in range(2):
        if abs(tangent[axis]) > 1e-12:
            a, b = (
                (low[axis] - base[axis]) / tangent[axis],
                (high[axis] - base[axis]) / tangent[axis],
            )
            t_low, t_high = max(t_low, min(a, b)), min(t_high, max(a, b))
    center = base + tangent * np.clip(tangent @ desired_center, t_low, t_high)
    matrix[:, 2] = output_center - rotation @ center
    samples = center + offsets
    if (samples.min(0) < padding - 1e-6).any() or (
        samples.max(0) > np.array([source_w - 1, source_h - 1]) - padding + 1e-6
    ).any():
        raise ValueError(
            "Studio portrait transform must cover the full Lanczos4 source footprint"
        )
    return matrix, {
        "branch": "studio_cover",
        "scale": float(scale),
        "cover_scale": float(cover_scale),
        "rotation_cover_scale": float(rotation_cover),
        "requested_eyes_mid": natural_mid.tolist(),
        "interpolation_padding": float(padding),
        "source_sample_bounds": [samples.min(0).tolist(), samples.max(0).tolist()],
        "out_of_bounds_pixels": 0,
    }


def source_eye_asymmetry(points: np.ndarray) -> dict:
    """Scale-independent bilateral gaps after roll leveling, in percent."""
    import numpy as np

    eyes = eye_geometry(points)
    if any(
        not np.isfinite([e["width"], e["height"]]).all()
        or e["width"] < 1
        or e["height"] < 0.5
        for e in eyes
    ):
        return {"valid": False}
    return {
        "valid": True,
        **{
            key: 200 * abs(eyes[0][key] - eyes[1][key]) / (eyes[0][key] + eyes[1][key])
            for key in ("width", "height")
        },
    }


def frame_reference(
    reference_image, target_w, target_h, reference_framing="center_crop"
):
    """One deterministic framing input shared by native VAE and VLM encoding."""
    if reference_framing not in ("center_crop", "auto_portrait"):
        raise ValueError(f"Unknown reference framing: {reference_framing}")

    def center():
        return comfy.utils.common_upscale(
            reference_image.movedim(-1, 1), target_w, target_h, "lanczos", "center"
        ).movedim(1, -1)

    if reference_framing == "center_crop":
        return center(), {"mode": "center_crop", "suppress_margin": False}
    import cv2
    import numpy as np

    rgb = np.rint(
        reference_image[0, ..., :3].detach().cpu().numpy().clip(0, 1) * 255
    ).astype(np.uint8)
    points = detect_portrait_landmarks(rgb)
    if points is None:
        logging.warning("MOSS auto_portrait: no face detected; using center_crop")
        return center(), {
            "mode": "center_crop",
            "reason": "no_face",
            "suppress_margin": False,
        }
    left, right = points[[33, 133]].mean(0), points[[362, 263]].mean(0)
    mid = (left + right) / 2
    dist = float(np.linalg.norm(right - left))
    if not np.isfinite(dist) or dist < 1:
        return center(), {
            "mode": "center_crop",
            "reason": "degenerate_eyes",
            "suppress_margin": False,
        }
    angle = float(np.degrees(np.arctan2(*(right - left)[::-1])))
    center_dist = dist * max(target_w / rgb.shape[1], target_h / rgb.shape[0])
    has_headwear, hat_fraction = portrait_headwear_evidence(
        rgb, points, center_dist, angle, target_w
    )
    candid_align = has_headwear or center_dist < 0.25 * target_w or abs(angle) > 4.0
    if candid_align:
        target_dist = 0.29 * target_w
        target_mid = np.array([0.50 * target_w, 0.365 * target_h])
        matrix = cv2.getRotationMatrix2D(tuple(mid), angle, target_dist / dist)
        matrix[:, 2] += target_mid - mid
        coverage = {
            "branch": "headwear" if has_headwear else "candid_align",
            "scale": target_dist / dist,
        }
    else:
        matrix, coverage = studio_portrait_transform(
            rgb.shape, target_w, target_h, mid, angle
        )
        target_dist = dist * coverage["scale"]
        target_mid = matrix[:, :2] @ mid + matrix[:, 2]
    aligned = cv2.warpAffine(
        rgb,
        matrix,
        (target_w, target_h),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT if candid_align else cv2.BORDER_REPLICATE,
        borderValue=(218, 214, 208),
    )
    warped = points @ matrix[:, :2].T + matrix[:, 2]
    framed, alpha = (
        suppress_portrait_headwear(aligned, warped, target_dist)
        if has_headwear
        else (aligned, np.zeros(aligned.shape[:2], dtype=np.float32))
    )
    asymmetry = source_eye_asymmetry(warped)
    if asymmetry["valid"] and max(asymmetry["width"], asymmetry["height"]) > 3.0:
        framed, symmetry = equalize_eye_symmetry(
            framed, warped, target_mid, target_dist
        )
    else:
        symmetry = {
            "applied": False,
            "reason": "source_eyes_within_threshold"
            if asymmetry["valid"]
            else "degenerate_eye_geometry",
        }
    symmetry.update(source_asymmetry_percent=asymmetry, threshold_percent=3.0)
    image = (
        torch.from_numpy(framed.astype(np.float32) / 255)
        .unsqueeze(0)
        .to(reference_image)
    )
    return image, {
        "mode": "auto_portrait",
        "suppress_margin": True,
        "source_eye_distance": dist,
        "source_eye_angle": angle,
        "eye_distance": target_dist,
        "eye_angle": 0.0,
        "eyes_mid": target_mid.tolist(),
        "matrix": matrix.tolist(),
        "has_headwear": bool(has_headwear),
        "hat_fraction": hat_fraction,
        "candid_align": bool(candid_align),
        "foreign_fraction": hat_fraction,
        "coverage": coverage,
        "eye_symmetry": symmetry,
        "replaced_pixels": int((alpha > 0).sum()),
    }


def exclude_reference_margin(
    mask, image_mask, vision_span, bounds, canvas_width, canvas_height
):
    """Proportional portrait crown margin sees text, but no reference/VLM image."""
    y0, x0, y1, x1 = bounds
    margin_rows = max(1, round((y1 - y0) * 9 / 52))
    stop = min(y0 + margin_rows, y1)
    mask = mask.clone()
    mask.reshape(1, canvas_height // 16, canvas_width // 16)[:, y0:stop, x0:x1] = False
    if image_mask is not None:
        image_mask = image_mask.clone()
        view = image_mask.reshape(1, canvas_height // 16, canvas_width // 16, -1)
        view[:, y0:stop, x0:x1] &= ~vision_span.reshape(1, 1, 1, -1)
    return mask, image_mask


def portrait_anchor(
    layout_json: str, width: int, height: int, anchor_mode: str = "full_portrait_panel"
) -> tuple:
    layout = json.loads(layout_json)
    if (
        layout.get("bbox_coord_space") != "abs_centralized"
        or layout.get("bbox_format") != "yxyx"
    ):
        raise ValueError(
            "Portrait anchoring requires abs_centralized yxyx layout coordinates"
        )
    if width % 16 or height % 16:
        raise ValueError("MOSS canvas dimensions must be multiples of 16")
    by0, bx0, by1, bx1 = layout["items"][0]["bbox"]
    h, w = height // 16, width // 16
    y0, x0 = int((by0 + height // 2) // 16), int((bx0 + width // 2) // 16)
    y1, x1 = math.ceil((by1 + height // 2) / 16), math.ceil((bx1 + width // 2) / 16)
    if not (0 <= y0 < y1 <= h and 0 <= x0 < x1 <= w):
        raise ValueError("Portrait bbox must be nonempty and inside the canvas")
    if anchor_mode == "upper_head_subbox":
        ph, pw = y1 - y0, x1 - x0
        y0, x0, y1, x1 = (
            y0 + math.floor(ph * 0.04),
            x0 + math.floor(pw * 0.06),
            y0 + math.ceil(ph * 0.66),
            x0 + math.ceil(pw * 0.94),
        )
    elif anchor_mode == "upper_torso_portrait":
        ph = y1 - y0
        y0, y1 = y0 + math.floor(ph * 0.02), y0 + math.ceil(ph * 0.78)
    elif anchor_mode != "full_portrait_panel":
        raise ValueError(f"Unknown anchor mode: {anchor_mode}")
    shift = ((y0 + y1 - 1) / 2 - (h - 1) / 2, (x0 + x1 - 1) / 2 - (w - 1) / 2)
    mask = torch.zeros((1, h, w), dtype=torch.bool)
    mask[:, y0:y1, x0:x1] = True
    return (y0, x0, y1, x1), shift, mask.flatten(1)


def vision_token_mask(tokens: dict) -> torch.Tensor:
    mask = []
    inside = False
    for token, *_ in next(iter(tokens.values()))[0]:
        if isinstance(token, dict):
            _, grid = comfy.text_encoders.qwen_vl.process_qwen2vl_images(
                token["data"], patch_size=16
            )
            mask.extend([True] * (int(grid[0, 1] * grid[0, 2]) // 4))
        else:
            if token == 248053:  # Qwen3.5 <|vision_start|>
                inside = True
            mask.append(inside)
            if token == 248054:  # <|vision_end|>
                inside = False
    return torch.tensor([mask], dtype=torch.bool)


class MOSSAnchoredReferenceEncode(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MOSSAnchoredReferenceEncode",
            display_name="MOSS Portrait Bbox - Anchored Reference",
            category="MOSS-Image/conditioning",
            inputs=[
                io.Clip.Input("clip"),
                io.Vae.Input("vae"),
                io.Image.Input("reference_image"),
                io.String.Input("prompt", multiline=True),
                io.String.Input("layout_json"),
                io.Int.Input("canvas_width", default=1536, min=16, max=16384, step=16),
                io.Int.Input("canvas_height", default=864, min=16, max=16384, step=16),
                io.Boolean.Input("ref_allow_text", default=True),
                io.Boolean.Input("mask_vision_tokens", default=False),
                io.Combo.Input(
                    "anchor_mode",
                    options=[
                        "full_portrait_panel",
                        "upper_head_subbox",
                        "upper_torso_portrait",
                    ],
                    default="full_portrait_panel",
                ),
                io.Boolean.Input("panel_scoped_text", default=True),
                io.Boolean.Input("mask_text_self_attention", default=False),
                io.Boolean.Input("mask_text_embedder", default=False),
                io.Combo.Input(
                    "reference_framing",
                    options=["center_crop", "auto_portrait"],
                    default="auto_portrait",
                    optional=True,
                ),
            ],
            outputs=[io.Conditioning.Output()],
        )

    @classmethod
    def execute(
        cls,
        clip,
        vae,
        reference_image,
        prompt,
        layout_json,
        canvas_width,
        canvas_height,
        ref_allow_text=True,
        mask_vision_tokens=False,
        anchor_mode="full_portrait_panel",
        panel_scoped_text=True,
        mask_text_self_attention=False,
        mask_text_embedder=False,
        reference_framing="auto_portrait",
    ):
        if not {
            "image_to_text_mask",
            "text_to_ref_mask",
            "dit_text_mask",
            "mask_text_embedder",
        }.issubset(inspect.signature(MOSSImage._forward).parameters):
            raise RuntimeError(
                "Reference support is missing. Stop ComfyUI and run this package's install_reference_support.py --comfy-root /path/to/ComfyUI --apply, then restart. See REFERENCE_SETUP.md."
            )
        if reference_image.shape[0] != 1:
            raise ValueError("Portrait anchoring takes one reference image")
        (y0, x0, y1, x1), shift, mask = portrait_anchor(
            layout_json, canvas_width, canvas_height, anchor_mode
        )
        image, framing = frame_reference(
            reference_image, (x1 - x0) * 16, (y1 - y0) * 16, reference_framing
        )
        if framing["suppress_margin"]:
            mask, _ = exclude_reference_margin(
                mask, None, None, (y0, x0, y1, x1), canvas_width, canvas_height
            )
        conditioning = TextEncodeMOSSImageEdit.execute(
            clip, prompt, "ai-toolkit", {"image_0": image}, vae
        ).result[0]
        if any(
            c[1]["reference_latents"][0].shape != (1, 128, y1 - y0, x1 - x0)
            for c in conditioning
        ):
            raise ValueError(
                "Portrait anchoring requires Flux2 reference latents at the portrait grid size"
            )
        values = {
            "ref_rope_offsets": (shift,),
            "ref_query_mask": mask,
            "ref_allow_text": ref_allow_text,
            "mask_text_self_attention": mask_text_self_attention,
            "mask_text_embedder": mask_text_embedder,
        }
        if (
            mask_vision_tokens
            or (panel_scoped_text and prompt.strip())
            or framing["suppress_margin"]
        ):
            scale = min(1.0, math.sqrt(384 * 384 / (image.shape[1] * image.shape[2])))
            vl = comfy.utils.common_upscale(
                image.movedim(-1, 1),
                round(image.shape[2] * scale),
                round(image.shape[1] * scale),
                "area",
                "disabled",
            ).movedim(1, -1)
            tokens = clip.tokenize(
                "Picture 1: <|vision_start|><|image_pad|><|vision_end|>" + prompt,
                images=[vl],
            )
            if mask_vision_tokens:
                values["context_vision_mask"] = vision_token_mask(tokens)
            if panel_scoped_text and prompt.strip():
                if json.loads(prompt) != json.loads(layout_json):
                    raise ValueError(
                        "Scoped JSON prompt and layout must describe the same four panels"
                    )
                image_mask, text_mask, spans = panel_text_masks(
                    tokens,
                    prompt,
                    canvas_width,
                    canvas_height,
                    mask_text_self_attention or mask_text_embedder,
                )
                if framing["suppress_margin"]:
                    _, image_mask = exclude_reference_margin(
                        mask,
                        image_mask,
                        spans["vision_span"],
                        (y0, x0, y1, x1),
                        canvas_width,
                        canvas_height,
                    )
                values["image_to_text_mask"] = image_mask
                if ref_allow_text:
                    values["text_to_ref_mask"] = spans["text_to_ref_mask"]
                values["dit_text_mask"] = (
                    text_mask if mask_text_self_attention else None
                )
                if mask_text_embedder or mask_text_self_attention:
                    values["text_attention_mask"] = text_mask
            if framing["suppress_margin"] and "image_to_text_mask" not in values:
                vision = vision_token_mask(tokens)
                image_mask = torch.ones(
                    (1, (canvas_width // 16) * (canvas_height // 16), vision.shape[1]),
                    dtype=torch.bool,
                )
                _, values["image_to_text_mask"] = exclude_reference_margin(
                    mask,
                    image_mask,
                    vision,
                    (y0, x0, y1, x1),
                    canvas_width,
                    canvas_height,
                )
            context_length = vision_token_mask(tokens).shape[1]
            if any(c[0].shape[1] != context_length for c in conditioning):
                raise ValueError(
                    "VLM vision mask does not match the encoded context length"
                )
        return io.NodeOutput(node_helpers.conditioning_set_values(conditioning, values))

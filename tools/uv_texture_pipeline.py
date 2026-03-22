#!/usr/bin/env python3
"""
Batch UV texture enhancement pipeline using OpenAI image generation/editing.

What it does
------------
1. Reads low-res flat UV textures from an input directory.
2. Reads a user-made UV reference layout image where each region is painted in a
   unique flat color. The color -> semantic region mapping is defined in config.
3. Builds per-region masks from that reference layout.
4. Infers section colors from the original UV texture.
5. Produces a neutral high-res scaffold that preserves the original UV layout.
6. Calls the OpenAI Images API to generate a detailed, high-resolution clothing
   texture using the original UV map + scaffold + prompt instructions.
7. Reprojects the generated result back onto the exact UV layout and alpha.
8. Optionally exports masks for debugging and writes a JSON sidecar with prompt
   metadata for reproducibility.

Intended use
------------
This is designed for Minecraft-style UV atlases, villager variants, mobs, and
other entities, as long as you provide a matching labeled UV reference layout.

Important notes
---------------
- This is a production-oriented starter pipeline, not a magic perfect system.
- The quality depends heavily on your UV reference map and the prompt profile.
- The script preserves UV placement. It allows the model to add frays, seams,
  dirt, folds, and rips *inside* each region but then remasks the result back to
  the original layout.
- You should test on a small batch first because image generation cost can add up.

Directory layout
----------------
project/
  uv_texture_pipeline.py
  config.json
  input/
    desert_farmer.png
    desert_cleric.png
  refs/
    villager_desert_layout.png
  output/
  debug/

Install
-------
pip install openai pillow numpy

Environment
-----------
export OPENAI_API_KEY="your_key_here"
# Windows PowerShell:
# $env:OPENAI_API_KEY="your_key_here"

Run
---
python uv_texture_pipeline.py --config config.json
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
from PIL import Image, ImageChops, ImageColor, ImageEnhance, ImageFilter, ImageOps
from openai import OpenAI
import fnmatch
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# -----------------------------------------------------------------------------
# Data structures
# -----------------------------------------------------------------------------

@dataclass
class RegionSpec:
    name: str
    hex_color: str
    material_hint: str
    style_hint: str = ""


@dataclass
class PipelineConfig:
    input_dir: Path
    output_dir: Path
    debug_dir: Path
    reference_layout: Path
    region_specs: List[RegionSpec]
    model: str
    quality: str
    size: str
    output_format: str
    upscale_factor: int
    preserve_alpha: bool
    export_debug_masks: bool
    base_theme: str
    creative_direction: str
    global_negative_prompt: str
    file_overrides: Dict[str, dict]
    process_extensions: Tuple[str, ...]
    generation_mode: str
    region_inpaint_padding: int
    region_color_tolerance: int
    max_file_workers: int
    max_region_workers: int
    env_file: str
    biome_keywords: Dict[str, List[str]]


MAX_RENDER_DIM = 256
SUPPORTED_API_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}


def normalize_api_size(size: str) -> str:
    normalized = str(size).lower().strip()
    if normalized in SUPPORTED_API_SIZES:
        return normalized
    return "1024x1024"


def compute_effective_upscale_factor(texture: Image.Image, configured_factor: int, max_dim: int = MAX_RENDER_DIM) -> int:
    configured = max(1, int(configured_factor))
    src_max = max(1, texture.width, texture.height)
    max_factor = max(1, max_dim // src_max)
    return min(configured, max_factor)


# -----------------------------------------------------------------------------
# Config loading
# -----------------------------------------------------------------------------

def load_config(config_path: Path) -> PipelineConfig:
    with config_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    region_specs = [
        RegionSpec(
            name=r["name"],
            hex_color=r["hex_color"],
            material_hint=r.get("material_hint", "cloth"),
            style_hint=r.get("style_hint", ""),
        )
        for r in raw["regions"]
    ]

    return PipelineConfig(
        input_dir=Path(raw["input_dir"]),
        output_dir=Path(raw["output_dir"]),
        debug_dir=Path(raw.get("debug_dir", "debug")),
        reference_layout=Path(raw["reference_layout"]),
        region_specs=region_specs,
        model=raw.get("model", "gpt-image-1"),
        quality=raw.get("quality", "medium"),
        size=normalize_api_size(raw.get("size", "1024x1024")),
        output_format=raw.get("output_format", "png"),
        upscale_factor=int(raw.get("upscale_factor", 8)),
        preserve_alpha=bool(raw.get("preserve_alpha", True)),
        export_debug_masks=bool(raw.get("export_debug_masks", False)),
        base_theme=raw.get("base_theme", "desert nomad clothing"),
        creative_direction=raw.get(
            "creative_direction",
            "weathered, functional, handmade garments with realistic fabric detail"
        ),
        global_negative_prompt=raw.get(
            "global_negative_prompt",
            "do not move UV islands, do not invent new floating pieces, no background clutter, no skin, no extra props, no text, no labels"
        ),
        file_overrides=raw.get("file_overrides", {}),
        process_extensions=tuple(raw.get("process_extensions", [".png", ".tga", ".webp"])),
        generation_mode=raw.get("generation_mode", "per_region"),
        region_inpaint_padding=int(raw.get("region_inpaint_padding", 24)),
        region_color_tolerance=int(raw.get("region_color_tolerance", 10)),
        max_file_workers=int(raw.get("max_file_workers", 2)),
        max_region_workers=int(raw.get("max_region_workers", 4)),
        env_file=raw.get("env_file", ".env"),
        biome_keywords=raw.get("biome_keywords", {}),
    )


# -----------------------------------------------------------------------------
# Image helpers
# -----------------------------------------------------------------------------

def open_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def save_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def upscale_nearest(img: Image.Image, factor: int) -> Image.Image:
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)


def upscale_lanczos(img: Image.Image, factor: int) -> Image.Image:
    return img.resize((img.width * factor, img.height * factor), Image.LANCZOS)


def get_alpha_mask(img: Image.Image) -> Image.Image:
    return img.getchannel("A")


def color_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    diff = a.astype(np.int32) - b.astype(np.int32)
    return np.sqrt(np.sum(diff * diff, axis=-1))


def dominant_visible_color(region_rgba: Image.Image, alpha_threshold: int = 8) -> Tuple[int, int, int]:
    arr = np.array(region_rgba)
    rgb = arr[..., :3]
    alpha = arr[..., 3]
    valid = alpha > alpha_threshold
    if not np.any(valid):
        return (128, 128, 128)
    pixels = rgb[valid]
    return tuple(np.median(pixels, axis=0).astype(np.uint8).tolist())


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def average_brightness(rgb: Tuple[int, int, int]) -> float:
    r, g, b = rgb
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def soften_mask(mask: Image.Image, radius: float = 1.0) -> Image.Image:
    if radius <= 0:
        return mask
    return mask.filter(ImageFilter.GaussianBlur(radius=radius))


# -----------------------------------------------------------------------------
# Region mask generation
# -----------------------------------------------------------------------------

def build_region_masks(reference_layout: Image.Image, specs: List[RegionSpec], tolerance: int = 6) -> Dict[str, Image.Image]:
    arr = np.array(reference_layout.convert("RGB"))
    masks: Dict[str, Image.Image] = {}
    matched_pixels: Dict[str, int] = {}

    for spec in specs:
        target = np.array(ImageColor.getrgb(spec.hex_color), dtype=np.uint8)
        dist = color_distance(arr, target)
        mask_arr = np.where(dist <= tolerance, 255, 0).astype(np.uint8)
        masks[spec.name] = Image.fromarray(mask_arr, mode="L")
        matched_pixels[spec.name] = int(np.count_nonzero(mask_arr))

    empty_regions = [name for name, count in matched_pixels.items() if count == 0]
    if empty_regions:
        print(
            f"WARNING: {len(empty_regions)}/{len(specs)} region masks are empty at tolerance={tolerance}: {', '.join(empty_regions)}",
            file=sys.stderr,
        )

    if len(empty_regions) == len(specs):
        colors = arr.reshape(-1, 3)
        unique, counts = np.unique(colors, axis=0, return_counts=True)
        top_idx = np.argsort(counts)[::-1][:8]
        top_hex = [rgb_to_hex(tuple(unique[i].tolist())) for i in top_idx]
        raise ValueError(
            "No region colors matched the reference layout. "
            "Check config 'regions[].hex_color' against the reference image colors "
            f"or increase 'region_color_tolerance'. Top colors in layout: {', '.join(top_hex)}"
        )

    return masks


# -----------------------------------------------------------------------------
# Color and prompt inference
# -----------------------------------------------------------------------------

def extract_region_preview(texture: Image.Image, mask: Image.Image) -> Image.Image:
    blank = Image.new("RGBA", texture.size, (0, 0, 0, 0))
    return Image.composite(texture, blank, mask)


def classify_color_language(rgb: Tuple[int, int, int]) -> str:
    # coarse language for prompt building
    r, g, b = rgb
    if max(rgb) - min(rgb) < 12:
        if average_brightness(rgb) < 0.2:
            return "charcoal"
        if average_brightness(rgb) < 0.45:
            return "gray"
        return "pale gray"

    if r > 160 and g > 130 and b < 100:
        return "warm ochre"
    if r > 150 and g > 100 and b > 120:
        return "dusty rose"
    if g > r and g > b:
        if g < 100:
            return "dark olive"
        return "faded sage green"
    if b > r and b > g:
        return "muted blue"
    if r > g and r > b:
        if g > 90:
            return "earthy rust"
        return "warm brown"
    if r > 140 and g > 120 and b > 90:
        return "sand beige"
    if r > 120 and g > 110 and b > 140:
        return "dusty lavender"
    return "earth-toned fabric"


def infer_region_descriptions(texture: Image.Image, region_masks: Dict[str, Image.Image], region_specs: List[RegionSpec]) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    spec_map = {s.name: s for s in region_specs}

    for region_name, mask in region_masks.items():
        preview = extract_region_preview(texture, mask)
        rgb = dominant_visible_color(preview)
        color_name = classify_color_language(rgb)
        spec = spec_map[region_name]
        out[region_name] = {
            "rgb": rgb,
            "hex": rgb_to_hex(rgb),
            "color_name": color_name,
            "material_hint": spec.material_hint,
            "style_hint": spec.style_hint,
        }

    return out


def build_prompt(
    file_stem: str,
    cfg: PipelineConfig,
    inferred_regions: Dict[str, dict],
    override: Optional[dict] = None,
) -> str:
    override = override or {}
    mob_type = override.get("mob_type", "Minecraft-style entity clothing UV texture")
    extra_direction = override.get("creative_direction", "")
    style_profile = override.get("style_profile", cfg.creative_direction)

    region_lines = []
    for region_name, data in inferred_regions.items():
        piece = (
            f"- {region_name}: keep its current color family as {data['color_name']} ({data['hex']}), "
            f"render as {data['material_hint']}, "
            f"with {data['style_hint'] or 'subtle wear and stitched construction'}"
        )
        region_lines.append(piece)

    region_text = "\n".join(region_lines)

    return f"""
STRICT UV ATLAS MODE.

You are generating a texture atlas, NOT a painting, illustration, garment concept sheet, or reconstructed outfit.
The input is a flat UV map for {mob_type}.

MANDATORY RULES:
- Preserve the exact UV layout and silhouette placement from the input image.
- Treat every UV island as isolated. Do not visually connect separate islands.
- Do not create continuity across empty space.
- Do not move, resize, rotate, merge, mirror, or invent UV islands.
- No detail may cross gaps between islands.
- Empty space outside the UV islands must remain empty.
- Keep all region boundaries aligned to the original map.
- Add detail only inside the existing islands.
- This must remain usable as a flat UV texture sheet.

Theme: {cfg.base_theme}
Direction: {style_profile}. {extra_direction}
File identity: {file_stem}

Allowed detail:
- realistic woven cloth, leather, stitching, hems, frayed edges, dust, wear, tears, patched repairs where appropriate
- preserve the original section colors and general material intent
- subtle local folds and seam logic inside each island only

Forbidden:
- any fabric bridge between disconnected pieces
- any background scene or props
- any text or labels in the final generated texture
- any skin unless already present in the input
- any face rendering outside mapped UV areas
- any shadows outside UV islands
- any extension of shapes beyond original island boundaries

Region guidance:
{region_text}

Negative requirements:
{cfg.global_negative_prompt}
""".strip()

def detect_biome_from_filename(filename: str, biome_keywords: Dict[str, List[str]]) -> Optional[str]:
    stem = Path(filename).stem.lower()
    tokens = set(stem.replace("-", "_").split("_"))

    for biome, keywords in biome_keywords.items():
        biome_l = biome.lower()
        if biome_l in stem or biome_l in tokens:
            return biome
        for keyword in keywords:
            kw = keyword.lower()
            if kw in stem or kw in tokens:
                return biome
    return None


def resolve_override_for_file(texture_name: str, cfg: PipelineConfig) -> dict:
    if texture_name in cfg.file_overrides:
        return cfg.file_overrides[texture_name]

    for pattern, payload in cfg.file_overrides.items():
        if any(ch in pattern for ch in "*?[") and fnmatch.fnmatch(texture_name, pattern):
            return payload

    biome = detect_biome_from_filename(texture_name, cfg.biome_keywords)
    if biome is not None:
        biome_pattern = f"{biome}_*.png"
        if biome_pattern in cfg.file_overrides:
            resolved = dict(cfg.file_overrides[biome_pattern])
            resolved.setdefault("detected_biome", biome)
            return resolved
        return {
            "mob_type": f"{biome} villager clothing UV texture",
            "creative_direction": f"apply biome-appropriate materials and wear for {biome}",
            "detected_biome": biome,
        }

    return {}


# -----------------------------------------------------------------------------
# Scaffold creation
# -----------------------------------------------------------------------------

def make_scaffold(texture: Image.Image, region_masks: Dict[str, Image.Image], inferred_regions: Dict[str, dict], factor: int) -> Image.Image:
    """
    Create a larger, clean scaffold image that preserves the UV layout and colors,
    giving the model a stronger hint before generation.
    """
    w, h = texture.size
    big_size = (w * factor, h * factor)
    scaffold = Image.new("RGBA", big_size, (0, 0, 0, 0))

    # Start from nearest-neighbor upscaled original to preserve exact block layout.
    up = upscale_nearest(texture, factor)
    scaffold.alpha_composite(up)

    for region_name, mask in region_masks.items():
        info = inferred_regions[region_name]
        rgb = info["rgb"]

        # Build softened fill to hint at smoother high-res materials while preserving layout.
        region_mask_big = upscale_nearest(mask, factor)
        fill = Image.new("RGBA", big_size, (*rgb, 255))

        # Slight brightness modulation to reduce flatness before model sees it.
        alpha = np.array(region_mask_big, dtype=np.uint8)
        yy, xx = np.mgrid[0:big_size[1], 0:big_size[0]]
        wave = ((np.sin(xx / 18.0) + np.cos(yy / 23.0)) * 7.0).astype(np.int16)
        mod = np.zeros((big_size[1], big_size[0], 4), dtype=np.uint8)
        mod[..., 0] = np.clip(rgb[0] + wave, 0, 255)
        mod[..., 1] = np.clip(rgb[1] + wave, 0, 255)
        mod[..., 2] = np.clip(rgb[2] + wave, 0, 255)
        mod[..., 3] = 255
        mod_img = Image.fromarray(mod, mode="RGBA")
        scaffold = Image.composite(mod_img, scaffold, soften_mask(region_mask_big, 0.5))

    # Re-apply exact alpha at the end.
    if texture.getchannel("A").getbbox():
        alpha_big = upscale_nearest(texture.getchannel("A"), factor)
        scaffold.putalpha(alpha_big)

    return scaffold


def build_uv_boundary_mask(texture: Image.Image, factor: int, erode_px: int = 1) -> Image.Image:
    """
    Build a hard UV boundary mask the model can see.
    White = valid UV area.
    Black = forbidden background.
    A slight erosion exaggerates gaps so separate islands are less likely to bleed together.
    """
    alpha = upscale_nearest(texture.getchannel("A"), factor)
    mask = alpha.point(lambda p: 255 if p > 10 else 0)

    if erode_px > 0:
        for _ in range(erode_px):
            mask = mask.filter(ImageFilter.MinFilter(3))

    rgb = Image.merge("RGB", (mask, mask, mask))
    out = rgb.convert("RGBA")
    out.putalpha(Image.new("L", out.size, 255))
    return out


def mask_to_bbox(mask: Image.Image, padding: int = 0) -> Optional[Tuple[int, int, int, int]]:
    bbox = mask.getbbox()
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - padding)
    y0 = max(0, y0 - padding)
    x1 = min(mask.width, x1 + padding)
    y1 = min(mask.height, y1 + padding)
    return (x0, y0, x1, y1)


def crop_with_bbox(img: Image.Image, bbox: Tuple[int, int, int, int]) -> Image.Image:
    return img.crop(bbox)


def crop_region_inputs(
    source_texture: Image.Image,
    scaffold_texture: Image.Image,
    region_mask: Image.Image,
    factor: int,
    padding: int,
) -> Tuple[Image.Image, Image.Image, Image.Image, Tuple[int, int, int, int]]:
    region_big = upscale_nearest(region_mask, factor)
    bbox = mask_to_bbox(region_big, padding=padding)
    if bbox is None:
        raise ValueError("Region mask has no visible pixels.")

    src_layout = upscale_nearest(source_texture, factor)
    uv_mask = build_uv_boundary_mask(source_texture, factor)

    return (
        crop_with_bbox(src_layout, bbox),
        crop_with_bbox(scaffold_texture, bbox),
        crop_with_bbox(uv_mask, bbox),
        bbox,
    )


# -----------------------------------------------------------------------------
# OpenAI image call
# -----------------------------------------------------------------------------

def call_openai_image_edit(
    client: OpenAI,
    source_texture: Image.Image,
    scaffold_texture: Image.Image,
    uv_mask: Image.Image,
    prompt: str,
    model: str,
    size: str,
) -> Image.Image:
    """
    Sends three images:
    - original UV crop or full layout
    - scaffold crop or full scaffold
    - UV boundary mask crop or full mask
    """
    result = client.images.edit(
        model=model,
        image=[
            ("layout.png", pil_to_png_bytes(source_texture), "image/png"),
            ("scaffold.png", pil_to_png_bytes(scaffold_texture), "image/png"),
            ("uv_mask.png", pil_to_png_bytes(uv_mask), "image/png"),
        ],
        prompt=prompt,
        size=size,
    )

    if not result.data or not result.data[0].b64_json:
        raise RuntimeError("OpenAI image API returned no base64 image payload.")

    decoded = base64.b64decode(result.data[0].b64_json)
    return Image.open(io.BytesIO(decoded)).convert("RGBA")


def build_region_prompt(
    file_stem: str,
    cfg: PipelineConfig,
    region_name: str,
    region_data: dict,
    override: Optional[dict] = None,
) -> str:
    override = override or {}
    mob_type = override.get("mob_type", "Minecraft-style entity clothing UV texture")
    extra_direction = override.get("creative_direction", "")
    style_profile = override.get("style_profile", cfg.creative_direction)

    return f"""
STRICT UV ATLAS MODE.

You are generating detail for exactly one isolated UV region inside a texture atlas for {mob_type}.
Only edit the visible non-background pixels in this crop.
Treat this crop as a flat texture region, not as clothing concept art.

MANDATORY RULES:
- Preserve the exact silhouette and placement of the visible region.
- Do not paint into the background.
- Do not extend fabric or material outside the current masked area.
- Do not invent new islands or connect to anything outside this crop.
- Keep this usable as part of a flat UV texture atlas.

File identity: {file_stem}
Region: {region_name}
Theme: {cfg.base_theme}
Direction: {style_profile}. {extra_direction}

Region material guidance:
- keep the current color family as {region_data['color_name']} ({region_data['hex']})
- render as {region_data['material_hint']}
- add {region_data['style_hint'] or 'subtle wear and stitched construction'}

Allowed detail:
- local stitching, seams, folds, fraying, dust, wear, tears, patches, woven detail, leather grain, wool texture, plant fiber texture, hide texture
- detail only inside the current visible region

Forbidden:
- text or labels
- background scene
- extra anatomy
- continuity beyond the masked crop
- shape extension beyond the visible region

Negative requirements:
{cfg.global_negative_prompt}
""".strip()


# -----------------------------------------------------------------------------
# Post-processing and remapping
# -----------------------------------------------------------------------------

def constrain_to_uv_layout(
    generated: Image.Image,
    source_texture: Image.Image,
    factor: int,
    preserve_alpha: bool,
) -> Image.Image:
    target_size = (source_texture.width * factor, source_texture.height * factor)
    if generated.size != target_size:
        generated = generated.resize(target_size, Image.LANCZOS)

    alpha_big = upscale_nearest(source_texture.getchannel("A"), factor)
    if preserve_alpha:
        generated.putalpha(alpha_big)

    # Hard clamp to the original UV silhouette so hallucinated bridges are cut away.
    blank = Image.new("RGBA", generated.size, (0, 0, 0, 0))
    generated = Image.composite(generated, blank, alpha_big)
    return generated


def downscale_preview(img: Image.Image, factor: int) -> Image.Image:
    return img.resize((max(1, img.width // factor), max(1, img.height // factor)), Image.LANCZOS)


def resize_to_max_dim(img: Image.Image, max_dim: int = MAX_RENDER_DIM) -> Image.Image:
    w, h = img.size
    current_max = max(w, h)
    if current_max <= max_dim:
        return img

    scale = max_dim / float(current_max)
    new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    return img.resize(new_size, Image.LANCZOS)


def sharpen_lightly(img: Image.Image) -> Image.Image:
    return img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=120, threshold=2))


# -----------------------------------------------------------------------------
# Main processing
# -----------------------------------------------------------------------------

def process_single_region(
    client: OpenAI,
    cfg: PipelineConfig,
    texture: Image.Image,
    scaffold: Image.Image,
    region_name: str,
    region_mask: Image.Image,
    region_data: dict,
    override: dict,
    file_stem: str,
    upscale_factor: int,
) -> Tuple[str, Image.Image, Tuple[int, int]]:
    region_prompt = build_region_prompt(file_stem, cfg, region_name, region_data, override)
    src_crop, scaffold_crop, uv_crop, bbox = crop_region_inputs(
        source_texture=texture,
        scaffold_texture=scaffold,
        region_mask=region_mask,
        factor=upscale_factor,
        padding=cfg.region_inpaint_padding,
    )

    region_generated = call_openai_image_edit(
        client=client,
        source_texture=src_crop,
        scaffold_texture=scaffold_crop,
        uv_mask=uv_crop,
        prompt=region_prompt,
        model=cfg.model,
        size=cfg.size,
    )

    target_size = (bbox[2] - bbox[0], bbox[3] - bbox[1])
    if region_generated.size != target_size:
        region_generated = region_generated.resize(target_size, Image.LANCZOS)

    region_big_mask = crop_with_bbox(upscale_nearest(region_mask, upscale_factor), bbox)
    blank = Image.new("RGBA", region_generated.size, (0, 0, 0, 0))
    region_constrained = Image.composite(region_generated, blank, region_big_mask)
    return region_name, region_constrained, (bbox[0], bbox[1])


def process_by_region(
    client: OpenAI,
    cfg: PipelineConfig,
    texture: Image.Image,
    region_masks: Dict[str, Image.Image],
    inferred: Dict[str, dict],
    override: dict,
    file_stem: str,
    upscale_factor: int,
) -> Tuple[Image.Image, Dict[str, Image.Image]]:
    scaffold = make_scaffold(texture, region_masks, inferred, upscale_factor)
    target_size = (texture.width * upscale_factor, texture.height * upscale_factor)
    final_canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))
    debug_regions: Dict[str, Image.Image] = {}

    region_jobs = []
    for region_name, region_mask in region_masks.items():
        if region_mask.getbbox() is None:
            continue
        region_jobs.append((region_name, region_mask, inferred[region_name]))

    if cfg.max_region_workers <= 1 or len(region_jobs) <= 1:
        for region_name, region_mask, region_data in region_jobs:
            out_name, region_img, dest = process_single_region(
                client=client,
                cfg=cfg,
                texture=texture,
                scaffold=scaffold,
                region_name=region_name,
                region_mask=region_mask,
                region_data=region_data,
                override=override,
                file_stem=file_stem,
                upscale_factor=upscale_factor,
            )
            final_canvas.alpha_composite(region_img, dest=dest)
            debug_regions[out_name] = region_img
    else:
        composite_lock = Lock()
        with ThreadPoolExecutor(max_workers=cfg.max_region_workers) as executor:
            futures = [
                executor.submit(
                    process_single_region,
                    client,
                    cfg,
                    texture,
                    scaffold,
                    region_name,
                    region_mask,
                    region_data,
                    override,
                    file_stem,
                    upscale_factor,
                )
                for region_name, region_mask, region_data in region_jobs
            ]
            for future in as_completed(futures):
                out_name, region_img, dest = future.result()
                with composite_lock:
                    final_canvas.alpha_composite(region_img, dest=dest)
                    debug_regions[out_name] = region_img

    final_canvas = constrain_to_uv_layout(
        generated=final_canvas,
        source_texture=texture,
        factor=upscale_factor,
        preserve_alpha=cfg.preserve_alpha,
    )
    final_canvas = sharpen_lightly(final_canvas)
    return final_canvas, debug_regions


def process_one(
    client: OpenAI,
    cfg: PipelineConfig,
    reference_layout: Image.Image,
    region_masks: Dict[str, Image.Image],
    texture_path: Path,
) -> None:
    texture = open_rgba(texture_path)
    override = resolve_override_for_file(texture_path.name, cfg)
    upscale_factor = compute_effective_upscale_factor(texture, cfg.upscale_factor)
    if upscale_factor != cfg.upscale_factor:
        print(
            f"INFO: {texture_path.name} upscale_factor capped to {upscale_factor} "
            f"to keep output within {MAX_RENDER_DIM}px",
            file=sys.stderr,
        )

    inferred = infer_region_descriptions(texture, region_masks, cfg.region_specs)

    if cfg.generation_mode == "per_region":
        constrained, debug_regions = process_by_region(
            client=client,
            cfg=cfg,
            texture=texture,
            region_masks=region_masks,
            inferred=inferred,
            override=override,
            file_stem=texture_path.stem,
            upscale_factor=upscale_factor,
        )
        generated = constrained.copy()
        scaffold = make_scaffold(texture, region_masks, inferred, upscale_factor)
        uv_mask = build_uv_boundary_mask(texture, upscale_factor)
    else:
        prompt = build_prompt(texture_path.stem, cfg, inferred, override)
        scaffold = make_scaffold(texture, region_masks, inferred, upscale_factor)
        uv_mask = build_uv_boundary_mask(texture, upscale_factor)
        generated = call_openai_image_edit(
            client=client,
            source_texture=upscale_nearest(texture, upscale_factor),
            scaffold_texture=scaffold,
            uv_mask=uv_mask,
            prompt=prompt,
            model=cfg.model,
            size=cfg.size,
        )
        constrained = constrain_to_uv_layout(
            generated=generated,
            source_texture=texture,
            factor=upscale_factor,
            preserve_alpha=cfg.preserve_alpha,
        )
        constrained = sharpen_lightly(constrained)
        debug_regions = {}

    pre_resize_size = constrained.size
    constrained = resize_to_max_dim(constrained, MAX_RENDER_DIM)
    if constrained.size != pre_resize_size:
        print(
            f"INFO: {texture_path.name} final output resized from {pre_resize_size[0]}x{pre_resize_size[1]} "
            f"to {constrained.size[0]}x{constrained.size[1]} to enforce max {MAX_RENDER_DIM}px",
            file=sys.stderr,
        )

    out_name = f"{texture_path.stem}_hr.{cfg.output_format}"
    out_path = cfg.output_dir / out_name
    constrained.save(out_path)

    preview_path = cfg.output_dir / f"{texture_path.stem}_preview.png"
    downscale_preview(constrained, upscale_factor).save(preview_path)

    meta_path = cfg.output_dir / f"{texture_path.stem}_meta.json"
    meta_payload = {
        "source": str(texture_path),
        "output": str(out_path),
        "preview": str(preview_path),
        "model": cfg.model,
        "quality": cfg.quality,
        "size": cfg.size,
        "output_format": cfg.output_format,
        "max_render_dim": MAX_RENDER_DIM,
        "output_dimensions": [constrained.width, constrained.height],
        "upscale_factor": upscale_factor,
        "configured_upscale_factor": cfg.upscale_factor,
        "generation_mode": cfg.generation_mode,
        "region_inpaint_padding": cfg.region_inpaint_padding,
        "inferred_regions": {
            k: {
                **v,
                "rgb": list(v["rgb"]),
            }
            for k, v in inferred.items()
        },
    }
    save_json(meta_path, meta_payload)

    if cfg.export_debug_masks:
        debug_texture_dir = cfg.debug_dir / texture_path.stem
        ensure_dir(debug_texture_dir)
        scaffold.save(debug_texture_dir / "scaffold.png")
        generated.save(debug_texture_dir / "generated_raw.png")
        constrained.save(debug_texture_dir / "generated_constrained.png")
        uv_mask.save(debug_texture_dir / "uv_mask.png")
        texture.save(debug_texture_dir / "source.png")
        for region_name, mask in region_masks.items():
            mask.save(debug_texture_dir / f"mask_{region_name}.png")
        for region_name, region_img in debug_regions.items():
            region_img.save(debug_texture_dir / f"region_{region_name}.png")

    print(f"[ok] {texture_path.name} -> {out_path.name}")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch UV texture enhancement pipeline.")
    parser.add_argument("--config", required=True, type=Path, help="Path to config.json")
    return parser.parse_args()


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

def run_one_file(
    cfg: PipelineConfig,
    reference_layout: Image.Image,
    region_masks: Dict[str, Image.Image],
    texture_path: Path,
) -> Tuple[Path, Optional[str]]:
    try:
        client = OpenAI()
        process_one(
            client=client,
            cfg=cfg,
            reference_layout=reference_layout,
            region_masks=region_masks,
            texture_path=texture_path,
        )
        return texture_path, None
    except Exception as exc:
        return texture_path, str(exc)


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)

    load_dotenv(cfg.env_file)

    ensure_dir(cfg.input_dir)
    ensure_dir(cfg.output_dir)
    ensure_dir(cfg.debug_dir)

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
        return 1

    reference_layout = open_rgba(cfg.reference_layout)
    region_masks = build_region_masks(
        reference_layout,
        cfg.region_specs,
        tolerance=cfg.region_color_tolerance,
    )

    inputs = [
        p for p in sorted(cfg.input_dir.iterdir())
        if p.is_file() and p.suffix.lower() in cfg.process_extensions
    ]

    if not inputs:
        print(f"No input textures found in: {cfg.input_dir}")
        return 0

    if cfg.max_file_workers <= 1 or len(inputs) <= 1:
        for texture_path in inputs:
            texture_path, err = run_one_file(cfg, reference_layout, region_masks, texture_path)
            if err:
                print(f"[error] {texture_path.name}: {err}", file=sys.stderr)
    else:
        with ThreadPoolExecutor(max_workers=cfg.max_file_workers) as executor:
            futures = [
                executor.submit(run_one_file, cfg, reference_layout, region_masks, texture_path)
                for texture_path in inputs
            ]
            for future in as_completed(futures):
                texture_path, err = future.result()
                if err:
                    print(f"[error] {texture_path.name}: {err}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

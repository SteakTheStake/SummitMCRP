
# ============================================================================
# SECOND SCRIPT: build_region_config.py
# ============================================================================
#!/usr/bin/env python3
"""
Auto-build the `regions` list for config.json from a labeled template image.

Expected inputs
---------------
1. A labeled template image where each region is filled with a unique flat color.
2. Optionally, a JSON file mapping colors to names/material hints/style hints.
   If omitted, the script will generate generic names automatically.

What it outputs
---------------
- A JSON file containing a `regions` array ready to paste into config.json.
- Optionally, a full starter config.json file.

Install
-------
pip install pillow numpy

Usage
-----
python build_region_config.py \
  --template refs/villager_desert_layout.png \
  --out regions.generated.json

With color label overrides:
python build_region_config.py \
  --template refs/villager_desert_layout.png \
  --labels color_labels.json \
  --out regions.generated.json

Generate a full starter config:
python build_region_config.py \
  --template refs/villager_desert_layout.png \
  --labels color_labels.json \
  --emit-full-config config.generated.json

Example color_labels.json
-------------------------
{
  "#b1a583": {"name": "head", "material_hint": "wrapped linen cloth", "style_hint": "sun-bleached woven folds"},
  "#be63be": {"name": "beanie", "material_hint": "dyed cloth headwear", "style_hint": "faded pigment and stitched hem"},
  "#cdc55d": {"name": "torso", "material_hint": "outer tunic cloth", "style_hint": "stitched seams and worn chest panel"}
}
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def slugify(text: str) -> str:
    allowed = []
    for ch in text.lower().strip():
        if ch.isalnum():
            allowed.append(ch)
        elif ch in {" ", "-", "_"}:
            allowed.append("_")
    slug = "".join(allowed)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_") or "region"


def load_labels(path: Path | None) -> Dict[str, dict]:
    if not path:
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return {k.lower(): v for k, v in raw.items()}


def find_flat_colors(img: Image.Image, ignore_transparent: bool = True) -> List[Tuple[Tuple[int, int, int], int]]:
    rgba = np.array(img.convert("RGBA"))
    rgb = rgba[..., :3]
    alpha = rgba[..., 3]

    if ignore_transparent:
        pixels = rgb[alpha > 0]
    else:
        pixels = rgb.reshape(-1, 3)

    counter = Counter(map(tuple, pixels.tolist()))
    # Sort largest regions first for easier review.
    return sorted(counter.items(), key=lambda item: item[1], reverse=True)


def build_regions(template: Image.Image, labels: Dict[str, dict]) -> List[dict]:
    regions: List[dict] = []
    found = find_flat_colors(template)

    auto_index = 1
    for rgb, pixel_count in found:
        hex_color = rgb_to_hex(rgb)
        label = labels.get(hex_color.lower(), {})

        name = label.get("name") or f"region_{auto_index:02d}"
        auto_index += 1

        regions.append({
            "name": slugify(name),
            "hex_color": hex_color,
            "material_hint": label.get("material_hint", "cloth or appropriate surface material"),
            "style_hint": label.get("style_hint", "preserve layout and add realistic detail"),
            "pixel_count": pixel_count,
        })

    return regions


def strip_pixel_counts(regions: List[dict]) -> List[dict]:
    return [
        {
            "name": r["name"],
            "hex_color": r["hex_color"],
            "material_hint": r["material_hint"],
            "style_hint": r["style_hint"],
        }
        for r in regions
    ]


def find_region_centroid(mask: np.ndarray) -> Tuple[int, int] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.mean()), int(ys.mean())


def draw_region_title_preview(template: Image.Image, regions: List[dict], out_path: Path) -> None:
    rgba = template.convert("RGBA").copy()
    draw = ImageDraw.Draw(rgba)
    font = ImageFont.load_default()
    arr = np.array(template.convert("RGBA"))

    for region in regions:
        hex_color = region["hex_color"].lower()
        target = tuple(int(hex_color[i:i+2], 16) for i in (1, 3, 5))
        mask = np.all(arr[..., :3] == target, axis=-1) & (arr[..., 3] > 0)
        centroid = find_region_centroid(mask)
        if centroid is None:
            continue
        x, y = centroid
        label = region["name"].replace("_", " ")
        bbox = draw.textbbox((x, y), label, font=font, anchor="mm")
        pad = 2
        draw.rectangle((bbox[0]-pad, bbox[1]-pad, bbox[2]+pad, bbox[3]+pad), fill=(255, 255, 255, 180))
        draw.text((x, y), label, fill=(0, 0, 0, 255), font=font, anchor="mm")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    rgba.save(out_path)


def emit_full_config(reference_layout: Path, regions: List[dict]) -> dict:
    return {
        "input_dir": "input",
        "output_dir": "output",
        "debug_dir": "debug",
        "reference_layout": str(reference_layout).replace("\\", "/"),
        "model": "gpt-image-1",
        "quality": "medium",
        "size": "1024x1024",
        "output_format": "png",
        "upscale_factor": 8,
        "preserve_alpha": True,
        "export_debug_masks": True,
        "base_theme": "desert clothing or species-appropriate surface detail",
        "creative_direction": "preserve UV layout, keep original color families, add realistic material detail",
        "global_negative_prompt": "do not alter UV placement, do not add background objects, no extra anatomy, no labels, no text, no floating scraps outside mapped islands",
        "process_extensions": [".png"],
        "regions": strip_pixel_counts(regions),
        "file_overrides": {}
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build region config entries from a flat-color labeled UV template.")
    parser.add_argument("--template", required=True, type=Path, help="Path to the labeled template image.")
    parser.add_argument("--labels", type=Path, default=None, help="Optional color_labels.json mapping hex colors to names and hints.")
    parser.add_argument("--out", required=False, type=Path, default=Path("regions.generated.json"), help="Output JSON path for generated regions.")
    parser.add_argument("--emit-full-config", type=Path, default=None, help="Optional output path for a full starter config.json.")
    parser.add_argument("--title-preview", type=Path, default=None, help="Optional output path for a title preview image with simple body-part labels over each region.")
    parser.add_argument("--include-pixel-counts", action="store_true", help="Keep pixel_count metadata in the regions output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    template = Image.open(args.template).convert("RGBA")
    labels = load_labels(args.labels)
    regions = build_regions(template, labels)

    out_regions = regions if args.include_pixel_counts else strip_pixel_counts(regions)
    payload = {"regions": out_regions}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Wrote region list: {args.out}")

    if args.emit_full_config:
        full_config = emit_full_config(args.template, regions)
        args.emit_full_config.parent.mkdir(parents=True, exist_ok=True)
        with args.emit_full_config.open("w", encoding="utf-8") as f:
            json.dump(full_config, f, indent=2, ensure_ascii=False)
        print(f"Wrote starter config: {args.emit_full_config}")

    if args.title_preview:
        draw_region_title_preview(template, regions, args.title_preview)
        print(f"Wrote title preview: {args.title_preview}")

    print(f"Detected {len(regions)} unique flat-color regions.")
    for region in regions:
        print(f"- {region['name']}: {region['hex_color']} ({region['pixel_count']} px)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

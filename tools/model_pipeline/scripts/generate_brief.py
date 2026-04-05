from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

try:
    from .common import dump_json, rel_to_repo
except ImportError:
    from common import dump_json, rel_to_repo


def infer_model_type_from_target(target_file: str) -> str:
    normalized = target_file.replace("\\", "/")
    if "/models/item/" in normalized:
        return "item"
    return "block"


def build_entity_brief(args: argparse.Namespace, repo_root: Path, target_path: Path) -> Dict[str, Any]:
    return {
        "kind": "entity",
        "target_file": rel_to_repo(target_path, repo_root),
        "idea": args.idea,
        "style_profile": args.style_profile,
        "texture": args.entity_texture,
        "texture_size": [args.texture_width, args.texture_height],
        "parts_priority": [p for p in args.parts_priority if p],
        "anti_goals": [
            "over-detailed noisy micro-shapes",
            "breaking vanilla readability",
            "duplicate or conflicting part ids",
        ],
        "constraints": {
            "keep_vanilla_pivots": True,
            "forbid_duplicate_part_ids": True,
            "require_invert_axis_z": True,
        },
    }


def build_block_item_brief(args: argparse.Namespace, repo_root: Path, target_path: Path) -> Dict[str, Any]:
    model_type = args.model_type or infer_model_type_from_target(str(target_path).replace("\\", "/"))
    brief: Dict[str, Any] = {
        "kind": "block_item",
        "model_type": model_type,
        "target_file": rel_to_repo(target_path, repo_root),
        "idea": args.idea,
        "style_profile": args.style_profile,
        "parent": args.parent,
        "textures": {},
        "anti_goals": [
            "unreadable silhouette",
            "random texture noise",
            "invalid geometry bounds",
        ],
        "constraints": {
            "max_elements": 112,
            "enforce_allowed_rotations": True,
            "coord_min": 0,
            "coord_max": 16,
        },
    }
    for kv in args.texture_map:
        if "=" not in kv:
            continue
        key, value = kv.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            brief["textures"][key] = value
    return brief


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate structured model brief JSON.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--kind", choices=["entity", "block_item"], required=True)
    parser.add_argument("--idea", required=True)
    parser.add_argument("--target", required=True, help="Relative or absolute target model path")
    parser.add_argument("--out", required=True)

    parser.add_argument("--style-profile", default="default")

    # Entity-focused options
    parser.add_argument("--entity-texture", default="")
    parser.add_argument("--texture-width", type=int, default=64)
    parser.add_argument("--texture-height", type=int, default=64)
    parser.add_argument("--parts-priority", nargs="*", default=[])

    # Block/item-focused options
    parser.add_argument("--model-type", choices=["block", "item"], default="")
    parser.add_argument("--parent", default="")
    parser.add_argument(
        "--texture-map",
        action="append",
        default=[],
        help="Texture mapping as key=value, repeat flag for multiple",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    out_path = Path(args.out).resolve()

    target_path = Path(args.target)
    if not target_path.is_absolute():
        target_path = (repo_root / target_path).resolve()

    if args.kind == "entity":
        brief = build_entity_brief(args, repo_root, target_path)
    else:
        brief = build_block_item_brief(args, repo_root, target_path)

    dump_json(out_path, brief)
    print(f"Wrote brief: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

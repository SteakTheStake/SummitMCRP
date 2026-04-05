from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

try:
    from .common import dump_json, load_json
except ImportError:
    from common import dump_json, load_json


def entity_ops_from_brief(brief: Dict[str, Any]) -> Dict[str, Any]:
    ops: List[Dict[str, Any]] = []

    texture = brief.get("texture")
    if isinstance(texture, str) and texture:
        ops.append({"action": "set_root", "path": "texture", "data": texture})

    texture_size = brief.get("texture_size")
    if isinstance(texture_size, list) and len(texture_size) == 2:
        ops.append({"action": "set_root", "path": "textureSize", "data": texture_size})

    # Seed optional placeholder operations for prioritized areas.
    for part in brief.get("parts_priority", []):
        if not isinstance(part, str) or not part:
            continue
        ops.append(
            {
                "action": "upsert_model_part",
                "id": f"todo_{part}",
                "data": {
                    "id": f"todo_{part}",
                    "part": part,
                    "invertAxis": "z",
                    "translate": [0, 0, 0],
                    "rotate": [0, 0, 0],
                    "boxes": [],
                    "submodels": [],
                    "_todo": "Replace with final geometry and valid part mapping before apply.",
                },
            }
        )

    return {
        "kind": "entity",
        "target_file": brief["target_file"],
        "ops": ops,
        "notes": [
            "This is a deterministic starter ops file.",
            "Fill TODO geometry entries before applying to production models.",
        ],
    }


def block_item_ops_from_brief(brief: Dict[str, Any]) -> Dict[str, Any]:
    ops: List[Dict[str, Any]] = []

    parent = brief.get("parent")
    if isinstance(parent, str) and parent:
        ops.append({"action": "set_root", "path": "parent", "data": parent})

    textures = brief.get("textures", {})
    if isinstance(textures, dict):
        for key, value in textures.items():
            if isinstance(key, str) and isinstance(value, str):
                ops.append({"action": "upsert_texture", "key": key, "data": value})

    if brief.get("model_type") == "block":
        ops.append(
            {
                "action": "set_root",
                "path": "_todo_block_elements",
                "data": "Add upsert_element ops with valid coordinates and allowed rotations.",
            }
        )
    else:
        ops.append(
            {
                "action": "set_root",
                "path": "_todo_item_overrides",
                "data": "Add upsert_override ops in least-specific to most-specific order.",
            }
        )

    return {
        "kind": "block_item",
        "target_file": brief["target_file"],
        "ops": ops,
        "notes": [
            "Starter ops generated from brief.",
            "Edit TODO markers before final apply.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deterministic starter ops from a brief JSON.")
    parser.add_argument("--brief", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    brief = load_json(Path(args.brief).resolve())

    kind = brief.get("kind")
    if kind == "entity":
        result = entity_ops_from_brief(brief)
    elif kind == "block_item":
        result = block_item_ops_from_brief(brief)
    else:
        raise ValueError(f"Unsupported brief kind: {kind}")

    dump_json(Path(args.out).resolve(), result)
    print(f"Wrote ops: {Path(args.out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

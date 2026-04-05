from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

try:
    from .common import load_json, rel_to_repo
    from .validate_models import validate_block_item_data, validate_entity_data
except ImportError:
    from common import load_json, rel_to_repo
    from validate_models import validate_block_item_data, validate_entity_data


def clamp_score(value: int) -> int:
    return max(0, min(10, value))


def score_entity(brief: Dict[str, Any], data: Dict[str, Any], path_label: str) -> Dict[str, Any]:
    validation = validate_entity_data(data, path_label)

    technical = 10
    technical -= min(8, len(validation["errors"]) * 3)
    technical -= min(2, len(validation["warnings"]))

    consistency = 9
    anti_goals = brief.get("anti_goals", [])
    if isinstance(anti_goals, list) and anti_goals:
        # We cannot measure visual style directly here; conservative consistency fallback.
        consistency -= 1

    style_match = 7
    vanilla_readability = 8

    blocking_issues: List[str] = list(validation["errors"])
    improvements = []
    if validation["warnings"]:
        improvements.extend(validation["warnings"][:3])
    if not improvements:
        improvements.append("Run in-game EMF debug mode to verify pivots and silhouette readability.")

    return {
        "kind": "entity",
        "path": path_label,
        "scores": {
            "style_match": clamp_score(style_match),
            "vanilla_readability": clamp_score(vanilla_readability),
            "technical_validity": clamp_score(technical),
            "consistency": clamp_score(consistency),
        },
        "blocking_issues": blocking_issues,
        "improvements": improvements,
        "validation": validation,
    }


def score_block_item(brief: Dict[str, Any], data: Dict[str, Any], path_label: str) -> Dict[str, Any]:
    validation = validate_block_item_data(data, path_label)

    technical = 10
    technical -= min(8, len(validation["errors"]) * 3)
    technical -= min(2, len(validation["warnings"]))

    style_match = 7
    vanilla_readability = 8
    consistency = 8

    improvements = []
    if validation["warnings"]:
        improvements.extend(validation["warnings"][:3])
    if not improvements:
        improvements.append("Validate model lighting and readability in GUI/in-world contexts.")

    return {
        "kind": "block_item",
        "path": path_label,
        "scores": {
            "style_match": clamp_score(style_match),
            "vanilla_readability": clamp_score(vanilla_readability),
            "technical_validity": clamp_score(technical),
            "consistency": clamp_score(consistency),
        },
        "blocking_issues": list(validation["errors"]),
        "improvements": improvements,
        "validation": validation,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Produce critic score report for a model file.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--brief", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--kind", choices=["entity", "block_item", "auto"], default="auto")
    parser.add_argument("--out", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()

    brief = load_json(Path(args.brief).resolve())
    if not isinstance(brief, dict):
        raise ValueError("Brief must be a JSON object")

    file_path = Path(args.path)
    if not file_path.is_absolute():
        file_path = (repo_root / file_path).resolve()

    data = load_json(file_path)
    if not isinstance(data, dict):
        raise ValueError("Model JSON must be a JSON object")

    kind = args.kind
    if kind == "auto":
        kind = "entity" if str(file_path).lower().endswith(".jem") else "block_item"

    path_label = rel_to_repo(file_path, repo_root)
    if kind == "entity":
        report = score_entity(brief, data, path_label)
    else:
        report = score_block_item(brief, data, path_label)

    if args.out:
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(report, f, indent=2, ensure_ascii=True)
            f.write("\n")
        print(f"Wrote critic report: {out_path}")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=True))

    return 1 if report["blocking_issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

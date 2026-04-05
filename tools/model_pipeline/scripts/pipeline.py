from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List


SCRIPT_DIR = Path(__file__).resolve().parent


def run_step(step_name: str, command: List[str]) -> int:
    print(f"[STEP] {step_name}")
    print(" ".join(command))
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        print(f"[FAIL] {step_name} (exit {completed.returncode})")
        return completed.returncode
    print(f"[OK] {step_name}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full model pipeline: brief -> ops -> apply -> validate -> critic")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--kind", choices=["entity", "block_item"], required=True)
    parser.add_argument("--idea", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--run-dir", required=True)

    parser.add_argument("--style-profile", default="default")

    # entity options
    parser.add_argument("--entity-texture", default="")
    parser.add_argument("--texture-width", type=int, default=64)
    parser.add_argument("--texture-height", type=int, default=64)
    parser.add_argument("--parts-priority", nargs="*", default=[])

    # block/item options
    parser.add_argument("--model-type", choices=["block", "item"], default="")
    parser.add_argument("--parent", default="")
    parser.add_argument("--texture", action="append", default=[])

    parser.add_argument("--dry-run", action="store_true", help="Apply ops in dry-run mode")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = (repo_root / run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    brief_path = run_dir / "brief.json"
    ops_path = run_dir / "ops.json"
    critic_path = run_dir / "critic.json"

    py = sys.executable

    brief_cmd = [
        py,
        str(SCRIPT_DIR / "generate_brief.py"),
        "--repo-root",
        str(repo_root),
        "--kind",
        args.kind,
        "--idea",
        args.idea,
        "--target",
        args.target,
        "--out",
        str(brief_path),
        "--style-profile",
        args.style_profile,
    ]

    if args.kind == "entity":
        brief_cmd.extend(["--entity-texture", args.entity_texture])
        brief_cmd.extend(["--texture-width", str(args.texture_width)])
        brief_cmd.extend(["--texture-height", str(args.texture_height)])
        if args.parts_priority:
            brief_cmd.extend(["--parts-priority", *args.parts_priority])
    else:
        if args.model_type:
            brief_cmd.extend(["--model-type", args.model_type])
        if args.parent:
            brief_cmd.extend(["--parent", args.parent])
        for texture_map in args.texture:
            brief_cmd.extend(["--texture-map", texture_map])

    rc = run_step("Generate Brief", brief_cmd)
    if rc != 0:
        return rc

    rc = run_step(
        "Generate Ops",
        [py, str(SCRIPT_DIR / "generate_ops.py"), "--brief", str(brief_path), "--out", str(ops_path)],
    )
    if rc != 0:
        return rc

    apply_cmd = [
        py,
        str(SCRIPT_DIR / "apply_ops.py"),
        "--repo-root",
        str(repo_root),
        "--ops",
        str(ops_path),
    ]
    if args.dry_run:
        apply_cmd.append("--dry-run")

    rc = run_step("Apply Ops", apply_cmd)
    if rc != 0:
        return rc

    rc = run_step(
        "Validate",
        [
            py,
            str(SCRIPT_DIR / "validate_models.py"),
            "--repo-root",
            str(repo_root),
            "--kind",
            args.kind,
            "--path",
            args.target,
        ],
    )
    if rc != 0:
        return rc

    rc = run_step(
        "Critic Score",
        [
            py,
            str(SCRIPT_DIR / "score_critic.py"),
            "--repo-root",
            str(repo_root),
            "--brief",
            str(brief_path),
            "--path",
            args.target,
            "--kind",
            args.kind,
            "--out",
            str(critic_path),
        ],
    )
    if rc != 0:
        return rc

    print("[DONE] Pipeline complete")
    print(f" - brief:  {brief_path}")
    print(f" - ops:    {ops_path}")
    print(f" - critic: {critic_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

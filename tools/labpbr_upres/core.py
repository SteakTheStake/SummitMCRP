from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageStat

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

IMAGE_EXT = ".png"
NORMAL_SUFFIX = "_n"
SPECULAR_SUFFIX = "_s"
DEFAULT_MODEL = "gpt-image-1.5"
DEFAULT_OUTPUT_DIR = "generated_labpbr_hd"
DEFAULT_BATCH_GUARD = 25
DEFAULT_RENDER_SIZE = 1024
DEFAULT_TARGET_SIZE = 256


@dataclass
class TextureTask:
    source_path: Path
    relative_path: str
    namespace: str
    kind: str
    logical_name: str
    source_size: tuple[int, int]
    has_alpha: bool
    alpha_coverage: float
    normal_path: Path | None
    specular_path: Path | None
    sidecar_path: Path | None
    normal_sidecar_path: Path | None
    specular_sidecar_path: Path | None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    pack_root = args.pack_root.resolve()
    if not (pack_root / "assets").exists():
        parser.error(f"{pack_root} does not look like a resource-pack root (missing assets/).")

    output_root = args.output_root.resolve()
    kinds = parse_kind_filter(args.kind)
    matches = [value.lower() for value in args.match]

    tasks, skipped = discover_texture_tasks(
        pack_root=pack_root,
        output_root=output_root,
        kinds=kinds,
        namespaces=set(args.namespace),
        matches=matches,
        limit=args.limit,
        skip_animated=not args.include_animated,
        skip_non_square=not args.allow_rectangular,
    )

    manifest_entries = []
    for task in tasks:
        base_stats = analyze_base_texture(task.source_path)
        normal_stats = analyze_normal_map(task.normal_path) if task.normal_path else None
        specular_stats = analyze_specular_map(task.specular_path) if task.specular_path else None
        prompt = build_generation_prompt(
            task=task,
            base_stats=base_stats,
            normal_stats=normal_stats,
            specular_stats=specular_stats,
            target_size=args.target_size,
        )
        manifest_entries.append(
            build_manifest_entry(
                task=task,
                pack_root=pack_root,
                prompt=prompt,
                base_stats=base_stats,
                normal_stats=normal_stats,
                specular_stats=specular_stats,
            )
        )

    prepare_output_pack(pack_root, output_root, args.target_size)
    if manifest_entries:
        print(f"Planned {len(manifest_entries)} texture generations.")
    else:
        print("No matching textures found.")
    if skipped:
        print(f"Skipped {len(skipped)} textures due to filters or unsupported source shape.")

    manifest = {
        "pack_root": to_posix(pack_root),
        "output_root": to_posix(output_root),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "dry_run": args.dry_run,
            "model": args.model,
            "api_key_provided": bool(args.api_key or os.environ.get("OPENAI_API_KEY")),
            "render_size": args.render_size,
            "target_size": args.target_size,
            "include_animated": args.include_animated,
            "allow_rectangular": args.allow_rectangular,
            "kind": sorted(kinds) if kinds else ["all"],
            "namespace": args.namespace,
            "match": args.match,
        },
        "tasks": manifest_entries,
        "skipped_summary": summarize_skips(skipped),
        "skipped_examples": skipped[:200],
    }

    if args.dry_run:
        write_manifest(output_root, manifest)
        print(f"Wrote dry-run manifest to {output_root / 'labpbr_upres_manifest.json'}")
        return 0

    if len(manifest_entries) > args.batch_guard and not args.yes:
        parser.error(
            "Refusing to submit a large batch without --yes. "
            f"Planned {len(manifest_entries)} generations; use --limit/--match first."
        )

    if OpenAI is None:
        parser.error("The openai package is not installed. Re-run with --dry-run or install openai.")

    api_key = resolve_api_key(args.api_key)

    try:
        generator = OpenAITextureGenerator(
            api_key=api_key,
            model=args.model,
            render_size=args.render_size,
            target_size=args.target_size,
            quality=args.quality,
            input_fidelity=args.input_fidelity,
            timeout_seconds=args.timeout,
            preserve_alpha=not args.no_preserve_alpha,
            seam_fix=not args.no_seam_fix,
        )
    except Exception as exc:
        parser.error(str(exc))

    for index, (task, entry) in enumerate(zip(tasks, manifest_entries), start=1):
        print(f"[{index}/{len(manifest_entries)}] {task.relative_path}")
        try:
            output_image = generator.generate_texture(task, entry["prompt"])
            albedo_output = output_root / entry["outputs"]["albedo"]
            albedo_output.parent.mkdir(parents=True, exist_ok=True)
            output_image.save(albedo_output)
            copy_sidecar_if_needed(task.sidecar_path, pack_root, output_root)

            if task.normal_path:
                normal_output = output_root / entry["outputs"]["normal"]
                normal_output.parent.mkdir(parents=True, exist_ok=True)
                upscale_normal_map(task.normal_path, args.target_size).save(normal_output)
                copy_sidecar_if_needed(task.normal_sidecar_path, pack_root, output_root)

            if task.specular_path:
                specular_output = output_root / entry["outputs"]["specular"]
                specular_output.parent.mkdir(parents=True, exist_ok=True)
                upscale_generic_map(task.specular_path, args.target_size).save(specular_output)
                copy_sidecar_if_needed(task.specular_sidecar_path, pack_root, output_root)

            entry["status"] = "generated"
        except Exception as exc:  # pragma: no cover - network path
            entry["status"] = "failed"
            entry["error"] = str(exc)
            print(f"  failed: {exc}")
            if args.fail_fast:
                write_manifest(output_root, manifest)
                return 1

        write_manifest(output_root, manifest)

    print(f"Wrote manifest to {output_root / 'labpbr_upres_manifest.json'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Scan a Minecraft LabPBR resource pack, analyze base/normal/specular textures, "
            "and generate realistic 256px albedo replacements plus upscaled companion maps."
        )
    )
    parser.add_argument("--pack-root", type=Path, default=Path("."), help="Resource-pack root. Defaults to the current directory.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(DEFAULT_OUTPUT_DIR),
        help=f"Output pack directory. Defaults to ./{DEFAULT_OUTPUT_DIR}.",
    )
    parser.add_argument(
        "--kind",
        action="append",
        default=[],
        help="Texture kinds to include: block, item, entity, other, all. Repeatable or comma-separated.",
    )
    parser.add_argument(
        "--namespace",
        action="append",
        default=[],
        help="Only include textures under assets/<namespace>/... Repeatable.",
    )
    parser.add_argument(
        "--match",
        action="append",
        default=[],
        help="Case-insensitive substring filter applied to relative texture paths. Repeatable.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Stop after planning this many textures.")
    parser.add_argument("--dry-run", action="store_true", help="Only write the manifest and prompts; skip API generation.")
    parser.add_argument("--yes", action="store_true", help="Allow large batch submissions without the safety guard.")
    parser.add_argument(
        "--api-key",
        default=None,
        help="OpenAI API key. If omitted, the tool uses the OPENAI_API_KEY environment variable.",
    )
    parser.add_argument("--include-animated", action="store_true", help="Include textures with animation sidecars.")
    parser.add_argument(
        "--allow-rectangular",
        action="store_true",
        help="Include non-square textures. Disabled by default because many atlases do not survive a forced 256x256 remap cleanly.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Image model for OpenAI edits. Defaults to {DEFAULT_MODEL}.")
    parser.add_argument("--quality", default="high", choices=["low", "medium", "high", "auto", "standard"], help="Image edit quality.")
    parser.add_argument("--input-fidelity", default="high", choices=["low", "high"], help="OpenAI image edit input fidelity.")
    parser.add_argument("--render-size", type=int, default=DEFAULT_RENDER_SIZE, choices=[256, 512, 1024], help="Intermediate image-edit size.")
    parser.add_argument("--target-size", type=int, default=DEFAULT_TARGET_SIZE, choices=[256, 512, 1024], help="Final saved texture size.")
    parser.add_argument("--timeout", type=int, default=180, help="OpenAI API timeout in seconds.")
    parser.add_argument("--batch-guard", type=int, default=DEFAULT_BATCH_GUARD, help="Require --yes when planning more than this many generations.")
    parser.add_argument("--no-preserve-alpha", action="store_true", help="Do not reapply the source alpha mask to generated outputs.")
    parser.add_argument("--no-seam-fix", action="store_true", help="Disable opposite-edge blending on opaque block textures.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on the first generation failure.")
    return parser


def parse_kind_filter(values: Iterable[str]) -> set[str]:
    if not values:
        return set()
    result: set[str] = set()
    for raw in values:
        for value in raw.split(","):
            cleaned = value.strip().lower()
            if cleaned:
                result.add(cleaned)
    if "all" in result:
        return set()
    unknown = result - {"block", "item", "entity", "other"}
    if unknown:
        raise SystemExit(f"Unknown --kind values: {', '.join(sorted(unknown))}")
    return result


def resolve_api_key(cli_value: str | None) -> str:
    api_key = cli_value or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit(
            "OpenAI API key missing. Pass --api-key or set the OPENAI_API_KEY environment variable."
        )
    return api_key

def discover_texture_tasks(
    *,
    pack_root: Path,
    output_root: Path,
    kinds: set[str],
    namespaces: set[str],
    matches: list[str],
    limit: int | None,
    skip_animated: bool,
    skip_non_square: bool,
) -> tuple[list[TextureTask], list[dict[str, Any]]]:
    tasks: list[TextureTask] = []
    skipped: list[dict[str, Any]] = []
    assets_root = pack_root / "assets"
    output_root_resolved = output_root.resolve()

    for source_path in sorted(assets_root.glob("*/*/**/*.png")):
        if not source_path.is_file():
            continue
        if is_descendant_of(source_path.resolve(), output_root_resolved):
            continue

        relative_path = to_posix(source_path.relative_to(pack_root))
        stem = source_path.stem
        if stem.endswith(NORMAL_SUFFIX) or stem.endswith(SPECULAR_SUFFIX):
            continue

        namespace = namespace_from_texture(source_path)
        kind = kind_from_texture(source_path)

        if namespaces and namespace not in namespaces:
            skipped.append({"path": relative_path, "reason": "namespace-filter"})
            continue
        if kinds and kind not in kinds:
            skipped.append({"path": relative_path, "reason": "kind-filter"})
            continue
        if matches and not any(token in relative_path.lower() for token in matches):
            skipped.append({"path": relative_path, "reason": "match-filter"})
            continue

        size = image_size(source_path)
        sidecar_path = sidecar_for_png(source_path)
        animated = sidecar_is_animated(sidecar_path)
        if animated and skip_animated:
            skipped.append({"path": relative_path, "reason": "animated"})
            continue
        if skip_non_square and size[0] != size[1]:
            skipped.append({"path": relative_path, "reason": "non-square"})
            continue

        rgba = open_rgba(source_path)
        has_alpha = rgba.getchannel("A").getextrema()[0] < 255
        alpha_coverage = alpha_coverage_ratio(rgba)
        rgba.close()

        normal_path = source_path.with_name(f"{stem}{NORMAL_SUFFIX}{IMAGE_EXT}")
        specular_path = source_path.with_name(f"{stem}{SPECULAR_SUFFIX}{IMAGE_EXT}")
        normal_path = normal_path if normal_path.exists() else None
        specular_path = specular_path if specular_path.exists() else None

        tasks.append(
            TextureTask(
                source_path=source_path,
                relative_path=relative_path,
                namespace=namespace,
                kind=kind,
                logical_name=logical_name_from_path(source_path),
                source_size=size,
                has_alpha=has_alpha,
                alpha_coverage=alpha_coverage,
                normal_path=normal_path,
                specular_path=specular_path,
                sidecar_path=sidecar_path if sidecar_path and sidecar_path.exists() else None,
                normal_sidecar_path=sidecar_for_png(normal_path) if normal_path else None,
                specular_sidecar_path=sidecar_for_png(specular_path) if specular_path else None,
            )
        )
        if limit is not None and len(tasks) >= limit:
            break

    return tasks, skipped


def build_manifest_entry(
    *,
    task: TextureTask,
    pack_root: Path,
    prompt: str,
    base_stats: dict[str, Any],
    normal_stats: dict[str, Any] | None,
    specular_stats: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "source": {
            "base": task.relative_path,
            "normal": to_posix(task.normal_path.relative_to(pack_root)) if task.normal_path else None,
            "specular": to_posix(task.specular_path.relative_to(pack_root)) if task.specular_path else None,
        },
        "namespace": task.namespace,
        "kind": task.kind,
        "logical_name": task.logical_name,
        "prompt": prompt,
        "analysis": {
            "base": base_stats,
            "normal": normal_stats,
            "specular": specular_stats,
        },
        "outputs": {
            "albedo": task.relative_path,
            "normal": task.relative_path.replace(IMAGE_EXT, f"{NORMAL_SUFFIX}{IMAGE_EXT}") if task.normal_path else None,
            "specular": task.relative_path.replace(IMAGE_EXT, f"{SPECULAR_SUFFIX}{IMAGE_EXT}") if task.specular_path else None,
        },
        "status": "planned",
        "error": None,
    }


def prepare_output_pack(pack_root: Path, output_root: Path, target_size: int) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    source_pack = pack_root / "pack.mcmeta"
    output_pack = output_root / "pack.mcmeta"

    if source_pack.exists():
        try:
            pack_data = json.loads(source_pack.read_text(encoding="utf-8"))
            description = pack_data.get("pack", {}).get("description")
            if isinstance(description, str):
                pack_data["pack"]["description"] = f"{description} [AI LabPBR upres {target_size}px]"
            output_pack.write_text(json.dumps(pack_data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        except Exception:
            shutil.copy2(source_pack, output_pack)

    source_icon = pack_root / "pack.png"
    if source_icon.exists():
        shutil.copy2(source_icon, output_root / "pack.png")


def write_manifest(output_root: Path, manifest: dict[str, Any]) -> None:
    path = output_root / "labpbr_upres_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def build_generation_prompt(
    *,
    task: TextureTask,
    base_stats: dict[str, Any],
    normal_stats: dict[str, Any] | None,
    specular_stats: dict[str, Any] | None,
    target_size: int,
) -> str:
    profile = material_profile(task.logical_name, task.kind)
    palette = ", ".join(base_stats["dominant_colors"][:4])

    prompt_lines = [
        "Create a realistic, production-usable Minecraft texture remake from the provided references.",
        f"Subject: {profile['subject']}.",
        f"Material intent: {profile['material']}.",
        output_rule_for_kind(task),
        "Use the source image as the identity and composition anchor; keep the same recognizable texture purpose.",
        f"Preserve the palette centered around {palette}.",
        f"Source observations: {base_observation_text(base_stats)}.",
    ]

    labpbr_notes = []
    if normal_stats and normal_stats["notes"]:
        labpbr_notes.extend(normal_stats["notes"])
    if specular_stats and specular_stats["notes"]:
        labpbr_notes.extend(specular_stats["notes"])
    if labpbr_notes:
        prompt_lines.append("LabPBR material cues to honor: " + "; ".join(labpbr_notes) + ".")

    prompt_lines.append("Detail targets: " + "; ".join(profile["detail_targets"]) + ".")
    prompt_lines.append(f"Keep the result readable after downsampling to {target_size}x{target_size}.")
    prompt_lines.append(
        "Avoid blurry color noise, centered scene composition, text, borders, camera perspective, heavy directional lighting, "
        "or unrelated objects. Do not turn the texture into a photograph of a scene."
    )
    return "\n".join(prompt_lines)


def base_observation_text(base_stats: dict[str, Any]) -> str:
    notes = []
    if base_stats["unique_color_count"] <= 32:
        notes.append("the source is low resolution with a limited palette and needs richer secondary detail")
    if base_stats["edge_density"] >= 0.18:
        notes.append("macro shapes are already strong and should remain readable")
    if base_stats["contrast"] <= 20:
        notes.append("keep contrast controlled so the texture stays usable in-game")
    if base_stats["alpha_coverage"] < 0.95:
        notes.append("preserve the cutout silhouette and transparent negative space")
    if not notes:
        notes.append("retain the recognizable surface pattern while adding believable microdetail")
    return "; ".join(notes)

def material_profile(logical_name: str, kind: str) -> dict[str, Any]:
    name = logical_name.lower()

    def match(*keywords: str) -> bool:
        return any(keyword in name for keyword in keywords)

    if match("dirt", "mud", "soil", "coarse_dirt", "rooted"):
        return {
            "subject": "packed earth and embedded pebbles",
            "material": "crumbly soil with small stones and natural brown variation",
            "detail_targets": [
                "compact soil clumps instead of flat brown noise",
                "small embedded pebbles with believable occlusion",
                "fine root fibers, damp patches, and granular breakup",
            ],
        }
    if match("stone", "cobble", "deepslate", "andesite", "diorite", "granite", "tuff", "basalt", "blackstone"):
        return {
            "subject": "weathered stone surface",
            "material": "mineral-rich rock with fractures and chiseled depth",
            "detail_targets": [
                "micro-fractures and mineral speckling",
                "subtle chipped edges and occluded seams",
                "tonal variation that still reads clearly at game distance",
            ],
        }
    if match("sand", "sandstone", "gravel", "clay", "terracotta", "mud_brick"):
        return {
            "subject": "granular sediment surface",
            "material": "sand, aggregate, and weathered sediment layers",
            "detail_targets": [
                "grain clusters and sediment layering",
                "small aggregate pieces and erosion marks",
                "avoid flat monochrome grain noise",
            ],
        }
    if match("ore", "diamond", "emerald", "lapis", "redstone", "quartz", "amethyst"):
        return {
            "subject": "ore-bearing host rock",
            "material": "stone with mineral seams or crystal inclusions",
            "detail_targets": [
                "crystalline or metallic inclusions integrated into host stone",
                "recessed seams and believable mineral edges",
                "controlled sparkle without turning into a scene render",
            ],
        }
    if match("wood", "log", "plank", "stem", "hyphae", "bamboo", "sign", "door", "trapdoor"):
        return {
            "subject": "wood grain and carved fibers",
            "material": "fibrous wood with pores, growth variation, and wear",
            "detail_targets": [
                "directional grain with fine pores",
                "small cracks, softened wear, and tonal variation",
                "keep the plank or bark pattern readable after downsampling",
            ],
        }
    if match("glass", "ice", "crystal"):
        return {
            "subject": "translucent glass or crystalline material",
            "material": "clear or frosted mineral surface with internal variation",
            "detail_targets": [
                "subtle bubbles, scratches, or frost blooms",
                "controlled edge variation without opaque clutter",
                "preserve transparency and clean readability",
            ],
        }
    if match("grass", "moss", "leaf", "leaves", "vine", "sapling", "flower", "fern", "kelp"):
        return {
            "subject": "dense plant matter",
            "material": "organic foliage with veins, fibers, and soft translucency",
            "detail_targets": [
                "leaf veins or blade fibers that fit the original silhouette",
                "natural hue shifts instead of uniform green noise",
                "light occlusion between overlapping organic forms",
            ],
        }
    if match("iron", "gold", "copper", "netherite", "chain", "anvil", "sword", "axe", "pickaxe", "shovel", "hoe", "shield", "spear"):
        return {
            "subject": "crafted metal and hard-surface detail",
            "material": "forged or cast metal with wear, scratches, and material breakup",
            "detail_targets": [
                "brushed grain, edge wear, and subtle oxidation where appropriate",
                "material separation between metal and handle or leather sections",
                "preserve the original icon silhouette and orientation",
            ],
        }
    if kind == "item" and match("apple", "bread", "beef", "carrot", "potato", "fish", "stew", "potion"):
        return {
            "subject": "realistic inventory food item",
            "material": "edible surface detail while preserving the game icon silhouette",
            "detail_targets": [
                "fine surface pores, fibers, or skin texture",
                "color variation that still reads instantly as the original item",
                "transparent background and centered inventory composition",
            ],
        }
    if kind == "item":
        return {
            "subject": humanize_name(logical_name),
            "material": "a realistic inventory icon with preserved silhouette and clean alpha",
            "detail_targets": [
                "keep the original shape, placement, and readability",
                "add believable material detail without clutter",
                "transparent background with no scene lighting",
            ],
        }
    return {
        "subject": humanize_name(logical_name),
        "material": "a realistic Minecraft texture remake that keeps the original identity",
        "detail_targets": [
            "add believable high-frequency detail without destroying the original pattern",
            "keep the texture usable as a repeating game asset",
            "avoid random scene content or photobash artifacts",
        ],
    }


def output_rule_for_kind(task: TextureTask) -> str:
    if task.kind == "item" or task.alpha_coverage < 0.95:
        return (
            "Produce a square texture on a transparent background, preserving the original silhouette, centered placement, "
            "and inventory readability."
        )
    if task.kind == "entity":
        return (
            "Produce a square UV texture sheet that keeps the reference layout coherent; "
            "do not turn it into a posed scene or portrait."
        )
    return "Produce one seamless square material tile with no borders, no perspective, no text, and no directional scene lighting."

class OpenAITextureGenerator:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        render_size: int,
        target_size: int,
        quality: str,
        input_fidelity: str,
        timeout_seconds: int,
        preserve_alpha: bool,
        seam_fix: bool,
    ) -> None:
        if OpenAI is None:
            raise RuntimeError("The openai package is required for generation.")
        self.client = OpenAI(api_key=api_key, timeout=timeout_seconds)
        self.model = model
        self.render_size = render_size
        self.target_size = target_size
        self.quality = quality
        self.input_fidelity = input_fidelity
        self.preserve_alpha = preserve_alpha
        self.seam_fix = seam_fix

    def generate_texture(self, task: TextureTask, prompt: str) -> Image.Image:
        with tempfile.TemporaryDirectory(prefix="labpbr_upres_") as temp_dir:
            temp_path = Path(temp_dir)
            reference_paths = []
            tiled_reference = task.kind == "block" and task.alpha_coverage >= 0.999

            for label, path in (
                ("base", task.source_path),
                ("normal", task.normal_path),
                ("specular", task.specular_path),
            ):
                if not path:
                    continue
                prepared = temp_path / f"{label}.png"
                prepare_reference_image(
                    source_path=path,
                    dest_path=prepared,
                    render_size=self.render_size,
                    tile_preview=tiled_reference,
                    transparent_background=(task.alpha_coverage < 0.999 or task.kind == "item"),
                )
                reference_paths.append(prepared)

            handles = [prepared.open("rb") for prepared in reference_paths]
            try:
                request_kwargs: dict[str, Any] = {
                    "model": self.model,
                    "image": handles,
                    "prompt": prompt,
                    "size": f"{self.render_size}x{self.render_size}",
                    "quality": self.quality,
                    "output_format": "png",
                    "response_format": "b64_json",
                }
                if self.model == "gpt-image-1":
                    request_kwargs["input_fidelity"] = self.input_fidelity
                response = self._edit_with_fallback(request_kwargs)
            finally:
                for handle in handles:
                    handle.close()

        image_bytes = base64.b64decode(response.data[0].b64_json)
        output = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        if output.size != (self.target_size, self.target_size):
            output = output.resize((self.target_size, self.target_size), Image.LANCZOS)
        if self.preserve_alpha and task.has_alpha:
            output.putalpha(source_alpha_mask(task.source_path, self.target_size))
        if self.seam_fix and task.kind == "block" and task.alpha_coverage >= 0.999:
            output = enforce_matching_edges(output, border=max(1, self.target_size // 64))
        return output

    def _edit_with_fallback(self, request_kwargs: dict[str, Any]) -> Any:
        retryable = {"input_fidelity", "quality", "background", "output_compression"}
        while True:
            try:
                return self.client.images.edit(**request_kwargs)
            except Exception as exc:
                unknown_param = extract_unknown_parameter(str(exc))
                if unknown_param not in retryable or unknown_param not in request_kwargs:
                    raise
                request_kwargs.pop(unknown_param, None)


def prepare_reference_image(
    *,
    source_path: Path,
    dest_path: Path,
    render_size: int,
    tile_preview: bool,
    transparent_background: bool,
) -> None:
    image = open_rgba(source_path)
    if tile_preview and image.width == image.height:
        image = tiled_preview_image(image, repeat=3)
    image = square_pad(image, transparent_background=transparent_background)
    image = image.resize((render_size, render_size), Image.NEAREST)
    image.save(dest_path)


def tiled_preview_image(image: Image.Image, repeat: int) -> Image.Image:
    canvas = Image.new("RGBA", (image.width * repeat, image.height * repeat))
    for y in range(repeat):
        for x in range(repeat):
            canvas.alpha_composite(image, (x * image.width, y * image.height))
    return canvas


def square_pad(image: Image.Image, *, transparent_background: bool) -> Image.Image:
    size = max(image.size)
    background = (0, 0, 0, 0) if transparent_background else (0, 0, 0, 255)
    canvas = Image.new("RGBA", (size, size), background)
    offset = ((size - image.width) // 2, (size - image.height) // 2)
    canvas.alpha_composite(image, offset)
    return canvas


def enforce_matching_edges(image: Image.Image, border: int) -> Image.Image:
    output = image.copy().convert("RGBA")
    pixels = output.load()
    width, height = output.size

    for offset in range(border):
        left = offset
        right = width - 1 - offset
        for y in range(height):
            blended = average_rgba(pixels[left, y], pixels[right, y])
            pixels[left, y] = blended
            pixels[right, y] = blended

    for offset in range(border):
        top = offset
        bottom = height - 1 - offset
        for x in range(width):
            blended = average_rgba(pixels[x, top], pixels[x, bottom])
            pixels[x, top] = blended
            pixels[x, bottom] = blended

    return output


def average_rgba(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return tuple((a[index] + b[index]) // 2 for index in range(4))


def upscale_normal_map(source_path: Path, target_size: int) -> Image.Image:
    image = open_rgba(source_path)
    r, g, b, a = image.split()
    r = r.resize((target_size, target_size), Image.BICUBIC)
    g = g.resize((target_size, target_size), Image.BICUBIC)
    b = b.resize((target_size, target_size), Image.LANCZOS)
    a = a.resize((target_size, target_size), Image.LANCZOS)

    fixed_r = []
    fixed_g = []
    for red, green in zip(r.getdata(), g.getdata()):
        x = (red / 127.5) - 1.0
        y = (green / 127.5) - 1.0
        length = math.sqrt((x * x) + (y * y))
        if length > 1.0 and length > 0.0:
            x /= length
            y /= length
        fixed_r.append(clamp_8bit(round((x + 1.0) * 127.5)))
        fixed_g.append(clamp_8bit(round((y + 1.0) * 127.5)))

    r.putdata(fixed_r)
    g.putdata(fixed_g)
    return Image.merge("RGBA", (r, g, b, a))


def upscale_generic_map(source_path: Path, target_size: int) -> Image.Image:
    image = open_rgba(source_path)
    return image.resize((target_size, target_size), Image.LANCZOS)

def analyze_base_texture(source_path: Path) -> dict[str, Any]:
    image = open_rgba(source_path)
    rgb = image.convert("RGB")
    stat = ImageStat.Stat(rgb)
    mean_rgb = [int(round(value)) for value in stat.mean[:3]]
    stddev = stat.stddev[:3]
    contrast = sum(stddev) / max(1, len(stddev))
    return {
        "size": list(image.size),
        "mean_rgb": mean_rgb,
        "dominant_colors": dominant_color_hexes(rgb, count=5),
        "alpha_coverage": round(alpha_coverage_ratio(image), 4),
        "unique_color_count": count_unique_colors(rgb),
        "contrast": round(float(contrast), 2),
        "edge_density": round(edge_density(rgb), 4),
    }


def analyze_normal_map(source_path: Path) -> dict[str, Any]:
    image = open_rgba(source_path)
    r, g, _, _ = image.split()
    stat = ImageStat.Stat(image)
    relief = average_normal_xy_magnitude(r, g)
    ao_mean = stat.mean[2] / 255.0
    height_mean = stat.mean[3] / 255.0
    notes = []
    if relief >= 0.18:
        notes.append("pronounced surface relief and edge beveling from the normal map")
    elif relief >= 0.08:
        notes.append("moderate surface relief from the normal map")
    if ao_mean <= 0.75:
        notes.append("darker ambient-occlusion pockets in crevices")
    if height_mean <= 0.75:
        notes.append("recessed or layered height detail that should stay readable")
    return {
        "relief_strength": round(relief, 4),
        "ao_mean": round(ao_mean, 4),
        "height_mean": round(height_mean, 4),
        "notes": notes,
    }


def analyze_specular_map(source_path: Path) -> dict[str, Any]:
    image = open_rgba(source_path)
    r, g, b, a = image.split()
    smoothness = ImageStat.Stat(r).mean[0] / 255.0
    reflectance = ImageStat.Stat(g).mean[0] / 255.0
    metallic_ratio = ratio_where(g, lambda value: value >= 230)
    porous_ratio = ratio_where(b, lambda value: value <= 64)
    subsurface_ratio = ratio_where(b, lambda value: 64 < value < 230)
    emissive_ratio = ratio_where(a, lambda value: value < 254)
    notes = []
    if metallic_ratio >= 0.08:
        notes.append("metallic or very high-F0 sections in the LabPBR specular map")
    elif smoothness <= 0.25:
        notes.append("very rough matte roughness response")
    elif smoothness >= 0.65:
        notes.append("smoother polished highlights on raised areas")
    if porous_ratio >= 0.25:
        notes.append("porous or chalky absorption behavior")
    if subsurface_ratio >= 0.25:
        notes.append("soft subsurface scattering hints in thinner areas")
    if emissive_ratio >= 0.01:
        notes.append("small emissive accents that should remain visually coherent")
    return {
        "smoothness_mean": round(smoothness, 4),
        "reflectance_mean": round(reflectance, 4),
        "metallic_ratio": round(metallic_ratio, 4),
        "porous_ratio": round(porous_ratio, 4),
        "subsurface_ratio": round(subsurface_ratio, 4),
        "emissive_ratio": round(emissive_ratio, 4),
        "notes": notes,
    }


def dominant_color_hexes(image: Image.Image, count: int) -> list[str]:
    quantized = image.convert("P", palette=Image.ADAPTIVE, colors=count)
    palette = quantized.getpalette()
    colors = quantized.getcolors()
    if not colors or palette is None:
        return []
    output = []
    for _, palette_index in sorted(colors, reverse=True)[:count]:
        start = palette_index * 3
        rgb = palette[start:start + 3]
        output.append("#%02x%02x%02x" % tuple(rgb))
    return output


def edge_density(image: Image.Image) -> float:
    width, height = image.size
    if width < 2 or height < 2:
        return 0.0
    pixels = image.load()
    samples = 0
    edges = 0
    for y in range(height - 1):
        for x in range(width - 1):
            current = pixels[x, y]
            right = pixels[x + 1, y]
            down = pixels[x, y + 1]
            if color_delta(current, right) >= 36:
                edges += 1
            if color_delta(current, down) >= 36:
                edges += 1
            samples += 2
    return edges / samples if samples else 0.0


def color_delta(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return float(sum(abs(a[index] - b[index]) for index in range(3))) / 3.0


def average_normal_xy_magnitude(r: Image.Image, g: Image.Image) -> float:
    total = 0.0
    count = 0
    for red, green in zip(r.getdata(), g.getdata()):
        x = (red / 127.5) - 1.0
        y = (green / 127.5) - 1.0
        total += min(1.0, math.sqrt((x * x) + (y * y)))
        count += 1
    return total / max(1, count)


def ratio_where(channel: Image.Image, predicate) -> float:
    matches = 0
    total = 0
    for value in channel.getdata():
        if predicate(value):
            matches += 1
        total += 1
    return matches / max(1, total)


def count_unique_colors(image: Image.Image) -> int:
    colors = image.getcolors(maxcolors=1_000_000)
    return len(colors) if colors is not None else 1_000_000


def open_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def alpha_coverage_ratio(image: Image.Image) -> float:
    alpha = image.getchannel("A")
    visible_pixels = sum(1 for value in alpha.getdata() if value > 0)
    return visible_pixels / max(1, image.width * image.height)


def source_alpha_mask(path: Path, target_size: int) -> Image.Image:
    with Image.open(path) as image:
        alpha = image.convert("RGBA").getchannel("A")
        return alpha.resize((target_size, target_size), Image.NEAREST)


def copy_sidecar_if_needed(sidecar_path: Path | None, pack_root: Path, output_root: Path) -> None:
    if not sidecar_path or not sidecar_path.exists():
        return
    destination = output_root / sidecar_path.relative_to(pack_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sidecar_path, destination)


def sidecar_for_png(path: Path | None) -> Path | None:
    if path is None:
        return None
    return path.with_name(path.name + ".mcmeta")


def sidecar_is_animated(sidecar_path: Path | None) -> bool:
    if not sidecar_path or not sidecar_path.exists():
        return False
    try:
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(data, dict) and "animation" in data


def namespace_from_texture(path: Path) -> str:
    parts = path.parts
    assets_index = parts.index("assets")
    return parts[assets_index + 1]


def kind_from_texture(path: Path) -> str:
    parts = path.parts
    try:
        textures_index = parts.index("textures")
        group = parts[textures_index + 1]
    except (ValueError, IndexError):
        return "other"
    if group in {"block", "item", "entity"}:
        return group
    return "other"


def summarize_skips(skipped: list[dict[str, Any]]) -> dict[str, Any]:
    by_reason: dict[str, int] = {}
    for entry in skipped:
        reason = str(entry.get("reason", "unknown"))
        by_reason[reason] = by_reason.get(reason, 0) + 1
    return {
        "count": len(skipped),
        "by_reason": by_reason,
    }


def logical_name_from_path(path: Path) -> str:
    stem = path.stem
    if stem.endswith(NORMAL_SUFFIX):
        stem = stem[: -len(NORMAL_SUFFIX)]
    if stem.endswith(SPECULAR_SUFFIX):
        stem = stem[: -len(SPECULAR_SUFFIX)]
    return stem


def humanize_name(name: str) -> str:
    return name.replace("_", " ")


def clamp_8bit(value: int) -> int:
    return max(0, min(255, int(value)))


def to_posix(path: Path) -> str:
    return str(path).replace("\\", "/")


def extract_unknown_parameter(message: str) -> str | None:
    match = re.search(r"Unknown parameter: '([^']+)'", message)
    if not match:
        return None
    return match.group(1)


def is_descendant_of(path: Path, candidate_root: Path) -> bool:
    try:
        path.relative_to(candidate_root)
        return True
    except ValueError:
        return False

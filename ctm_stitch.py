#!/usr/bin/env python3
"""
ctm_stitch.py — CTM Tile Stitcher & Resource Pack Exporter

Commands:
  stitch        Recursively stitch split CTM tiles → ctm/indev/ sprite sheets
  pack --mode dev   Same as stitch: tiles in ctm/* → stitched sheets in ctm/indev/
  pack --mode prod  Reverse: split ctm/indev/ sheets → individual tiles back into ctm/*
  export        Zip the resource pack, excluding indev/, git files, and dev-only files

Usage:
  python ctm_stitch.py stitch [--ctm-dir PATH] [--out-dir PATH] [--dry-run]
  python ctm_stitch.py pack --mode dev  [--ctm-dir PATH] [--indev-dir PATH] [--dry-run]
  python ctm_stitch.py pack --mode prod [--ctm-dir PATH] [--indev-dir PATH] [--dry-run]
  python ctm_stitch.py export [--pack-dir PATH] [--output FILE] [--dry-run]
"""

import argparse
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit(
        "Pillow is required. Install it with:  pip install Pillow"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_properties(path: Path) -> dict:
    """Parse a .properties file into a dict (strips comments, blank lines)."""
    props = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                props[key.strip()] = value.strip()
    return props


def parse_tile_range(tiles_str: str) -> list[int]:
    """
    Parse the 'tiles' property into a sorted list of tile indices.
    Supports:
      '0-3'       → [0, 1, 2, 3]
      '0-3 5 7'   → [0, 1, 2, 3, 5, 7]
      '0 1 2 3'   → [0, 1, 2, 3]
    """
    indices = []
    for token in tiles_str.split():
        if "-" in token:
            start, end = token.split("-", 1)
            indices.extend(range(int(start), int(end) + 1))
        else:
            indices.append(int(token))
    return sorted(set(indices))


def detect_suffixes(folder: Path, tile_indices: list[int]) -> list[str]:
    """
    Auto-detect which texture suffixes are present for this CTM folder.
    Checks against tile 0 (or the first available tile).
    Returns a list like ['', '_n', '_s'] — without the .png extension.
    """
    if not tile_indices:
        return [""]
    probe = tile_indices[0]
    suffixes = []
    # Always include the base suffix if the base tile exists
    if (folder / f"{probe}.png").exists():
        suffixes.append("")
    # Check for _n and _s (normal/specular PBR maps)
    for suffix in ("_n", "_s", "_e"):
        if (folder / f"{probe}{suffix}.png").exists():
            suffixes.append(suffix)
    return suffixes if suffixes else [""]


def stitch_tiles(
    folder: Path,
    name: str,
    tile_indices: list[int],
    width: int,
    height: int,
    suffix: str,
    out_dir: Path,
    dry_run: bool,
) -> bool:
    """
    Stitch numbered tile PNGs into a single sprite sheet.

    Tiles are laid out left-to-right, top-to-bottom:
      tile_indices[row*width + col]  →  position (col, row)

    Returns True on success, False if any tile is missing.
    """
    # Verify all tiles exist
    missing = []
    for idx in tile_indices:
        tile_path = folder / f"{idx}{suffix}.png"
        if not tile_path.exists():
            missing.append(str(tile_path))
    if missing:
        print(
            f"  [SKIP] {name}{suffix}.png - missing tiles:\n"
            + "\n".join(f"    {m}" for m in missing)
        )
        return False

    # Load first tile to determine tile size
    first_tile = Image.open(folder / f"{tile_indices[0]}{suffix}.png").convert("RGBA")
    tile_w, tile_h = first_tile.size

    sheet_w = width * tile_w
    sheet_h = height * tile_h

    if dry_run:
        print(
            f"  [DRY-RUN] Would stitch {len(tile_indices)} tiles "
            f"-> {sheet_w}x{sheet_h}px : {out_dir / (name + suffix + '.png')}"
        )
        return True

    sheet = Image.new("RGBA", (sheet_w, sheet_h))

    for linear_idx, tile_num in enumerate(tile_indices):
        row = linear_idx // width
        col = linear_idx % width
        tile_img = Image.open(folder / f"{tile_num}{suffix}.png").convert("RGBA")
        if tile_img.size != (tile_w, tile_h):
            tile_img = tile_img.resize((tile_w, tile_h), Image.LANCZOS)
        sheet.paste(tile_img, (col * tile_w, row * tile_h))

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}{suffix}.png"
    sheet.save(out_path, "PNG")
    print(f"  [OK] {out_path.relative_to(out_dir.parent.parent)}")
    return True


# ---------------------------------------------------------------------------
# Stitch command
# ---------------------------------------------------------------------------

# Folders/files inside ctm/ that are not CTM packs and should be skipped
SKIP_DIRS = {"indev"}


def find_ctm_folders(ctm_root: Path) -> list[tuple[Path, Path]]:
    """
    Walk ctm_root recursively. A folder is a CTM folder if it contains a
    .properties file. Returns list of (folder, properties_file) tuples,
    skipping anything inside SKIP_DIRS.
    """
    results = []
    for dirpath, dirnames, filenames in os.walk(ctm_root):
        current = Path(dirpath)

        # Prune skip dirs in-place so os.walk doesn't descend into them
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in SKIP_DIRS
        ]

        props_files = [f for f in filenames if f.endswith(".properties")]
        for pf in props_files:
            results.append((current, current / pf))

    return results


def cmd_stitch(args):
    ctm_root = Path(args.ctm_dir).resolve()
    out_root = Path(args.out_dir).resolve()

    if not ctm_root.exists():
        sys.exit(f"CTM directory not found: {ctm_root}")

    print(f"CTM root : {ctm_root}")
    print(f"Output   : {out_root}")
    if args.dry_run:
        print("(DRY RUN - no files will be written)\n")

    ctm_folders = find_ctm_folders(ctm_root)
    if not ctm_folders:
        print("No .properties files found.")
        return

    total_ok = 0
    total_skip = 0
    total_folders = 0

    for folder, props_path in ctm_folders:
        props = parse_properties(props_path)

        # Only process 'repeat' method CTM (the tile-grid type)
        method = props.get("method", "repeat").lower()
        if method != "repeat":
            print(f"[SKIP-METHOD={method}] {props_path.relative_to(ctm_root)}")
            continue

        tiles_str = props.get("tiles", "")
        width_str = props.get("width", "")
        height_str = props.get("height", "")

        if not tiles_str or not width_str or not height_str:
            print(f"[SKIP-INCOMPLETE] {props_path.relative_to(ctm_root)} - missing tiles/width/height")
            continue

        try:
            tile_indices = parse_tile_range(tiles_str)
            width = int(width_str)
            height = int(height_str)
        except ValueError as exc:
            print(f"[SKIP-PARSE] {props_path.relative_to(ctm_root)} - {exc}")
            continue

        if not tile_indices:
            print(f"[SKIP-EMPTY] {props_path.relative_to(ctm_root)} - no tile indices")
            continue

        # Derive output name from the folder name (matches the .properties stem)
        name = props_path.stem  # e.g. 'clay', 'mud', 'stone_bricks'

        # Build the relative path from ctm_root to this folder for namespacing
        rel_folder = folder.relative_to(ctm_root)
        # Output goes into indev/<relative_path_from_ctm>/
        out_dir = out_root / rel_folder

        suffixes = detect_suffixes(folder, tile_indices)

        print(f"\n[{name}]  {rel_folder}  ({width}x{height}, {len(tile_indices)} tiles, suffixes: {suffixes})")
        total_folders += 1

        for suffix in suffixes:
            ok = stitch_tiles(
                folder=folder,
                name=name,
                tile_indices=tile_indices,
                width=width,
                height=height,
                suffix=suffix,
                out_dir=out_dir,
                dry_run=args.dry_run,
            )
            if ok:
                total_ok += 1
            else:
                total_skip += 1

    print(f"\nDone. {total_folders} CTM folders processed - {total_ok} sheets stitched, {total_skip} skipped.")


# ---------------------------------------------------------------------------
# Pack command (dev / prod)
# ---------------------------------------------------------------------------

def split_sheet(
    sheet_path: Path,
    name: str,
    tile_indices: list[int],
    width: int,
    height: int,
    suffix: str,
    out_dir: Path,
    dry_run: bool,
) -> bool:
    """
    Split a stitched sprite sheet back into individual numbered tile PNGs.
    Reverses the work of stitch_tiles().
    Returns True on success, False if the sheet is missing.
    """
    if not sheet_path.exists():
        print(f"  [SKIP] {sheet_path.name} - sheet not found")
        return False

    sheet = Image.open(sheet_path).convert("RGBA")
    sheet_w, sheet_h = sheet.size
    tile_w = sheet_w // width
    tile_h = sheet_h // height

    if dry_run:
        print(
            f"  [DRY-RUN] Would split {sheet_w}x{sheet_h}px sheet "
            f"-> {len(tile_indices)} tiles ({tile_w}x{tile_h}px each) : {out_dir}"
        )
        return True

    out_dir.mkdir(parents=True, exist_ok=True)
    for linear_idx, tile_num in enumerate(tile_indices):
        row = linear_idx // width
        col = linear_idx % width
        box = (col * tile_w, row * tile_h, (col + 1) * tile_w, (row + 1) * tile_h)
        tile_img = sheet.crop(box)
        out_path = out_dir / f"{tile_num}{suffix}.png"
        tile_img.save(out_path, "PNG")

    print(f"  [OK] {len(tile_indices)} tiles -> {out_dir}")
    return True


def find_indev_folders(indev_root: Path) -> list[tuple[Path, str]]:
    """
    Walk indev_root. A folder is an indev folder if it contains at least one
    .png that matches a name without a numeric prefix (i.e. the stitched sheet).
    Returns list of (folder, stem_name) tuples.
    """
    results = []
    for dirpath, dirnames, filenames in os.walk(indev_root):
        current = Path(dirpath)
        # Look for files that look like stitched sheets: <name>.png, <name>_n.png, etc.
        # Stitched sheet names never start with a digit.
        sheets = [
            f for f in filenames
            if f.endswith(".png") and not f[0].isdigit()
        ]
        if sheets:
            # Derive stem: strip all known suffixes to get the base name
            stems = set()
            for s in sheets:
                stem = s
                for suf in ("_n.png", "_s.png", "_e.png", ".png"):
                    if stem.endswith(suf):
                        stem = stem[: -len(suf)]
                        break
                stems.add(stem)
            for stem in stems:
                results.append((current, stem))
    return results


def cmd_pack(args):
    ctm_root = Path(args.ctm_dir).resolve()
    indev_root = Path(args.indev_dir).resolve()
    mode = args.mode.lower()

    if mode not in ("dev", "prod"):
        sys.exit("--mode must be 'dev' or 'prod'")

    if not ctm_root.exists():
        sys.exit(f"CTM directory not found: {ctm_root}")

    print(f"Mode     : {mode}")
    print(f"CTM root : {ctm_root}")
    print(f"Indev    : {indev_root}")
    if args.dry_run:
        print("(DRY RUN - no files will be written)\n")

    # ---- DEV: tiles → stitched sheets in indev/ (same as stitch command) ----
    if mode == "dev":
        ctm_folders = find_ctm_folders(ctm_root)
        if not ctm_folders:
            print("No .properties files found.")
            return

        total_ok = 0
        total_skip = 0
        total_folders = 0

        for folder, props_path in ctm_folders:
            props = parse_properties(props_path)
            method = props.get("method", "repeat").lower()
            if method != "repeat":
                print(f"[SKIP-METHOD={method}] {props_path.relative_to(ctm_root)}")
                continue

            tiles_str = props.get("tiles", "")
            width_str = props.get("width", "")
            height_str = props.get("height", "")

            if not tiles_str or not width_str or not height_str:
                print(f"[SKIP-INCOMPLETE] {props_path.relative_to(ctm_root)}")
                continue

            try:
                tile_indices = parse_tile_range(tiles_str)
                width = int(width_str)
                height = int(height_str)
            except ValueError as exc:
                print(f"[SKIP-PARSE] {props_path.relative_to(ctm_root)} - {exc}")
                continue

            if not tile_indices:
                continue

            name = props_path.stem
            rel_folder = folder.relative_to(ctm_root)
            out_dir = indev_root / rel_folder
            suffixes = detect_suffixes(folder, tile_indices)

            print(f"\n[{name}]  {rel_folder}  ({width}x{height}, {len(tile_indices)} tiles)")
            total_folders += 1

            for suffix in suffixes:
                ok = stitch_tiles(
                    folder=folder,
                    name=name,
                    tile_indices=tile_indices,
                    width=width,
                    height=height,
                    suffix=suffix,
                    out_dir=out_dir,
                    dry_run=args.dry_run,
                )
                if ok:
                    total_ok += 1
                else:
                    total_skip += 1

        print(f"\nDone. {total_folders} CTM folders -> {total_ok} sheets stitched, {total_skip} skipped.")

    # ---- PROD: indev sheets → individual tiles back into ctm/* ----
    else:
        if not indev_root.exists():
            sys.exit(f"Indev directory not found: {indev_root}")

        # We need the .properties files from ctm/* to know width/height/tiles.
        # Build a lookup: relative-folder-path → (props, props_path)
        props_lookup: dict[Path, tuple[dict, Path]] = {}
        for folder, props_path in find_ctm_folders(ctm_root):
            rel = folder.relative_to(ctm_root)
            props_lookup[rel] = (parse_properties(props_path), props_path)

        total_ok = 0
        total_skip = 0
        total_folders = 0

        for dirpath, dirnames, filenames in os.walk(indev_root):
            current = Path(dirpath)
            rel_folder = current.relative_to(indev_root)

            # Find stitched sheet files: <name>.png (not starting with digit)
            sheet_bases: dict[str, list[str]] = {}  # stem → [suffixes found]
            for f in filenames:
                if not f.endswith(".png") or f[0].isdigit():
                    continue
                stem = f
                found_suf = ""
                for suf in ("_n.png", "_s.png", "_e.png", ".png"):
                    if stem.endswith(suf):
                        stem = stem[: -len(suf)]
                        found_suf = suf[:-4]  # strip .png → e.g. '_n'
                        break
                sheet_bases.setdefault(stem, []).append(found_suf)

            if not sheet_bases:
                continue

            # Look up the matching properties from ctm/*
            if rel_folder not in props_lookup:
                print(f"[SKIP-NO-PROPS] {rel_folder} - no matching .properties in ctm/")
                continue

            props, props_path = props_lookup[rel_folder]
            method = props.get("method", "repeat").lower()
            if method != "repeat":
                print(f"[SKIP-METHOD={method}] {rel_folder}")
                continue

            tiles_str = props.get("tiles", "")
            width_str = props.get("width", "")
            height_str = props.get("height", "")

            if not tiles_str or not width_str or not height_str:
                print(f"[SKIP-INCOMPLETE] {rel_folder}")
                continue

            try:
                tile_indices = parse_tile_range(tiles_str)
                width = int(width_str)
                height = int(height_str)
            except ValueError as exc:
                print(f"[SKIP-PARSE] {rel_folder} - {exc}")
                continue

            out_dir = ctm_root / rel_folder

            for stem, suffixes in sheet_bases.items():
                print(f"\n[{stem}]  {rel_folder}  ({width}x{height}, {len(tile_indices)} tiles, suffixes: {suffixes})")
                total_folders += 1

                for suffix in suffixes:
                    sheet_path = current / f"{stem}{suffix}.png"
                    ok = split_sheet(
                        sheet_path=sheet_path,
                        name=stem,
                        tile_indices=tile_indices,
                        width=width,
                        height=height,
                        suffix=suffix,
                        out_dir=out_dir,
                        dry_run=args.dry_run,
                    )
                    if ok:
                        total_ok += 1
                    else:
                        total_skip += 1

        print(f"\nDone. {total_folders} indev sheets processed - {total_ok} split, {total_skip} skipped.")


# ---------------------------------------------------------------------------
# Export command
# ---------------------------------------------------------------------------

# Patterns to EXCLUDE from the export zip
EXPORT_EXCLUDE_DIRS = {
    ".git",
    ".github",
    "indev",
    "__pycache__",
    ".windsurf",
    ".vscode",
    ".idea",
}

EXPORT_EXCLUDE_EXTENSIONS = {
    ".ps1",
    ".bat",
    ".sh",
    ".py",
    ".md",
    ".zip",
    ".7z",
    ".rar",
}

EXPORT_EXCLUDE_FILES = {
    "thumbs.db",
    ".ds_store",
    "desktop.ini",
    ".gitattributes",
    ".gitignore",
    ".gitmodules",
}


def should_exclude(rel_path: Path) -> bool:
    """Return True if this relative path should be excluded from the export."""
    parts_lower = [p.lower() for p in rel_path.parts]

    # Exclude if any path component is a banned dir
    for part in parts_lower[:-1]:  # all but last (filename)
        if part in EXPORT_EXCLUDE_DIRS:
            return True

    filename = rel_path.name
    filename_lower = filename.lower()

    if filename_lower in EXPORT_EXCLUDE_FILES:
        return True

    suffix_lower = "".join(s.lower() for s in rel_path.suffixes)
    if suffix_lower in EXPORT_EXCLUDE_EXTENSIONS:
        return True
    # Also check single suffix
    if rel_path.suffix.lower() in EXPORT_EXCLUDE_EXTENSIONS:
        return True

    return False


def cmd_export(args):
    pack_dir = Path(args.pack_dir).resolve()
    output_file = Path(args.output).resolve()

    if not pack_dir.exists():
        sys.exit(f"Pack directory not found: {pack_dir}")

    if output_file.suffix.lower() != ".zip":
        output_file = output_file.with_suffix(".zip")

    print(f"Pack dir : {pack_dir}")
    print(f"Output   : {output_file}")
    if args.dry_run:
        print("(DRY RUN - no zip will be written)\n")

    included = []
    excluded = []

    for root, dirnames, filenames in os.walk(pack_dir):
        current = Path(root)
        rel_root = current.relative_to(pack_dir)

        # Prune excluded dirs so os.walk doesn't descend
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in EXPORT_EXCLUDE_DIRS
        ]

        for filename in filenames:
            rel_path = rel_root / filename
            if should_exclude(rel_path):
                excluded.append(rel_path)
            else:
                included.append((current / filename, rel_path))

    print(f"Files to include : {len(included)}")
    print(f"Files excluded   : {len(excluded)}")

    if args.dry_run:
        print("\n--- Excluded files ---")
        for ep in sorted(excluded):
            print(f"  EXCL  {ep}")
        print("\n--- Included files (sample, first 20) ---")
        for ap, rp in included[:20]:
            print(f"  INCL  {rp}")
        if len(included) > 20:
            print(f"  ... and {len(included) - 20} more")
        return

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for abs_path, rel_path in included:
            zf.write(abs_path, rel_path)

    size_mb = output_file.stat().st_size / (1024 * 1024)
    print(f"\nExport complete -> {output_file}  ({size_mb:.2f} MB)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    root_dir = Path(__file__).resolve().parent
    default_ctm = root_dir / "assets" / "minecraft" / "optifine" / "ctm"
    default_indev = default_ctm / "indev"
    default_pack = root_dir

    parser = argparse.ArgumentParser(
        prog="ctm_stitch",
        description="CTM tile stitcher & resource pack exporter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- pack ---
    pack_p = subparsers.add_parser(
        "pack",
        help="Prepare CTM for dev (tiles→indev sheets) or prod (indev sheets→tiles)",
    )
    pack_p.add_argument(
        "--mode",
        required=True,
        choices=["dev", "prod"],
        metavar="MODE",
        help="'dev' stitches tiles into ctm/indev/ sheets; 'prod' splits indev sheets back into ctm/* tiles",
    )
    pack_p.add_argument(
        "--ctm-dir",
        default=str(default_ctm),
        metavar="PATH",
        help=f"Root CTM folder (default: {default_ctm})",
    )
    pack_p.add_argument(
        "--indev-dir",
        default=str(default_indev),
        metavar="PATH",
        help=f"Indev directory for stitched sheets (default: {default_indev})",
    )
    pack_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing files",
    )
    pack_p.set_defaults(func=cmd_pack)

    # --- stitch ---
    stitch_p = subparsers.add_parser(
        "stitch",
        help="Stitch split CTM tiles back into sprite sheets",
    )
    stitch_p.add_argument(
        "--ctm-dir",
        default=str(default_ctm),
        metavar="PATH",
        help=f"Root CTM folder (default: {default_ctm})",
    )
    stitch_p.add_argument(
        "--out-dir",
        default=str(default_indev),
        metavar="PATH",
        help=f"Output directory for stitched sheets (default: {default_indev})",
    )
    stitch_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing files",
    )
    stitch_p.set_defaults(func=cmd_stitch)

    # --- export ---
    export_p = subparsers.add_parser(
        "export",
        help="Zip the resource pack excluding dev/indev files",
    )
    export_p.add_argument(
        "--pack-dir",
        default=str(default_pack),
        metavar="PATH",
        help=f"Resource pack root directory (default: {default_pack})",
    )
    export_p.add_argument(
        "--output",
        default=str(default_pack / "SummitMCRP.zip"),
        metavar="FILE",
        help="Output zip file path (default: SummitMCRP.zip in pack root)",
    )
    export_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be included/excluded without writing zip",
    )
    export_p.set_defaults(func=cmd_export)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

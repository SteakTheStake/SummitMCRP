from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Sequence

try:
    from .common import (
        ALLOWED_BLOCK_ROTATION_ANGLES,
        collect_all_jem_ids,
        count_predicate_keys,
        load_json,
        rel_to_repo,
        walk_jem_models,
    )
except ImportError:
    from common import (
        ALLOWED_BLOCK_ROTATION_ANGLES,
        collect_all_jem_ids,
        count_predicate_keys,
        load_json,
        rel_to_repo,
        walk_jem_models,
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_vec3(vec: Any, name: str, errors: List[str]) -> None:
    if not isinstance(vec, list) or len(vec) != 3 or not all(_is_number(v) for v in vec):
        errors.append(f"{name} must be a numeric [x,y,z] array")


def validate_entity_data(data: Dict[str, Any], label: str) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    texture = data.get("texture")
    if not isinstance(texture, str) or not texture:
        errors.append("Missing or invalid root `texture` string")
    elif not texture.startswith("textures/"):
        warnings.append("Root `texture` should usually begin with `textures/` for JEM")

    texture_size = data.get("textureSize")
    if (
        not isinstance(texture_size, list)
        or len(texture_size) != 2
        or not all(isinstance(v, int) and v > 0 for v in texture_size)
    ):
        errors.append("Missing or invalid root `textureSize` [w,h] integers")

    models = data.get("models")
    if not isinstance(models, list):
        errors.append("Missing or invalid root `models` array")
        models = []

    # Root-level model checks
    for i, model in enumerate(models):
        if not isinstance(model, dict):
            errors.append(f"models[{i}] must be an object")
            continue

        part = model.get("part")
        model_id = model.get("id")
        if not isinstance(part, str) or not part:
            errors.append(f"models[{i}] missing required `part` string")
        if not isinstance(model_id, str) or not model_id:
            errors.append(f"models[{i}] missing required `id` string")

        translate = model.get("translate")
        if translate is not None:
            _validate_vec3(translate, f"models[{i}].translate", errors)

        rotate = model.get("rotate")
        if rotate is not None:
            _validate_vec3(rotate, f"models[{i}].rotate", errors)

    ids = collect_all_jem_ids(data)
    if len(ids) != len(set(ids)):
        seen = set()
        duplicates = []
        for model_id in ids:
            if model_id in seen and model_id not in duplicates:
                duplicates.append(model_id)
            seen.add(model_id)
        errors.append(f"Duplicate model ids detected: {duplicates}")

    for model in walk_jem_models(models):
        if model.get("_todo"):
            warnings.append(f"Model id `{model.get('id', '<unknown>')}` still contains TODO marker")
        if "submodels" in model and not isinstance(model.get("submodels"), list):
            errors.append(f"Model id `{model.get('id', '<unknown>')}` has non-list `submodels`")

    # Submodels should not define `part` (AGENTS rule)
    for root_model in models:
        if not isinstance(root_model, dict):
            continue
        for sub in _walk_submodels(root_model.get("submodels", [])):
            if isinstance(sub, dict) and "part" in sub:
                warnings.append(
                    f"Submodel id `{sub.get('id', '<unknown>')}` contains `part`; submodels should not declare root part names"
                )

    return {
        "kind": "entity",
        "path": label,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "root_models": len(models),
            "total_ids": len(ids),
            "unique_ids": len(set(ids)),
        },
    }


def _walk_submodels(submodels: Sequence[Any]) -> Sequence[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for submodel in submodels:
        if isinstance(submodel, dict):
            out.append(submodel)
            nested = submodel.get("submodels")
            if isinstance(nested, list):
                out.extend(_walk_submodels(nested))
    return out


def _validate_face_refs(element: Dict[str, Any], textures: Dict[str, Any], idx: int, errors: List[str]) -> None:
    faces = element.get("faces")
    if faces is None:
        return
    if not isinstance(faces, dict):
        errors.append(f"elements[{idx}].faces must be an object")
        return

    for face_name, face in faces.items():
        if not isinstance(face, dict):
            errors.append(f"elements[{idx}].faces.{face_name} must be an object")
            continue
        tex = face.get("texture")
        if isinstance(tex, str) and tex.startswith("#"):
            tex_key = tex[1:]
            if tex_key not in textures:
                errors.append(f"elements[{idx}].faces.{face_name} references unknown texture variable `{tex}`")


def validate_block_item_data(data: Dict[str, Any], label: str) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    textures = data.get("textures")
    if textures is None:
        textures = {}
    if not isinstance(textures, dict):
        errors.append("`textures` must be an object when present")
        textures = {}

    elements = data.get("elements")
    if elements is None:
        elements = []
    if not isinstance(elements, list):
        errors.append("`elements` must be an array when present")
        elements = []

    if len(elements) > 112:
        errors.append(f"Model has {len(elements)} elements; max supported is 112")

    for i, element in enumerate(elements):
        if not isinstance(element, dict):
            errors.append(f"elements[{i}] must be an object")
            continue

        from_vec = element.get("from")
        to_vec = element.get("to")
        if from_vec is not None:
            _validate_vec3(from_vec, f"elements[{i}].from", errors)
            if isinstance(from_vec, list) and all(_is_number(v) for v in from_vec):
                for axis, value in enumerate(from_vec):
                    if value < 0 or value > 16:
                        warnings.append(f"elements[{i}].from[{axis}]={value} is outside recommended 0..16")

        if to_vec is not None:
            _validate_vec3(to_vec, f"elements[{i}].to", errors)
            if isinstance(to_vec, list) and all(_is_number(v) for v in to_vec):
                for axis, value in enumerate(to_vec):
                    if value < 0 or value > 16:
                        warnings.append(f"elements[{i}].to[{axis}]={value} is outside recommended 0..16")

        rotation = element.get("rotation")
        if rotation is not None:
            if not isinstance(rotation, dict):
                errors.append(f"elements[{i}].rotation must be an object")
            else:
                angle = rotation.get("angle")
                if not _is_number(angle):
                    errors.append(f"elements[{i}].rotation.angle must be numeric")
                elif float(angle) not in ALLOWED_BLOCK_ROTATION_ANGLES:
                    errors.append(
                        f"elements[{i}].rotation.angle={angle} not in allowed set {sorted(ALLOWED_BLOCK_ROTATION_ANGLES)}"
                    )

        _validate_face_refs(element, textures, i, errors)

    overrides = data.get("overrides")
    if isinstance(overrides, list):
        predicate_sizes = [count_predicate_keys(o) for o in overrides if isinstance(o, dict)]
        for i in range(1, len(predicate_sizes)):
            if predicate_sizes[i] < predicate_sizes[i - 1]:
                warnings.append(
                    "`overrides` may be ordered from more-specific to less-specific; expected least-specific to most-specific"
                )
                break

    for key in data.keys():
        if isinstance(key, str) and key.startswith("_todo"):
            warnings.append(f"Temporary key `{key}` still present")

    return {
        "kind": "block_item",
        "path": label,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "elements": len(elements),
            "textures": len(textures),
            "overrides": len(overrides) if isinstance(overrides, list) else 0,
        },
    }


def validate_file(repo_root: Path, file_path: Path, kind: str) -> Dict[str, Any]:
    label = rel_to_repo(file_path, repo_root)
    data = load_json(file_path)
    if not isinstance(data, dict):
        return {
            "kind": kind,
            "path": label,
            "errors": ["Top-level JSON must be an object"],
            "warnings": [],
            "stats": {},
        }

    if kind == "entity":
        return validate_entity_data(data, label)

    return validate_block_item_data(data, label)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate JEM and block/item model JSON files.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--kind", choices=["entity", "block_item", "auto"], default="auto")
    parser.add_argument("--path", action="append", required=True, help="Relative or absolute model file path")
    return parser.parse_args()


def infer_kind_from_path(path: Path) -> str:
    normalized = str(path).replace("\\", "/").lower()
    if normalized.endswith(".jem"):
        return "entity"
    return "block_item"


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    has_errors = False

    for raw_path in args.path:
        file_path = Path(raw_path)
        if not file_path.is_absolute():
            file_path = (repo_root / file_path).resolve()

        if not file_path.exists():
            print(f"[ERROR] Missing file: {rel_to_repo(file_path, repo_root)}")
            has_errors = True
            continue

        kind = infer_kind_from_path(file_path) if args.kind == "auto" else args.kind
        report = validate_file(repo_root, file_path, kind)

        print(f"[{report['kind']}] {report['path']}")
        for err in report["errors"]:
            print(f"  ERROR: {err}")
        for warn in report["warnings"]:
            print(f"  WARN:  {warn}")
        print(f"  stats: {report['stats']}")

        if report["errors"]:
            has_errors = True

    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

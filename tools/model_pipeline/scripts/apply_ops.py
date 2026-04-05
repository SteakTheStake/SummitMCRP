from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

try:
    from .common import dump_json, find_jem_model_by_id, load_json, rel_to_repo
except ImportError:
    from common import dump_json, find_jem_model_by_id, load_json, rel_to_repo


def set_nested_key(root: Dict[str, Any], path: str, value: Any) -> None:
    if "." not in path:
        root[path] = value
        return

    keys = path.split(".")
    cursor: Dict[str, Any] = root
    for key in keys[:-1]:
        next_obj = cursor.get(key)
        if not isinstance(next_obj, dict):
            next_obj = {}
            cursor[key] = next_obj
        cursor = next_obj
    cursor[keys[-1]] = value


def merge_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def _remove_jem_model_by_id(models: List[Dict[str, Any]], target_id: str) -> bool:
    for i, model in enumerate(models):
        if model.get("id") == target_id:
            del models[i]
            return True

    for model in models:
        submodels = model.get("submodels")
        if isinstance(submodels, list) and _remove_jem_model_by_id(submodels, target_id):
            return True

    return False


def _upsert_by_id(models: List[Dict[str, Any]], model_data: Dict[str, Any], target_id: str) -> bool:
    for i, model in enumerate(models):
        if model.get("id") == target_id:
            models[i] = merge_dict(model, model_data)
            return True
    return False


def apply_entity_ops(target_data: Dict[str, Any], ops: List[Dict[str, Any]]) -> List[str]:
    if not isinstance(target_data.get("models"), list):
        target_data["models"] = []

    changes: List[str] = []

    for op in ops:
        action = op.get("action")
        if action == "set_root":
            set_nested_key(target_data, str(op.get("path", "")), op.get("data"))
            changes.append(f"set_root:{op.get('path')}")

        elif action == "upsert_model_part":
            model_data = op.get("data", {})
            target_id = op.get("id") or model_data.get("id")
            if not isinstance(model_data, dict) or not isinstance(target_id, str) or not target_id:
                raise ValueError(f"Invalid upsert_model_part op: {op}")

            if not _upsert_by_id(target_data["models"], model_data, target_id):
                target_data["models"].append(model_data)
            changes.append(f"upsert_model_part:{target_id}")

        elif action == "remove_model_part":
            target_id = op.get("id") or op.get("target_id")
            if not isinstance(target_id, str) or not target_id:
                raise ValueError(f"Invalid remove_model_part op: {op}")
            removed = _remove_jem_model_by_id(target_data["models"], target_id)
            changes.append(f"remove_model_part:{target_id}:{'ok' if removed else 'missing'}")

        elif action == "upsert_submodel":
            parent_id = op.get("parent_id")
            model_data = op.get("data", {})
            target_id = op.get("id") or model_data.get("id")
            if (
                not isinstance(parent_id, str)
                or not parent_id
                or not isinstance(model_data, dict)
                or not isinstance(target_id, str)
                or not target_id
            ):
                raise ValueError(f"Invalid upsert_submodel op: {op}")

            parent_model = find_jem_model_by_id(target_data, parent_id)
            if parent_model is None:
                raise ValueError(f"Parent id not found for submodel upsert: {parent_id}")

            if not isinstance(parent_model.get("submodels"), list):
                parent_model["submodels"] = []

            submodels = parent_model["submodels"]
            if not _upsert_by_id(submodels, model_data, target_id):
                submodels.append(model_data)
            changes.append(f"upsert_submodel:{parent_id}->{target_id}")

        elif action == "remove_submodel":
            parent_id = op.get("parent_id")
            target_id = op.get("id") or op.get("target_id")
            if not isinstance(parent_id, str) or not isinstance(target_id, str):
                raise ValueError(f"Invalid remove_submodel op: {op}")

            parent_model = find_jem_model_by_id(target_data, parent_id)
            if parent_model is None:
                changes.append(f"remove_submodel:{parent_id}->{target_id}:missing_parent")
                continue

            submodels = parent_model.get("submodels", [])
            if not isinstance(submodels, list):
                parent_model["submodels"] = []
                submodels = parent_model["submodels"]

            removed = _remove_jem_model_by_id(submodels, target_id)
            changes.append(f"remove_submodel:{parent_id}->{target_id}:{'ok' if removed else 'missing'}")

        else:
            raise ValueError(f"Unsupported entity action: {action}")

    return changes


def apply_block_item_ops(target_data: Dict[str, Any], ops: List[Dict[str, Any]]) -> List[str]:
    changes: List[str] = []

    for op in ops:
        action = op.get("action")
        if action == "set_root":
            set_nested_key(target_data, str(op.get("path", "")), op.get("data"))
            changes.append(f"set_root:{op.get('path')}")

        elif action == "upsert_texture":
            key = op.get("key")
            value = op.get("data")
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError(f"Invalid upsert_texture op: {op}")
            if not isinstance(target_data.get("textures"), dict):
                target_data["textures"] = {}
            target_data["textures"][key] = value
            changes.append(f"upsert_texture:{key}")

        elif action == "remove_texture":
            key = op.get("key")
            if not isinstance(key, str):
                raise ValueError(f"Invalid remove_texture op: {op}")
            if isinstance(target_data.get("textures"), dict):
                target_data["textures"].pop(key, None)
            changes.append(f"remove_texture:{key}")

        elif action == "upsert_element":
            if not isinstance(target_data.get("elements"), list):
                target_data["elements"] = []
            index = op.get("index")
            data = op.get("data")
            if not isinstance(data, dict):
                raise ValueError(f"Invalid upsert_element op: {op}")

            if isinstance(index, int) and index >= 0:
                while len(target_data["elements"]) <= index:
                    target_data["elements"].append({})
                target_data["elements"][index] = data
                changes.append(f"upsert_element:{index}")
            else:
                target_data["elements"].append(data)
                changes.append("upsert_element:append")

        elif action == "remove_element":
            index = op.get("index")
            if not isinstance(index, int) or index < 0:
                raise ValueError(f"Invalid remove_element op: {op}")
            removed = False
            if isinstance(target_data.get("elements"), list) and index < len(target_data["elements"]):
                del target_data["elements"][index]
                removed = True
            changes.append(f"remove_element:{index}:{'ok' if removed else 'missing'}")

        elif action == "upsert_override":
            if not isinstance(target_data.get("overrides"), list):
                target_data["overrides"] = []
            index = op.get("index")
            data = op.get("data")
            if not isinstance(data, dict):
                raise ValueError(f"Invalid upsert_override op: {op}")
            if isinstance(index, int) and index >= 0:
                while len(target_data["overrides"]) <= index:
                    target_data["overrides"].append({})
                target_data["overrides"][index] = data
                changes.append(f"upsert_override:{index}")
            else:
                target_data["overrides"].append(data)
                changes.append("upsert_override:append")

        elif action == "remove_override":
            index = op.get("index")
            if not isinstance(index, int) or index < 0:
                raise ValueError(f"Invalid remove_override op: {op}")
            removed = False
            if isinstance(target_data.get("overrides"), list) and index < len(target_data["overrides"]):
                del target_data["overrides"][index]
                removed = True
            changes.append(f"remove_override:{index}:{'ok' if removed else 'missing'}")

        else:
            raise ValueError(f"Unsupported block/item action: {action}")

    return changes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply operation patches to JEM or block/item model JSON.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--ops", required=True, help="Path to ops JSON")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_or_init_target(path: Path, kind: str) -> Dict[str, Any]:
    if path.exists():
        loaded = load_json(path)
        if not isinstance(loaded, dict):
            raise ValueError(f"Target model must be a JSON object: {path}")
        return loaded

    if kind == "entity":
        return {
            "credit": "model_pipeline",
            "texture": "",
            "textureSize": [64, 64],
            "models": [],
        }

    return {}


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    ops_path = Path(args.ops).resolve()
    payload = load_json(ops_path)
    if not isinstance(payload, dict):
        raise ValueError("Ops payload must be a JSON object.")

    kind = payload.get("kind")
    target_file = payload.get("target_file")
    ops = payload.get("ops", [])

    if kind not in {"entity", "block_item"}:
        raise ValueError(f"Unsupported ops kind: {kind}")
    if not isinstance(target_file, str) or not target_file:
        raise ValueError("Ops payload missing target_file")
    if not isinstance(ops, list):
        raise ValueError("Ops payload missing ops list")

    target_path = Path(target_file)
    if not target_path.is_absolute():
        target_path = (repo_root / target_path).resolve()

    target_data = load_or_init_target(target_path, kind)

    if kind == "entity":
        changes = apply_entity_ops(target_data, ops)
    else:
        changes = apply_block_item_ops(target_data, ops)

    if args.dry_run:
        print("Dry-run only; no file written.")
    else:
        dump_json(target_path, target_data)
        print(f"Wrote model: {target_path}")

    print(f"Target: {rel_to_repo(target_path, repo_root)}")
    for change in changes:
        print(f" - {change}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

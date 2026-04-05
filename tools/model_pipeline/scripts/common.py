from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

ALLOWED_BLOCK_ROTATION_ANGLES = {-45, -22.5, 0, 22.5, 45}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)
        f.write("\n")


def rel_to_repo(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def walk_jem_models(models: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    for model in models:
        yield model
        for submodel in _walk_submodels(model.get("submodels", [])):
            yield submodel


def _walk_submodels(submodels: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    for submodel in submodels:
        yield submodel
        for nested in _walk_submodels(submodel.get("submodels", [])):
            yield nested


def collect_all_jem_ids(jem_data: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for model in walk_jem_models(jem_data.get("models", [])):
        model_id = model.get("id")
        if isinstance(model_id, str) and model_id:
            ids.append(model_id)
    return ids


def find_jem_model_by_id(jem_data: Dict[str, Any], target_id: str) -> Dict[str, Any] | None:
    for model in walk_jem_models(jem_data.get("models", [])):
        if model.get("id") == target_id:
            return model
    return None


def count_predicate_keys(override: Dict[str, Any]) -> int:
    predicate = override.get("predicate")
    if not isinstance(predicate, dict):
        return 0
    return len(predicate)

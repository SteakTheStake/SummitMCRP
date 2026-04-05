from __future__ import annotations

import unittest

from tools.model_pipeline.scripts.validate_models import (
    validate_block_item_data,
    validate_entity_data,
)


class ValidateModelsTest(unittest.TestCase):
    def test_entity_duplicate_ids_are_errors(self) -> None:
        data = {
            "texture": "textures/entity/villager/villager.png",
            "textureSize": [64, 64],
            "models": [
                {"part": "head", "id": "head", "submodels": []},
                {"part": "body", "id": "head", "submodels": []},
            ],
        }
        report = validate_entity_data(data, "villager.jem")
        self.assertGreater(len(report["errors"]), 0)

    def test_block_invalid_rotation_angle_is_error(self) -> None:
        data = {
            "parent": "block/block",
            "textures": {"all": "block/stone"},
            "elements": [
                {
                    "from": [0, 0, 0],
                    "to": [16, 16, 16],
                    "rotation": {"origin": [8, 8, 8], "axis": "y", "angle": 30},
                    "faces": {"north": {"texture": "#all"}},
                }
            ],
        }
        report = validate_block_item_data(data, "stone.json")
        self.assertGreater(len(report["errors"]), 0)


if __name__ == "__main__":
    unittest.main()

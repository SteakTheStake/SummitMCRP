from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tools.labpbr_upres.core import (
    analyze_base_texture,
    analyze_normal_map,
    analyze_specular_map,
    build_generation_prompt,
    discover_texture_tasks,
    enforce_matching_edges,
    upscale_normal_map,
)


class LabPbrUpresTests(unittest.TestCase):
    def test_discover_texture_tasks_groups_companion_maps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            texture_dir = root / "assets" / "minecraft" / "textures" / "block"
            texture_dir.mkdir(parents=True)
            (root / "pack.mcmeta").write_text('{"pack":{"pack_format":34,"description":"x"}}\n', encoding="utf-8")

            Image.new("RGBA", (16, 16), (120, 80, 50, 255)).save(texture_dir / "dirt.png")
            Image.new("RGBA", (16, 16), (128, 128, 255, 255)).save(texture_dir / "dirt_n.png")
            Image.new("RGBA", (16, 16), (10, 40, 10, 255)).save(texture_dir / "dirt_s.png")

            tasks, skipped = discover_texture_tasks(
                pack_root=root,
                output_root=root / "generated_labpbr_hd",
                kinds=set(),
                namespaces=set(),
                matches=[],
                limit=None,
                skip_animated=True,
                skip_non_square=True,
            )

            self.assertEqual(len(tasks), 1)
            self.assertEqual(skipped, [])
            self.assertEqual(tasks[0].relative_path, "assets/minecraft/textures/block/dirt.png")
            self.assertIsNotNone(tasks[0].normal_path)
            self.assertIsNotNone(tasks[0].specular_path)
            self.assertEqual(tasks[0].kind, "block")

    def test_prompt_builder_uses_material_and_labpbr_cues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            texture_dir = root / "assets" / "minecraft" / "textures" / "block"
            texture_dir.mkdir(parents=True)
            base = texture_dir / "dirt.png"
            normal = texture_dir / "dirt_n.png"
            specular = texture_dir / "dirt_s.png"

            image = Image.new("RGBA", (16, 16))
            pixels = image.load()
            for y in range(16):
                for x in range(16):
                    pixels[x, y] = (110 + (x % 3) * 20, 70 + (y % 2) * 15, 45, 255)
            image.save(base)

            Image.new("RGBA", (16, 16), (140, 120, 180, 150)).save(normal)
            Image.new("RGBA", (16, 16), (30, 20, 10, 255)).save(specular)

            task = discover_texture_tasks(
                pack_root=root,
                output_root=root / "generated_labpbr_hd",
                kinds=set(),
                namespaces=set(),
                matches=[],
                limit=None,
                skip_animated=True,
                skip_non_square=True,
            )[0][0]

            prompt = build_generation_prompt(
                task=task,
                base_stats=analyze_base_texture(base),
                normal_stats=analyze_normal_map(normal),
                specular_stats=analyze_specular_map(specular),
                target_size=256,
            )

            self.assertIn("packed earth and embedded pebbles", prompt)
            self.assertIn("seamless square material tile", prompt)
            self.assertIn("LabPBR material cues", prompt)
            self.assertIn("compact soil clumps instead of flat brown noise", prompt)

    def test_upscale_normal_map_and_edge_fix_keep_expected_size(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "stone_n.png"
            Image.new("RGBA", (4, 4), (255, 0, 180, 200)).save(path)

            upscaled = upscale_normal_map(path, 256)
            self.assertEqual(upscaled.size, (256, 256))

            fixed = enforce_matching_edges(Image.new("RGBA", (16, 16), (10, 20, 30, 255)), border=2)
            self.assertEqual(fixed.size, (16, 16))


if __name__ == "__main__":
    unittest.main()

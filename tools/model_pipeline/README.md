# Model Pipeline (JEM + Block/Item JSON)

A deterministic AI-assisted pipeline for Minecraft 1.21.1 resource-pack model work.

This system is designed to prevent low-quality full-file rewrites by splitting work into strict stages:

1. `generate_brief.py` - build a structured brief from a simple idea.
2. `generate_ops.py` - turn brief into operation skeletons (patch-style actions).
3. `apply_ops.py` - apply operations to existing files.
4. `validate_models.py` - enforce technical constraints from AGENTS.md.
5. `score_critic.py` - generate machine-readable quality scores.
6. `pipeline.py` - orchestrates all stages.

## Supported Targets

- Entity models (`.jem`) under `assets/minecraft/optifine/cem/` or `assets/minecraft/emf/mob/`
- Block models (`assets/minecraft/models/block/*.json`)
- Item models (`assets/minecraft/models/item/*.json`)

## Why this works

- AI acts as Director/Builder/Critic with strict schemas.
- The pipeline applies small ops, not whole-model regeneration.
- Validators block invalid geometry/IDs/references before output is accepted.

## Quick Start

From repo root:

```powershell
python tools/model_pipeline/scripts/generate_brief.py --repo-root . --kind entity --idea "desert trader robe layers" --target assets/minecraft/optifine/cem/villager.jem --out tools/model_pipeline/runs/villager_entity_brief.json --entity-texture textures/entity/villager/villager.png
python tools/model_pipeline/scripts/generate_ops.py --brief tools/model_pipeline/runs/villager_entity_brief.json --out tools/model_pipeline/runs/villager_entity_ops.json
python tools/model_pipeline/scripts/apply_ops.py --repo-root . --ops tools/model_pipeline/runs/villager_entity_ops.json
python tools/model_pipeline/scripts/validate_models.py --repo-root . --kind entity --path assets/minecraft/optifine/cem/villager.jem
python tools/model_pipeline/scripts/score_critic.py --repo-root . --brief tools/model_pipeline/runs/villager_entity_brief.json --path assets/minecraft/optifine/cem/villager.jem --kind entity
```

Or run all steps:

```powershell
python tools/model_pipeline/scripts/pipeline.py --repo-root . --kind block_item --idea "aged sandstone crate" --target assets/minecraft/models/block/desert_market_crate.json --run-dir tools/model_pipeline/runs/desert_crate --texture all=block/sandstone
```

## Operation Format

Entity ops and block/item ops are JSON arrays with explicit actions (e.g. `set_root`, `upsert_texture`, `upsert_element`, `upsert_model_part`).

This keeps diffs readable and reversible.

## AI Prompting

Prompt templates live in `tools/model_pipeline/prompts/`:

- `director_entity.md`
- `builder_entity_ops.md`
- `critic_entity.md`
- `director_block_item.md`
- `builder_block_item_ops.md`
- `critic_block_item.md`

Use them with your preferred LLM. The pipeline itself is model-agnostic.

## Validation Highlights

Entity (`.jem`):
- duplicate `id` detection across root + submodels
- required root fields (`texture`, `textureSize`, `models`)
- part-level integrity checks

Block/Item JSON:
- valid `elements` coordinate bounds (default 0..16 check)
- allowed element rotations (`-45`, `-22.5`, `0`, `22.5`, `45`)
- max `112` elements
- override order warning (less-specific to more-specific)

## Notes

- Uses only Python standard library.
- JSON output is ASCII-safe and normalized with 2-space indentation.
- Built for Fabric 1.21.1 pack conventions (pack format 34).

# AGENTS.md — Minecraft Java Fabric 1.21.1 Model System Reference
## ETF (Entity Texture Features) & EMF (Entity Model Features)

This document defines the system architecture, file structure, constraints, and rules for creating **block models**, **item models**, **entity models**, and **random/conditional textures** in a Minecraft Java Edition resource pack targeting **Fabric 1.21.1** with the **ETF** and **EMF** mods installed.

---

## Table of Contents

1. [Environment & Mod Versions](#1-environment--mod-versions)
2. [Resource Pack Structure Overview](#2-resource-pack-structure-overview)
3. [Block Models](#3-block-models)
4. [Item Models](#4-item-models)
5. [Entity Textures — ETF (Entity Texture Features)](#5-entity-textures--etf-entity-texture-features)
6. [Entity Models — EMF (Entity Model Features)](#6-entity-models--emf-entity-model-features)
7. [ETF Properties Files Reference](#7-etf-properties-files-reference)
8. [EMF Model JSON Reference](#8-emf-model-json-reference)
9. [CIT (Custom Item Textures) via CIT Resewn](#9-cit-custom-item-textures-via-cit-resewn)
10. [Blockstates & Multipart Models](#10-blockstates--multipart-models)
11. [Advanced EMF Entity Modelling](#11-advanced-emf-entity-modelling)
12. [Constraints & Common Pitfalls](#12-constraints--common-pitfalls)
13. [Validation Checklist](#13-validation-checklist)
14. [Respackopts — In-Game Config Menus for Your Pack](#14-respackopts--in-game-config-menus-for-your-pack)

---

## 1. Environment & Mod Versions

| Component | Value |
|---|---|
| Minecraft Version | Java Edition 1.21.1 |
| Mod Loader | Fabric |
| Fabric API | Required |
| ETF | Entity Texture Features (latest for 1.21.1) |
| EMF | Entity Model Features (latest for 1.21.1) |
| Optional Companions | CIT Resewn, Continuity, Iris/Sodium |

> **Agent Rule:** Always target `1.21.1` namespace conventions. Pack format for 1.21.x is **`pack_format: 34`** in `pack.mcmeta`. Do not use OptiFine-specific paths; ETF/EMF have their own path conventions that differ in subtle ways.

```json
// pack.mcmeta
{
  "pack": {
    "pack_format": 34,
    "description": "My Resource Pack"
  }
}
```

---

## 2. Resource Pack Structure Overview

```
my_resourcepack/
├── pack.mcmeta
├── pack.png
└── assets/
    └── minecraft/
        ├── blockstates/
        │   └── <block_name>.json
        ├── models/
        │   ├── block/
        │   │   └── <block_name>.json
        │   └── item/
        │       └── <item_name>.json
        ├── textures/
        │   ├── block/
        │   ├── item/
        │   ├── entity/
        │   │   └── <mob>/
        │   │       ├── <mob>.png
        │   │       ├── <mob>2.png          ← ETF variant texture
        │   │       └── <mob>.properties    ← ETF rules file
        │   └── optifine/                   ← NOT used; ETF uses its own paths
        └── emf/
            └── mob/
                └── <mob_name>.jem          ← EMF root model file
```

---

## 3. Block Models

### 3.1 File Location

```
assets/minecraft/models/block/<block_name>.json
```

### 3.2 JSON Structure

```json
{
  "parent": "block/cube_all",
  "textures": {
    "all": "block/stone"
  }
}
```

### 3.3 Common Parents

| Parent | Description |
|---|---|
| `block/cube_all` | All six faces use one texture |
| `block/cube` | Specify each face individually (down, up, north, south, west, east) |
| `block/cube_column` | Top/bottom vs sides (logs) |
| `block/cross` | X-shaped plant model |
| `block/slab` | Standard slab (bottom half) |
| `block/slab_top` | Slab top half |
| `block/stairs` | Standard stairs |
| `block/orientable` | Directional face (furnace, etc.) |
| `block/template_*` | Vanilla templates for complex shapes |

### 3.4 Custom Block Model Rules

- `"elements"` array defines custom geometry. Each element is an axis-aligned box.
- Coordinates are in a 0–16 unit space (1 block = 16 units).
- `"from"` and `"to"` must both be within `[0, 16]` on all axes. Values outside this range are technically allowed but cause Z-fighting and rendering issues.
- `"rotation"` on elements supports only fixed angles: **-45, -22.5, 0, 22.5, 45** degrees.
- `"faces"` defines textures per face. Omitting a face culls it.
- `"cullface"` tells the engine to hide the face when an adjacent block is solid.
- `"shade"`: set to `false` to disable ambient occlusion shading (e.g. for glowing models).

```json
{
  "parent": "block/block",
  "textures": {
    "particle": "block/glass",
    "glass": "block/glass"
  },
  "elements": [
    {
      "from": [0, 0, 0],
      "to": [16, 16, 16],
      "faces": {
        "down":  { "texture": "#glass", "cullface": "down" },
        "up":    { "texture": "#glass", "cullface": "up" },
        "north": { "texture": "#glass", "cullface": "north" },
        "south": { "texture": "#glass", "cullface": "south" },
        "west":  { "texture": "#glass", "cullface": "west" },
        "east":  { "texture": "#glass", "cullface": "east" }
      }
    }
  ]
}
```

### 3.5 Constraints

- Maximum **112 elements** per model file (Minecraft hard limit).
- Element rotations apply to the element only, not the whole model. For full-model rotation, use blockstate `"y"` and `"x"` rotation.
- UV coordinates default to the element's face size if omitted. Explicit UV is `[u1, v1, u2, v2]` in 0–16 space.
- Textures referenced with `#variable` must be resolved in the `"textures"` block or via a parent.

---

## 4. Item Models

### 4.1 File Location

```
assets/minecraft/models/item/<item_name>.json
```

### 4.2 Basic Item (Flat Sprite)

```json
{
  "parent": "item/generated",
  "textures": {
    "layer0": "item/stick"
  }
}
```

### 4.3 Handheld Item

```json
{
  "parent": "item/handheld",
  "textures": {
    "layer0": "item/iron_sword"
  }
}
```

### 4.4 Block Item

```json
{
  "parent": "block/oak_log"
}
```

### 4.5 Layered Textures

Items support multiple `layer0`, `layer1`, `layer2`... textures for color overlay compositing (used by potions, dyed items, etc.).

```json
{
  "parent": "item/generated",
  "textures": {
    "layer0": "item/potion_overlay",
    "layer1": "item/potion"
  }
}
```

### 4.6 Overrides (Predicate-Based Model Switching)

In **vanilla 1.21.1**, item model overrides use predicates. In 1.21.4+ Mojang changed the system, but for 1.21.1:

```json
{
  "parent": "item/handheld",
  "textures": {
    "layer0": "item/bow_standby"
  },
  "overrides": [
    { "predicate": { "pulling": 1, "pull": 0.65 }, "model": "item/bow_pulling_1" },
    { "predicate": { "pulling": 1, "pull": 0.9 },  "model": "item/bow_pulling_2" },
    { "predicate": { "pulling": 1 },               "model": "item/bow_pulling_0" }
  ]
}
```

**Important:** Overrides are evaluated **last-match-wins** when multiple predicates could match. Order them from least specific to most specific.

### 4.7 Custom Model Data

For resource pack item variants without mods, use `custom_model_data`:

```json
"overrides": [
  { "predicate": { "custom_model_data": 1 }, "model": "item/my_custom_sword" },
  { "predicate": { "custom_model_data": 2 }, "model": "item/my_other_sword" }
]
```

Players/servers set this via `/give @s diamond_sword{CustomModelData:1}`.

### 4.8 Display Transforms

Control how an item appears in hand, GUI, ground, frame, etc.:

```json
"display": {
  "thirdperson_righthand": {
    "rotation": [0, 90, -35],
    "translation": [0, 1.25, -3.5],
    "scale": [0.85, 0.85, 0.85]
  },
  "firstperson_righthand": {
    "rotation": [0, -90, 25],
    "translation": [1.13, 3.2, 1.13],
    "scale": [0.68, 0.68, 0.68]
  }
}
```

Valid display positions: `thirdperson_righthand`, `thirdperson_lefthand`, `firstperson_righthand`, `firstperson_lefthand`, `gui`, `head`, `ground`, `fixed`.

### 4.9 Constraints

- `translation` is clamped to **±80** units.
- `scale` is clamped to **4x** maximum.
- `item/generated` and `item/handheld` only work for 2D sprite items.
- Do not nest more than **3 levels** of parent inheritance or you risk infinite-loop errors in certain loaders.

---

## 5. Entity Textures — ETF (Entity Texture Features)

ETF provides OptiFine-compatible random/rule-based entity textures natively on Fabric, without OptiFine.

### 5.1 How ETF Works

ETF reads `.properties` files placed alongside the default entity texture. It selects an alternate texture based on entity properties (UUID, name, biome, health, etc.) at spawn/load time. Textures are cached per-entity.

### 5.2 File Locations

```
assets/minecraft/textures/entity/<mob>/<mob>.png           ← base texture (vanilla)
assets/minecraft/textures/entity/<mob>/<mob>.properties    ← ETF rules
assets/minecraft/textures/entity/<mob>/<mob>2.png          ← variant 2
assets/minecraft/textures/entity/<mob>/<mob>3.png          ← variant 3
...
```

The `.properties` file must share the **exact same name and location** as the base texture, with `.properties` extension.

For example, for creepers:
```
textures/entity/creeper/creeper.png
textures/entity/creeper/creeper.properties
textures/entity/creeper/creeper2.png
textures/entity/creeper/creeper3.png
```

### 5.3 Properties File Format

ETF uses the OptiFine random entity `.properties` format:

```properties
# creeper.properties

skins=7

1.weights=10
1.biomes=desert mesa

2.weights=5
2.name=Creepella

3.weights=85
```

**Fields supported by ETF:**

| Field | Description |
|---|---|
| `skins=N` | Total number of variant textures (2 through N+1) |
| `N.weights=W` | Probability weight for skin N (relative, not percentage) |
| `N.biomes=` | Space-separated biome names or biome tags |
| `N.name=` | Entity name (CustomName). Supports regex if wrapped in `/pattern/` |
| `N.heights=Y1-Y2` | Block Y range |
| `N.health=H1-H2` | Health range |
| `N.moonPhase=0-7` | Moon phase (0=full, 4=new) |
| `N.weather=clear rain thunder` | Current weather |
| `N.dayTime=start-end` | Time of day in ticks (0–23999) |
| `N.baby=true/false` | Whether entity is a baby |
| `N.teams=teamname` | Scoreboard team name |
| `N.sizes=S1-S2` | Size (for slimes/phantoms) |
| `N.nbt.path=value` | Match NBT tag at path (ETF extension) |

### 5.4 ETF-Specific Extensions Beyond OptiFine

ETF supports additional matching not in OptiFine:

```properties
# Match by NBT
1.nbt.CustomName={"text":"Bob"}

# Match entity UUID suffix (last digits)
2.uuid=xxxx-xxxx-xxxx-xx01

# Profession (villagers)
3.professions=farmer weaponsmith
```

### 5.5 Emissive Textures (ETF)

ETF supports emissive (glow-in-the-dark) overlays without shaders. Place an emissive texture at:

```
textures/entity/<mob>/<mob>_e.png      ← emissive overlay for base texture
textures/entity/<mob>/<mob>2_e.png     ← emissive overlay for variant 2
```

- The emissive texture must be the **same dimensions** as the base texture.
- Transparent pixels in the emissive texture are ignored.
- Emissive pixels render at full brightness regardless of light level.
- Configure ETF behavior in-game via the ETF config screen (Mod Menu required) or `config/etf.json`.

### 5.6 ETF Blink / Animation Textures

ETF supports blinking and eye animations:

```
textures/entity/<mob>/<mob>_blink.png   ← eye-closed frame
```

Configure via ETF config or per-mob properties:
```properties
# In creeper.properties
1.blink.time=140
1.blink.time2=3
```

`blink.time` = ticks between blinks, `blink.time2` = duration of closed eye.

### 5.7 Constraints — ETF

- ETF does **not** support OptiFine's `entities/` folder path. Use the vanilla entity texture paths.
- Skin indices start at **2** (skin 1 is always the base `.png` file).
- `skins=N` must reflect the highest skin number referenced (not the count of variants).
- Properties files use **Java `.properties`** syntax: `key=value`, `#` for comments, no quotes around values.
- Biome names must match vanilla biome resource location IDs (e.g., `minecraft:desert`, or just `desert` — ETF strips the namespace).
- ETF is **not** compatible with OptiFine installed simultaneously.
- Regex in `name=` uses Java regex syntax wrapped in `/regex/i` (case-insensitive flag optional).

---

## 6. Entity Models — EMF (Entity Model Features)

EMF allows replacing and modifying entity models using `.jem` and `.jpm` JSON files, providing OptiFine-compatible model replacement on Fabric.

### 6.1 File Locations

```
assets/minecraft/emf/mob/<mob_name>.jem          ← root model file
assets/minecraft/emf/mob/<mob_name>_<part>.jpm   ← part override (optional)
```

Examples:
```
emf/mob/creeper.jem
emf/mob/zombie.jem
emf/mob/villager.jem
emf/mob/villager_nose.jpm
```

> **Important:** EMF uses `assets/minecraft/emf/mob/` — **not** `assets/minecraft/optifine/cem/` which is the OptiFine path. EMF also reads from `cem/` for compatibility, but prefer `emf/mob/` for clarity and future-proofing.

Both paths are scanned:
- `assets/minecraft/emf/mob/`  ← preferred EMF path
- `assets/minecraft/optifine/cem/`  ← OptiFine-compatibility path (also read by EMF)

### 6.2 JEM File Structure

A `.jem` file defines the entire entity model as a list of named model parts:

```json
{
  "credit": "Author Name",
  "texture": "textures/entity/creeper/creeper.png",
  "textureSize": [64, 32],
  "models": [
    {
      "part": "head",
      "id": "head",
      "invertAxis": "z",
      "translate": [0, 0, 0],
      "rotate": [0, 0, 0],
      "mirrorTexture": "",
      "boxes": [
        {
          "coordinates": [-4, 0, -4, 8, 8, 8],
          "uvDown":  [32, 8, 40, 16],
          "uvUp":    [24, 8, 32, 16],
          "uvNorth": [8,  8, 16, 16],
          "uvSouth": [24, 8, 32, 16],
          "uvWest":  [16, 8, 24, 16],
          "uvEast":  [0,  8, 8,  16]
        }
      ],
      "submodels": []
    }
  ]
}
```

### 6.3 JEM Fields Reference

**Root fields:**

| Field | Type | Description |
|---|---|---|
| `credit` | string | Author credit (optional) |
| `texture` | string | Path to texture, relative to `assets/minecraft/` |
| `textureSize` | [W, H] | Texture dimensions in pixels |
| `models` | array | Array of model part objects |

**Model part fields:**

| Field | Type | Description |
|---|---|---|
| `part` | string | Vanilla part name to replace (must match exactly) |
| `id` | string | Unique identifier for this part (used in animations) |
| `invertAxis` | string | Axes to invert: e.g. `"z"`, `"xz"`, `""` |
| `translate` | [x, y, z] | Translation offset in model units |
| `rotate` | [x, y, z] | Rotation in degrees around pivot |
| `mirrorTexture` | string | Mirror UV: `"u"`, `"v"`, `"uv"`, or `""` |
| `boxes` | array | Array of box definitions |
| `submodels` | array | Child model parts (same structure, no `part` field) |
| `animations` | array | Animation keyframe/expression data |
| `hidden` | bool | Hide this part by default |

**Box fields:**

| Field | Type | Description |
|---|---|---|
| `coordinates` | [x, y, z, w, h, d] | Position (xyz from pivot) and size (whd) |
| `uvNorth/South/East/West/Up/Down` | [u1, v1, u2, v2] | UV rectangle per face |
| `sizeAdd` | float | Expand box on all sides (for armor layers, +0.5) |

### 6.4 JPM File Structure

A `.jpm` file overrides a single part of an existing vanilla or JEM model:

```json
{
  "credit": "Author",
  "invertAxis": "z",
  "translate": [0, 0, 0],
  "rotate": [0, 0, 0],
  "boxes": [
    {
      "coordinates": [-4, 0, -4, 8, 8, 8],
      "uvNorth": [8, 8, 16, 16]
    }
  ],
  "submodels": []
}
```

JPM files do not have a `models` array — they ARE the part definition.

### 6.5 Vanilla Part Names

Part names must match vanilla's internal model part names. Common names:

**Humanoids (Player, Zombie, Skeleton, Villager, etc.):**
`head`, `hat`, `body`, `right_arm`, `left_arm`, `right_leg`, `left_leg`

**Creeper:**
`head`, `body`, `leg1`, `leg2`, `leg3`, `leg4`

**Spider:**
`head`, `neck`, `body`, `right_middle_front_leg`, `left_middle_front_leg`, `right_hind_middle_leg`, `left_hind_middle_leg`, `right_front_leg`, `left_front_leg`, `right_middle_hind_leg`, `left_middle_hind_leg`, `right_hind_leg`, `left_hind_leg`

**Cow/Horse/Pig (quadrupeds):**
`head`, `body`, `right_front_leg`, `left_front_leg`, `right_hind_leg`, `left_hind_leg`

**Chicken:**
`head`, `body`, `right_wing`, `left_wing`, `bill`, `chin`, `right_leg`, `left_leg`

> **Agent Rule:** To discover exact vanilla part names for any mob, use EMF's built-in **model debug mode** (toggle in EMF config or press the debug hotkey in-game) which overlays part names on entities.

### 6.6 EMF Animations

EMF supports keyframe and expression-based animations in `.jem` files:

```json
"animations": [
  {
    "head.rx": "head.rx + sin(age * 0.1) * 0.05"
  }
]
```

**Animation variables:**

| Variable | Description |
|---|---|
| `age` | Entity's living tick timer |
| `limb_swing` | Limb swing speed |
| `limb_swing_amount` | Limb swing amplitude |
| `head.rx/ry/rz` | Head rotation angles |
| `body.rx/ry/rz` | Body rotation angles |
| `move_forward`, `move_strafing` | Movement direction inputs |
| `is_sneaking`, `is_sprinting` | Boolean states (0 or 1) |
| `PI` | π (3.14159...) |

**Math functions available:**
`sin()`, `cos()`, `tan()`, `asin()`, `acos()`, `atan()`, `atan2()`, `abs()`, `floor()`, `ceil()`, `clamp()`, `max()`, `min()`, `sqrt()`, `pow()`, `round()`, `random()`, `torad()`, `todeg()`

Animation expressions follow a syntax similar to GeckoLib/OptiFine CEM:
```json
"animations": [
  {
    "tail.ry": "sin(age * 0.2) * 20"
  }
]
```

### 6.7 Constraints — EMF

- `.jem` model coordinate system: **Y-up**, with Z forward. Set `"invertAxis": "z"` to match OptiFine's convention (Z-backward).
- Texture paths in `.jem` must be valid resource location paths from the pack root (relative to `assets/minecraft/`).
- `part` names are **case-sensitive** and must exactly match vanilla internal names.
- `submodels` do not use the `part` field — they are anonymous children.
- EMF does **not** support procedural animation via `.jem` alone; complex animations require the expression system.
- The `textureSize` must match the actual pixel dimensions of the referenced texture file.
- EMF model replacement is **per-entity-type**, not per-variant. Use ETF for per-entity texture variants.
- Combining EMF + ETF: ETF handles texture selection; EMF handles geometry. They operate independently and are fully compatible.
- EMF is incompatible with OptiFine (which has its own CEM system).

---

## 7. ETF Properties Files Reference

### 7.1 Full Properties Example

```properties
# Applies to: assets/minecraft/textures/entity/wolf/wolf.png
# Variants: wolf2.png through wolf5.png

skins=5

# Skin 2: Snowy wolves
2.weights=15
2.biomes=snowy_taiga snowy_plains grove

# Skin 3: Named wolves (owner-named pet)
3.weights=0
3.name=/^Fluffy$/i

# Skin 4: Low health wolf (wounded)
4.weights=0
4.health=1-8

# Skin 5: Everything else
5.weights=85
```

### 7.2 Biome Name Conventions

Use vanilla biome IDs without namespace for compatibility:
```properties
1.biomes=desert badlands eroded_badlands
2.biomes=jungle bamboo_jungle sparse_jungle
3.biomes=snowy_plains snowy_taiga ice_spikes frozen_river
```

### 7.3 NBT Matching

```properties
# Match specific NBT path values
1.nbt.Variant=1
2.nbt.Tags[0]=special

# Villager profession
1.nbt.VillagerData.profession=minecraft:farmer
```

---

## 8. EMF Model JSON Reference

### 8.1 Minimal Working JEM

```json
{
  "textureSize": [64, 32],
  "models": [
    {
      "part": "head",
      "id": "head",
      "invertAxis": "z",
      "translate": [0, -6, 0],
      "boxes": [
        { "coordinates": [-4, 0, -4, 8, 8, 8], "textureOffset": [0, 0] }
      ],
      "submodels": [],
      "animations": []
    }
  ]
}
```

### 8.2 textureOffset vs Explicit UV

You can use either `"textureOffset": [u, v]` (uses standard Minecraft UV-box wrapping) or explicit `uvNorth/uvSouth/uvEast/uvWest/uvUp/uvDown` per face. Do not mix both on the same box.

```json
// Auto UV from offset
{ "coordinates": [0, 0, 0, 8, 8, 8], "textureOffset": [0, 0] }

// Explicit UV per face
{
  "coordinates": [0, 0, 0, 8, 8, 8],
  "uvNorth": [8, 8, 16, 16],
  "uvSouth": [24, 8, 32, 16],
  "uvUp":    [8,  0, 16, 8],
  "uvDown":  [16, 0, 24, 8],
  "uvWest":  [16, 8, 24, 16],
  "uvEast":  [0,  8, 8, 16]
}
```

---

## 9. CIT (Custom Item Textures) via CIT Resewn

CIT Resewn provides OptiFine-compatible Custom Item Texture support on Fabric.

### 9.1 File Location

```
assets/minecraft/optifine/cit/<name>.properties
assets/minecraft/optifine/cit/<name>.png       ← texture (if type=item)
assets/minecraft/optifine/cit/<name>.json      ← model (if type=item with model)
```

### 9.2 Properties Format

```properties
type=item
items=minecraft:diamond_sword
texture=textures/item/my_sword.png
model=models/item/my_sword
nbt.display.Name=ipattern:My Sword
```

**Common fields:**

| Field | Description |
|---|---|
| `type` | `item` (texture/model swap), `armor`, `elytra` |
| `items` | Space-separated item IDs |
| `texture` | Path to replacement texture |
| `model` | Path to replacement model (no `.json` extension) |
| `nbt.*` | NBT condition matching |
| `damage` | Damage value or range |
| `damageMask` | Damage bit mask |
| `stackSize` | Item count range |
| `enchantments` | Required enchantment(s) |
| `weight` | Priority when multiple CIT match (higher = preferred) |

---

## 10. Blockstates & Multipart Models

### 10.1 Variants Format

```json
// assets/minecraft/blockstates/oak_log.json
{
  "variants": {
    "axis=x": { "model": "block/oak_log_horizontal", "x": 90, "y": 90 },
    "axis=y": { "model": "block/oak_log" },
    "axis=z": { "model": "block/oak_log_horizontal", "x": 90 }
  }
}
```

### 10.2 Multipart Format

```json
{
  "multipart": [
    {
      "apply": { "model": "block/fence_post" }
    },
    {
      "when": { "north": "true" },
      "apply": { "model": "block/fence_side", "uvlock": true }
    },
    {
      "when": { "OR": [{"north": "true"}, {"south": "true"}] },
      "apply": { "model": "block/fence_side" }
    }
  ]
}
```

### 10.3 Model Rotation in Blockstates

| Field | Values | Description |
|---|---|---|
| `x` | 0, 90, 180, 270 | Tilt around X axis |
| `y` | 0, 90, 180, 270 | Rotate around Y axis |
| `uvlock` | true/false | Lock UV to world axes during rotation |
| `weight` | integer | Random selection weight for variants |

### 10.4 Random Variants

```json
{
  "variants": {
    "": [
      { "model": "block/grass_block", "weight": 95 },
      { "model": "block/grass_block_variant", "weight": 5 }
    ]
  }
}
```

---

## 11. Advanced EMF Entity Modelling

This section covers the full depth of what EMF can do: adding entirely new geometry parts, authoring complex multi-channel animations, making surgical edits to vanilla models without replacing them wholesale, managing pivot hierarchies, and compositing extra texture sheets.

---

### 11.1 Understanding the Pivot / Transform Hierarchy

Every part in EMF has a **pivot point** — the origin around which it rotates and around which child submodels orbit. Understanding this is the foundation of all advanced modelling.

```
Root (world origin)
└── body          ← pivot at body center
    ├── head      ← pivot at neck joint, relative to body pivot
    │   └── hat   ← pivot at top of head, relative to head pivot
    ├── right_arm ← pivot at shoulder, relative to body pivot
    └── left_arm
```

**Key rules:**

- `"translate": [x, y, z]` moves the **pivot itself** in the parent's local space. It does NOT move the boxes — it shifts where the part "lives" relative to its parent.
- `"rotate": [rx, ry, rz]` rotates the entire part (pivot + all its boxes + all submodels) around the pivot point.
- Boxes defined in `"boxes"` are positioned with `"coordinates": [px, py, pz, w, h, d]` where `px/py/pz` is the box corner **relative to the pivot**.
- Submodels inherit the cumulative world transform of their parent chain — position, rotation, and scale all stack.

**Practical pivot workflow:**

To attach a hat on a custom animal head pivoting at `[0, -6, 0]` in model space, the hat submodel's `translate` should be `[0, 8, 0]` (8 units up from the head pivot = top of an 8-unit-tall head). Then its boxes are placed relative to that new pivot, not the head pivot.

---

### 11.2 Adding Entirely New Geometry Parts (Extra Parts)

EMF allows you to add geometry that has no vanilla equivalent by using `"submodels"` hung off existing vanilla parts. You cannot inject a brand-new root-level part that vanilla doesn't know about — but you can attach unlimited child submodels to any existing part.

#### 11.2.1 Strategy: Attach to the Nearest Logical Parent

Choose the vanilla part whose movement your new geometry should follow:

- A tail → attach to `body`
- A horn → attach to `head`
- A saddle bag → attach to `body`
- Wing feathers → attach to a wing part if it exists, else `body`
- A held item prop → attach to `right_arm`

#### 11.2.2 Submodel Structure

Submodels live inside a parent's `"submodels"` array. They do **not** have a `"part"` field (that field is only for root-level vanilla part replacements). They do need a unique `"id"` for animation targeting.

```json
{
  "part": "head",
  "id": "head",
  "invertAxis": "z",
  "translate": [0, 0, 0],
  "rotate": [0, 0, 0],
  "boxes": [
    { "coordinates": [-4, 0, -4, 8, 8, 8], "textureOffset": [0, 0] }
  ],
  "submodels": [
    {
      "id": "left_horn",
      "invertAxis": "z",
      "translate": [-2, 8, 0],
      "rotate": [-15, -10, 0],
      "boxes": [
        { "coordinates": [-1, 0, -1, 2, 5, 2], "textureOffset": [48, 0] }
      ],
      "submodels": [
        {
          "id": "left_horn_tip",
          "invertAxis": "z",
          "translate": [0, 5, 0],
          "rotate": [-10, 0, 0],
          "boxes": [
            { "coordinates": [-0.5, 0, -0.5, 1, 3, 1], "textureOffset": [56, 0] }
          ],
          "submodels": []
        }
      ]
    },
    {
      "id": "right_horn",
      "invertAxis": "z",
      "translate": [2, 8, 0],
      "rotate": [-15, 10, 0],
      "boxes": [
        { "coordinates": [-1, 0, -1, 2, 5, 2], "textureOffset": [48, 0] }
      ],
      "submodels": []
    }
  ]
}
```

> **Agent Rule:** Submodels can nest arbitrarily deep. Each level inherits all parent transforms. Keep nesting ≤ 5 levels deep for performance and debuggability.

#### 11.2.3 Adding Extra Texture Space for New Parts

New geometry needs UV space. You have two options:

**Option A — Expand the existing texture.** Increase `"textureSize"` in the JEM to match an expanded texture file (e.g. from `[64, 32]` to `[128, 64]`). Place new parts' UVs in the newly added region. The vanilla skin area in the top-left must remain untouched.

**Option B — Use a second texture via a submodel override.** EMF does not natively support per-submodel texture overrides in the same way GeckoLib does. Stick to Option A for vanilla mobs; use Option B only when writing a mod with Fabric rendering hooks.

```json
// JEM root — expanded texture
{
  "textureSize": [128, 64],
  "texture": "textures/entity/cow/cow_custom.png",
  "models": [ ... ]
}
```

---

### 11.3 Surgically Editing Vanilla Parts Without Full Replacement

When you only need to tweak part of a model — resize the snout, move an ear, add a detail — you don't have to redefine every single vanilla box. Instead, use a targeted `.jem` that re-declares only the parts you need to change, letting EMF merge it with the vanilla model for the rest.

#### 11.3.1 Partial JEM — Only Include Parts You're Modifying

If your `.jem` does not list every vanilla part, EMF retains the vanilla geometry for the missing ones. This is the recommended approach for minor edits:

```json
// assets/minecraft/emf/mob/pig.jem
// Only modifying the snout — body, legs, head base are untouched
{
  "textureSize": [64, 32],
  "models": [
    {
      "part": "head",
      "id": "head",
      "invertAxis": "z",
      "translate": [0, 0, 0],
      "rotate": [0, 0, 0],
      "boxes": [
        { "coordinates": [-4, 0, -4, 8, 8, 8], "textureOffset": [0, 0] }
      ],
      "submodels": [
        {
          "id": "snout",
          "invertAxis": "z",
          "translate": [0, 1, -4],
          "rotate": [0, 0, 0],
          "boxes": [
            { "coordinates": [-2, -2, -2, 4, 3, 2], "textureOffset": [16, 16] }
          ],
          "submodels": []
        }
      ]
    }
  ]
}
```

#### 11.3.2 Hiding Vanilla Sub-Geometry

If a vanilla part has geometry you want gone (e.g. default snout you're replacing), include it in your JEM with `"hidden": true` and an empty `"boxes"` array, then add your replacement as a submodel:

```json
{
  "part": "snout",
  "id": "snout",
  "hidden": true,
  "boxes": [],
  "submodels": [
    {
      "id": "custom_snout",
      "translate": [0, 0, 0],
      "boxes": [
        { "coordinates": [-2, -1, -2, 4, 2, 2], "textureOffset": [16, 16] }
      ],
      "submodels": []
    }
  ]
}
```

#### 11.3.3 Resizing / Repositioning Individual Boxes

You cannot edit individual boxes within a vanilla part without redefining the whole part's `"boxes"` array. When you include a part in your JEM, your `"boxes"` array **completely replaces** the vanilla box list for that part. Strategy:

1. Open the vanilla model source (decompile the jar or reference community wikis) to get the exact vanilla box coordinates.
2. Copy all vanilla boxes into your JEM entry for that part.
3. Modify only the box you want to change.
4. Leave all other boxes identical to vanilla.

---

### 11.4 Animation System — Deep Reference

EMF's animation system evaluates **expression strings** per-frame and applies the result to a named property of a named part. Expressions are mathematical formulas that can reference entity state variables, other parts' current transforms, and built-in math functions.

#### 11.4.1 Animation Entry Format

Animations are defined as an array of single-key objects inside any part's `"animations"` array:

```json
"animations": [
  { "PART_ID.PROPERTY": "EXPRESSION" },
  { "PART_ID.PROPERTY": "EXPRESSION" }
]
```

Each object in the array is a single assignment. Order matters — assignments are applied sequentially and later entries can reference values set by earlier ones.

#### 11.4.2 Animatable Properties

| Property Suffix | Description | Units |
|---|---|---|
| `.rx` | Rotation around X axis | Degrees |
| `.ry` | Rotation around Y axis | Degrees |
| `.rz` | Rotation around Z axis | Degrees |
| `.tx` | Translation on X axis | Model units |
| `.ty` | Translation on Y axis | Model units |
| `.tz` | Translation on Z axis | Model units |
| `.sx` | Scale on X axis | Multiplier (1.0 = normal) |
| `.sy` | Scale on Y axis | Multiplier |
| `.sz` | Scale on Z axis | Multiplier |
| `.visible` | Show/hide part (0 = hidden, 1 = visible) | 0 or 1 |
| `.visible_boxes` | Show/hide boxes only (not submodels) | 0 or 1 |

Example — rotate head up and down sinusoidally:
```json
{ "head.rx": "sin(age * 0.05) * 10" }
```

#### 11.4.3 Full Variable Reference

**Time & Motion:**

| Variable | Description |
|---|---|
| `age` | Entity age in ticks (increments every tick, interpolated between ticks) |
| `limb_swing` | Accumulated walk distance (drives leg cycles) |
| `limb_swing_amount` | Speed of current limb swing (0 when still, ~1.4 at full sprint) |
| `head_yaw` | Head yaw relative to body in degrees |
| `head_pitch` | Head pitch in degrees |
| `body_yaw_delta` | Body turning speed |

**Entity State (Boolean — 0 or 1):**

| Variable | Description |
|---|---|
| `is_sneaking` | Entity is crouching |
| `is_sprinting` | Entity is sprinting |
| `is_swimming` | Entity is swimming |
| `is_flying` | Entity is flying (elytra or creative) |
| `is_gliding` | Entity is gliding with elytra |
| `is_sleeping` | Entity is sleeping |
| `is_on_ground` | Entity is on the ground |
| `is_riding` | Entity is riding a vehicle |
| `is_burning` | Entity is on fire |
| `is_alive` | Entity is alive (not dead/dying) |
| `is_in_water` | Entity is submerged |
| `is_aggressive` | Entity is in aggressive/attack state |
| `is_baby` | Entity is in baby/child state |

**Entity Properties:**

| Variable | Description |
|---|---|
| `health` | Current health points |
| `max_health` | Maximum health points |
| `health_normalized` | health / max_health (0.0–1.0) |
| `anger_time` | Ticks of anger remaining (bees, piglins, etc.) |
| `anger_time_normalized` | anger_time / max_anger_time |
| `move_forward` | Forward movement input (-1 to 1) |
| `move_strafing` | Strafe input (-1 to 1) |
| `id` | Entity's unique numeric ID (consistent per entity, random range) |
| `PI` | π = 3.14159265... |
| `E` | Euler's number = 2.71828... |

**Part Self-Reference:**

You can read another part's current transform value, even one set by an earlier animation entry in the same frame:

```json
{ "left_arm.rx": "right_arm.rx * -1" }
```

Readable properties: `PART_ID.rx`, `PART_ID.ry`, `PART_ID.rz`, `PART_ID.tx`, `PART_ID.ty`, `PART_ID.tz`

#### 11.4.4 Math Functions

| Function | Description |
|---|---|
| `sin(x)` | Sine (argument in **radians**) |
| `cos(x)` | Cosine (radians) |
| `tan(x)` | Tangent (radians) |
| `asin(x)` | Arc sine, returns radians |
| `acos(x)` | Arc cosine, returns radians |
| `atan(x)` | Arc tangent, returns radians |
| `atan2(y, x)` | Two-argument arc tangent |
| `torad(deg)` | Degrees → radians |
| `todeg(rad)` | Radians → degrees |
| `abs(x)` | Absolute value |
| `floor(x)` | Round down to integer |
| `ceil(x)` | Round up to integer |
| `round(x)` | Round to nearest integer |
| `sqrt(x)` | Square root |
| `pow(base, exp)` | Exponentiation |
| `log(x)` | Natural logarithm |
| `min(a, b)` | Minimum of two values |
| `max(a, b)` | Maximum of two values |
| `clamp(x, min, max)` | Clamp x between min and max |
| `lerp(a, b, t)` | Linear interpolation between a and b by factor t |
| `if(cond, a, b)` | Ternary: returns a if cond ≠ 0, else b |
| `random(seed)` | Deterministic pseudo-random based on seed |

> **Agent Rule:** `sin()` and `cos()` take **radians**. EMF rotation properties use **degrees**. To drive a rotation with a sine wave: `sin(age * speed) * amplitude_in_degrees`. The `torad()` / `todeg()` functions convert between them but are rarely needed since you can simply scale the amplitude directly.

#### 11.4.5 Animation Patterns & Recipes

**Idle body bob:**
```json
{ "body.ty": "sin(age * 0.1) * 0.5" }
```

**Quadruped leg cycle (walk):**
```json
{ "right_front_leg.rx": "sin(limb_swing * 0.6662) * 1.4 * limb_swing_amount * 57.3" },
{ "left_front_leg.rx":  "sin(limb_swing * 0.6662 + PI) * 1.4 * limb_swing_amount * 57.3" },
{ "right_hind_leg.rx":  "sin(limb_swing * 0.6662 + PI) * 1.4 * limb_swing_amount * 57.3" },
{ "left_hind_leg.rx":   "sin(limb_swing * 0.6662) * 1.4 * limb_swing_amount * 57.3" }
```
*(The factor 57.3 ≈ 180/π converts the radians output of sin() to a degrees value for rx.)*

**Tail wag with idle sway:**
```json
{ "tail.ry": "sin(age * 0.2) * 20 * is_aggressive + sin(age * 0.08) * 5 * (1 - is_aggressive)" }
```

**Conditional ear droop when sneaking:**
```json
{ "left_ear.rz":  "if(is_sneaking, -30, lerp(-30, 0, health_normalized))" },
{ "right_ear.rz": "if(is_sneaking, 30, lerp(30, 0, health_normalized))" }
```

**Wing flap cycle:**
```json
{ "left_wing.rz":  "if(is_flying, sin(age * 0.5) * 40 - 10, -5)" },
{ "right_wing.rz": "if(is_flying, sin(age * 0.5) * -40 + 10, 5)" }
```

**Snout twitch — random periodic:**
```json
{ "snout.rx": "sin(floor(age * 0.05) * random(id * 7)) * 3" }
```

**Death roll (entity dying):**
```json
{ "body.rz": "if(is_alive, 0, min(age * 3, 90))" }
```

**Head tracking look — re-apply vanilla head yaw/pitch on a custom head part:**
```json
{ "custom_head.ry": "head_yaw" },
{ "custom_head.rx": "head_pitch" }
```

**Scale pulse on low health:**
```json
{ "body.sx": "1 + (1 - health_normalized) * sin(age * 0.4) * 0.05" },
{ "body.sy": "1 + (1 - health_normalized) * sin(age * 0.4) * 0.05" },
{ "body.sz": "1 + (1 - health_normalized) * sin(age * 0.4) * 0.05" }
```

#### 11.4.6 Where to Put Animation Entries

Animations can be declared on **any part**, not just the part being animated. All animation entries are evaluated regardless of which part they're attached to. Convention: put all animations in the root part (usually `body` or `head`) for maintainability.

```json
{
  "part": "body",
  "id": "body",
  "invertAxis": "z",
  "translate": [0, 0, 0],
  "boxes": [ ... ],
  "submodels": [ ... ],
  "animations": [
    { "body.ty":          "sin(age * 0.1) * 0.5" },
    { "head.rx":          "head_pitch" },
    { "head.ry":          "head_yaw" },
    { "tail.ry":          "sin(age * 0.2) * 20" },
    { "left_horn.rx":     "sin(age * 0.07) * 2" },
    { "right_horn.rx":    "sin(age * 0.07) * 2" }
  ]
}
```

---

### 11.5 Full Advanced Example — Custom Horned Cow

This example demonstrates extra parts (horns), a tail, modification of the vanilla snout, and a full animation set.

#### File: `assets/minecraft/emf/mob/cow.jem`

```json
{
  "credit": "Custom Cow — horns, tail, and animations",
  "texture": "textures/entity/cow/cow.png",
  "textureSize": [128, 64],
  "models": [
    {
      "part": "head",
      "id": "head",
      "invertAxis": "z",
      "translate": [0, 0, 0],
      "rotate": [0, 0, 0],
      "boxes": [
        { "coordinates": [-4,  0, -6, 8, 8, 6], "textureOffset": [0,  0]  },
        { "coordinates": [-2, -2, -8, 4, 4, 2], "textureOffset": [24, 0]  }
      ],
      "submodels": [
        {
          "id": "left_horn",
          "invertAxis": "z",
          "translate": [-3, 8, -4],
          "rotate": [-20, -15, 5],
          "boxes": [
            { "coordinates": [-1, 0, -1, 2, 6, 2], "textureOffset": [64, 0] }
          ],
          "submodels": [
            {
              "id": "left_horn_tip",
              "invertAxis": "z",
              "translate": [0, 6, 0],
              "rotate": [-15, 0, 0],
              "boxes": [
                { "coordinates": [-0.5, 0, -0.5, 1, 4, 1], "textureOffset": [72, 0] }
              ],
              "submodels": []
            }
          ]
        },
        {
          "id": "right_horn",
          "invertAxis": "z",
          "translate": [3, 8, -4],
          "rotate": [-20, 15, -5],
          "boxes": [
            { "coordinates": [-1, 0, -1, 2, 6, 2], "textureOffset": [64, 0] }
          ],
          "submodels": [
            {
              "id": "right_horn_tip",
              "invertAxis": "z",
              "translate": [0, 6, 0],
              "rotate": [-15, 0, 0],
              "boxes": [
                { "coordinates": [-0.5, 0, -0.5, 1, 4, 1], "textureOffset": [72, 0] }
              ],
              "submodels": []
            }
          ]
        }
      ],
      "animations": []
    },
    {
      "part": "body",
      "id": "body",
      "invertAxis": "z",
      "translate": [0, 0, 0],
      "rotate": [0, 0, 0],
      "boxes": [
        { "coordinates": [-6, -10, -7, 12, 18, 10], "textureOffset": [18, 4] }
      ],
      "submodels": [
        {
          "id": "tail_base",
          "invertAxis": "z",
          "translate": [0, -8, 7],
          "rotate": [20, 0, 0],
          "boxes": [
            { "coordinates": [-1, 0, 0, 2, 5, 2], "textureOffset": [80, 0] }
          ],
          "submodels": [
            {
              "id": "tail_mid",
              "invertAxis": "z",
              "translate": [0, 5, 0],
              "rotate": [15, 0, 0],
              "boxes": [
                { "coordinates": [-1, 0, 0, 2, 5, 2], "textureOffset": [80, 4] }
              ],
              "submodels": [
                {
                  "id": "tail_tuft",
                  "invertAxis": "z",
                  "translate": [0, 5, 0],
                  "rotate": [10, 0, 0],
                  "boxes": [
                    { "coordinates": [-2, 0, -1, 4, 4, 4], "textureOffset": [80, 8] }
                  ],
                  "submodels": []
                }
              ]
            }
          ]
        }
      ],
      "animations": [
        { "head.rx":          "head_pitch" },
        { "head.ry":          "head_yaw" },
        { "body.ty":          "if(is_sneaking, 5, 0)" },
        { "tail_base.ry":     "sin(age * 0.15) * 25" },
        { "tail_mid.ry":      "sin(age * 0.15 + 0.5) * 20" },
        { "tail_tuft.ry":     "sin(age * 0.15 + 1.0) * 15" },
        { "left_horn.rx":     "head_pitch" },
        { "left_horn.ry":     "head_yaw" },
        { "right_horn.rx":    "head_pitch" },
        { "right_horn.ry":    "head_yaw" },
        { "right_front_leg.rx": "sin(limb_swing * 0.6662)          * 1.4 * limb_swing_amount * 57.3" },
        { "left_front_leg.rx":  "sin(limb_swing * 0.6662 + PI)     * 1.4 * limb_swing_amount * 57.3" },
        { "right_hind_leg.rx":  "sin(limb_swing * 0.6662 + PI)     * 1.4 * limb_swing_amount * 57.3" },
        { "left_hind_leg.rx":   "sin(limb_swing * 0.6662)          * 1.4 * limb_swing_amount * 57.3" }
      ]
    }
  ]
}
```

---

### 11.6 Per-Variant Model Switching with ETF + EMF

ETF selects textures; EMF handles geometry. They're independent — but you can approximate per-variant geometry by creating **multiple JEM files targeting the same mob** and using different pack layers or ETF's `nbt` matching to select between them. This requires a mod or datapack to set NBT tags on entities, but it is a valid pattern for server resource packs.

A more practical approach: design your `.jem` so geometry that should only appear on certain variants is **toggled via animation visibility expressions** that read EMF variables correlated to ETF-selected skins. This requires careful coordination and is an advanced technique.

---

### 11.7 Debugging Advanced Models

**Use EMF's built-in debug mode:**
- In EMF config (via Mod Menu), enable **"Model Debug Render"** to render part bounding boxes and pivot crosses on all entities in-game.
- Press the configured debug hotkey (default: none — assign one in controls) to cycle through single-part highlight modes.
- Part names are overlaid as floating text — confirm your `part` and `id` strings match exactly.

**Iterative reloading:**
- Press `F3+T` to reload resource packs without restarting the game.
- EMF model changes reload with the resource pack. Animation expression errors are logged immediately to `logs/latest.log`.

**Common animation debug patterns:**
- To confirm a variable is being read: `{ "head.rx": "health * 5" }` — the head will droop proportionally to current health. If it responds, the variable is working.
- To confirm a part ID is valid: `{ "my_part.ty": "20" }` — a static 20-unit upward translation. If the part doesn't move, the ID is wrong.
- To confirm `invertAxis` is correct: place a box asymmetrically (not centered) and check whether it appears on the correct side in-game.

**Log error signatures:**

| Log Message Pattern | Likely Cause |
|---|---|
| `Unknown part: X` | `part` name doesn't match vanilla |
| `Failed to parse animation expression` | Syntax error in expression string |
| `Texture not found` | `texture` path is incorrect or file missing |
| `Could not load JEM` | JSON parse error (missing comma, bracket, etc.) |
| Model loads but geometry is wrong | `invertAxis` incorrect, or `translate` misunderstood as box offset |
| Animations evaluate but do nothing | `id` in animation doesn't match any part's `id` field |

---

### 11.8 Performance Considerations for Advanced Models

- **Expression complexity:** Each animation expression runs every rendered frame for every visible entity of that type. Avoid expressions with deeply nested calls (e.g. avoid `pow(sin(cos(age)), 3)` when `sin(age * 0.1)` suffices).
- **Part count:** Every submodel is an additional draw call component. Aim to keep total parts (vanilla + submodels) under **30 per mob** for smooth performance with many entities on screen.
- **Scale animations:** Scaling individual boxes is cheap; scaling with `sx/sy/sz` at runtime is more expensive. Prefer baked geometry sizing where static.
- **Visibility toggling:** Using `.visible = 0` to hide parts is cheaper than animating them off-screen. For parts that are conditionally shown (e.g. only when flying), use `{ "wing.visible": "is_flying" }` rather than moving them far away.
- **`random()` usage:** The `random(seed)` function is deterministic but still computed per frame. Cache-friendly patterns use `floor()` to lock the result to intervals: `random(floor(age * 0.1) + id)` changes value every 10 ticks rather than every frame.

---

## 12. Constraints & Common Pitfalls

### 12.1 General

- All JSON must be **valid JSON** (no trailing commas, no comments).
- Texture paths are always relative to `assets/<namespace>/textures/` — do not include `textures/` in the path value for model JSON `"textures"` blocks; the engine prepends it. However, in EMF `.jem` `"texture"` fields, include `textures/` explicitly.
- Namespace defaults to `minecraft` unless you create your own namespace folder.

### 12.2 Block Models

- Rotations in elements are **not cumulative** — each box rotates around its own `"origin"` point.
- `"ambient_occlusion": false` at the model root disables AO for the entire model.
- `"gui_light": "front"` or `"side"` controls GUI render lighting.

### 12.3 Item Models

- `"item/generated"` does NOT support 3D elements from a parent; always define elements directly or use a block model parent.
- `"overrides"` require the predicates to be defined in the item's data component (vanilla) or via NBT/server commands.
- Predicates are evaluated in **list order**; later matching entries override earlier ones.

### 12.4 ETF

- The properties file applies to the **base texture** and all its variants; you cannot have separate properties for each variant.
- `skins=N` must be ≥ the highest skin number used in rules. If `skins=3`, valid variant files are `mob2.png` and `mob3.png`.
- Weight of `0` means the skin is **never selected randomly** — only via matching rules (useful for name-matched skins).
- ETF's emissive suffix `_e` is configurable; default is `_e` but can be changed in ETF config.
- ETF processes entity textures; **it does not replace geometry.** Use EMF for that.
- ETF is version-specific; ensure you use the build compiled for 1.21.1.

### 12.5 EMF

- If a `.jem` is missing a part that vanilla expects, EMF will keep the vanilla part for that missing entry.
- Providing a `.jem` for a mob does **not** automatically remove unused vanilla parts; you must include (or explicitly hide with `"hidden": true`) all parts.
- `"invertAxis": "z"` is **almost always needed** to match OptiFine CEM's coordinate system. If your model appears mirrored front-to-back, toggle this.
- EMF uses degrees for rotation, not radians.
- `translate` moves the **pivot origin**, not the box. Boxes are positioned relative to their parent's pivot.
- Submodels inherit parent transforms cumulatively.
- Expression-based animations run every frame; keep them computationally simple.
- EMF logs model loading errors to the Minecraft log file — check `logs/latest.log` when debugging.

### 12.6 Compatibility Matrix

| | ETF | EMF | CIT Resewn | Continuity | Iris |
|---|---|---|---|---|---|
| **ETF** | — | ✅ | ✅ | ✅ | ✅ |
| **EMF** | ✅ | — | ✅ | ✅ | ✅ |
| **OptiFine** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Sodium** | ✅ | ✅ | ✅ | ✅ | requires Iris |

---

## 13. Validation Checklist

Use this checklist before finalizing any asset:

### Block/Item Models
- [ ] `pack_format` is `34` in `pack.mcmeta`
- [ ] JSON is valid (no trailing commas, no comments)
- [ ] All `#texture` references are resolved in `"textures"` block or parent chain
- [ ] Element coordinates are within 0–16 range (or intentionally outside)
- [ ] Element rotations use only: -45, -22.5, 0, 22.5, 45
- [ ] Parent model path exists in vanilla or in the pack
- [ ] Item overrides are ordered least-specific to most-specific

### ETF Textures
- [ ] `.properties` file is in the same folder as the base entity texture
- [ ] `.properties` filename matches the base texture filename
- [ ] `skins=N` value is ≥ highest numbered skin rule
- [ ] Variant texture files are named `<mob>2.png`, `<mob>3.png`, etc.
- [ ] Biome names use correct vanilla biome IDs
- [ ] Emissive textures use `_e` suffix and match base dimensions
- [ ] No OptiFine installed alongside ETF

### EMF Models
- [ ] `.jem` is placed in `assets/minecraft/emf/mob/` (or `optifine/cem/`)
- [ ] Filename matches the mob's internal name (e.g. `zombie.jem`)
- [ ] `part` names exactly match vanilla internal names (verify with EMF debug mode)
- [ ] `textureSize` matches actual texture pixel dimensions
- [ ] `invertAxis` set correctly (usually `"z"`)
- [ ] Animation expressions use valid variable and function names
- [ ] No syntax errors in JSON (check `logs/latest.log`)
- [ ] `submodels` do not include a `part` field
- [ ] All submodel `id` values are unique across the entire JEM file
- [ ] Expanded texture dimensions declared in `textureSize` match the actual PNG file
- [ ] New UV regions for extra parts do not overlap vanilla UV regions
- [ ] Animation expressions targeting custom parts use the correct `id` string (not `part`)
- [ ] Parts toggled with `.visible` still exist in the model (hidden parts still need geometry)
- [ ] Pivot positions verified in-game using EMF debug mode before finalizing
- [ ] `sin()` / `cos()` inputs are in radians; rotation outputs scaled to degrees (multiply by 57.3 or use `todeg()`)
- [ ] Parts with no vanilla equivalent are added as `submodels`, not root-level `part` entries

### General
- [ ] Resource pack folder structure is correct
- [ ] All referenced texture files exist at the specified paths
- [ ] Pack tested in-game with F3+T resource pack reload
- [ ] Checked `logs/latest.log` for asset loading errors

---

## 14. Respackopts — In-Game Config Menus for Your Pack

Respackopts (by JFronny) gives resource packs their own in-game configuration screen. Users see a gear/settings button next to your pack in the Resource Packs list and can toggle options, select variants, and adjust numeric settings — all without touching any files. The pack reloads automatically when they save.

This section explains how to wire Respackopts into a pack that uses the systems described in the rest of this document (block models, item models, ETF entity textures, EMF entity models).

**Dependencies (Fabric 1.21.1):**
- Respackopts (latest 4.x for 1.21.1)
- LibJF (required dependency of Respackopts)
- Fabric API

---

### 14.1 How Respackopts Works

Respackopts intercepts the resource loader at the file level. Before Minecraft reads a file, Respackopts checks whether a corresponding `.rpo` sidecar file exists. If it does, the sidecar's **condition** expression is evaluated against the user's current config values. If the condition is false, the file is hidden from the loader entirely — as if it doesn't exist. The vanilla fallback (the next pack in the stack, or the built-in asset) takes over.

This means Respackopts doesn't "swap" files at runtime in memory — it controls which files are **visible to the loader** at reload time. Changing a setting triggers a resource pack reload (F3+T equivalent).

---

### 14.2 File Layout

```
my_resourcepack/
├── respackopts.json5                          ← root config definition (REQUIRED)
├── pack.mcmeta
└── assets/
    └── minecraft/
        ├── textures/
        │   └── item/
        │       ├── diamond_sword.png           ← default texture (always present)
        │       ├── diamond_sword_alt.png        ← alternate texture file
        │       └── diamond_sword_alt.png.rpo   ← sidecar: condition to show alt
        ├── models/
        │   └── item/
        │       ├── diamond_sword.json
        │       ├── diamond_sword_alt.json
        │       └── diamond_sword_alt.json.rpo
        └── emf/
            └── mob/
                ├── cow_horned.jem
                └── cow_horned.jem.rpo          ← condition to use the horned cow model
    └── mypack/
        └── lang/
            └── en_us.json                      ← translations for config screen labels
```

> **Agent Rule:** The `respackopts.json5` file goes in the **root of the pack**, alongside `pack.mcmeta`. Not inside `assets/`. The lang file goes inside `assets/<your_pack_id>/lang/`.

---

### 14.3 The Root Config File — `respackopts.json5`

This is the single source of truth for every option your pack exposes. It uses JSON5 syntax (comments allowed, trailing commas allowed).

```json5
{
    // Unique identifier for your pack. camelCase, alphabetic only — no spaces or special chars.
    id: "myPack",

    // Format version. Use 13 for 1.21.1 (latest stable as of this writing).
    version: 13,

    // Capabilities tell Respackopts which features your pack uses.
    capabilities: ["FileFilter", "DirFilter"],

    // conf defines every user-facing option.
    conf: {
        // Boolean toggle — shows as an on/off switch in the config screen
        alternativeSword: true,

        // Number slider — shows as a slider with min/max bounds
        // (Advanced config: see 14.4)
        // textureScale: 1,

        // Enum / dropdown — shows as a cycle button or dropdown
        // (Advanced config: see 14.4)
        // mobVariant: "default"
    }
}
```

**Capabilities reference:**

| Capability | Default | Description |
|---|---|---|
| `FileFilter` | Enabled | Enables `.rpo` sidecar file toggling |
| `DirFilter` | Disabled | Enables `.rpo` sidecar directory toggling |
| `DirFilterAdditive` | Disabled | Compat fix for mods that also modify resources (use if conflicts arise) |
| `Shaders` | Disabled | Enables Fabulous/FREX shader uniform injection |

Always include at minimum `["FileFilter"]`. Add `"DirFilter"` if you use directory-level toggling.

---

### 14.4 Config Entry Types

#### 14.4.1 Boolean (Toggle)

```json5
conf: {
    hornedCow: true,         // on by default
    altCreeper: false        // off by default
}
```

Renders as an on/off toggle button in the config screen.

#### 14.4.2 Number (Slider)

```json5
conf: {
    particleDensity: 1.0
}
```

Numbers render as sliders. The range shown is inferred from the default — for explicit control, use the object form:

```json5
conf: {
    particleDensity: {
        value: 1.0,
        min: 0.0,
        max: 3.0,
        step: 0.5
    }
}
```

Number values are accessed in conditions as plain numeric variables (e.g. `particleDensity > 1.5`).

#### 14.4.3 Enum (Dropdown/Cycle)

```json5
conf: {
    mobVariant: ["default", "spooky", "festive"]
}
```

An array of strings defines an enum. The first entry is the default selection. Renders as a cycle button that steps through the options. The active enum value is accessed in conditions as a boolean per key: `mobVariant.spooky` is true only when `"spooky"` is selected.

#### 14.4.4 Categories (Grouping Options)

Nest options inside an object to group them into a collapsible category in the config screen:

```json5
conf: {
    entities: {
        hornedCow: true,
        spookyCreeper: false,
        mobVariant: ["default", "festive"]
    },
    items: {
        altSword: true,
        altPickaxe: false
    }
}
```

When using categories, reference entries in `.rpo` conditions using dot notation: `entities.hornedCow`, `items.altSword`.

> **Agent Rule:** Category names must also be camelCase, alphabetic only. Nesting more than two levels deep is technically supported but not recommended for UI clarity.

---

### 14.5 Sidecar `.rpo` Files

Every file that should be conditionally shown or hidden gets a `.rpo` sidecar. The sidecar is named `<original_filename>.rpo` and sits **in the same directory** as the file it controls.

#### 14.5.1 Simple Boolean Condition

```json5
// assets/minecraft/textures/entity/creeper/creeper2.png.rpo
{
    condition: "spookyCreeper"
}
```

When `spookyCreeper` is true, `creeper2.png` is visible to the loader. When false, it's hidden.

For a category-scoped entry:
```json5
{
    condition: "entities.spookyCreeper"
}
```

#### 14.5.2 Condition Expressions (μScript)

Conditions are evaluated as μScript expressions — a small expression language. Boolean and numeric values from your config can be combined with standard operators:

| Operator | Description |
|---|---|
| `!x` | NOT |
| `x & y` | AND |
| `x \| y` | OR |
| `x == y` | Equals / XNOR |
| `x != y` | Not equals / XOR |
| `x > y`, `x < y`, `x >= y`, `x <= y` | Numeric comparisons |
| `x + y`, `x - y`, `x * y`, `x / y`, `x % y` | Arithmetic |

Examples:

```json5
// Show this file only when hornedCow is on AND festive variant is selected
{ "condition": "entities.hornedCow & entities.mobVariant.festive" }

// Show when altSword is on OR altPickaxe is on
{ "condition": "items.altSword | items.altPickaxe" }

// Show when particle density is above 1.0
{ "condition": "particleDensity > 1.0" }

// Negation — show when a toggle is OFF
{ "condition": "!entities.hornedCow" }
```

#### 14.5.3 Switching Between Two Files (Fallback)

When you want to swap one file for another based on a condition, use the `fallback` field to name an alternative file to use when the condition is false:

```json5
// assets/minecraft/textures/item/diamond_sword.png.rpo
{
    condition: "items.altSword",
    fallback: "diamond_sword_vanilla.png"
}
```

When `altSword` is true: `diamond_sword.png` is loaded normally. When false: `diamond_sword_vanilla.png` is loaded instead. The fallback path is relative to the same directory as the sidecar.

> **Agent Rule:** Never reference a fallback file that itself has a `.rpo` sidecar pointing back to the original. This creates an infinite loop and Respackopts will crash with a `StackOverflowException`.

#### 14.5.4 Directory-Level `.rpo` (DirFilter)

Requires `"DirFilter"` in capabilities. Place an `.rpo` file in a directory to show or hide the entire directory:

```
assets/minecraft/textures/entity/cow_horned/
assets/minecraft/textures/entity/cow_horned.rpo   ← controls the whole folder
```

```json5
// cow_horned.rpo
{
    condition: "entities.hornedCow"
}
```

When the condition is false, nothing inside `cow_horned/` is visible to the loader.

---

### 14.6 Translations & Config Screen Labels

Without translations, Respackopts shows raw entry names (`hornedCow`, `altSword`) in the config screen. Add a lang file to give them human-readable labels and optional tooltips.

**File location:** `assets/<your_pack_id>/lang/en_us.json`

The pack ID in the path must match the `id` field in `respackopts.json5`.

```json
{
    "rpo.myPack": "My Resource Pack Options",

    "rpo.myPack.entities": "Entity Variants",
    "rpo.myPack.entities.hornedCow": "Horned Cow",
    "rpo.myPack.entities.hornedCow.tooltip": "Adds horns and a tail to the vanilla cow model",
    "rpo.myPack.entities.spookyCreeper": "Spooky Creeper",
    "rpo.myPack.entities.spookyCreeper.tooltip": "Replaces the creeper with a jack-o-lantern variant",
    "rpo.myPack.entities.mobVariant": "Mob Style",
    "rpo.myPack.entities.mobVariant.default": "Default",
    "rpo.myPack.entities.mobVariant.festive": "Festive",

    "rpo.myPack.items": "Item Textures",
    "rpo.myPack.items.altSword": "Alternative Sword",
    "rpo.myPack.items.altSword.tooltip": "Replaces the diamond sword with a custom design",
    "rpo.myPack.items.altPickaxe": "Alternative Pickaxe"
}
```

**Translation key format:**
- Pack title: `rpo.<packId>`
- Category label: `rpo.<packId>.<categoryName>`
- Entry label: `rpo.<packId>.<entryName>` or `rpo.<packId>.<category>.<entryName>`
- Entry tooltip: append `.tooltip` to any entry key
- Enum option label: `rpo.<packId>.<entryName>.<enumKey>`

---

### 14.7 Resource Expansion (Injecting Config Values Into Files)

Sometimes toggling files isn't enough — you want to inject a config value directly into a file's content. For example, inserting a user-controlled scale value into a model JSON, or choosing a texture path based on an enum.

Respackopts supports this via the `expansions` block in a `.rpo` sidecar (requires format `version: 13` or higher).

```json5
// assets/minecraft/models/item/diamond_sword.json.rpo
{
    condition: "true",
    expansions: {
        // Replace the placeholder string "RPO_SCALE" in the file with the computed value
        "RPO_SCALE": "items.textureScale || ''"
    }
}
```

In the target file, put the placeholder string exactly where the value should go:

```json
{
    "display": {
        "gui": {
            "scale": [RPO_SCALE, RPO_SCALE, RPO_SCALE]
        }
    }
}
```

The expression on the right side of each expansion entry is a μScript expression; its result (always coerced to a string) replaces the placeholder. Use `||` for string concatenation if needed.

> **Agent Rule:** Expansions run at resource load time, not at render time. The resulting file is what Minecraft sees after the substitution. The placeholder string must appear **verbatim** in the file — it is a plain text find-and-replace, not a JSON-aware operation. Wrap placeholders in a comment or use unique enough strings to avoid accidental collisions with real content.

---

### 14.8 Practical Example — Full Bonemeal-Style Pack Integration

This example mirrors a real-world texture pack that offers entity model variants, alternate item textures, and a detail density option — the kind of pack Bonemeal might ship.

#### `respackopts.json5`

```json5
{
    id: "boneMealPack",
    version: 13,
    capabilities: ["FileFilter", "DirFilter"],
    conf: {
        entities: {
            hornedCow:    true,
            spookyCreeper: false,
            cowVariant:   ["natural", "highland", "angus"]
        },
        items: {
            altDiamondSword:   true,
            altDiamondPickaxe: false
        },
        detail: {
            emissiveGlows: true
        }
    }
}
```

#### Directory structure

```
assets/
└── minecraft/
    ├── emf/mob/
    │   ├── cow.jem                          ← horned cow model
    │   └── cow.jem.rpo                      ← condition: entities.hornedCow
    ├── textures/entity/creeper/
    │   ├── creeper2.png                     ← spooky creeper texture
    │   ├── creeper2.png.rpo                 ← condition: entities.spookyCreeper
    │   ├── creeper.properties               ← ETF rules (references creeper2.png)
    │   └── creeper_e.png                    ← emissive overlay
    ├── textures/entity/cow/
    │   ├── cow.png                          ← base texture
    │   ├── cow_highland.png
    │   ├── cow_highland.png.rpo             ← condition: entities.cowVariant.highland
    │   ├── cow_angus.png
    │   └── cow_angus.png.rpo               ← condition: entities.cowVariant.angus
    ├── textures/item/
    │   ├── diamond_sword_custom.png
    │   ├── diamond_sword_custom.png.rpo     ← condition: items.altDiamondSword
    │   ├── diamond_pickaxe_custom.png
    │   └── diamond_pickaxe_custom.png.rpo  ← condition: items.altDiamondPickaxe
    └── textures/entity/creeper/
        └── creeper_e.png.rpo               ← condition: detail.emissiveGlows
└── boneMealPack/lang/
    └── en_us.json
```

#### `cow.jem.rpo`

```json5
{
    condition: "entities.hornedCow"
}
```

#### `creeper2.png.rpo` (ETF + Respackopts combined)

```json5
{
    condition: "entities.spookyCreeper"
}
```

ETF will still read `creeper.properties` and try to select `creeper2.png` as a variant — but if Respackopts hides `creeper2.png`, ETF simply won't find it and falls back to the base texture. ETF and Respackopts operate independently and compose cleanly.

#### `cow_highland.png.rpo`

```json5
{
    condition: "entities.cowVariant.highland"
}
```

#### `en_us.json` (excerpt)

```json
{
    "rpo.boneMealPack": "Bonemeal Pack Options",
    "rpo.boneMealPack.entities": "Entity Variants",
    "rpo.boneMealPack.entities.hornedCow": "Horned Cow Model",
    "rpo.boneMealPack.entities.hornedCow.tooltip": "Adds horns and a tail to all cows",
    "rpo.boneMealPack.entities.spookyCreeper": "Spooky Creeper",
    "rpo.boneMealPack.entities.cowVariant": "Cow Coat",
    "rpo.boneMealPack.entities.cowVariant.natural": "Natural",
    "rpo.boneMealPack.entities.cowVariant.highland": "Highland",
    "rpo.boneMealPack.entities.cowVariant.angus": "Angus",
    "rpo.boneMealPack.items": "Item Textures",
    "rpo.boneMealPack.items.altDiamondSword": "Custom Diamond Sword",
    "rpo.boneMealPack.items.altDiamondPickaxe": "Custom Diamond Pickaxe",
    "rpo.boneMealPack.detail": "Visual Detail",
    "rpo.boneMealPack.detail.emissiveGlows": "Emissive Glows",
    "rpo.boneMealPack.detail.emissiveGlows.tooltip": "Enables glow-in-the-dark texture overlays (ETF)"
}
```

---

### 14.9 Debugging Respackopts

**In-game commands** (requires cheats or operator permissions):

| Command | What it does |
|---|---|
| `/rpoc dump config` | Dumps all loaded pack config options and their current values |
| `/rpoc dump scope` | Dumps the full μScript scope — shows every variable name available in conditions |
| `/rpoc dump asset <id>` | Shows the actual resolved file Minecraft will use for a given resource identifier |
| `/rpoc dump glsl` | Dumps shader integration code (only useful if using the `Shaders` capability) |
| `/rpoc execute <expr>` | Evaluates a μScript expression live with current config applied |

**Common issues:**

| Symptom | Likely Cause |
|---|---|
| Config screen button doesn't appear | `respackopts.json5` not found in pack root, or JSON5 parse error |
| Option appears but does nothing | `.rpo` condition references wrong entry name; check category prefix |
| Pack fails to load entirely | Commas or colons used instead of dots in condition strings; or circular fallback reference |
| Two packs interfere with each other | Both packs share the same `id` value — IDs must be globally unique |
| File always hidden regardless of toggle | Condition expression evaluates to false due to logic error; use `/rpoc execute` to test |
| StackOverflowException on reload | Circular fallback: file A's `.rpo` fallback points to file B, whose `.rpo` fallback points back to A |

**Saved user settings** are stored next to the resource pack file on disk (e.g. `MyPack.zip.rpo` in the `resourcepacks/` folder). Delete this file to reset a user's saved config to your defaults.

---

### 14.10 Respackopts Constraints

- `id` must be **camelCase, alphabetic characters only**. No numbers, hyphens, underscores, or spaces. Violation causes the pack to fail silently.
- `id` must be **globally unique** across all installed packs. Duplicate IDs cause condition conflicts with no clear error.
- Condition strings use **normal dots only** for category access (`entities.hornedCow`). Commas or colons in conditions will cause the pack to fail to load.
- `.rpo` sidecar conditions are **μScript expressions**, not plain property names — though a plain name like `"hornedCow"` is a valid μScript identifier expression.
- Fallback chains must be **acyclic**. A → B → A will crash.
- `DirFilter` must be listed in `capabilities` before directory-level `.rpo` files have any effect.
- Respackopts does **not** support runtime hot-swapping. All changes require a resource pack reload (F3+T).
- The `version` field should be **13** for 1.21.1 packs. Using an old version number disables features introduced in later format versions.
- ETF `.properties` files are not `.rpo`-filterable in the same way as textures — hiding a `.properties` file removes the ETF ruleset, falling back to no randomization. This is a valid technique for an "enable ETF randomization" toggle.
- **Performance:** Respackopts adds roughly 6% overhead to resource reload time and 18% to initial game load time (measured on 1.20.1). Pack scanning is the most expensive phase. This is generally acceptable but worth noting for packs with hundreds of `.rpo` sidecars.

---

*This document reflects behavior as of Fabric 1.21.1 with ETF and EMF at their latest compatible releases. Always verify mod changelogs when updating to new versions, as file path conventions and supported fields may change.*
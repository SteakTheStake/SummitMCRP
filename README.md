# SummitMCRP

A high-fidelity 64x Minecraft Java resource pack focused on subtle realism and enhanced visual immersion. Built for Fabric 1.21.1 with advanced mod support including CTM, EMF/ETF, and Respackopts.

## 🎯 Features

- **64x64 textures** with attention to detail and realism
- **Connected Textures (CTM)** using Athena and Fusion loaders for seamless blocks
- **Entity Models** via EMF (Entity Model Features) and ETF (Entity Texture Features)
- **Configurable Options** through Respackopts in-game menu
- **Custom Sounds** for enhanced audio immersion
- **3D Grass Blades** and bushy leaf variants
- **Animated Mobs** with Fresh Animations integration

## 📋 Requirements

### Required Mods (Fabric 1.21.1)
- **Fabric API** - Core mod loader
- **EMF** (Entity Model Features) - Custom entity models
- **ETF** (Entity Texture Features) - Random entity textures
- **Respackopts** - In-game configuration menu
- **Continuity** (recommended) - Additional CTM features

### Optional Companions
- **CIT Resewn** - Custom item textures
- **Polytone** - Dynamic color adjustments
- **Iris/Sodium** - Performance optimization
- **Athena CTM** - Connected texture system
- **Fusion CTM** - Alternative CTM loader

## 🚀 Installation

1. Install the required mods using your preferred mod manager
2. Download the latest SummitMCRP release
3. Place the `.zip` file in your `resourcepacks` folder
4. Enable the pack in Minecraft options
5. Configure options using Respackopts (accessible via Mod Menu)

## ⚙️ Configuration

The pack includes extensive configuration options accessible through the Respackopts menu:

- **Alternative Totem** - Custom totem of undying texture
- **3D Bushy Leaves** - Enhanced leaf models for all tree types
- **Custom Entity Models** - EMF animated mob reskins
- **Legacy CEM Models** - OptiFine-compatible mob models
- **Connected Textures** - Toggle CTM for stones, woods, grasses, etc.
- **3D Grass Blades** - Realistic grass rendering
- **Custom Sounds** - Enhanced dig and step sounds

## 🛠️ Development

### Building the Pack

This repository includes development tools for managing CTM textures:

```bash
# Stitch split CTM tiles into sprite sheets (development mode)
python ctm_stitch.py pack --mode dev

# Export production pack (splits sheets back to individual tiles)
python ctm_stitch.py pack --mode prod

# Create distributable zip
python ctm_stitch.py export

# Generate CTM configurations
python ctm_stitch.py athena --manifest athena_ctm.json
python ctm_stitch.py fusion --manifest fusion_ctm.json
```

### Project Structure

```
SummitMCRP/
├── assets/minecraft/          # Main pack assets
│   ├── blockstates/          # Block state definitions
│   ├── models/               # Block and item models
│   ├── textures/             # Texture files
│   ├── emf/                  # EMF entity models
│   ├── optifine/             # CEM/legacy models
│   └── polytone/             # Color configurations
├── ctm_stitch.py             # CTM development tools
├── respackopts.json5         # Pack configuration
├── athena_ctm.json           # Athena CTM manifest
└── fusion_ctm.json           # Fusion CTM manifest
```

## 🎨 Asset Credits

### Trager_Grant
- **TG Terrifying Sculk Shrieker**  
  https://www.planetminecraft.com/texture-pack/tg-terrifying-sculk-shrieker/

### Fresh Animations
- Animated CEM models by FreshLX  
  https://modrinth.com/resourcepack/fresh-animations

### CanineGray
- **Gray's Mob Overhaul** integration  
  https://modrinth.com/resourcepack/grays-mob-overhaul-x-fresh-animations/versions

## 🤝 Contributors

### SPARKAT150
- Comprehensive IRL item/texture research
- Lore accuracy validation
- Reference imagery collection
- Project goal setting

### Foxtrot12
- Texture contributions
- Bug testing and reporting
- Performance optimization
- Gameplay experience refinement

### Leed / Daclownless
- Project coordination
- Reference imagery
- Debugging support
- Lore accuracy checks

## 🌐 Community

- **ShaderLABS Discord**: https://discord.gg/p4nb4HFhyq
- **SummitMC Discord**: https://discord.gg/JgK6rFxDAd
- **Website**: https://summitmc.xyz/
- **Patreon**: https://www.patreon.com/Summitmc

## 📄 License

This resource pack is the collective work of the SummitMC team and contributors. Please respect the original creators' rights when using or modifying assets.

---

*Special thanks to everyone in ShaderLABS who helped with questions and fixes!*


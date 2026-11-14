# hd_hud

Made by LunicAura106
https://nfsmods.xyz/mod/1096

Faithful HD remakes of the game's 2D textures: HUD, frontend, fonts, track maps and minimaps.

Version used: `NFSMWUHUD01022026b.7z`, files were laid out as Xbox 360 game data.

## Layout

- `files/<file>/<pack>/<TEXTURE>.dds`: one texture per file.
- `files/TRACKS/L2RA/MINI_MAP*.BIN`: the mod's minimap tiles.
- `files/_overrides/RUSSIAN/`: the mod's Russian fonts overrides.
- `.sblink`: duplicate textures, each linked to one file.
- `SOURCES.tsv`: each file mapped to its path in the mod archive.

## Extras selection

- Included: the X360Stuff `360v4+` variants (`RVM_MASK`, `WS_XENON_SPLASHBACK`).
- Left out: PC prompts, mod icons, grit styles (to preserve the original grit art).

## Changes

- `CROSSHAIR_CORNER`: original layout restored.
- `GUIDE`: [Aero_](https://github.com/AeroWidescreen)'s HD version.

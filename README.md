# speedbreaker-mod-assets

Downloadable mod packs for the `mw-fixes-mods` branch of my [SpeedBreaker fork](https://github.com/feelbadinc/speedbreaker) (not in upstream). SpeedBreaker fetches them in-game; the releases are not meant to be downloaded manually.

Build tooling by [feelbadinc](https://github.com/feelbadinc).
The HUFF decoder in `tools/eac/` comes from EA (see Licenses).

## How it works

- `sources/<key>/files/` holds the original mod files, one folder per mod; `sources/<key>/VERSION` holds its version (one line, a whole number, `1` for now). `build.py` compresses them into a set the game reads (`dist/<key>/`) and a release zip (`dist/<key>-v<VERSION>.zip` + `.sha256`).
- `manifest.json` lists every mod: key = `mods/` folder name, `tag` = release tag `<key>-vN`, `file` = release zip name. SpeedBreaker reads it from `master` branch to install and update mods.
- Currently the mods are limited to UI textures.

## Requirements

- Python 3.14 or later built with zstd support (`compression.zstd`).
- g++ with C++20 (g++ 10+; builds the decoder; only for mods with minimaps).
- tqdm: shows a progress bar; without it, a plain progress counter is shown.

## Building

- `build.py` builds all mods, `build.py <key>` builds a specific mod.
- `.dds` -> `.dds.zst`; `MINI_MAP*.BIN` -> raw TPK (`tools/jdlz_huff_decode.cpp`) -> `.BIN.zst`; `.sblink` copied as-is.
- Output in `dist/`:
  - `dist/<key>/`: the built set, ready to drop into SpeedBreaker `mods/` as is.
  - `dist/<key>-v<VERSION>.zip` + `.sha256`.

## Releasing

- When a mod is upgraded, increment its `sources/<key>/VERSION` and the `-vN` in its `manifest.json` `tag` and `file`; the game offers an update only when `N` is higher than the installed one. Rebuild, then upload `dist/<key>-vN.zip` and `.sha256` to the release `tag` as they are. Commit the `manifest.json` change to master only after the release is made, so the game never sees an update resolving 404.
- Zip format the game accepts: stored (no compression), everything under `<key>/`, no `..`/absolute paths/symlinks, no zip64. `build.py` already writes it that way.

## Licenses

- `sources/`: each mod has its own `LICENSE`; where the author gave none, a `NOTICE` with credit instead.
- `tools/eac/`: GPLv3 with EA additional terms (`tools/eac/LICENSE`). HUFF decoder from C&C Generals [source release](https://github.com/electronicarts/CnC_Generals_Zero_Hour).
- The rest of the repo: GPLv3 (`LICENSE`).

## Disclaimer

Need for Speed™ Most Wanted (2005) and all related names, artwork and trademarks belong to Electronic Arts and their respective owners. This is an unofficial, non-commercial fan project, not affiliated with or endorsed by them. Assets are to be removed on request.

"""
Builds the mod sets in sources/ into dist/.
Usage: build.py [key] (no key = all mods).
"""

import sys

if sys.version_info < (3, 14):
    found = f"{sys.version_info.major}.{sys.version_info.minor}"
    sys.exit(f"Python 3.14+ required ({found} found).")

try:
    from compression import zstd
except ImportError:
    sys.exit("Your Python build lacks zstd support.")

import hashlib
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources"
DIST = ROOT / "dist"
TEMP = DIST / ".temp"  # dot name: can't clash with a mod key
TOOLS = ROOT / "tools"


class BuildError(Exception):
    pass


class PlainProgress:
    def __init__(self):
        self.live = sys.stderr.isatty()

    def phase(self, label, total):
        self.label, self.done, self.total = label, 0, total
        self.show()

    def show(self):
        if self.live:
            line = f"\r{self.label}: {self.done}/{self.total}"
            print(line, end="", file=sys.stderr, flush=True)

    def step(self, count=1):
        self.done += count
        self.show()

    def end_phase(self, ok=True):
        if not self.live:
            line = f"{self.label}: {self.done}/{self.total}"
            print(line, end="", file=sys.stderr)
        print(" - done" if ok else " - failed", file=sys.stderr)


class BarProgress:
    bar = None

    def phase(self, label, total):
        if self.bar:
            print(file=sys.stderr)
        self.bar = tqdm(
            total=total, desc=label, unit="file", dynamic_ncols=True
        )

    def step(self, count=1):
        self.bar.update(count)

    def end_phase(self, ok=True):
        if not ok:
            self.bar.set_postfix_str("failed")
        self.bar.close()


def remove_zip(key):
    # Any version of the mod: <key>-vN.zip and its .sha256
    pattern = re.compile(rf"{re.escape(key)}-v\d+\.zip(\.sha256)?")

    for path in DIST.glob("*"):
        if pattern.fullmatch(path.name):
            path.unlink()


def bad_link(files, link):
    # The game reads the first line of .sblink as a texture path relative to
    # the set root, so it must stay inside the set and name an existing .dds
    try:
        lines = link.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return f"bad link: {link} (not UTF-8)"

    if not lines or not lines[0].strip():
        return f"bad link: {link} (empty)"

    target = Path(lines[0].rstrip())
    where = f"bad link: {link} -> {target}"

    if target.is_absolute() or ".." in target.parts:
        return f"{where} (outside the set)"

    # Dot folders are not shipped, so a link into one would dangle.
    if any(p.startswith(".") for p in target.parts):
        return f"{where} (dot folder)"

    if target.suffix.lower() != ".dds":
        return f"{where} (not a .dds)"

    if not (files / target).is_file():
        return f"{where} (missing)"

    return None


class Mod:
    def __init__(self, key):
        self.key = key
        self.source = SOURCES / key
        self.files = self.source / "files"
        self.version = None
        self.dds, self.links, self.minimaps, self.errors = [], [], [], []

        # Same rule as the game uses for mod keys.
        if not re.fullmatch(r"[a-z0-9_-]{1,64}", key):
            self.errors.append(f"bad mod name '{key}' (a-z, 0-9, _ and - only)")
            return

        try:
            text = (self.source / "VERSION").read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""

        if not re.fullmatch(r"[1-9][0-9]*\n?", text):
            self.errors.append(
                f"VERSION missing or bad: {self.source / 'VERSION'} "
                "(one line, a whole number from 1)"
            )

        self.version = text.strip()

        if not self.files.is_dir():
            self.errors.append(f"files/ not found: {self.files}")
            return

        # Sorted for a stable build order; dotfiles and dotdirs are ignored.
        for src in sorted(self.files.rglob("*")):
            relative = src.relative_to(self.files)

            if not src.is_file() or any(p.startswith(".") for p in relative.parts):
                continue

            suffix = src.suffix.lower()

            if suffix == ".dds":
                self.dds.append(src)
            elif suffix == ".sblink":
                self.links.append(src)
                if error := bad_link(self.files, src):
                    self.errors.append(error)
            elif src.name.upper().startswith("MINI_MAP") and suffix == ".bin":
                self.minimaps.append(src)
            else:
                self.errors.append(f"unknown file type: {src}")

        if not self.dds:
            self.errors.append(f"no textures (.dds) found in {self.files}")


def compress(data, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(zstd.compress(data, level=22))


def build_helper():
    # Built once per run, shared by all mods.
    helper = TEMP / "jdlz_huff_decode"

    if helper.is_file():
        return helper

    if not shutil.which("g++"):
        raise BuildError("g++ not found; needed to build the decoder.")

    TEMP.mkdir(parents=True, exist_ok=True)

    result = subprocess.run([
        "g++", "-O2", "-std=c++20", "-I",
        TOOLS / "eac",
        TOOLS / "jdlz_huff_decode.cpp",
        TOOLS / "eac" / "huffdecode.cpp",
        "-o", helper,
    ], capture_output=True, text=True, check=False)

    if result.returncode != 0:
        raise BuildError(
            f"building the decoder failed:\n{result.stderr.strip()}"
        )

    return helper


def build_minimaps(mod, out, progress):
    # Minimap .BIN files are JDLZ/HUFF-packed. The decoder is compiled into a
    # temp dir, unpacks each one to a raw TPK, and that is zstd compressed.
    progress.phase(f"{mod.key} bin", len(mod.minimaps))

    try:
        helper = build_helper()
    except BuildError as error:
        mod.errors.append(str(error))
        progress.step(len(mod.minimaps))  # skipped, keep the total right
        progress.end_phase(ok=False)
        return

    raw = TEMP / "minimap.tpk"

    for src in mod.minimaps:
        result = subprocess.run(
            [helper, src, raw], capture_output=True, text=True, check=False
        )

        if result.returncode == 0:
            compress(raw.read_bytes(), out / f"{src.relative_to(mod.files)}.zst")
        else:
            mod.errors.append(result.stderr.strip() or f"unpacking {src} failed")

        raw.unlink(missing_ok=True)
        progress.step()

    progress.end_phase(ok=not mod.errors)


def write_zip(key, version, out):
    # Not deflated: the payload is already zstd. Fixed date and
    # permissions keep identical sources and an identical zip.
    archive = DIST / f"{key}-v{version}.zip"

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED, allowZip64=False) as zf:
        for path in sorted(out.rglob("*")):
            if path.is_file():
                name = f"{key}/{path.relative_to(out).as_posix()}"
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.external_attr = 0o644 << 16
                zf.writestr(info, path.read_bytes())

    with archive.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()

    Path(f"{archive}.sha256").write_text(f"{digest}  {archive.name}\n")


def build(mod, progress):
    out = DIST / mod.key
    shutil.rmtree(out, ignore_errors=True)
    remove_zip(mod.key)
    out.mkdir(parents=True)

    progress.phase(f"{mod.key} dds", len(mod.dds))

    for src in mod.dds:
        compress(src.read_bytes(), out / f"{src.relative_to(mod.files)}.zst")
        progress.step()

    for src in mod.links:
        dest = out / src.relative_to(mod.files)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)

    progress.end_phase()

    for name in ("NOTICE", "LICENSE"):
        if (mod.source / name).is_file():
            shutil.copyfile(mod.source / name, out / name)

    if mod.minimaps:
        build_minimaps(mod, out, progress)

    # Never leave a broken set behind.
    if mod.errors:
        shutil.rmtree(out)
    else:
        write_zip(mod.key, mod.version, out)


def main():
    if len(sys.argv) > 2:
        sys.exit(__doc__.strip())

    if not SOURCES.is_dir():
        sys.exit(f"Error: {SOURCES} not found.")

    keys = sorted(
        p.name
        for p in SOURCES.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )

    if len(sys.argv) == 2:
        key = sys.argv[1]
        if key not in keys:
            sys.exit(f"Error: unknown mod '{key}' (have: {', '.join(keys)}).")
        keys = [key]
    else:
        for path in [*DIST.glob("*.zip"), *DIST.glob("*.zip.sha256")]:
            path.unlink()  # incl. zips of removed mods

    if hasattr(os, "nice"):
        os.nice(19)  # zstd 22 is slow, keep the machine usable

    # Source problems are found early; such mods are skipped.
    mods = [Mod(key) for key in keys]
    ready = [mod for mod in mods if not mod.errors]
    progress = BarProgress() if tqdm else PlainProgress()

    try:
        for mod in ready:
            build(mod, progress)
    except KeyboardInterrupt:
        # Ctrl+C: drop the half-built set, finished ones stay.
        shutil.rmtree(DIST / mod.key, ignore_errors=True)
        remove_zip(mod.key)
        sys.exit(f"\nInterrupted; {mod.key} not built.")

    # Errors go last so the progress output doesn't bury them.
    failed = [mod for mod in mods if mod.errors]

    for mod in failed:
        print(f"\n{mod.key}: not built", file=sys.stderr)
        for error in mod.errors:
            error = error.replace(f"{ROOT}/", "").replace("\n", "\n    ")
            print(f"  {error}", file=sys.stderr)

    if len(failed) < len(mods):
        print("\nBuild files are in dist/")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted.")  # outside the build loop, nothing to undo
    finally:
        shutil.rmtree(TEMP, ignore_errors=True)

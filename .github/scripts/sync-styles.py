#!/usr/bin/env python3
"""Copy matching tileserver styles from an upstream styles checkout.

Only directories present in both trees are updated. Directories whose names
contain "svg" are skipped, along with everything under them. PNG extensions are
lowercased so sprite.PNG replaces sprite.png. style.json source, sprite, and
glyph URLs are rewritten in the original file text for TileServer GL serving
the RBT and TERRAIN MBTiles.

This is a copy of .github/scripts/sync-styles.py in
ReleasableBasemapTiles/rbt-local, so the published styles match what
rbt-local serves. Keep the two in step.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Every style needs RBT; TERRAIN is optional (a style may have no hillshade).
SOURCE_URLS = {"RBT": "mbtiles://{RBT}", "TERRAIN": "mbtiles://{TERRAIN}"}
SPRITE = "{styleJsonFolder}/sprite"
GLYPHS = "{fontstack}/{range}.pbf"


def is_svg_dir(name: str) -> bool:
    return "svg" in name.lower()


def in_svg_dir(path: Path, root: Path) -> bool:
    return any(is_svg_dir(part) for part in path.relative_to(root).parts)


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not is_svg_dir(d)]
        dirnames.sort()
        for filename in sorted(filenames):
            yield Path(dirpath) / filename


def normalized_rel(path: Path, root: Path) -> Path:
    rel = path.relative_to(root)
    if rel.suffix.lower() == ".png":
        return rel.with_suffix(".png")
    return rel


def replace_unique(text: str, old: str, new: str, label: str) -> str:
    if old == new:
        return text
    quoted_old = json.dumps(old)
    quoted_new = json.dumps(new)
    count = text.count(quoted_old)
    if count != 1:
        raise SystemExit(f"{label}: {old!r} appears {count} times, expected 1")
    return text.replace(quoted_old, quoted_new, 1)


def read_style_text(path: Path) -> str:
    # Path.read_text(newline=...) is Python 3.13+. The runner is 3.12.
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def write_style_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def rewrite_style(path: Path, label: str) -> None:
    text = read_style_text(path)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label}: style.json is not valid JSON ({exc})") from exc

    sources = data.get("sources")
    if not isinstance(sources, dict):
        raise SystemExit(f"{label}: style.json has no sources object")

    unknown = sorted(set(sources) - set(SOURCE_URLS))
    if unknown:
        raise SystemExit(
            f"{label}: style.json has sources this tileserver doesn't serve: "
            f"{', '.join(unknown)} (only {' and '.join(SOURCE_URLS)})"
        )
    if "RBT" not in sources:
        raise SystemExit(f"{label}: style.json is missing sources.RBT")
    for name, source in sources.items():
        if not isinstance(source, dict) or not isinstance(source.get("url"), str):
            raise SystemExit(f"{label}: style.json is missing sources.{name}.url")

    for key in ("sprite", "glyphs"):
        if not isinstance(data.get(key), str):
            raise SystemExit(f"{label}: style.json is missing {key}")

    for name, source in sources.items():
        text = replace_unique(
            text, source["url"], SOURCE_URLS[name], f"{label} sources.{name}.url"
        )
    text = replace_unique(text, data["sprite"], SPRITE, f"{label} sprite")
    text = replace_unique(text, data["glyphs"], GLYPHS, f"{label} glyphs")

    rewritten = json.loads(text)
    for name, source in sources.items():
        new = rewritten["sources"][name]
        if new["url"] != SOURCE_URLS[name]:
            raise SystemExit(f"{label}: sources.{name}.url was not rewritten")
        for key in ("type", "tileSize", "encoding"):
            if new.get(key) != source.get(key):
                raise SystemExit(f"{label}: sources.{name}.{key} changed")
    if rewritten["sprite"] != SPRITE or rewritten["glyphs"] != GLYPHS:
        raise SystemExit(f"{label}: sprite or glyphs were not rewritten")

    write_style_text(path, text)


def should_keep(existing: Path, dest_style: Path, keep: set[Path]) -> bool:
    rel = existing.relative_to(dest_style)
    if rel in keep:
        return True
    if rel.suffix.lower() != ".png":
        return False
    normalized = rel.with_suffix(".png")
    if normalized not in keep:
        return False
    kept = dest_style / normalized
    return kept.exists() and existing.samefile(kept)


def prune_empty_dirs(root: Path) -> None:
    for dirpath, _dirnames, _filenames in os.walk(root, topdown=False):
        current = Path(dirpath)
        if current == root or in_svg_dir(current, root):
            continue
        if not any(current.iterdir()):
            current.rmdir()


def sync_style(upstream_style: Path, dest_style: Path) -> tuple[int, int]:
    planned: dict[Path, Path] = {}
    for source in iter_files(upstream_style):
        rel = normalized_rel(source, upstream_style)
        previous = planned.get(rel)
        if previous is not None:
            raise SystemExit(
                f"{dest_style.name}: {previous.relative_to(upstream_style).as_posix()} "
                f"and {source.relative_to(upstream_style).as_posix()} both map to {rel.as_posix()}"
            )
        planned[rel] = source

    if Path("style.json") not in planned:
        raise SystemExit(f"{dest_style.name}: upstream style has no style.json")

    for rel, source in planned.items():
        target = dest_style / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    rewrite_style(dest_style / "style.json", dest_style.name)

    keep = set(planned)
    removed = 0
    for existing in list(iter_files(dest_style)):
        if should_keep(existing, dest_style, keep):
            continue
        existing.unlink()
        removed += 1

    prune_empty_dirs(dest_style)
    return len(planned), removed


def style_dirs(root: Path) -> set[str]:
    return {path.name for path in root.iterdir() if path.is_dir() and not is_svg_dir(path.name)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path, help="Upstream styles directory (styles/)")
    parser.add_argument("dest", type=Path, help="Local tileserver/styles directory")
    args = parser.parse_args()

    upstream = args.upstream.resolve()
    dest = args.dest.resolve()
    if not upstream.is_dir():
        raise SystemExit(f"upstream styles directory not found: {upstream}")
    if not dest.is_dir():
        raise SystemExit(f"dest styles directory not found: {dest}")

    upstream_names = style_dirs(upstream)
    dest_names = style_dirs(dest)
    for name in sorted(dest_names - upstream_names):
        # A workflow annotation, so a style upstream renamed or removed shows up.
        print(f"::warning::{name} is not in the upstream checkout; left as is")

    matched = sorted(dest_names & upstream_names)
    if not matched:
        raise SystemExit("no matching styles to sync")

    for name in matched:
        copied, removed = sync_style(upstream / name, dest / name)
        print(f"synced {name} ({copied} files, removed {removed})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

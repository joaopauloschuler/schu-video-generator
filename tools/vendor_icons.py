"""(Re)vendor icons from the ``lucide-static`` npm package into ``src/vidgen/data/icons``.

Not shipped with vidgen; a maintainer tool. The icon list is ``tools/icon_set.json``::

    {"package": "lucide-static", "version": "1.52.0",
     "categories": {"tech": ["cpu", ...], "data": [...], ...},
     "extra_tags": {"cloud": ["internet", ...]}}       # optional, added after Lucide's tags

Run from the repository root (needs ``npm`` on PATH, or ``--package-dir`` with an extracted
package)::

    python tools/vendor_icons.py                       # npm pack + extract into a temp folder
    python tools/vendor_icons.py --package-dir DIR     # DIR contains icons/, tags.json, LICENSE

It copies ``icons/<name>.svg`` verbatim to ``lucide/<name>.svg``, the package's ``LICENSE`` to
``lucide/LICENSE``, removes vendored SVGs no longer listed and writes ``manifest.json`` (name,
category, tags from the package's ``tags.json`` plus ``extra_tags``, source; DESIGN.md §22).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SET = ROOT / "tools" / "icon_set.json"
DEFAULT_OUT = ROOT / "src" / "vidgen" / "data" / "icons"
SOURCE = "lucide"


def fetch_package(package: str, version: str, workdir: Path) -> Path:
    """Download ``package@version`` with ``npm pack`` into ``workdir`` and extract it; returns
    the extracted ``package/`` folder."""
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm not found on PATH (or pass --package-dir with an extracted package)")
    result = subprocess.run(
        [npm, "pack", f"{package}@{version}", "--pack-destination", str(workdir)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    tarball = workdir / result.stdout.strip().splitlines()[-1]
    with tarfile.open(tarball) as archive:
        if sys.version_info >= (3, 12):
            archive.extractall(workdir, filter="data")
        else:  # pragma: no cover - Python < 3.12 has no extraction filters
            archive.extractall(workdir)  # noqa: S202 - the npm registry tarball of a pinned version
    return workdir / "package"


def build_manifest(package_dir: Path, icon_set: dict[str, Any], categories: dict[str, str]) -> dict[str, Any]:
    """The manifest for ``icon_set`` read from the extracted ``package_dir``."""
    meta = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
    if meta.get("version") != icon_set["version"]:
        raise SystemExit(f"package version {meta.get('version')} differs from icon_set version {icon_set['version']}")
    tags_file = package_dir / "tags.json"
    tags: dict[str, list[str]] = json.loads(tags_file.read_text(encoding="utf-8")) if tags_file.is_file() else {}
    extra: dict[str, list[str]] = icon_set.get("extra_tags", {})
    icons: list[dict[str, Any]] = []
    seen: set[str] = set()
    for category, names in icon_set["categories"].items():
        if category not in categories:
            raise SystemExit(f"unknown category {category!r}; known: {', '.join(categories)}")
        for name in names:
            if name in seen:
                raise SystemExit(f"icon {name!r} is listed twice")
            seen.add(name)
            if not (package_dir / "icons" / f"{name}.svg").is_file():
                raise SystemExit(f"icon {name!r} is not in {icon_set['package']} {icon_set['version']}")
            merged = list(dict.fromkeys([*tags.get(name, []), *extra.get(name, [])]))
            icons.append({"name": name, "category": category, "tags": merged, "source": SOURCE})
    unlisted = sorted(set(extra) - seen)
    if unlisted:
        raise SystemExit(f"extra_tags for icons not listed: {', '.join(unlisted)}")
    return {
        "version": 1,
        "sources": {
            SOURCE: {
                "package": icon_set["package"],
                "version": icon_set["version"],
                "license": meta.get("license", ""),
                "license_file": f"{SOURCE}/LICENSE",
                "homepage": meta.get("homepage", ""),
            }
        },
        "icons": sorted(icons, key=lambda entry: entry["name"]),
    }


def vendor(package_dir: Path, icon_set: dict[str, Any], out_dir: Path, categories: dict[str, str]) -> dict[str, Any]:
    """Copy the listed SVGs and the licence into ``out_dir`` and write its manifest."""
    manifest = build_manifest(package_dir, icon_set, categories)
    folder = out_dir / SOURCE
    folder.mkdir(parents=True, exist_ok=True)
    wanted = {entry["name"] for entry in manifest["icons"]}
    for stale in folder.glob("*.svg"):
        if stale.stem not in wanted:
            stale.unlink()
    for name in sorted(wanted):
        shutil.copyfile(package_dir / "icons" / f"{name}.svg", folder / f"{name}.svg")
    shutil.copyfile(package_dir / "LICENSE", folder / "LICENSE")
    text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    (out_dir / "manifest.json").write_text(text, encoding="utf-8", newline="\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", type=Path, default=DEFAULT_SET, help="icon list (default: tools/icon_set.json)")
    parser.add_argument("--package-dir", type=Path, help="an extracted lucide-static package (default: npm pack)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="target folder (default: src/vidgen/data/icons)")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT / "src"))
    from vidgen.icons import CATEGORIES

    icon_set = json.loads(args.set.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        package_dir = args.package_dir or fetch_package(icon_set["package"], icon_set["version"], Path(tmp))
        manifest = vendor(package_dir, icon_set, args.out, CATEGORIES)
    print(f"vendored {len(manifest['icons'])} icons from {icon_set['package']} {icon_set['version']} into {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

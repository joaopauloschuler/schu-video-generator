"""Project: locate and load a project's config, apply a variant, resolve paths (DESIGN.md §3)."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import yaml

from vidgen.config import BeatConfig, FormatConfig, SceneConfig, VideoConfig, parse_config
from vidgen.errors import VidgenError

CONFIG_NAMES: tuple[str, ...] = ("video.yaml", "video.yml", "video.json")


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``base`` with ``override`` merged in.

    Mappings are merged recursively; any other value (lists included) replaces the base value.
    Neither input is modified.
    """
    merged = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def find_config_file(path: str | Path) -> Path:
    """Find the config file for ``path`` (a project directory or a config file)."""
    path = Path(path)
    if path.is_file():
        if path.suffix.lower() not in (".yaml", ".yml", ".json"):
            raise VidgenError(f"{path}: config file must be .yaml, .yml or .json")
        return path
    if not path.is_dir():
        raise VidgenError(f"project not found: {path}")
    found = [path / name for name in CONFIG_NAMES if (path / name).is_file()]
    if not found:
        raise VidgenError(f"no config file in {path} (expected one of: {', '.join(CONFIG_NAMES)})")
    if len(found) > 1:
        names = ", ".join(p.name for p in found)
        raise VidgenError(f"more than one config file in {path} ({names}); keep only one")
    return found[0]


def read_config_file(path: Path) -> Any:
    """Parse a YAML or JSON config file (UTF-8)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise VidgenError(f"{path.name}: cannot read file: {exc}") from None
    try:
        if path.suffix.lower() == ".json":
            return json.loads(text)
        return yaml.safe_load(text)
    except json.JSONDecodeError as exc:
        raise VidgenError(f"{path.name}: invalid JSON at line {exc.lineno}: {exc.msg}") from None
    except yaml.YAMLError as exc:
        raise VidgenError(f"{path.name}: invalid YAML: {exc}") from None


class Project:
    """A loaded project folder. Create with :meth:`Project.load`."""

    def __init__(self, root: Path, config_file: Path, config: VideoConfig, variant: str | None) -> None:
        self.root = root
        self.config_file = config_file
        self.config = config
        self.variant = variant

    @classmethod
    def load(cls, path: str | Path = ".", variant: str | None = None) -> Project:
        """Load the project at ``path`` (directory or config file), optionally applying a variant.

        The variant's overrides are deep-merged onto the raw config before validation.
        """
        config_file = find_config_file(path).resolve()
        source = config_file.name
        data = read_config_file(config_file)
        base = parse_config(data, source)
        if variant is not None:
            if variant not in base.variants:
                known = ", ".join(sorted(base.variants)) or "(none defined)"
                raise VidgenError(f"{source}: unknown variant '{variant}'; available variants: {known}")
            data = deep_merge(data, base.variants[variant])
            base = parse_config(data, f"{source} (variant '{variant}')")
        return cls(config_file.parent, config_file, base, variant)

    # ----- names and paths -------------------------------------------------------------------

    @property
    def output_name(self) -> str:
        """Basename of output files: ``config.output`` or the project folder's name."""
        return self.config.output or self.root.name

    @property
    def audio_dir(self) -> Path:
        """``<root>/audio``: narration MP3s and their hash files."""
        return self.root / "audio"

    @property
    def build_dir(self) -> Path:
        """``<root>/build``: all intermediate render output."""
        return self.root / "build"

    @property
    def extension_dirs(self) -> list[Path]:
        """Configured extension directories (absolute; they may not exist)."""
        return [self.root / d for d in self.config.extensions]

    def render_dir(self, preview: bool) -> Path:
        """Per-quality build folder: ``build/<final|preview>[_<variant>]``."""
        name = "preview" if preview else "final"
        if self.variant:
            name += f"_{self.variant}"
        return self.build_dir / name

    def render_format(self, preview: bool) -> FormatConfig:
        """Resolution/fps for a final or preview render."""
        return self.config.preview if preview else self.config.format

    def _output_stem(self, preview: bool) -> str:
        stem = self.output_name
        if self.variant:
            stem += f"_{self.variant}"
        if preview:
            stem += "_preview"
        return stem

    def output_path(self, preview: bool = False) -> Path:
        """Final video path: ``<output>[_<variant>][_preview].mp4`` in the project root."""
        return self.root / f"{self._output_stem(preview)}.mp4"

    def srt_path(self, preview: bool = False) -> Path:
        """Subtitle path matching :meth:`output_path`."""
        return self.root / f"{self._output_stem(preview)}.srt"

    def asset(self, rel: str | Path) -> Path:
        """Resolve an asset path relative to the project root; error if it does not exist."""
        path = self.root / rel
        if not path.exists():
            raise VidgenError(f"asset not found: {rel} (looked for {path})")
        return path

    # ----- scenes and beats ------------------------------------------------------------------

    def scene(self, scene_id: str) -> SceneConfig:
        """Look up a scene by id."""
        for scene in self.config.scenes:
            if scene.id == scene_id:
                return scene
        known = ", ".join(s.id for s in self.config.scenes)
        raise VidgenError(f"unknown scene '{scene_id}'; scenes: {known}")

    def beats(self) -> Iterator[tuple[SceneConfig, BeatConfig]]:
        """Iterate over ``(scene, beat)`` pairs in video order."""
        for scene in self.config.scenes:
            for beat in scene.beats:
                yield scene, beat

    def beat(self, beat_id: str) -> BeatConfig:
        """Look up a beat by id."""
        for _, beat in self.beats():
            if beat.id == beat_id:
                return beat
        raise VidgenError(f"unknown beat '{beat_id}'")

    def estimated_duration(self) -> float:
        """Rough video length in seconds from word counts, padding and silent-scene durations."""
        narration = self.config.narration
        total = 0.0
        for scene in self.config.scenes:
            if scene.silent:
                total += scene.duration or 0.0
            for beat in scene.beats:
                total += beat.estimated_duration(narration.words_per_second) + narration.pad
        return total

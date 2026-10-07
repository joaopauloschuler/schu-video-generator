"""Project: locate and load a project's config, apply a variant, resolve paths (DESIGN.md §3)."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import yaml

from vidgen.config import BeatConfig, FormatConfig, SceneConfig, VideoConfig, VoiceConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.pronunciation import Pronunciation, load_pronunciation
from vidgen.voices import audio_fields, beat_voice_names, resolve_voice, speaker_tags

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
    """Parse a YAML or JSON config file (UTF-8, with or without a byte order mark)."""
    try:
        text = path.read_text(encoding="utf-8-sig")
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

    def __init__(
        self,
        root: Path,
        config_file: Path,
        config: VideoConfig,
        variant: str | None,
        base_config: VideoConfig | None = None,
    ) -> None:
        self.root = root
        self.config_file = config_file
        self.config = config
        self.variant = variant
        #: The config without the variant applied (equals ``config`` when there is no variant).
        self.base_config = base_config if base_config is not None else config
        #: How the narrator says terms (``pronunciation:`` + ``pronunciation_file``, DESIGN.md §45);
        #: loading reads the files, so a missing or invalid one is a :class:`VidgenError` here.
        self.pronunciation: Pronunciation = load_pronunciation(config, root)
        self._own_audio: bool | None = None
        self._voices: dict[str | None, VoiceConfig] = {}

    @classmethod
    def load(cls, path: str | Path = ".", variant: str | None = None) -> Project:
        """Load the project at ``path`` (directory or config file), optionally applying a variant.

        The variant's overrides are deep-merged onto the raw config before validation.
        """
        config_file = find_config_file(path).resolve()
        source = config_file.name
        data = read_config_file(config_file)
        base = parse_config(data, source)
        config = base
        if variant is not None:
            if variant not in base.variants:
                known = ", ".join(sorted(base.variants)) or "(none defined)"
                raise VidgenError(f"{source}: unknown variant '{variant}'; available variants: {known}")
            data = deep_merge(data, base.variants[variant])
            try:
                config = parse_config(data, f"{source} (variant '{variant}')")
            except VidgenError as exc:
                raise VidgenError(str(exc), problems=[p.in_variant(variant) for p in exc.problems]) from None
        return cls(config_file.parent, config_file, config, variant, base)

    # ----- names and paths -------------------------------------------------------------------

    @property
    def output_name(self) -> str:
        """Basename of output files: ``config.output`` or the project folder's name."""
        return self.config.output or self.root.name

    @property
    def audio_dir(self) -> Path:
        """Narration MP3s and their hash files: ``<root>/audio``, or ``<root>/audio/<variant>``
        when :attr:`has_own_audio` (the variant's voice or beat texts differ from the base)."""
        base = self.root / "audio"
        return base / self.variant if self.variant and self.has_own_audio else base

    @property
    def has_own_audio(self) -> bool:
        """True for a variant whose audio would differ from the base config's: its effective
        ``voice`` differs, or a beat id present in both configs has a different spoken text (its
        text, or the pronunciation of a term in it) or a different effective voice (``voices:``;
        a speaker's ``label`` / ``color`` do not count)."""
        if self.variant is None:
            return False
        if self._own_audio is None:
            self._own_audio = self._audio_differs()
        return self._own_audio

    def _audio_differs(self) -> bool:
        if audio_fields(self.config.voice) != audio_fields(self.base_config.voice):
            return True
        base = Project(self.root, self.config_file, self.base_config, None)
        base_spoken = base.spoken_texts()
        for beat_id, spoken in self.spoken_texts().items():
            if beat_id not in base_spoken:
                continue
            if base_spoken[beat_id] != spoken or audio_fields(base.beat_voice(beat_id)) != audio_fields(self.beat_voice(beat_id)):
                return True
        return False

    # ----- voices (DESIGN.md §46) -------------------------------------------------------------

    def voice_names(self) -> dict[str, str | None]:
        """Beat id -> name of the voice that says it (``None``: the base ``voice:``), video order."""
        return beat_voice_names(self.config)

    def voice(self, name: str | None = None) -> VoiceConfig:
        """The effective voice ``name`` (``None`` / ``default``: the base voice), see
        :func:`vidgen.voices.resolve_voice`."""
        if name not in self._voices:
            self._voices[name] = resolve_voice(self.config, name)
        return self._voices[name]

    def beat_voice(self, beat_id: str) -> VoiceConfig:
        """The effective voice of a beat."""
        names = self.voice_names()
        if beat_id not in names:
            raise VidgenError(f"unknown beat '{beat_id}'")
        return self.voice(names[beat_id])

    def speaker_tags(self, mode: str | None = None) -> dict[str, str]:
        """Beat id -> speaker label shown before it (where the speaker changes) when ``mode``
        (default ``subtitles.speakers``) shows names; empty when it is ``off``."""
        mode = self.config.subtitles.speakers if mode is None else mode
        return {} if mode in ("off", "color") else speaker_tags(self.config)

    def spoken_texts(self) -> dict[str, str]:
        """Beat id -> the text the TTS gets for it (``pronunciation`` applied), in video order."""
        say = self.pronunciation.say
        return {beat.id: say(beat.text) for _, beat in self.beats()}

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

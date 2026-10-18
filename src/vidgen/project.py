"""Project: locate and load a project's config (with its ``include:`` files), apply a variant, resolve paths (DESIGN.md §3)."""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

import yaml

from vidgen.config import BeatConfig, FormatConfig, SceneConfig, VideoConfig, VoiceConfig, draft_format, parse_config
from vidgen.emotions import Prosody, named_cues, prosody
from vidgen.errors import Problem, VidgenError
from vidgen.includes import (
    ConfigSource,
    Origin,
    after_variant,
    attributed,
    attributed_error,
    expand_character_size,
    expand_sets,
    project_relative,
    read_project_config,
)
from vidgen.kokoro_voices import voice_parts
from vidgen.pronunciation import Pronunciation, Spoken, load_pronunciation
from vidgen.translation import TranslationReport, apply_translations, read_translation_file
from vidgen.word_anchors import pin_translated_anchors, retime_project_anchors
from vidgen.voices import audio_fields, beat_voice_names, resolve_voice, speaker_tags
from vidgen.voicesounds import is_tagged_voice, voiced_spoken

CONFIG_NAMES: tuple[str, ...] = ("video.yaml", "video.yml", "video.json")
#: Folder of the deliverables (MP4, SRT, chapter list, thumbnail) without ``output_dir:`` or ``--output-dir``.
DEFAULT_OUTPUT_DIR = "output"


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


#: Environment variable naming a folder that every file a config refers to must lie in (set by
#: ``vidgen mcp`` for the commands it runs: its ``--root``; DESIGN.md §63).
CONFINE_ENV = "VIDGEN_CONFINE_ROOT"
#: Config keys (anywhere in the config, variants and sets included) whose string values are
#: files or folders of the project: scene ``path`` / ``logo``, watermark, thumbnail, stage and
#: layer ``image``, music ``source``, ``pronunciation_file``, ``translations``, ``extensions``,
#: ``output_dir``, ``soundfont``, a character's ``look.svg`` and a stage prop's ``svg``.
PATH_KEYS = frozenset({"path", "logo", "image", "source", "pronunciation_file", "translations", "extensions", "output_dir", "soundfont", "svg"})
#: Config key whose value may name a file among other words: a Kokoro ``voice`` (a blend
#: ``af_bella,own.pt``) whose parts ending in ``.pt`` are voice files Kokoro reads from the
#: current folder (DESIGN.md §68).
VOICE_FILE_KEY = "voice"


def confinement_problems(data: Any, root: Path, confine: Path) -> list[str]:
    """Config locations whose file (a :data:`PATH_KEYS` value, relative to ``root``, or a ``.pt``
    part of a ``voice``, relative to ``root`` and to the current folder) resolves outside
    ``confine`` — through an absolute path, ``..`` or a link. Values that are not paths (a
    quote's ``source`` text, a music bed's name, a voice name) resolve inside and pass."""
    confine = confine.resolve()
    problems: list[str] = []

    def check(value: str, where: str, base: Path = root) -> None:
        try:
            resolved = (base / value).resolve()
        except (OSError, ValueError):
            return
        if not resolved.is_relative_to(confine):
            problems.append(f"{where}: {value!r} is outside the allowed folder {confine}")

    def walk(node: Any, where: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                here = f"{where}.{key}" if where else str(key)
                if key == VOICE_FILE_KEY and isinstance(value, str):
                    for part in voice_parts(value):
                        if part.endswith(".pt"):
                            check(part, here)
                            check(part, here, Path.cwd())
                elif key in PATH_KEYS and isinstance(value, str):
                    check(value, here)
                elif key in PATH_KEYS and isinstance(value, list) and all(isinstance(v, str) for v in value):
                    for k, v in enumerate(value):
                        check(v, f"{here}[{k}]")
                else:
                    walk(value, here)
        elif isinstance(node, list):
            for k, value in enumerate(node):
                walk(value, f"{where}[{k}]")

    walk(data, "")
    return list(dict.fromkeys(problems))


def _confine(data: Any, root: Path, source: str) -> None:
    """Raise when :data:`CONFINE_ENV` is set and the config names a file outside that folder."""
    confine = os.environ.get(CONFINE_ENV)
    if not confine:
        return
    problems = confinement_problems(data, root, Path(confine))
    if problems:
        raise VidgenError(f"{source}: files outside the allowed folder:\n" + "\n".join(f"  {p}" for p in problems))


def _dump(config: VideoConfig) -> dict[str, Any]:
    """A raw mapping of ``config`` (for a project built from a validated config alone)."""
    return config.model_dump(mode="json", by_alias=True, exclude_none=True)


def _parsed(data: Any, where: str, origins: Mapping[str, Origin]) -> VideoConfig:
    """:func:`parse_config` with its problems placed where their values are written (DESIGN.md §69.35)."""
    try:
        return parse_config(data, where)
    except VidgenError as exc:
        raise attributed_error(exc, origins) from None


def _translated(
    data: dict[str, Any], root: Path, where: str, origins: Mapping[str, Origin]
) -> tuple[VideoConfig, tuple[dict[str, Any], VideoConfig], TranslationReport | None]:
    """The config validated from the raw ``data`` with its ``translations:`` file applied
    (DESIGN.md §54): the translated config, the source ``(data, config)`` and the report."""
    config = _parsed(data, where, origins)
    source = (data, config)
    if config.translations is None:
        return config, source, None
    rel = config.translations
    if not (root / rel).is_file():  # not written yet: every text shows its source (a validate warning)
        return config, source, TranslationReport(rel, None, missing=True)
    doc = read_translation_file(root / rel, rel)
    translated, report = apply_translations(data, doc, rel)
    pin_translated_anchors(translated, data, config)
    return _parsed(translated, f"{where} with the translations of {rel}", origins), source, report


class Project:
    """A loaded project folder. Create with :meth:`Project.load`."""

    def __init__(
        self,
        root: Path,
        config_file: Path,
        config: VideoConfig,
        variant: str | None,
        base_config: VideoConfig | None = None,
        source: tuple[dict[str, Any], VideoConfig] | None = None,
        translation: TranslationReport | None = None,
        included: ConfigSource | None = None,
        origins: Mapping[str, Origin] | None = None,
    ) -> None:
        self.root = root
        self.config_file = config_file
        self.config = config
        self.variant = variant
        #: The config without the variant applied (equals ``config`` when there is no variant).
        self.base_config = base_config if base_config is not None else config
        #: The raw config mapping (variant merged) before its ``translations:`` were applied, and
        #: its validated form (DESIGN.md §54); for a project built from a config alone, its dump.
        self.source_data, self.source_config = source if source is not None else (_dump(config), config)
        #: What applying the ``translations:`` file did (``None`` without one).
        self.translation = translation
        #: The ``include:`` files merged into the config (absolute, in merge order) and the files
        #: they name (SVGs, pictures), DESIGN.md §69.35.
        self.included_files: tuple[Path, ...] = included.files if included is not None else ()
        self.files_named_by_includes: tuple[Path, ...] = included.named_files if included is not None else ()
        #: Where values of the merged config are written (included files, sets), for :meth:`attributed`.
        self.origins: dict[str, Origin] = dict(origins or {})
        #: How the narrator says terms (``pronunciation:`` + ``pronunciation_file``, DESIGN.md §45);
        #: loading reads the files, so a missing or invalid one is a :class:`VidgenError` here.
        self.pronunciation: Pronunciation = load_pronunciation(config, root)
        self._own_audio: bool | None = None
        self._voices: dict[str | None, VoiceConfig] = {}
        #: True for :meth:`without_overlays` copies: their renders go to ``build/..._bare``.
        self.bare = False
        #: True for a draft (``vidgen render --draft``, DESIGN.md §74): every render of it goes to
        #: ``build/draft...`` in the draft format, every output name ends in ``_draft``, whatever
        #: ``preview`` the path methods are given.
        self.draft = False
        #: The ``--output-dir`` folder (absolute); it wins over ``output_dir:`` (see :attr:`output_dir`).
        self.output_dir_override: Path | None = None
        retime_project_anchors(self)   # actions at a spoken word, timed by the beats' audio (§87.2)

    @classmethod
    def load(
        cls, path: str | Path = ".", variant: str | None = None, output_dir: str | Path | None = None, draft: bool = False,
    ) -> Project:
        """Load the project at ``path`` (directory or config file), optionally applying a variant.

        The ``include:`` files are merged first and each stage's ``set:`` applied (DESIGN.md
        §69.35); the variant's overrides are deep-merged onto the raw config before validation.
        ``output_dir`` (the CLI's ``--output-dir``; relative to the current directory) overrides
        where the deliverables go (:attr:`output_dir`). ``draft``: load it as a draft (:attr:`draft`).
        """
        project = cls._load(path, variant)
        if output_dir is not None:
            project.output_dir_override = Path(output_dir).resolve()
        project.draft = draft
        return project

    @classmethod
    def _load(cls, path: str | Path, variant: str | None) -> Project:
        config_file = find_config_file(path).resolve()
        root = config_file.parent
        source = config_file.name
        confine = os.environ.get(CONFINE_ENV)
        included = read_project_config(config_file, Path(confine) if confine else None)
        data = included.data
        _confine(data, root, source)
        base_data, base_origins = expand_character_size(*expand_sets(data, included.origins))
        base, base_source, base_report = _translated(base_data, root, source, base_origins)
        if variant is None:
            return cls(root, config_file, base, None, base, base_source, base_report, included, base_origins)
        if variant not in base.variants:
            known = ", ".join(sorted(base.variants)) or "(none defined)"
            raise VidgenError(f"{source}: unknown variant '{variant}'; available variants: {known}")
        override = base.variants[variant]
        data, origins = expand_character_size(*expand_sets(deep_merge(data, override), after_variant(included.origins, data, override)))
        where = f"{source} (variant '{variant}')"
        try:
            config, merged, report = _translated(data, root, where, origins)
        except VidgenError as exc:
            raise VidgenError(str(exc), problems=[p.in_variant(variant) for p in exc.problems]) from None
        return cls(root, config_file, config, variant, base, merged, report, included, origins)

    def without_overlays(self) -> Project:
        """This project without any overlay (no video ``overlays``, every scene ``overlays:
        false``), rendering into its own folders ``build/<final|preview>[_<variant>]_bare`` (a
        frame thumbnail without overlays, DESIGN.md §53); the render worker's ``--bare``."""
        scenes = [scene.model_copy(update={"overlays": False}) for scene in self.config.scenes]
        config = self.config.model_copy(update={"overlays": [], "scenes": scenes})
        bare = Project(self.root, self.config_file, config, self.variant, self.base_config, (self.source_data, self.source_config), self.translation)
        bare.included_files, bare.files_named_by_includes, bare.origins = self.included_files, self.files_named_by_includes, self.origins
        bare.bare = True
        bare.draft = self.draft
        bare.output_dir_override = self.output_dir_override
        return bare

    @property
    def included_labels(self) -> list[str]:
        """The ``include:`` files merged into the config, relative to the project folder."""
        return [project_relative(path, self.root) for path in self.included_files]

    def attributed(self, problems: Iterable[Problem]) -> list[Problem]:
        """``problems`` placed where their values are written: an ``include:`` file (``file``),
        a set's entry (``sets.NAME...``), the scene's own entry (:func:`vidgen.includes.attributed`)."""
        return attributed(problems, self.origins)

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
        text, or the pronunciation of a term in it), a different effective voice (``voices:``;
        a speaker's ``label`` / ``color`` do not count) or a different emotion."""
        if self.variant is None:
            return False
        if self._own_audio is None:
            self._own_audio = self._audio_differs()
        return self._own_audio

    def _audio_differs(self) -> bool:
        base = Project(self.root, self.config_file, self.base_config, None)
        if audio_fields(self.voice()) != audio_fields(base.voice()):
            return True
        base_spoken = base.spoken_texts()
        for beat_id, spoken in self.spoken_texts().items():
            if beat_id not in base_spoken:
                continue
            if base_spoken[beat_id] != spoken or audio_fields(base.beat_voice(beat_id)) != audio_fields(self.beat_voice(beat_id)):
                return True
            if base.beat_emotion(beat_id) != self.beat_emotion(beat_id):
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

    def beat_emotion(self, beat_id: str) -> Prosody | None:
        """How a beat's line feels (DESIGN.md §72): its ``emotion``, else its voice's; ``None``
        when neither is set or the emotion changes nothing (``neutral``)."""
        beat = self.beat(beat_id)
        return prosody(beat.emotion if beat.emotion is not None else self.beat_voice(beat_id).emotion)

    def speaker_tags(self, mode: str | None = None) -> dict[str, str]:
        """Beat id -> speaker label shown before it (where the speaker changes) when ``mode``
        (default ``subtitles.speakers``) shows names; empty when it is ``off``."""
        mode = self.config.subtitles.speakers if mode is None else mode
        return {} if mode in ("off", "color") else speaker_tags(self.config)

    def spoken(self, beat: BeatConfig) -> Spoken:
        """What the TTS gets for ``beat``: its text with ``pronunciation`` applied, what its
        voice says for its voice sounds (:func:`vidgen.voicesounds.voiced_spoken`) and, for an
        ElevenLabs v3 voice, its emotion's audio tag before it (DESIGN.md §73)."""
        spoken = self.pronunciation.apply(beat.text)
        voice = self.beat_voice(beat.id)
        if beat.voice_sounds:
            spoken = voiced_spoken(spoken, beat.voice_sounds, voice)
        cues = named_cues(self.beat_emotion(beat.id)) if is_tagged_voice(voice) else None
        return spoken.inserted([(0, f"{cues.tag} ", "emotion")]) if cues is not None else spoken

    def spoken_texts(self) -> dict[str, str]:
        """Beat id -> the text the TTS gets for it (:meth:`spoken`), in video order."""
        return {beat.id: self.spoken(beat).spoken for _, beat in self.beats()}

    @property
    def build_dir(self) -> Path:
        """``<root>/build``: all intermediate render output."""
        return self.root / "build"

    @property
    def extension_dirs(self) -> list[Path]:
        """Configured extension directories (absolute; they may not exist)."""
        return [self.root / d for d in self.config.extensions]

    def render_dir(self, preview: bool) -> Path:
        """Per-quality build folder: ``build/<final|preview|draft>[_<variant>]`` (``draft`` for a
        :attr:`draft`; ``..._bare`` for a project :meth:`without_overlays`)."""
        name = "draft" if self.draft else "preview" if preview else "final"
        if self.variant:
            name += f"_{self.variant}"
        if self.bare:
            name += "_bare"
        return self.build_dir / name

    def render_format(self, preview: bool) -> FormatConfig:
        """Resolution/fps for a final or preview render, or a :attr:`draft`'s (:func:`draft_format`)."""
        if self.draft:
            return draft_format(self.config.format, self.config.draft)
        return self.config.preview if preview else self.config.format

    def _output_stem(self, preview: bool) -> str:
        stem = self.output_name
        if self.variant:
            stem += f"_{self.variant}"
        if self.draft:
            stem += "_draft"
        elif preview:
            stem += "_preview"
        return stem

    @property
    def output_dir(self) -> Path:
        """The folder of the deliverables (MP4, SRT, chapter list, thumbnail; DESIGN.md §3):
        ``--output-dir`` (:attr:`output_dir_override`), else ``output_dir:`` (relative to the
        project root, or absolute), else ``<root>/output``. Not created here: writers create it."""
        if self.output_dir_override is not None:
            return self.output_dir_override
        return self.root / (self.config.output_dir or DEFAULT_OUTPUT_DIR)

    def output_path(self, preview: bool = False) -> Path:
        """Final video path: ``<output>[_<variant>][_preview|_draft].mp4`` in :attr:`output_dir`."""
        return self.output_dir / f"{self._output_stem(preview)}.mp4"

    def srt_path(self, preview: bool = False) -> Path:
        """Subtitle path matching :meth:`output_path`."""
        return self.output_dir / f"{self._output_stem(preview)}.srt"

    def chapters_path(self, preview: bool = False) -> Path:
        """YouTube chapter list matching :meth:`output_path`: ``<output>[_<variant>][_preview|_draft]_chapters.txt``."""
        return self.output_dir / f"{self._output_stem(preview)}_chapters.txt"

    def thumbnail_path(self, preview: bool = False, suffix: str = ".png") -> Path:
        """Thumbnail matching :meth:`output_path`: ``<output>[_<variant>][_preview|_draft]_thumbnail.png``
        (``suffix`` ``.jpg`` for the JPEG copy)."""
        return self.output_dir / f"{self._output_stem(preview)}_thumbnail{suffix}"

    def animatic_path(self) -> Path:
        """The animatic (``vidgen animatic``, DESIGN.md §75): ``<output>[_<variant>]_animatic.mp4``
        in :attr:`output_dir`."""
        stem = self.output_name + (f"_{self.variant}" if self.variant else "")
        return self.output_dir / f"{stem}_animatic.mp4"

    def export_stem(self, preview: bool = False) -> str:
        """Start of the names of ``vidgen export`` files: ``<output>[_<variant>][_preview|_draft]``."""
        return self._output_stem(preview)

    @property
    def exports_dir(self) -> Path:
        """``<root>/exports``: GIFs and clips written by ``vidgen export`` (DESIGN.md §53)."""
        return self.root / "exports"

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
        """Rough video length in seconds from word counts, padding and silent-scene durations
        (less the crossfades, pushes and wipes, which overlap scenes)."""
        from vidgen.transitions import effective

        narration = self.config.narration
        total = 0.0
        for i, scene in enumerate(self.config.scenes):
            if scene.silent:
                total += scene.duration or 0.0
            for beat in scene.beats:
                total += beat.estimated_duration(narration.words_per_second) + narration.pad
            transition = effective(self.config, i)
            if transition.overlaps:
                total -= transition.seconds
        return total

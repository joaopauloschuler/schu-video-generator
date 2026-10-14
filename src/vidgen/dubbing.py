"""Dubbing (DESIGN.md §80): which voice says each speaker's lines in the video's language. No manim.

A video in another language is a variant with a ``language:`` and a translation file (§54). Its
voices change by these rules, applied by :func:`vidgen.voices.resolve_voice`:

- a voice's ``dub: {LANG: VOICE}`` (the base ``voice:`` or a ``voices:`` entry) names its voice
  in that language: the provider's voice name (ElevenLabs: ``voice_id``) or a mapping of voice
  keys; the most specific key matching the video's language wins (``pt-BR`` before ``pt``);
- a named voice that keeps the base voice (no ``voice`` / ``voice_id`` of its own) follows the
  base voice's dub;
- otherwise a Kokoro voice of another language than the video's (and no ``lang`` written) is
  replaced by a Kokoro voice of the video's language of the same kind (feminine / masculine, the
  voice name's second letter): the one used least so far, best grade first, never a novelty
  voice (:data:`NOVELTY_VOICES`); one source voice gets one dubbed voice everywhere;
- ElevenLabs and OpenRouter voices are kept (their voices speak many languages).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

from vidgen import kokoro_voices
from vidgen.languages import language_matches

if TYPE_CHECKING:
    from vidgen.config import DubSetting, VideoConfig
    from vidgen.project import Project

#: Voice kinds by the second letter of a Kokoro voice name (DESIGN.md §69.25 ``voice_kind``).
KOKORO_KINDS: dict[str, str] = {"f": "feminine", "m": "masculine"}
#: Kokoro voices automatic dubbing never picks (a ``dub:`` may still name them).
NOVELTY_VOICES: tuple[str, ...] = ("santa",)


@dataclass(frozen=True)
class Dub:
    """The voice of ``name`` (a ``voices:`` name, ``None``: the base voice) in the video's
    language: ``source`` is its own voice (provider voice name or id), ``target`` the one it
    speaks with here, ``fields`` the voice keys that replace its own, ``how`` ``given`` (its
    ``dub:``), ``base`` (the base voice's dub) or ``auto``; ``kind`` the source's voice kind and
    ``kind_kept`` whether the target has it."""

    name: str | None
    source: str | None
    target: str | None
    fields: Mapping[str, Any]
    how: Literal["given", "base", "auto"]
    kind: str | None = None
    kind_kept: bool = True


def dub_setting(dub: Mapping[str, DubSetting] | None, language: str | None) -> DubSetting | None:
    """The entry of ``dub`` for a video in ``language``: the most specific key that matches it
    (``pt-BR`` before ``pt``); ``None`` when none does or the video has no language."""
    if language is None or not dub:
        return None
    keys = [k for k in dub if language_matches(k, language)]
    return dub[max(keys, key=lambda k: k.count("-"))] if keys else None


def _voice_key(provider: str) -> str:
    return "voice_id" if provider == "elevenlabs" else "voice"


def dub_fields(setting: DubSetting, provider: str) -> dict[str, Any]:
    """The voice keys a ``dub:`` entry sets: a string is the provider's voice (``voice_id`` for
    ElevenLabs, else ``voice``); a mapping its keys given."""
    if isinstance(setting, str):
        return {_voice_key(provider): setting}
    return setting.model_dump(exclude_none=True)


def voice_kind(voice: str | None) -> str | None:
    """``feminine`` / ``masculine`` for a Kokoro voice name (a blend: its first voice), else ``None``."""
    parts = kokoro_voices.voice_parts(voice or "")
    return KOKORO_KINDS.get(parts[0][1:2]) if parts and kokoro_voices.lang_of_voice(parts[0]) else None


def _same_language(lang: str, other: str) -> bool:
    return lang == other or {lang, other} <= kokoro_voices.TIMED_LANGS   # American and British English


def _pick(lang: str, kind: str | None, used: Counter[str]) -> tuple[str, bool]:
    """The Kokoro voice of ``lang`` of ``kind`` used least so far (best grade first) and whether
    it has that kind (a language without one: any of its voices)."""
    listed = [v for v in kokoro_voices.voices_of(lang) if not any(n in v for n in NOVELTY_VOICES)] or kokoro_voices.voices_of(lang)
    fitting = [v for v in listed if KOKORO_KINDS.get(v[1:2]) == kind]
    pool = fitting or listed
    best = min(range(len(pool)), key=lambda k: (used[pool[k]], k))
    return pool[best], bool(fitting) or kind is None


def voice_dubs(config: VideoConfig) -> dict[str | None, Dub]:
    """The voices of ``config`` that speak with another voice in its ``language`` (the module
    doc's rules): voice name (``None``: the base voice) -> :class:`Dub`. Empty without a language."""
    language = config.language
    if language is None:
        return {}
    provider = config.voice.provider
    key = _voice_key(provider)
    base_source = getattr(config.voice, key, None)
    out: dict[str | None, Dub] = {}
    pending: list[tuple[str | None, str]] = []   # (name, Kokoro source voice) to pick automatically
    base_setting = dub_setting(config.voice.dub, language)
    if base_setting is not None:
        fields = dub_fields(base_setting, provider)
        out[None] = Dub(None, base_source, fields.get(key, base_source), fields, "given", voice_kind(base_source))
    elif provider == "kokoro" and config.voice.lang is None:
        pending.append((None, base_source or ""))
    for name, entry in config.voices.items():
        own_source = getattr(entry, key, None)
        setting = dub_setting(entry.dub, language)
        if setting is not None:
            fields = dub_fields(setting, provider)
            source = own_source or base_source
            out[name] = Dub(name, source, fields.get(key, source), fields, "given", voice_kind(source))
        elif own_source is None and entry.lang is None:
            pending.append((name, ""))   # follows the base voice
        elif provider == "kokoro" and entry.lang is None and own_source is not None:
            pending.append((name, own_source))
    used: Counter[str] = Counter(d.target for d in out.values() if d.target)
    target_lang = kokoro_voices.lang_of_language(language) if provider == "kokoro" else None
    chosen: dict[str, tuple[str, bool]] = {}
    for name, source in pending:
        if not source:   # a named voice keeping the base voice
            if None in out:
                out[name] = replace(out[None], name=name, how="base" if out[None].how == "given" else out[None].how)
            continue
        lang = kokoro_voices.lang_of_voice(source)
        if target_lang is None or lang is None or _same_language(lang, target_lang):
            continue
        kind = voice_kind(source)
        if source not in chosen:
            chosen[source] = _pick(target_lang, kind, used)
            used[chosen[source][0]] += 1
        target, kept = chosen[source]
        out[name] = Dub(name, source, target, {"voice": target}, "auto", kind, kept)
    return {name: out[name] for name in [None, *config.voices] if name in out}


def config_dub_warnings(config: VideoConfig, used_names: list[str | None]) -> list[str]:
    """What ``vidgen validate`` warns about the dubbing of ``config`` (DESIGN.md §80): a voice
    dubbed with a voice of another kind, and voices of ``used_names`` that differ in their own
    language but speak with one voice in this one."""
    from vidgen.voices import resolve_voice

    dubs = voice_dubs(config)
    if not dubs:
        return []
    language = config.language
    out = []

    def label(name: str | None) -> str:
        return "the base voice" if name is None else f"voices.{name}"

    for dub in dubs.values():
        if not dub.kind_kept:
            out.append(
                f"dub ({language}): {label(dub.name)} ({dub.source}, {dub.kind}) speaks with {dub.target}: Kokoro has no "
                f"{dub.kind} voice of {kokoro_voices.lang_name(kokoro_voices.lang_of_voice(dub.target))}; give it a dub: "
                f"{{{language}: ...}}"
            )
    key = _voice_key(config.voice.provider)
    speakers: dict[str, list[tuple[str | None, str | None]]] = {}
    for name in dict.fromkeys(used_names):
        voice = resolve_voice(config, name)
        target = getattr(voice, key, None)
        source = dubs[name].source if name in dubs else target
        if target is not None:
            speakers.setdefault(target, []).append((name, source))
    for target, names in speakers.items():
        sources = {source for _, source in names}
        if len(sources) > 1 and any(name in dubs for name, _ in names):
            who = " and ".join(f"{label(name)} ({source})" for name, source in names)
            blend = f", or a blend such as {target}+{names[-1][1]}:0.3" if config.voice.provider == "kokoro" else ""
            out.append(f"dub ({language}): {who} speak with {target} here; give one a dub: {{{language}: ...}} (another voice{blend})")
    return out


def dub_warnings(project: Project) -> list[str]:
    """:func:`config_dub_warnings` for the voices the project's beats use."""
    return config_dub_warnings(project.config, list(project.voice_names().values()))


def dub_summary(project: Project) -> str | None:
    """``default bf_emma -> pf_dora (auto), fen_voice af_heart -> pf_dora (given)`` for a project
    whose voices are dubbed, else ``None``."""
    dubs = voice_dubs(project.config)
    if not dubs:
        return None
    parts = [f"{name or 'default'} {d.source or '(default)'} -> {d.target} ({d.how})" for name, d in dubs.items()]
    return ", ".join(parts)


def language_variants(project: Project) -> list[tuple[str, str | None]]:
    """``(variant, language)`` of every variant of ``project`` (the base config) whose
    ``language`` differs from the base config's, in config order: what ``--all-languages``
    makes besides the base config."""
    from vidgen.project import Project as _Project

    out = []
    for name in project.config.variants:
        language = _Project.load(project.config_file, variant=name).config.language
        if language != project.config.language:
            out.append((name, language))
    return out

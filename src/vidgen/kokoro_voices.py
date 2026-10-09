"""Kokoro-82M's languages and voices (DESIGN.md §68): no PyTorch, no ``kokoro`` package needed.

Kokoro names a language with one letter (``voice.lang``) and every voice starts with its
language's letter, then ``f`` / ``m`` (female / male): ``af_heart`` is American English,
``pf_dora`` Brazilian Portuguese. The bundled list ``data/kokoro/voices.json`` (dated) is the
model repository's ``voices/`` folder; ``vidgen validate`` checks names against it.

How the language is chosen when ``voice.lang`` is not given: the first letter of ``voice``, else
the video's ``language:`` (:data:`LANGUAGE_TO_LANG`; no ``language:``: American English). The
voice, when not given, is the language's best-graded voice (``default_voice``).
"""

from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any

#: Video language (BCP-47 language subtag) -> Kokoro language; ``en-GB`` is British English.
LANGUAGE_TO_LANG: dict[str, str] = {"en": "a", "es": "e", "fr": "f", "hi": "h", "it": "i", "ja": "j", "pt": "p", "zh": "z"}
#: English regions read with British pronunciation (lang ``b``).
BRITISH_REGIONS: frozenset[str] = frozenset({"GB", "UK", "IE", "AU", "NZ"})
#: Languages whose pipeline yields word timings (misaki's English tokens).
TIMED_LANGS: frozenset[str] = frozenset({"a", "b"})
#: How Kokoro voice names look: language letter, f / m, underscore, name.
_VOICE_NAME = re.compile(r"^[a-z][fm]_\w+$")


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    """The bundled list: ``{date, source, repo, weights, weights_bytes, voice_bytes, langs:
    {letter: {name, default_voice, g2p, espeak}}, voices: {name: grade | null}}``."""
    text = resources.files("vidgen").joinpath("data/kokoro/voices.json").read_text(encoding="utf-8")
    return json.loads(text)


def langs() -> dict[str, dict[str, Any]]:
    """Language letter -> ``{name, default_voice, g2p, espeak}``."""
    return catalog()["langs"]


def lang_name(lang: str | None) -> str:
    """``American English`` for ``a`` (the letter itself when unknown)."""
    entry = langs().get(lang or "")
    return str(entry["name"]) if entry else str(lang)


def describe_langs() -> str:
    """``a American English, b British English, ...``."""
    return ", ".join(f"{letter} {entry['name']}" for letter, entry in langs().items())


def voice_parts(voice: str) -> list[str]:
    """The voices of a blend (``af_bella,af_heart``: Kokoro averages them), stripped."""
    return [part.strip() for part in voice.split(",") if part.strip()]


def lang_of_voice(voice: str | None) -> str | None:
    """The language letter a voice name starts with (its first voice for a blend), ``None`` when
    it names no Kokoro language (a ``.pt`` file, an unknown name)."""
    parts = voice_parts(voice or "")
    if not parts or not _VOICE_NAME.match(parts[0]):
        return None
    letter = parts[0][:1]
    return letter if letter in langs() else None


def lang_of_language(language: str | None) -> str | None:
    """The Kokoro language of a video language (``None``: English, ``a``); ``None`` when Kokoro
    has no voice for it."""
    if language is None:
        return "a"
    parts = language.split("-")
    primary = parts[0].lower()
    if primary == "en" and any(p.upper() in BRITISH_REGIONS for p in parts[1:]):
        return "b"
    return LANGUAGE_TO_LANG.get(primary)


def resolve(voice: str | None, lang: str | None, language: str | None) -> tuple[str | None, str | None]:
    """The effective ``(voice, lang)``: ``lang`` as given, else the voice's first letter, else
    the video's language; ``voice`` as given, else the language's default voice. ``lang`` is
    ``None`` only when none of these names a Kokoro language (a config error, see
    :func:`vidgen.voices.voice_provider_problems`)."""
    lang = lang or lang_of_voice(voice) or lang_of_language(language)
    if voice is None and lang is not None:
        voice = str(langs()[lang]["default_voice"])
    return voice, lang


def voices_of(lang: str | None) -> list[str]:
    """The listed voices of a language, best grade first."""
    order = ["A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F+", "F"]
    graded = [(name, grade) for name, grade in catalog()["voices"].items() if lang is None or name.startswith(lang)]
    return [name for name, grade in sorted(graded, key=lambda v: order.index(v[1]) if v[1] in order else len(order))]


def voice_warnings(voice: str | None, lang: str | None, language: str | None, timestamps: bool, where: str) -> list[str]:
    """What ``vidgen validate`` says about a resolved Kokoro voice without the network: a voice
    not in the bundled list, a voice of another language than ``lang``, a ``lang`` that is not
    the video's language, ``timestamps`` with a language that has no word timings."""
    out: list[str] = []
    known = catalog()["voices"]
    date = catalog()["date"]
    for part in voice_parts(voice or ""):
        if part.endswith(".pt"):
            continue  # a voice file of the user's own
        if part not in known:
            close = difflib.get_close_matches(part, list(known), n=1, cutoff=0.6)
            hint = f"did you mean {close[0]}? " if close else ""
            shown = ", ".join(voices_of(lang)[:6])
            out.append(
                f"{where}.voice: '{part}' is not among Kokoro-82M's voices of {date} ({hint}voices of lang {lang}: {shown}; "
                "all: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)"
            )
            continue
        own = part[:1]
        if lang is not None and own != lang:
            out.append(
                f"{where}.voice: '{part}' is a {lang_name(own)} voice but lang is {lang} ({lang_name(lang)}): the text is "
                f"read with {lang_name(lang)} pronunciation; set lang: {own} or a voice starting with {lang}"
            )
    wanted = lang_of_language(language) if language is not None else None
    if lang is not None and wanted is not None and wanted != lang and not {lang, wanted} <= TIMED_LANGS:
        out.append(
            f"{where}.lang: {lang} ({lang_name(lang)}) but the video's language is {language} (Kokoro lang {wanted}, "
            f"{lang_name(wanted)})"
        )
    if timestamps and lang is not None and lang not in TIMED_LANGS:
        out.append(f"{where}.timestamps: Kokoro gives word timings for English only (lang a, b); captions use estimated timings")
    return out

"""Lip sync: a beat's viseme track (DESIGN.md §69.4). No manim here.

A *viseme* is the mouth shape of a group of speech sounds (:data:`VISEMES`). A beat's track is
a list of :class:`VisemeCue` (start, end, viseme) over its audio, from 0 (the audio's start) to
its length. The phonemes come from Kokoro's own G2P when Kokoro voiced the beat
(:func:`timed_phoneme_units`, captured by ``vidgen tts``), else from the spoken text
(:func:`text_phonemes`: misaki or espeak-ng when installed, a letter-based fallback otherwise),
timed with the word timings captions use (:func:`vidgen.speech.beat_word_times`). Cues shorter
than :data:`MIN_CUE_SECONDS` are merged into a neighbour (:func:`merge_short_cues`) so the
mouth does not flicker.

``vidgen tts`` stores a track as ``<audio_dir>/<beat_id>.visemes.json`` with the sha1 of the
MP3 and the spoken text it belongs to (:func:`write_visemes`); :func:`beat_visemes` reads it
back while it matches, else builds one from the text (not stored).
"""

from __future__ import annotations

import bisect
import importlib.util
import json
import shutil
import subprocess
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from vidgen.errors import VidgenError
from vidgen.fileio import write_text_atomic
from vidgen.languages import language_rules, primary_language
from vidgen.speech import audio_digest, audio_duration, beat_word_times, read_alignment

if TYPE_CHECKING:
    from vidgen.project import Project

#: The mouth shapes of speech: ``rest`` (closed, silence), ``A`` (also I: open), ``E`` (wide;
#: also most consonants: t, d, s, k, n, r...), ``O`` (round), ``U`` (small round), ``M`` (M, B,
#: P: lips closed), ``F`` (F, V: lip under the teeth), ``L`` (also TH: tongue up), ``W`` (W, Q:
#: puckered).
VISEMES: tuple[str, ...] = ("rest", "A", "E", "O", "U", "M", "F", "L", "W")
REST = "rest"
#: The mouth shapes that show each viseme, in order of preference: the first one a character has
#: is shown; none (and ``rest``) shows the mouth's rest shape at the time lip sync starts.
VISEME_SHAPES: dict[str, tuple[str, ...]] = {
    "rest": (),
    "A": ("A", "open"),
    "E": ("E", "A", "open"),
    "O": ("O", "A", "open"),
    "U": ("U", "O", "W", "open"),
    "M": ("M",),
    "F": ("F", "E", "M"),
    "L": ("L", "E", "A", "open"),
    "W": ("W", "U", "O", "open"),
}
#: A cue shorter than this is merged into its longer neighbour (2 frames at 30 fps).
MIN_CUE_SECONDS = 0.07
#: Version of the ``.visemes.json`` format.
VISEME_VERSION = 1

_V = {name: (name,) for name in VISEMES}
#: IPA phonemes (espeak-ng, misaki) and misaki's own diphthong letters -> visemes; a diphthong
#: gives two. Characters not listed (stress and length marks, h, the glottal stop, tone digits,
#: punctuation) take no time of their own.
PHONEME_VISEMES: dict[str, tuple[str, ...]] = {
    **dict.fromkeys("aɑæʌɐəᵊ", _V["A"]),
    **dict.fromkeys("eɛiɪᵻɨɜɚɝ", _V["E"]),
    **dict.fromkeys("oɔɒɵøœ", _V["O"]),
    **dict.fromkeys("uʊyʏɯʉ", _V["U"]),
    # misaki: A = eɪ, I = aɪ, O = oʊ, Q = əʊ, W = aʊ, Y = ɔɪ
    "A": ("E",), "I": ("A", "E"), "O": ("O", "U"), "Q": ("O", "U"), "W": ("A", "U"), "Y": ("O", "E"),
    **dict.fromkeys("mbpβ", _V["M"]),
    **dict.fromkeys("fvɱ", _V["F"]),
    **dict.fromkeys("lɫθðɬʎ", _V["L"]),
    **dict.fromkeys("wʍɥ", _V["W"]),
    **dict.fromkeys("tdnszkgɡŋrɹɾɻʁʀʃʒʧʤjcɟxɣçɲɳʂʐɕʑʝ", _V["E"]),
}
VOWEL_PHONEMES = frozenset("aɑæʌɐəᵊeɛiɪᵻɨɜɚɝoɔɒɵøœuʊyʏɯʉAIOQWY")
#: Letter-based fallback: digraphs first (an empty tuple: silent), then single letters.
LETTER_DIGRAPHS: dict[str, tuple[str, ...]] = {
    "th": ("L",), "ph": ("F",), "sh": ("E",), "ch": ("E",), "wh": ("W",), "qu": ("W",),
    "oo": ("U",), "ee": ("E",), "ck": ("E",), "ng": ("E",), "gh": (),
}
LETTER_VISEMES: dict[str, tuple[str, ...]] = {
    "a": ("A",), "e": ("E",), "i": ("E",), "y": ("E",), "o": ("O",), "u": ("U",),
    **dict.fromkeys("mbp", _V["M"]), **dict.fromkeys("fv", _V["F"]), "l": ("L",), **dict.fromkeys("wq", _V["W"]),
    "h": (),
}
VOWEL_LETTERS = frozenset("aeiouy")
#: Relative length of a vowel, a consonant and a word gap inside a word's or token's time.
VOWEL_WEIGHT, CONSONANT_WEIGHT, GAP_WEIGHT = 2.0, 1.0, 0.5

#: Where a track's phonemes came from.
SOURCES: tuple[str, ...] = ("kokoro", "misaki", "espeak", "letters")
#: How a track was timed: Kokoro's token times, the stored alignment, the estimate within the
#: MP3's speech, or the estimate over the beat (no MP3).
TIMINGS: tuple[str, ...] = ("kokoro", "alignment", "speech", "estimate")

Unit = tuple[str, float]  # (viseme, weight)


class VisemeCue(NamedTuple):
    """One mouth shape of a track: ``viseme`` from ``start`` to ``end`` (seconds into the beat's audio)."""

    start: float
    end: float
    viseme: str


@dataclass(frozen=True)
class VisemeTrack:
    """A beat's visemes: contiguous cues from 0 to the beat's length; ``source`` / ``timing``
    say where the phonemes and the times came from (:data:`SOURCES`, :data:`TIMINGS`)."""

    cues: tuple[VisemeCue, ...]
    source: str = "letters"
    timing: str = "estimate"

    @property
    def duration(self) -> float:
        """The end of the last cue (seconds)."""
        return self.cues[-1].end if self.cues else 0.0

    def at(self, seconds: float) -> str:
        """The viseme at ``seconds`` into the beat (``rest`` before 0 and after the end)."""
        if not self.cues or seconds < 0 or seconds >= self.duration:
            return REST
        k = bisect.bisect_right([c.start for c in self.cues], seconds) - 1
        return self.cues[max(k, 0)].viseme

    def until(self, seconds: float) -> VisemeTrack:
        """The track cut at ``seconds`` (an interrupted line, DESIGN.md §69.34): ``rest`` from then on."""
        cues = tuple(c._replace(end=min(c.end, seconds)) for c in self.cues if c.start < seconds)
        return VisemeTrack(cues, self.source, self.timing)


# ----- phonemes and letters -> visemes ------------------------------------------------------------


def phoneme_units(phonemes: str) -> list[Unit]:
    """The visemes of a phoneme string with their weights; a space is a short ``rest``."""
    out: list[Unit] = []
    for ch in phonemes:
        if ch.isspace():
            out.append((REST, GAP_WEIGHT))
            continue
        weight = VOWEL_WEIGHT if ch in VOWEL_PHONEMES else CONSONANT_WEIGHT
        visemes = PHONEME_VISEMES.get(ch, ())
        out.extend((v, weight / len(visemes)) for v in visemes)
    return out


def letter_units(word: str, language: str | None = None) -> list[Unit]:
    """The visemes of a written word (the fallback without a G2P): accents dropped, digraphs
    (:data:`LETTER_DIGRAPHS`) then letters (:data:`LETTER_VISEMES`; other Latin consonants
    ``E``, other letters and digits ``A``), a silent final ``e`` dropped where the language has one."""
    letters = "".join(ch for ch in word.lower() if ch.isalnum())
    if language_rules(language).silent_final_e and len(letters) > 2 and letters.endswith("e") and set(letters[:-1]) & VOWEL_LETTERS:
        letters = letters[:-1]  # before the accents go: a final "é" is said
    letters = "".join(ch for ch in unicodedata.normalize("NFD", letters) if unicodedata.category(ch) != "Mn")
    out: list[Unit] = []
    k = 0
    while k < len(letters):
        pair = letters[k : k + 2]
        if pair in LETTER_DIGRAPHS:
            weight = VOWEL_WEIGHT if set(pair) <= VOWEL_LETTERS else CONSONANT_WEIGHT
            out.extend((v, weight) for v in LETTER_DIGRAPHS[pair])
            k += 2
            continue
        ch = letters[k]
        if ch in LETTER_VISEMES:
            visemes = LETTER_VISEMES[ch]
        elif "a" <= ch <= "z":
            visemes = ("E",)
        else:
            visemes = ("A",)
        weight = VOWEL_WEIGHT if ch in VOWEL_LETTERS or not ("a" <= ch <= "z") else CONSONANT_WEIGHT
        out.extend((v, weight) for v in visemes)
        k += 1
    return out


# ----- phonemes from the text ---------------------------------------------------------------------

Phonemizer = Callable[[str], "str | None"]


def _available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _is_english(language: str | None) -> bool:
    return primary_language(language) == "en"


def espeak_voice(language: str | None) -> str:
    """The espeak-ng voice of a BCP-47 tag: lower case, ``en`` -> ``en-us``."""
    tag = (language or "en").lower().replace("_", "-")
    return "en-us" if tag == "en" else tag


def _misaki(language: str | None) -> Phonemizer | None:
    """misaki's G2P: English with spaCy's small model (when installed: misaki would otherwise
    pip-install it), other languages through misaki's espeak-ng wrapper."""
    if not _available("misaki"):
        return None
    if _is_english(language):
        if not _available("en_core_web_sm"):
            return None
        from misaki import en  # type: ignore[import-not-found]

        g2p = en.G2P(trf=False, british=espeak_voice(language) in ("en-gb", "en-ie", "en-au", "en-nz"), fallback=None)
    else:
        if not _available("espeakng_loader"):
            return None
        from misaki import espeak  # type: ignore[import-not-found]

        g2p = espeak.EspeakG2P(language=espeak_voice(language))
    return lambda word: str(g2p(word)[0] or "") or None


def _espeak_ng(language: str | None) -> Phonemizer | None:
    """The ``espeak-ng`` program on ``PATH`` (IPA output)."""
    program = shutil.which("espeak-ng")
    if program is None:
        return None
    voice = espeak_voice(language)

    def say(word: str) -> str | None:
        done = subprocess.run([program, "-q", "--ipa", "-v", voice, word], capture_output=True, check=True, timeout=10)
        return done.stdout.decode("utf-8", errors="replace").strip() or None

    return say


#: G2P back ends in order of preference (name, factory); each factory returns ``None`` when
#: its package or program is missing.
G2P_BACKENDS: tuple[tuple[str, Callable[[str | None], Phonemizer | None]], ...] = (("misaki", _misaki), ("espeak", _espeak_ng))


@lru_cache(maxsize=16)
def text_g2p(language: str | None) -> tuple[str, Phonemizer] | None:
    """The first G2P back end installed here for ``language`` (``(name, word -> phonemes)``), or
    ``None`` (then letters are used). A back end that fails to load is skipped."""
    for name, factory in G2P_BACKENDS:
        try:
            phonemizer = factory(language)
        except Exception:  # noqa: BLE001 - an optional package that fails to load is not used
            phonemizer = None
        if phonemizer is not None:
            return name, phonemizer
    return None


def text_phonemes(words: Sequence[str], language: str | None = None) -> tuple[str, list[list[Unit]]]:
    """The visemes of each word and the source used (:data:`SOURCES`): the installed G2P's
    phonemes, or the letters (for every word when none is installed, and for a word it cannot
    voice)."""
    g2p = text_g2p(language)
    out: list[list[Unit]] = []
    for word in words:
        units: list[Unit] = []
        if g2p is not None:
            try:
                units = phoneme_units((g2p[1](word) or "").strip())
            except Exception:  # noqa: BLE001 - one word the G2P cannot voice falls back to letters
                units = []
        out.append(units or letter_units(word, language))
    return (g2p[0] if g2p is not None else "letters"), out


def timed_phoneme_units(timed: Sequence[tuple[str, float, float]]) -> list[tuple[list[Unit], float, float]]:
    """``(phonemes, start, end)`` (Kokoro's tokens, or a whole chunk) -> units with their times."""
    return [(phoneme_units(phonemes.strip()), start, end) for phonemes, start, end in timed]


# ----- cues ----------------------------------------------------------------------------------------


def _joined(cues: Sequence[VisemeCue]) -> list[VisemeCue]:
    out: list[VisemeCue] = []
    for cue in cues:
        if out and out[-1].viseme == cue.viseme:
            out[-1] = out[-1]._replace(end=cue.end)
        else:
            out.append(cue)
    return out


def _length(cue: VisemeCue) -> float:
    return cue.end - cue.start


def merge_short_cues(cues: Sequence[VisemeCue], min_seconds: float = MIN_CUE_SECONDS) -> list[VisemeCue]:
    """Neighbouring cues of one viseme joined; then, shortest first, every cue shorter than
    ``min_seconds`` is given to its longer neighbour (the earlier one on a tie), until none is
    left or one cue remains. A short ``M`` (closed lips: a missing closure shows) is lengthened to
    ``min_seconds`` from its longer neighbour instead, when that one stays long enough. Cues must
    be contiguous; the result covers the same time."""
    out = _joined(cues)
    while len(out) > 1:
        k = min(range(len(out)), key=lambda i: (_length(out[i]), i))
        cue = out[k]
        if _length(cue) >= min_seconds - 1e-9:
            break
        before = out[k - 1] if k > 0 else None
        after = out[k + 1] if k + 1 < len(out) else None
        to_before = after is None or (before is not None and _length(before) >= _length(after))
        longer = before if to_before else after
        need = min_seconds - _length(cue)
        if cue.viseme == "M" and longer is not None and _length(longer) - need >= min_seconds:
            if to_before:
                out[k - 1], out[k] = longer._replace(end=cue.start - need), cue._replace(start=cue.start - need)
            else:
                out[k], out[k + 1] = cue._replace(end=cue.end + need), longer._replace(start=cue.end + need)
            continue
        if to_before:
            out[k - 1] = before._replace(end=cue.end)  # type: ignore[union-attr]
        else:
            out[k + 1] = after._replace(start=cue.start)  # type: ignore[union-attr]
        del out[k]
        out = _joined(out)
    return out


def cues_from_units(timed: Sequence[tuple[Sequence[Unit], float, float]], duration: float, min_seconds: float = MIN_CUE_SECONDS) -> list[VisemeCue]:
    """A track's cues: each entry's units spread over its time by weight, ``rest`` between the
    entries and around them (0 .. ``duration``), short cues merged (:func:`merge_short_cues`)."""
    raw: list[VisemeCue] = []
    for units, start, end in timed:
        total = sum(weight for _, weight in units)
        if total <= 0 or end <= start:
            continue
        t = start
        for viseme, weight in units:
            step = (end - start) * weight / total
            raw.append(VisemeCue(t, t + step, viseme))
            t += step
    out: list[VisemeCue] = []
    t = 0.0
    for cue in sorted(raw, key=lambda c: c.start):
        start, end = max(cue.start, t), min(cue.end, duration)
        if start > t:
            out.append(VisemeCue(t, start, REST))
        if end > start:
            out.append(VisemeCue(start, end, cue.viseme))
            t = end
    if duration > t:
        out.append(VisemeCue(t, duration, REST))
    return merge_short_cues(out, min_seconds)


# ----- a beat's track ------------------------------------------------------------------------------


def _timing_of(audio_dir: Path | None, beat_id: str, text: str) -> str:
    if audio_dir is None or not (audio_dir / f"{beat_id}.mp3").is_file():
        return "estimate"
    return "alignment" if read_alignment(audio_dir, beat_id, text) is not None else "speech"


def build_visemes(
    audio_dir: Path | None,
    beat_id: str,
    text: str,
    duration: float,
    language: str | None = None,
    phonemes: Sequence[tuple[str, float, float]] | None = None,
) -> VisemeTrack:
    """The track of a beat whose spoken text is ``text`` and whose audio lasts ``duration``:
    from Kokoro's timed ``phonemes`` when given, else from the text's phonemes
    (:func:`text_phonemes`) timed like its captions' words (the stored alignment, else the
    estimate within the MP3's speech, else over ``duration``)."""
    if phonemes:
        cues = cues_from_units(timed_phoneme_units(phonemes), duration)
        return VisemeTrack(tuple(cues), "kokoro", "kokoro")
    words = beat_word_times(audio_dir, beat_id, text, 0.0, duration, language=language)
    source, units = text_phonemes([w.text for w in words], language)
    cues = cues_from_units([(u, w.start, w.end) for u, w in zip(units, words)], duration)
    return VisemeTrack(tuple(cues), source, _timing_of(audio_dir, beat_id, text))


def visemes_path(audio_dir: Path, beat_id: str) -> Path:
    """``<audio_dir>/<beat_id>.visemes.json``: a beat's stored viseme track."""
    return audio_dir / f"{beat_id}.visemes.json"


def write_visemes(audio_dir: Path, beat_id: str, text: str, audio: bytes, track: VisemeTrack) -> Path:
    """Store ``track`` for the MP3 ``audio`` of the spoken text ``text``; returns the file."""
    doc = {
        "version": VISEME_VERSION,
        "text": text,
        "audio_sha1": audio_digest(audio),
        "source": track.source,
        "timing": track.timing,
        "cues": [[round(c.start, 4), round(c.end, 4), c.viseme] for c in track.cues],
    }
    path = visemes_path(audio_dir, beat_id)
    write_text_atomic(path, json.dumps(doc, ensure_ascii=False))
    return path


def _track_of(doc: Any) -> VisemeTrack | None:
    if not isinstance(doc, Mapping) or doc.get("version") != VISEME_VERSION:
        return None
    try:
        cues = tuple(VisemeCue(float(s), float(e), str(v)) for s, e, v in doc["cues"])
    except (KeyError, TypeError, ValueError):
        return None
    if any(c.viseme not in VISEMES for c in cues):
        return None
    return VisemeTrack(cues, str(doc.get("source", "letters")), str(doc.get("timing", "estimate")))


@lru_cache(maxsize=512)
def _read_visemes(path: Path, mtime_ns: int, mp3: Path, mp3_mtime_ns: int) -> tuple[str, VisemeTrack] | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        digest = audio_digest(mp3.read_bytes())
    except (OSError, ValueError):
        return None
    track = _track_of(doc)
    if track is None or not isinstance(doc.get("text"), str) or doc.get("audio_sha1") != digest:
        return None
    return doc["text"], track


def read_visemes(audio_dir: Path, beat_id: str, text: str) -> VisemeTrack | None:
    """The stored track of a beat when it belongs to its current MP3 and spoken ``text``, else ``None``."""
    path, mp3 = visemes_path(audio_dir, beat_id), audio_dir / f"{beat_id}.mp3"
    try:
        stamp, mp3_stamp = path.stat().st_mtime_ns, mp3.stat().st_mtime_ns
    except OSError:
        return None
    found = _read_visemes(path, stamp, mp3, mp3_stamp)
    return found[1] if found is not None and found[0] == text else None


def write_beat_visemes(
    audio_dir: Path, beat_id: str, text: str, audio: bytes, language: str | None = None,
    phonemes: Sequence[tuple[str, float, float]] | None = None,
) -> Path:
    """Build and store the track of a beat whose MP3 (``audio``) is already in ``audio_dir``
    (``vidgen tts`` calls it after writing the MP3 and its alignment)."""
    duration = audio_duration(audio_dir / f"{beat_id}.mp3")
    track = build_visemes(audio_dir, beat_id, text, duration, language, phonemes)
    return write_visemes(audio_dir, beat_id, text, audio, track)


def with_cues(track: VisemeTrack, spans: Sequence[tuple[float, float, str]]) -> VisemeTrack:
    """``track`` with ``(start, end, viseme)`` spans laid over it (the generated voice sounds of
    a beat, DESIGN.md §69.33): cut to 0 and on, past its end with ``rest`` before them."""
    cues = list(track.cues)
    for start, end, viseme in spans:
        start = max(start, 0.0)
        if end <= start:
            continue
        kept: list[VisemeCue] = []
        for cue in cues:
            if cue.start < start:
                kept.append(cue._replace(end=min(cue.end, start)))
            if cue.end > end:
                kept.append(cue._replace(start=max(cue.start, end)))
        last = max((c.end for c in kept), default=0.0)
        if start > last:   # past the track's end
            kept.append(VisemeCue(last, start, REST))
        kept.append(VisemeCue(start, end, viseme))
        cues = sorted(kept, key=lambda c: c.start)
    return VisemeTrack(tuple(cues), track.source, track.timing)


def beat_visemes(project: Project, beat_id: str, duration: float | None = None) -> VisemeTrack:
    """The viseme track of a beat of ``project``: the stored one while it matches the beat's MP3
    and spoken text, else built from the spoken text (not stored); the mouth shapes of its
    generated voice sounds over it (:func:`with_cues`). ``duration`` (seconds) is the beat's
    length; default: its MP3's length, else the word-count estimate."""
    from vidgen.voicesounds import VOICE_SOUNDS, beat_sound_spans

    spoken = project.spoken_texts()
    if beat_id not in spoken:
        raise VidgenError(f"unknown beat '{beat_id}'")
    beat = project.beat(beat_id)
    audio_dir = project.audio_dir
    track = read_visemes(audio_dir, beat_id, spoken[beat_id])
    if track is not None and not beat.voice_sounds:
        return track
    if duration is None:
        mp3 = audio_dir / f"{beat_id}.mp3"
        duration = audio_duration(mp3) if mp3.is_file() else beat.estimated_duration(project.config.narration.words_per_second)
    if track is None:
        track = build_visemes(audio_dir, beat_id, spoken[beat_id], duration, project.config.language)
    spans = [(s.start, s.end, VOICE_SOUNDS[s.kind].viseme) for s in beat_sound_spans(project, beat, duration) if s.generated]
    return with_cues(track, spans) if spans else track

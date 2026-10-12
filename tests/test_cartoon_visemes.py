"""Step 71: lip sync (viseme tracks, DESIGN.md §69.4).

No TTS call: tracks are built from stored alignments, estimates, and fake providers; misaki and
espeak-ng are mocked (the tests pass without them: the letter-based fallback)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_scene import make_tone
from vidgen.cartoon import visemes as vz
from vidgen.cartoon.character import Character, CharacterPart
from vidgen.cartoon.visemes import VISEME_SHAPES, VISEMES, VisemeCue, VisemeTrack, merge_short_cues
from vidgen.config import CharacterLook, VoiceConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.speech import write_alignment

PIP = [{"name": "pip"}]


@pytest.fixture(autouse=True)
def _no_installed_g2p(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts from the letter fallback unless it installs a fake G2P."""
    monkeypatch.setattr(vz, "G2P_BACKENDS", ())
    vz.text_g2p.cache_clear()
    yield
    vz.text_g2p.cache_clear()


def cue(start: float, end: float, viseme: str) -> VisemeCue:
    return VisemeCue(start, end, viseme)


def contiguous(cues: list[VisemeCue], duration: float) -> bool:
    return cues[0].start == 0 and cues[-1].end == pytest.approx(duration) and all(a.end == pytest.approx(b.start) for a, b in zip(cues, cues[1:]))


# ----- the mapping table ---------------------------------------------------------------------------


def test_tables_name_only_known_visemes() -> None:
    assert VISEMES == ("rest", "A", "E", "O", "U", "M", "F", "L", "W")
    assert set(VISEME_SHAPES) == set(VISEMES) and VISEME_SHAPES["rest"] == ()
    for table in (vz.PHONEME_VISEMES, vz.LETTER_DIGRAPHS, vz.LETTER_VISEMES):
        assert {v for visemes in table.values() for v in visemes} <= set(VISEMES) - {"rest"}
    assert all(len(key) == 1 for key in vz.PHONEME_VISEMES)  # one code point each: no longest match needed
    assert vz.VOWEL_PHONEMES <= set(vz.PHONEME_VISEMES)


@pytest.mark.parametrize(
    ("phonemes", "expected"),
    [
        ("mbp", "MMM"), ("fv", "FF"), ("lθð", "LLL"), ("wʍ", "WW"), ("æɑʌə", "AAAA"), ("iɪɛ", "EEE"),
        ("oɔ", "OO"), ("uʊ", "UU"), ("tdskgnɹʃʧ", "EEEEEEEEE"),
        ("I", "AE"), ("O", "OU"), ("W", "AU"), ("Y", "OE"), ("A", "E"),  # misaki's diphthongs
        ("ˈhɛˌlː", "EL"),  # stress, length and h take no time
    ],
)
def test_phonemes_to_visemes(phonemes: str, expected: str) -> None:
    assert "".join(v for v, _ in vz.phoneme_units(phonemes)) == expected


def test_phoneme_weights_and_word_gaps() -> None:
    units = vz.phoneme_units("mˈæ wI")
    assert units == [("M", 1.0), ("A", 2.0), ("rest", 0.5), ("W", 1.0), ("A", 1.0), ("E", 1.0)]  # a diphthong splits its weight


@pytest.mark.parametrize(
    ("word", "language", "expected"),
    [
        ("Mama!", None, "MAMA"), ("thumb", None, "LUMM"), ("phone", None, "FOE"), ("food", None, "FUE"),
        ("whale", None, "WAL"), ("night", None, "EEE"), ("Café", "fr", "EAFE"), ("vela", "pt-BR", "FELA"),
        ("42", None, "AA"), ("мама", "ru", "AAAA"),
    ],
)
def test_letter_fallback(word: str, language: str | None, expected: str) -> None:
    assert "".join(v for v, _ in vz.letter_units(word, language)) == expected


# ----- the merge rule ------------------------------------------------------------------------------


def test_merge_joins_same_visemes_and_gives_short_cues_to_the_longer_neighbour() -> None:
    cues = [cue(0, 0.2, "rest"), cue(0.2, 0.25, "E"), cue(0.25, 0.5, "A"), cue(0.5, 0.6, "A"), cue(0.6, 0.64, "O"), cue(0.64, 0.7, "U"), cue(0.7, 1.0, "rest")]
    out = merge_short_cues(cues, 0.07)
    # the two As join (0.35); shortest first: O (0.04) goes to A (longer than U), E (0.05) to A
    # (longer than rest's 0.2), U (0.06) to A (0.44, longer than the last rest's 0.3)
    assert [(round(c.start, 2), round(c.end, 2), c.viseme) for c in out] == [(0, 0.2, "rest"), (0.2, 0.7, "A"), (0.7, 1.0, "rest")]
    assert contiguous(out, 1.0)


def test_merge_tie_goes_to_the_earlier_cue_and_one_cue_stays() -> None:
    assert merge_short_cues([cue(0, 0.1, "A"), cue(0.1, 0.12, "E"), cue(0.12, 0.22, "O")], 0.07) == [cue(0, 0.12, "A"), cue(0.12, 0.22, "O")]
    assert merge_short_cues([cue(0, 0.03, "A")], 0.07) == [cue(0, 0.03, "A")]
    assert merge_short_cues([cue(0, 0.03, "A"), cue(0.03, 0.05, "E")], 0.07) == [cue(0, 0.05, "A")]
    assert merge_short_cues([], 0.07) == []


def test_merge_keeps_a_short_closed_mouth() -> None:
    out = merge_short_cues([cue(0, 0.3, "A"), cue(0.3, 0.34, "M"), cue(0.34, 0.5, "E")], 0.07)
    assert [c.viseme for c in out] == ["A", "M", "E"]
    assert out[1].end - out[1].start == pytest.approx(0.07) and out[0].end == pytest.approx(0.27) and contiguous(out, 0.5)
    # no neighbour can spare the time: merged like any other cue
    out = merge_short_cues([cue(0, 0.08, "A"), cue(0.08, 0.12, "M"), cue(0.12, 0.2, "E")], 0.07)
    assert [c.viseme for c in out] == ["A", "E"]


def test_cues_from_units_fill_rests_and_cover_the_beat() -> None:
    timed = [([("M", 1.0), ("A", 2.0)], 0.2, 0.5), ([("O", 1.0)], 0.9, 1.1), ([("E", 1.0)], 1.1, 1.1)]
    out = vz.cues_from_units(timed, 1.5)
    assert [(round(c.start, 3), round(c.end, 3), c.viseme) for c in out] == [
        (0, 0.2, "rest"), (0.2, 0.3, "M"), (0.3, 0.5, "A"), (0.5, 0.9, "rest"), (0.9, 1.1, "O"), (1.1, 1.5, "rest"),
    ]
    assert vz.cues_from_units([], 0.5) == [cue(0, 0.5, "rest")]
    track = VisemeTrack(tuple(out))
    assert [track.at(t) for t in (-1, 0.0, 0.25, 0.35, 0.95, 1.2, 1.5, 9)] == ["rest", "rest", "M", "A", "O", "rest", "rest", "rest"]
    assert track.duration == 1.5 and VisemeTrack(()).at(0.1) == "rest"


# ----- phonemes from the text: the installed G2P ---------------------------------------------------


def test_installed_g2p_is_used_and_falls_back_per_word(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(language: str | None) -> Any:
        raise RuntimeError("does not load")

    def fake(language: str | None) -> Any:
        return lambda word: {"hi": "hˈI", "mom": "mˈɑm"}.get(word.lower()) or (_ for _ in ()).throw(ValueError(word))

    monkeypatch.setattr(vz, "G2P_BACKENDS", (("misaki", broken), ("espeak", fake)))
    vz.text_g2p.cache_clear()
    source, units = vz.text_phonemes(["Hi", "mom", "zoo"])
    assert source == "espeak"
    assert ["".join(v for v, _ in u) for u in units] == ["AE", "MAM", "EU"]  # zoo: the letters


def test_without_any_g2p_the_letters_are_used() -> None:
    assert vz.text_g2p("en") is None
    assert vz.text_phonemes(["Hello"])[0] == "letters"


def test_espeak_ng_program(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: Any) -> Any:
        calls.append(args)
        assert kwargs["check"] is True and kwargs["capture_output"] is True
        return types.SimpleNamespace(stdout=" ˈolɐ\n".encode("utf-8"))

    monkeypatch.setattr(vz.shutil, "which", lambda name: "/usr/bin/espeak-ng" if name == "espeak-ng" else None)
    monkeypatch.setattr(vz.subprocess, "run", run)
    say = vz._espeak_ng("pt-BR")
    assert say is not None and say("olá") == "ˈolɐ"
    assert calls == [["/usr/bin/espeak-ng", "-q", "--ipa", "-v", "pt-br", "olá"]]
    assert vz.espeak_voice(None) == "en-us" and vz.espeak_voice("en-GB") == "en-gb"
    monkeypatch.setattr(vz.shutil, "which", lambda name: None)
    assert vz._espeak_ng("en") is None


def test_misaki_english_needs_the_spacy_model(monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[dict[str, Any]] = []

    class G2P:
        def __init__(self, **kwargs: Any) -> None:
            made.append(kwargs)

        def __call__(self, text: str) -> tuple[str, list[Any]]:
            return "hˈɛlO", []

    package = types.ModuleType("misaki")
    package.en = types.SimpleNamespace(G2P=G2P)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "misaki", package)
    installed = {"misaki"}
    monkeypatch.setattr(vz, "_available", lambda name: name in installed)
    assert vz._misaki("en") is None  # no en_core_web_sm: misaki would pip-install it
    installed.add("en_core_web_sm")
    say = vz._misaki("en-GB")
    assert say is not None and say("hello") == "hˈɛlO" and made == [{"trf": False, "british": True, "fallback": None}]
    assert vz._misaki("pt") is None  # other languages need espeakng_loader


# ----- storage and a track from a stored alignment -------------------------------------------------


def make_voiced(make_project, text: str = "Hi mom.", seconds: float = 1.0, **overrides: Any) -> Project:
    data = minimal_config(scenes=[{"id": "s", "type": "text_card", "params": {"text": "x"}, "beats": [{"id": "b", "text": text}]}], **overrides)
    project = Project.load(make_project(data))
    make_tone(project.audio_dir / "b.mp3", seconds)
    return project


def test_track_from_a_stored_alignment(make_project) -> None:
    project = make_voiced(make_project, characters=PIP)
    mp3 = project.audio_dir / "b.mp3"
    text = "Hi mom."
    starts = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    alignment = {"characters": list(text), "character_start_times_seconds": starts, "character_end_times_seconds": [s + 0.1 for s in starts]}
    write_alignment(project.audio_dir, "b", text, mp3.read_bytes(), alignment)
    track = vz.beat_visemes(project, "b")
    assert (track.source, track.timing) == ("letters", "alignment")
    # "Hi" is spoken 0.1-0.3 (E: h is silent), "mom." 0.4-0.8 (M O M); rest around
    assert [(round(c.start, 2), round(c.end, 2), c.viseme) for c in track.cues] == [
        (0, 0.1, "rest"), (0.1, 0.3, "E"), (0.3, 0.4, "rest"), (0.4, 0.5, "M"), (0.5, 0.7, "O"), (0.7, 0.8, "M"), (0.8, track.duration, "rest"),
    ]
    assert track.duration == pytest.approx(1.0, abs=0.05)


def test_estimated_track_without_audio(make_project) -> None:
    data = minimal_config(scenes=[{"id": "s", "type": "text_card", "params": {"text": "x"}, "beats": [{"id": "b", "text": "Hello there."}]}])
    project = Project.load(make_project(data))
    track = vz.beat_visemes(project, "b", duration=2.0)
    assert (track.source, track.timing, track.duration) == ("letters", "estimate", 2.0)
    assert contiguous(list(track.cues), 2.0) and {c.viseme for c in track.cues} == {"E", "L", "O"}  # no MP3: speech fills the beat
    with pytest.raises(VidgenError, match="unknown beat 'nope'"):
        vz.beat_visemes(project, "nope")


def test_stored_track_is_tied_to_the_mp3_and_the_text(make_project) -> None:
    project = make_voiced(make_project)
    audio_dir, mp3 = project.audio_dir, project.audio_dir / "b.mp3"
    track = VisemeTrack((cue(0, 0.5, "A"), cue(0.5, 1.0, "rest")), "kokoro", "kokoro")
    path = vz.write_visemes(audio_dir, "b", "Hi mom.", mp3.read_bytes(), track)
    assert path == audio_dir / "b.visemes.json"
    assert vz.read_visemes(audio_dir, "b", "Hi mom.") == track
    assert vz.beat_visemes(project, "b") == track
    assert vz.read_visemes(audio_dir, "b", "Other text.") is None
    make_tone(mp3, 0.6)  # new audio: the stored track no longer applies
    assert vz.read_visemes(audio_dir, "b", "Hi mom.") is None
    assert vz.beat_visemes(project, "b").source == "letters"
    path.write_text("{not json", encoding="utf-8")
    assert vz.read_visemes(audio_dir, "b", "Hi mom.") is None


# ----- vidgen tts writes the tracks ----------------------------------------------------------------


class FakeProvider:
    """A provider that returns one fixed MP3 (and Kokoro-like phonemes when given)."""

    name = "fake"

    def __init__(self, mp3: bytes, phonemes: list[tuple[str, float, float]] | None = None) -> None:
        self.mp3, self.calls = mp3, 0
        if phonemes is not None:
            self.last_phonemes = phonemes

    def cache_key(self, text: str) -> str:
        return f"fake|{text}"

    def matches(self, text: str, stored: str) -> bool:
        return stored == self.cache_key(text)

    def check_credentials(self) -> None:
        pass

    def synthesize(self, text: str, previous_text: str | None = None, next_text: str | None = None) -> bytes:
        self.calls += 1
        return self.mp3


def test_tts_writes_tracks_only_for_videos_with_characters(make_project, tmp_path: Path) -> None:
    from vidgen.tts.run import run_tts

    mp3 = make_tone(tmp_path / "tone.mp3", 0.8).read_bytes()
    plain = Project.load(make_project(minimal_config(), folder="plain"))
    run_tts(plain, provider=FakeProvider(mp3), out=lambda line: None)
    assert (plain.audio_dir / "custom.mp3").is_file() and not list(plain.audio_dir.glob("*.visemes.json"))

    # adding characters later: the next run writes tracks for the beats already voiced
    root = make_project(minimal_config(characters=PIP), folder="plain")
    lines: list[str] = []
    provider = FakeProvider(mp3)
    run_tts(Project.load(root), provider=provider, out=lines.append)
    assert provider.calls == 0 and "wrote viseme tracks (lip sync) for 3 beat(s) already voiced" in lines
    project = Project.load(root)
    track = vz.read_visemes(project.audio_dir, "custom", "One two three four.")
    assert track is not None and (track.source, track.timing) == ("letters", "speech")

    lines.clear()
    run_tts(project, provider=FakeProvider(mp3), out=lines.append, force=True, beat_ids=["custom"])
    assert not any("wrote viseme tracks" in line for line in lines)


def test_tts_keeps_kokoro_phonemes(make_project, tmp_path: Path) -> None:
    from vidgen.tts.run import run_tts

    mp3 = make_tone(tmp_path / "tone.mp3", 0.8).read_bytes()
    project = Project.load(make_project(minimal_config(characters=PIP)))
    provider = FakeProvider(mp3, phonemes=[("wˈʌn", 0.1, 0.3), ("tˈu", 0.3, 0.5)])
    run_tts(project, provider=provider, beat_ids=["custom"], out=lambda line: None)
    track = vz.read_visemes(project.audio_dir, "custom", "One two three four.")
    assert track is not None and (track.source, track.timing) == ("kokoro", "kokoro")
    # wˈʌn tˈu: W (0.05 s) is merged into the rest before it (a tie with A: the earlier cue)
    assert [c.viseme for c in track.cues] == ["rest", "A", "E", "U", "rest"]


def test_kokoro_provider_captures_token_and_chunk_phonemes(tmp_path: Path) -> None:
    from vidgen.tts import kokoro as kk

    class Token:
        def __init__(self, text: str, phonemes: str | None, start: float | None, end: float | None) -> None:
            self.text, self.phonemes, self.start_ts, self.end_ts = text, phonemes, start, end

    class Pipeline:
        def __call__(self, text: str, voice: str, speed: float, split_pattern: Any) -> Any:
            silence = np.zeros(kk.SAMPLE_RATE // 2, dtype=np.float32)  # 0.5 s per chunk
            yield types.SimpleNamespace(audio=silence, tokens=[Token("Hi", "hˈI", 0.1, 0.3), Token(".", ".", None, None)], phonemes="hˈI.")
            yield types.SimpleNamespace(audio=silence, tokens=None, phonemes="ˈolɐ")

    engine = types.SimpleNamespace(device="cpu", pipeline=lambda lang: Pipeline())
    provider = kk.KokoroProvider(VoiceConfig(provider="kokoro"), engine=engine)  # type: ignore[arg-type]
    provider.synthesize_timed("Hi. Olá")
    assert provider.last_phonemes == [("hˈI", 0.1, 0.3), ("ˈolɐ", 0.5, 1.0)]


def test_fingerprint_follows_the_track_with_characters(make_project) -> None:
    from vidgen.render.fingerprint import scene_fingerprint

    project = make_voiced(make_project, characters=PIP)
    before = scene_fingerprint(project, "s")
    vz.write_beat_visemes(project.audio_dir, "b", "Hi mom.", (project.audio_dir / "b.mp3").read_bytes())
    assert scene_fingerprint(project, "s") != before


# ----- the character's mouth -----------------------------------------------------------------------


def generated() -> Character:
    from vidgen.cartoon.generator import generate_parts

    colors = {key: "#888888" for key in ("skin", "clothes", "outline", "features", "hair", "accessory")}
    return Character(generate_parts(CharacterLook(), colors), name="pip")


def two_mouths() -> Character:
    """A character whose mouth has only ``smile`` and ``open`` (like an SVG without visemes)."""
    from manim import Circle, Square

    parts = [CharacterPart(name, {"rest": Square(0.2)}, (0, 0)) for name in ("body", "arm_left", "arm_right", "head", "eyes", "brows")]
    parts.append(CharacterPart("mouth", {"smile": Circle(0.05), "open": Circle(0.1)}, (0, 0)))
    return Character(parts, name="duo")


def test_viseme_shapes_fall_back_to_what_the_character_has() -> None:
    full = generated()
    assert [full.viseme_shape(v) for v in VISEMES] == [None, "A", "E", "O", "U", "M", "F", "L", "W"]
    duo = two_mouths()
    assert [duo.viseme_shape(v) for v in VISEMES] == [None, "open", "open", "open", "open", None, None, "open", "open"]
    with pytest.raises(VidgenError, match="unknown viseme 'X'"):
        duo.viseme_shape("X")
    assert duo.show_viseme("M").pose_of("mouth").shape in (None, "smile")
    assert duo.show_viseme("O").pose_of("mouth").shape == "open"
    assert duo.show_viseme("rest").pose_of("mouth").shape == "smile"


def test_lip_sync_updater_follows_the_track_and_stops() -> None:
    c = generated().set_expression("sad")
    sad = c.pose_of("mouth")
    track = VisemeTrack((cue(0, 0.2, "rest"), cue(0.2, 0.5, "O"), cue(0.5, 0.6, "M"), cue(0.6, 1.0, "rest")))
    c.lip_sync(track)
    seen = []
    for _ in range(10):
        c.update(0.1)
        seen.append(c.pose_of("mouth").shape or "smile")  # None: the rest shape
    assert seen == ["smile", "O", "O", "O", "M", "smile", "smile", "smile", "smile", "smile"]
    assert c.pose_of("mouth").scale == sad.scale  # the expression's flip is kept
    c.lip_sync(track, start=0.3)  # a new lip sync replaces the running one
    assert len(c.updaters) == 1 and c.pose_of("mouth").shape == "O"
    c.stop_lip_sync()
    assert not c.updaters and c.pose_of("mouth") == sad
    assert c.stop_lip_sync() is c


def test_lip_sync_without_a_mouth_does_nothing() -> None:
    from manim import Square

    body_only = Character([CharacterPart("body", {"rest": Square(1)}, (0, 0))], name="blob", required=("body",))
    assert body_only.lip_sync(VisemeTrack((cue(0, 1, "A"),))) is body_only and not body_only.updaters
    assert body_only.show_viseme("A") is body_only


def test_scene_helper_and_api() -> None:
    from vidgen import api
    from vidgen.scene import NarratedScene

    assert callable(NarratedScene.beat_visemes)
    assert api.VisemeTrack is VisemeTrack and api.VISEMES == VISEMES

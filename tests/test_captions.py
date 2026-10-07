"""Burned-in captions, Step 40 (DESIGN.md §43): word times (estimate, speech bounds, TTS
alignments), cue cutting shared with the SRT, the ``captions`` overlay (subtitles and karaoke,
reserve, contrast, placement), ElevenLabs with-timestamps (mocked) and lint."""

from __future__ import annotations

import base64
import json
import urllib.request
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from manim import ManimColor, tempconfig

from conftest import minimal_config
from test_overlays import FPS, NARRATION, bullets, objects_of, render
from test_tts import KEY, FakeAPI, provider
from vidgen import api, extensions
from vidgen.cues import caption_cues, phrase_break_cost, segment_cues, split_cues
from vidgen.errors import VidgenError
from vidgen.lint import timing_rules
from vidgen.overlays import Overlay, scene_overlays
from vidgen.project import Project
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.render.worker import frame_size
from vidgen.runtime import current_theme
from vidgen.speech import (
    WordTime,
    aligned_word_times,
    alignment_path,
    beat_word_times,
    estimate_word_times,
    pause_after,
    read_alignment,
    speech_bounds,
    spoken_words,
    syllables,
    write_alignment,
)
from vidgen.tts.run import run_tts
from vidgen.videoplan import VideoPlan

SENTENCE = "First, you write the narration as a list of short beats."


def tone(path: Path, lead: float, speech: float, trail: float, rate: int = 16000) -> Path:
    """Silence, a tone, silence: a WAV (PyAV reads it whatever the file is called)."""
    t = np.arange(int(speech * rate)) / rate
    samples = np.concatenate([np.zeros(int(lead * rate)), 0.5 * np.sin(2 * np.pi * 440 * t), np.zeros(int(trail * rate))])
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((samples * 32767).astype(np.int16).tobytes())
    return path


def alignment_of(text: str, start: float = 0.0, step: float = 0.1) -> dict[str, Any]:
    """A provider alignment: one character every ``step`` seconds from ``start``."""
    return {
        "characters": list(text),
        "character_start_times_seconds": [start + k * step for k in range(len(text))],
        "character_end_times_seconds": [start + (k + 1) * step for k in range(len(text))],
    }


# ----- word times ------------------------------------------------------------------------------------


def test_syllables_and_pauses() -> None:
    assert [syllables(w) for w in ("cat", "narration", "beats.", "make", "table", "GPU", "77%", "one-by-one")] == [1, 3, 1, 1, 2, 3, 6, 3]
    assert pause_after("beats.") > pause_after("First,") > pause_after("the") == 0
    assert pause_after("so—") == pause_after("First,")
    # moved from the lint package, still importable there
    assert timing_rules.spoken_words is spoken_words and timing_rules.speech_bounds is speech_bounds


def test_estimated_word_times_follow_syllables_and_punctuation() -> None:
    words = SENTENCE.split()
    times = estimate_word_times(words, 1.0, 5.0)
    assert [w.text for w in times] == words
    assert times[0].start == 1.0 and times[-1].end == pytest.approx(5.0)
    assert all(a.end <= b.start + 1e-9 for a, b in zip(times, times[1:]))
    durations = {w.text: w.end - w.start for w in times}
    assert durations["narration"] > durations["the"]
    # the pause after "First," shows as a gap before "you"
    assert times[1].start - times[0].end > 0.1 and times[3].start - times[2].end == pytest.approx(0.0)
    assert estimate_word_times([], 0, 1) == []


def test_alignment_files_are_tied_to_text_and_audio(tmp_path: Path) -> None:
    audio = tmp_path / "audio"
    mp3 = tone(audio / "b1.mp3", 0.2, 1.0, 0.2)
    text = "Hello big world."
    assert write_alignment(audio, "b1", text, mp3.read_bytes(), alignment_of(text)) == alignment_path(audio, "b1")
    doc = read_alignment(audio, "b1", text)
    assert doc is not None and doc["characters"] == list(text)
    assert read_alignment(audio, "b1", "Other text.") is None
    words = aligned_word_times(text, doc, offset=10.0)
    assert words == [WordTime("Hello", 10.0, pytest.approx(10.5)), WordTime("big", pytest.approx(10.6), pytest.approx(10.9)),
                     WordTime("world.", pytest.approx(11.0), pytest.approx(11.6))]
    # a new MP3 makes the stored alignment stale
    tone(audio / "b1.mp3", 0.3, 1.0, 0.2)
    assert read_alignment(audio, "b1", text) is None
    write_alignment(audio, "b1", text, b"", None)
    assert not alignment_path(audio, "b1").exists()


def test_beat_word_times_prefer_alignment_then_speech_then_estimate(tmp_path: Path) -> None:
    audio = tmp_path / "audio"
    text = "one two three"
    # no audio: spread over the beat
    plain = beat_word_times(audio, "b1", text, 2.0, 4.0)
    assert plain[0].start == 2.0 and plain[-1].end == pytest.approx(4.0)
    # an MP3 with 0.5 s of silence before and 0.5 s after: words within the speech
    mp3 = tone(audio / "b1.mp3", 0.5, 1.0, 0.5)
    speech = beat_word_times(audio, "b1", text, 2.0, 4.0)
    assert speech[0].start == pytest.approx(2.5, abs=0.02) and speech[-1].end == pytest.approx(3.5, abs=0.02)
    # a stored alignment wins
    write_alignment(audio, "b1", text, mp3.read_bytes(), alignment_of(text, start=0.7, step=0.05))
    aligned = beat_word_times(audio, "b1", text, 2.0, 4.0)
    assert aligned[0].start == pytest.approx(2.7) and aligned[1].start == pytest.approx(2.7 + 4 * 0.05)
    assert beat_word_times(None, "b1", text, 0.0, 1.0)[-1].end == pytest.approx(1.0)


# ----- cues ------------------------------------------------------------------------------------------


def test_phrase_break_costs() -> None:
    assert phrase_break_cost("beats.", "Then") < phrase_break_cost("First,", "you") < phrase_break_cost("beats", "and")
    assert phrase_break_cost("beats", "and") < phrase_break_cost("list", "of") < phrase_break_cost("write", "beats")
    assert phrase_break_cost("the", "narration") > phrase_break_cost("write", "beats")
    assert phrase_break_cost("one", "—") == phrase_break_cost("one,", "two")


def test_segment_cues_limits_and_long_words() -> None:
    words = SENTENCE.split()
    cues = segment_cues(words, [len(w) for w in words], 1, 20, max_lines=1, max_words=3)
    assert all(len(lines) == 1 and lines[0][1] - lines[0][0] <= 3 for lines in cues)
    assert [w for lines in cues for a, b in lines for w in words[a:b]] == words
    # never "the | narration" when it can be avoided
    texts = [" ".join(words[a:b]) for lines in cues for a, b in lines]
    assert not any(t.split()[-1].lower() in ("the", "a", "of", "as") for t in texts[:-1]), texts
    # a word wider than the line gets a line of its own
    assert segment_cues(["tiny", "supercalifragilistic", "end"], [4, 20, 3], 1, 10, max_lines=1) == [[(0, 1)], [(1, 2)], [(2, 3)]]
    assert segment_cues([], [], 1, 10) == []
    with pytest.raises(ValueError):
        segment_cues(["a"], [1], 1, 10, max_lines=0)
    assert split_cues("Short one.", 42) == [["Short one."]]


def test_caption_cues_are_timed_by_their_first_words() -> None:
    words = SENTENCE.split()
    timed = [WordTime(w, 1.0 + 0.3 * k, 1.25 + 0.3 * k) for k, w in enumerate(words)]
    cues = caption_cues(SENTENCE, 0.5, 4.0, words=timed, max_width=20, max_lines=1, max_words=3, until=4.6)
    assert cues[0].start == 0.5 and cues[-1].end == 4.6
    for a, b in zip(cues, cues[1:]):
        assert a.end == b.start == b.words[0].start
    assert [w.text for c in cues for w in c.words] == words
    assert caption_cues("   ", 0, 1) == []


# ----- the overlay -----------------------------------------------------------------------------------


def load(make_project, scenes: list[dict[str, Any]], overlays: list[dict[str, Any]], **extra: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, overlays=overlays, narration=NARRATION, **extra)))


def built(project: Project, scene_id: str, size: tuple[int, int] = (320, 180)) -> list[Overlay]:
    """The overlays of a scene, built in a tiny frame (``o.built``, the scene's planned start ``o.at``)."""
    w, h = size
    fw, fh = frame_size(w, h)
    with tempconfig({"pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "frame_rate": FPS}):
        theme = extensions.activate(project)
        plan = VideoPlan(project, FPS)
        overlays = scene_overlays(project, project.scene(scene_id), theme, plan)
        for o in overlays:
            o.built = o.build()  # type: ignore[attr-defined]
            o.at = plan.scene_start(scene_id)  # type: ignore[attr-defined]
    return overlays


def narrated(sid: str, *texts: str, **extra: Any) -> dict[str, Any]:
    return {"id": sid, "type": "text_card", "params": {"text": "Card"}, "beats": [{"text": t} for t in texts], **extra}


LONG = "First, you write the narration as a list of short beats, and then you render a preview of every scene in the video."


def test_subtitles_show_one_cue_at_a_time_and_reserve_the_bottom(make_project) -> None:
    project = load(make_project, [narrated("a", "A short beat."), narrated("b", LONG, "The end.")], [{"type": "captions"}])
    (cap,) = built(project, "b")
    at = cap.at  # type: ignore[attr-defined]
    band, *cues = cap.built.submobjects  # type: ignore[attr-defined]
    assert len(cues) == 3 and cap.reserves and cap.layer > 0
    assert band.get_fill_opacity() == 0 and band.get_bottom()[1] == pytest.approx(-4 + 0.5, abs=0.01)   # on the safe area's bottom
    states = [cap.state(at + t) for t in np.arange(0, 8, 0.1)]
    shown = [s for s in states if s is not None]
    assert shown[0] == 0 and sorted(set(shown)) == [0, 1, 2] and shown == sorted(shown)
    assert cap.pose(cap.built, 1) is cues[1]  # type: ignore[attr-defined]
    plate, *lines = cues[0].submobjects
    assert len(lines) == 2 and plate.get_fill_opacity() >= 0.8
    assert all(line.get_center()[0] == pytest.approx(0, abs=0.05) for line in lines)
    # cut like the SRT (here widths are measured, not characters): every word once, in order
    shown = [line.original_text for cue in cues[:2] for line in cue.submobjects[1:]]
    assert " ".join(shown) == LONG
    assert not any(line.split()[-1] in ("the", "a", "as") for line in shown)   # never right after an article
    # the first beat's caption is not shown in the other scene
    assert cap.state(at - 0.05) is None


def test_karaoke_highlights_the_spoken_word(make_project) -> None:
    project = load(make_project, [narrated("a", SENTENCE)], [{"type": "captions", "style": "words"}])
    (cap,) = built(project, "a", size=(180, 320))
    assert cap.options.style == "karaoke" and cap.karaoke  # type: ignore[attr-defined]
    states = [cap.state(t) for t in np.arange(0, 3.0, 0.05)]
    pairs = [s for s in states if s is not None]
    assert all(isinstance(s, tuple) for s in pairs) and pairs == sorted(pairs)
    assert len({k for k, _ in pairs}) >= 3   # a few words at a time
    k, w = next(s for s in pairs if s[1] >= 1)
    cue = cap.built.submobjects[1 + k]  # type: ignore[attr-defined]
    posed = cap.pose(cap.built, (k, w))  # type: ignore[attr-defined]
    assert posed is not cue and posed.width >= cue.width - 1e-6
    highlight = ManimColor(current_theme().color("highlight")).to_hex().upper()
    colours = {ManimColor(g.get_fill_color()).to_hex().upper() for line in posed.submobjects[1:] for g in line.submobjects if len(g.points)}
    assert highlight in colours and len(colours) == 2
    assert cap.pose(cap.built, (k, -1)) is cue  # type: ignore[attr-defined]
    # karaoke is bigger and bold; in 9:16 the bottom band is raised for phone controls
    band = cap.built.submobjects[0]  # type: ignore[attr-defined]
    assert band.get_bottom()[1] > -frame_size(180, 320)[1] / 2 + 0.5 + 0.1


def test_reserve_defaults_and_silent_scenes(make_project) -> None:
    scenes = [{"id": "card", "type": "text_card", "params": {"text": "Silent"}, "duration": 1.0}, narrated("a", "Hello there.")]
    assert built(load(make_project, scenes, [{"type": "captions"}]), "card") == []   # nothing to caption, nothing reserved
    assert built(load(make_project, scenes, [{"type": "captions", "position": "center"}]), "a")[0].reserves is False
    assert built(load(make_project, scenes, [{"type": "captions", "reserve": False}]), "a")[0].reserves is False
    (top,) = built(load(make_project, scenes, [{"type": "captions", "position": "top"}]), "a")
    assert top.reserves and top.built.get_top()[1] == pytest.approx(4 - 0.5, abs=0.01)  # type: ignore[attr-defined]


def test_plate_opacity_rises_until_the_text_reads(make_project) -> None:
    scenes = [narrated("a", "Hello there.")]
    (cap,) = built(load(make_project, scenes, [{"type": "captions", "background_opacity": 0.1}]), "a")
    plate = cap.built.submobjects[1].submobjects[0]  # type: ignore[attr-defined]
    text = cap.built.submobjects[1].submobjects[1].submobjects[0]  # type: ignore[attr-defined]   # a glyph
    opacity = plate.get_fill_opacity()
    assert opacity > 0.1
    text_hex, plate_hex = ManimColor(text.get_fill_color()).to_hex(), ManimColor(plate.get_fill_color()).to_hex()
    assert api.plate_contrast(text_hex, plate_hex, opacity, theme=current_theme()) >= 4.5
    # no plate: an outline in the background colour
    (bare,) = built(load(make_project, scenes, [{"type": "captions", "background": None}]), "a")
    line = bare.built.submobjects[1].submobjects[0]  # type: ignore[attr-defined]
    assert line.submobjects[0].get_stroke_width(background=True) > 0


def test_plate_contrast_is_the_worst_case() -> None:
    from vidgen.theme import Theme

    theme = Theme()
    assert api.plate_contrast("#FFFFFF", "#000000", 1.0, theme=theme) == pytest.approx(21.0)
    assert api.plate_contrast("#FFFFFF", "#000000", 0.0, theme=theme) == pytest.approx(1.0)   # no plate over white
    assert 1 < api.plate_contrast("text", "surface", 0.8, theme=theme) < api.plate_contrast("text", "surface", 1.0, theme=theme)


def test_options_are_validated(make_project) -> None:
    from vidgen.cli import project_problems

    project = load(make_project, [narrated("a", "Hi there.")], [{"type": "captions", "style": "marquee", "max_lines": 5, "pop": 3}])
    found = {p.location for p in project_problems(project)}
    assert {"overlays[0].style", "overlays[0].max_lines", "overlays[0].pop"} <= found


def test_fingerprint_follows_alignments(make_project) -> None:
    project = load(make_project, [narrated("a", "Hello there.")], [{"type": "captions"}])
    before = scene_fingerprint(project, "a")
    mp3 = tone(project.audio_dir / "a_b1.mp3", 0.1, 0.5, 0.1)
    with_audio = scene_fingerprint(project, "a")
    write_alignment(project.audio_dir, "a_b1", "Hello there.", mp3.read_bytes(), alignment_of("Hello there."))
    assert len({before, with_audio, scene_fingerprint(project, "a")}) == 3


def test_api_exports() -> None:
    for name in ("CaptionCue", "caption_cues", "phrase_break_cost", "segment_cues", "WordTime", "beat_word_times",
                 "estimate_word_times", "speech_bounds", "spoken_words", "syllables", "plate_contrast"):
        assert name in api.__all__ and name in api.VIDGEN_NAMES and getattr(api, name).__doc__


# ----- ElevenLabs with timestamps (mocked) ----------------------------------------------------------


def timestamped(text: str, audio: bytes = b"MP3DATA") -> bytes:
    return json.dumps({"audio_base64": base64.b64encode(audio).decode(), "alignment": alignment_of(text), "normalized_alignment": None}).encode()


def test_synthesize_timed_uses_the_timestamps_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeAPI()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setenv("ELEVENLABS_API_KEY", KEY)
    fake.responses = [timestamped("Hi."), b"not json", json.dumps({"audio_base64": "QUJD"}).encode()]
    p = provider(voice_id="abc")
    audio, alignment = p.synthesize_timed("Hi.", None, "Next.")
    assert audio == b"MP3DATA" and alignment is not None and alignment["characters"] == ["H", "i", "."]
    req = fake.requests[0]
    assert req.full_url == "https://api.elevenlabs.io/v1/text-to-speech/abc/with-timestamps?output_format=mp3_44100_128"
    assert req.get_header("Accept") == "application/json" and fake.body(0)["next_text"] == "Next."
    with pytest.raises(VidgenError, match="unreadable with-timestamps"):
        p.synthesize_timed("Hi.")
    assert p.synthesize_timed("Hi.") == (b"ABC", None)   # audio without timings


def test_tts_stores_alignments_when_asked(make_project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeAPI()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setenv("ELEVENLABS_API_KEY", KEY)
    scenes = [narrated("a", "Hello there.", "Second beat.")]
    root = make_project(minimal_config(scenes=scenes, voice={"timestamps": True}))
    fake.responses = [timestamped("Hello there.", b"A1"), timestamped("Second beat.", b"A2")]
    run_tts(Project.load(root), out=lambda s: None)
    audio = root / "audio"
    assert (audio / "a_b1.mp3").read_bytes() == b"A1"
    assert read_alignment(audio, "a_b1", "Hello there.") is not None and read_alignment(audio, "a_b2", "Second beat.") is not None
    assert all("/with-timestamps" in r.full_url for r in fake.requests)
    # without timestamps the plain endpoint is used and a stale alignment removed
    (root / "video.yaml").write_text(
        (root / "video.yaml").read_text(encoding="utf-8").replace("timestamps: true", "timestamps: false"), encoding="utf-8"
    )
    run_tts(Project.load(root), beat_ids=["a_b1"], force=True, out=lambda s: None)
    assert "/with-timestamps" not in fake.requests[-1].full_url
    assert not alignment_path(audio, "a_b1").exists() and alignment_path(audio, "a_b2").exists()


# ----- rendered + lint -------------------------------------------------------------------------------


@pytest.mark.render
def test_captions_render_into_the_frames_and_the_layout_dump(make_project, tmp_path: Path) -> None:
    project = load(make_project, [bullets("s", beats=2)], [{"type": "captions"}])
    scene = render(project, "s", tmp_path / "media", per_beat=1)
    texts = [o["text"] for frame in scene.layout for o in objects_of(frame, "captions") if o["kind"] == "text"]
    assert texts and all(t in "one two three four five six seven eight" for t in texts)
    # the scene's safe area ends above the captions' band
    assert scene.safe_box.y0 > scene.frame_safe.y0 + 0.3


@pytest.mark.render
@pytest.mark.slow
@pytest.mark.parametrize("position", ["bottom", "center"])
def test_lint_sees_captions_over_scene_text(position: str, make_project) -> None:
    """Bottom captions reserve their band (no finding: they pass the contrast and size rules
    too); centred ones over a centred text card are an ``overlay_overlap``."""
    from vidgen.lint import RULES, lint_project

    card = {"id": "s", "type": "text_card", "beats": [{"text": "one two three four five six seven eight nine ten"}],
             "params": {"text": "A card with a long line of text in the middle of the frame", "size": "heading"}}
    root = make_project(minimal_config(scenes=[card], overlays=[{"type": "captions", "position": position}], narration=NARRATION,
                                       preview={"width": 320, "height": 180, "fps": FPS}))
    result = lint_project(Project.load(root), rules=[name for name, entry in RULES.items() if entry.scope == "still"])
    found = sorted({f.rule for f in result.findings})
    assert found == ([] if position == "bottom" else ["overlay_overlap"]), [f.message for f in result.findings]

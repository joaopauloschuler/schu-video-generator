"""Built-in music data for ``web`` scenes (Step 347, DESIGN.md §120.8): the analysis, the score's
events, the song time of a scene, the cache and the keys, and ``ctx.music`` on a page.

No music is synthesised here: a project's piece is given its render in the music cache (as the
join would leave it), and music files are short WAVs written by the test."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from vidgen import extensions
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.sfx import RATE, write_wav
from vidgen.studio import parse_music_score
from vidgen.studio.events import score_events, score_facts
from vidgen.web import music as wm

FPS = 10
#: A loop of two bars at 120 BPM (4 s): a kick on every beat, an accented clap, notes with marks, chords.
SCORE = {
    "title": "Test loop", "key": "C major", "tempo": 120, "progression": "I IV", "loop": True,
    "sections": [{"name": "a", "bars": 1}, {"name": "b", "bars": 1}],
    "tracks": {
        "kick": {"instrument": "kick", "steps": "x . x . x . x ."},
        "clap": {"instrument": "clap", "steps": ". . X . . . X ."},
        "cello": {"instrument": "cellos", "steps": "[pizzicato] D3 . [spiccato f] E3 . [sustain p <] (F3 - G3 -) [ff]"},
        "pad": {"instrument": "pad", "play": "chords"},
    },
}


def _click(seconds: float, at: list[float], hz: float = 80.0) -> np.ndarray:
    """Stereo audio of ``seconds`` with a decaying ``hz`` burst at each time of ``at``."""
    x = np.zeros(int(seconds * RATE))
    t = np.arange(int(0.25 * RATE)) / RATE
    burst = 0.5 * np.sin(2 * np.pi * hz * t) * np.exp(-t / 0.05) * np.sin(0.5 * np.pi * np.clip(t / 0.01, 0, 1)) ** 2
    for s in at:
        a = int(s * RATE)
        x[a:a + len(burst)] += burst[: len(x) - a]
    return np.stack([x, x], axis=1).astype(np.float32)


def _project(make_project: Any, music: Any, scenes: list[dict[str, Any]] | None = None, score: dict[str, Any] | None = None,
             seed_piece: bool = True) -> Project:
    """Three silent ``web`` scenes of 2 s (the last with ``music_data``) and ``music``; with a
    score, its render seeded into the music cache (clicks on its kick)."""
    scenes = scenes or [
        {"id": "s1", "type": "web", "duration": 2, "params": {"script": "x.js"}},
        {"id": "s2", "type": "web", "duration": 2, "params": {"script": "x.js"}},
        {"id": "s3", "type": "web", "duration": 2, "params": {"script": "x.js", "music_data": True}},
    ]
    config = {"title": "M", "format": {"width": 160, "height": 90, "fps": FPS}, "preview": {"width": 80, "height": 46, "fps": FPS},
              "transition": "cut", "scenes": scenes}
    if music is not None:
        config["music"] = music
    root = make_project(config)
    (root / "x.js").write_text("export function frame() {}\n", encoding="utf-8")
    if score is not None:
        path = root / "assets" / "music" / "tune.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(score, sort_keys=False), encoding="utf-8")
        if seed_piece:
            from vidgen.music_pieces import piece_key

            cache = root / "build" / "music" / f"piece-{piece_key(path)}.npy"
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache, _click(4.0, [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]), allow_pickle=False)
    return Project.load(root)


def _series(data: dict[str, Any], name: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(data["series"][name]), np.uint8) / 255


def _times(column: dict[str, Any]) -> np.ndarray:
    return np.frombuffer(base64.b64decode(column["t"]), "<u4") / RATE


# ----- the analysis -------------------------------------------------------------------------------


def test_the_analysis_follows_the_bursts_and_is_deterministic() -> None:
    audio = _click(4.0, [1.0, 2.5]).mean(axis=1)
    series = wm.analyse(audio, RATE, 30, 120, bands=8)
    again = wm.analyse(audio, RATE, 30, 120, bands=8)
    assert all(np.array_equal(series[k], again[k]) for k in series)
    assert series["bands"].shape == (120, 8)
    edges = wm.band_edges(8)
    burst_band = int(np.searchsorted(edges, 80.0)) - 1
    hit = 30   # the frame of the first burst
    assert series["low"][hit] > 0.8 and series["low"][hit - 5] == 0.0
    assert series["level"][hit] > 0.9
    two = (_click(4.0, [1.0]) + _click(4.0, [2.5], hz=3000.0)).mean(axis=1)
    bands = wm.analyse(two, RATE, 30, 120, bands=8)["bands"]
    high_band = int(np.searchsorted(edges, 3000.0)) - 1
    assert bands[hit + 1, burst_band] > 0.9 and bands[hit + 1, high_band] < 0.3
    assert bands[75 + 1, high_band] > 0.9 and bands[75 + 1, burst_band] < 0.5
    onset = series["onset"]
    assert onset[hit - 2:hit + 2].max() > 0.6 and onset[73:78].max() > 0.6 and onset[hit - 10] == 0.0 and onset.max() == pytest.approx(1.0)
    # the release: after the burst the low end falls by at most 20 % of itself per frame
    low = series["low"]
    assert np.all(low[hit + 1:hit + 20] >= 0.8 * low[hit:hit + 19] - 1e-12)


def test_silence_gives_zeros_and_frames_outside_the_music_do_not_set_the_scale() -> None:
    silent = wm.analyse(np.zeros(RATE), RATE, 10, 10)
    assert all(not np.any(v) for v in silent.values())
    audio = (_click(4.0, [1.0]) + 0.2 * _click(4.0, [2.5])).mean(axis=1)
    everywhere = wm.analyse(audio, RATE, 30, 120)
    playing = np.arange(120) >= 60   # the softer burst alone sets the scale
    some = wm.analyse(audio, RATE, 30, 120, playing=playing)
    assert not np.array_equal(everywhere["bands"], some["bands"])


def test_a_band_narrower_than_a_bin_reads_the_nearest_bin() -> None:
    series = wm.analyse(_click(2.0, [0.5]).mean(axis=1), RATE, 10, 20, bands=64)
    assert series["bands"].shape == (20, 64) and np.all(np.isfinite(series["bands"]))


def test_pcm16_rounds_as_the_wav_writer() -> None:
    x = np.array([[0.5, -1.2], [1e-6, 0.25]])
    assert np.array_equal(wm.pcm16(x) * 32768, np.clip(np.round(x * 32767), -32768, 32767))


def test_the_settings_and_their_errors() -> None:
    assert wm.music_settings(True) == wm.MusicDataSettings() and wm.music_settings(False) is None
    assert wm.music_settings({"bands": 32}).bands == 32
    with pytest.raises(ValueError, match="less than or equal to 64"):
        wm.music_settings({"bands": 65})
    with pytest.raises(ValueError, match="Extra inputs"):
        wm.music_settings({"band": 8})


# ----- the score's events -------------------------------------------------------------------------


def test_score_events_name_hits_notes_dynamics_strokes_slurs_and_chords() -> None:
    score = parse_music_score(SCORE)
    events = score_events(score)
    kicks = events["kick"]
    assert [e.time for e in kicks] == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
    assert all(e.pitches == () and e.instrument == "kick" for e in kicks)
    assert [e.gain for e in events["clap"]][:2] == [1.5, 1.5]
    cello = events["cello"]
    assert [(e.time, e.pitches, e.stroke) for e in cello[:2]] == [(0.0, (50,), "pizzicato"), (0.5, (52,), "spiccato")]
    assert cello[1].dynamic == pytest.approx(4.0)   # f
    held, slurred = cello[2], cello[3]
    assert (held.time, held.duration, held.pitches, held.slur, held.stroke) == (1.0, 0.5, (53,), False, "sustain")
    assert (slurred.time, slurred.duration, slurred.pitches, slurred.slur) == (1.5, 0.5, (55,), True)
    assert held.dynamic < slurred.dynamic < slurred.dynamic_end   # p < ... ff
    pad = events["pad"]
    assert [(e.time, e.duration) for e in pad] == [(0.0, 2.0), (2.0, 2.0)] and len(pad[0].pitches) >= 3
    facts = score_facts(score)
    assert facts["bar"] == 2.0 and facts["loop"] and [s["name"] for s in facts["sections"]] == ["a", "b"]


def test_the_film_layout_of_holds_across_sections_is_kept() -> None:
    data = {**SCORE, "loop": False, "tracks": {"lead": {"instrument": "soft_lead", "steps": "C4 - - -", "sections": {"b": {"steps": "- - E4 ."}}}}}
    lead = score_events(parse_music_score(data))["lead"]
    assert [(e.time, e.duration) for e in lead] == [(0.0, 3.0), (3.0, 0.5)]


# ----- a project's music data ----------------------------------------------------------------------


def test_a_music_file_gives_analysis_no_events_and_the_scenes_song_time(make_project: Any) -> None:
    project = _project(make_project, {"source": "assets/song.wav", "start": 1.5, "loop": False, "fade_in": 0, "fade_out": 0})
    write_wav(project.root / "assets" / "song.wav", _click(10.0, [2.0, 3.0, 5.5]))
    with extensions.project_session(project):
        data = wm.scene_music(project, "s3", FPS, wm.MusicDataSettings())
    assert data["first"] == 40 and data["start"] == 4.0 and data["t0"] == pytest.approx(5.5)   # 1.5 s into the file + 4 s
    assert data["source"]["kind"] == "file" and data["score"] is None
    level = _series(data, "level")
    assert data["from"] == 0 and len(level) == data["to"] - data["from"]
    # the burst at 5.5 s into the file is heard at video 4.0 s = frame 40, the start of s3
    assert level[40] > 0.9 and level[35] < 0.5
    with pytest.raises(VidgenError, match="only a score file has tracks"):
        with extensions.project_session(project):
            wm.scene_music(project, "s3", FPS, wm.MusicDataSettings(tracks=["kick"]))


def test_volume_and_a_fade_change_what_is_heard(make_project: Any) -> None:
    clicks = [0.5 + k for k in range(6)]
    data = {}
    for name, cue in (("plain", {"fade_in": 0, "fade_out": 0}), ("faded", {"fade_in": 0, "fade_out": 3})):
        project = _project(make_project, {"source": "assets/song.wav", "loop": False, **cue}, )
        write_wav(project.root / "assets" / "song.wav", _click(6.0, clicks))
        with extensions.project_session(project):
            data[name] = _series(wm.video_music_data(project, FPS), "level")
        (project.root / "video.yaml").unlink()
    assert data["plain"][55] > data["faded"][55] + 0.1   # the last burst, inside the fade
    assert abs(data["plain"][15] - data["faded"][15]) < 0.02


def test_a_looping_score_repeats_its_events_in_song_time(make_project: Any) -> None:
    project = _project(make_project, {"source": "tune", "start": 1.0, "fade_in": 0, "fade_out": 0}, score=SCORE)
    with extensions.project_session(project):
        data = wm.scene_music(project, "s3", FPS, wm.MusicDataSettings(tracks=["kick", "cello"]))
    assert data["t0"] == pytest.approx(5.0)   # 1 s into the loop + 4 s of video: song time goes on counting
    assert data["source"] == {"kind": "score", "label": "tune", "loop": True}
    score = data["score"]
    assert list(score["tracks"]) == ["kick", "cello"] and score["seconds"] == 4.0 and score["file"] == "tune.yaml"
    kicks = _times(score["tracks"]["kick"])
    assert np.allclose(np.diff(kicks), 0.5) and kicks[0] <= 1.0 and kicks[-1] >= 7.0   # the video's 6 s from song 1 s
    cello = score["tracks"]["cello"]
    assert cello["strokes"] == ["pizzicato", "spiccato", "sustain"] and "l" in cello and "v" in cello
    with pytest.raises(VidgenError, match="did you mean 'kick'"):
        with extensions.project_session(project):
            wm.scene_music(project, "s3", FPS, wm.MusicDataSettings(tracks=["kik"]))


def test_t0_can_be_given_and_a_scene_outside_the_music_counts_video_time(make_project: Any) -> None:
    project = _project(make_project, {"source": "tune", "from": "s1", "to": "s2", "fade_in": 0, "fade_out": 0}, score=SCORE)
    with extensions.project_session(project):
        outside = wm.scene_music(project, "s3", FPS, wm.MusicDataSettings())
        given = wm.scene_music(project, "s3", FPS, wm.MusicDataSettings(t0=12.5))
    assert outside["source"] is None and outside["score"] is None and outside["t0"] == 4.0
    assert given["t0"] == 12.5 and given["first"] == outside["first"]


def test_the_data_is_cached_and_its_key_follows_the_score(make_project: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(make_project, {"source": "tune", "fade_in": 0, "fade_out": 0}, score=SCORE)
    made: list[int] = []
    real = wm._make_music_data
    monkeypatch.setattr(wm, "_make_music_data", lambda *a: made.append(1) or real(*a))
    with extensions.project_session(project):
        key = wm.music_data_key(project, FPS)
        first = wm.video_music_data(project, FPS)
        assert wm.video_music_data(project, FPS) == first and made == [1]
        assert (project.build_dir / "music" / f"music-data-{key}.json").is_file()
        assert wm.music_data_key(project, FPS, 8) != key and wm.music_data_key(project, 30) != key
        path = project.root / "assets" / "music" / "tune.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("x . x . x . x .", "x x x . x . x ."), encoding="utf-8")
        assert wm.music_data_key(project, FPS) != key


def test_the_music_is_taken_from_the_music_cache_not_synthesised(make_project: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import vidgen.studio

    project = _project(make_project, {"source": "tune", "fade_in": 0, "fade_out": 0}, score=SCORE)
    monkeypatch.setattr(vidgen.studio, "render_music_score", lambda *a, **k: pytest.fail("the music was synthesised"))
    with extensions.project_session(project):
        data = wm.video_music_data(project, FPS)
    assert data["frames"] == 6 * FPS + wm.SPARE_FRAMES and data["cues"][0]["score"] == "assets/music/tune.yaml"


def test_a_video_without_music_is_refused(make_project: Any) -> None:
    from vidgen.cli import check_project

    project = _project(make_project, None)
    with extensions.project_session(project):
        assert any("scenes[2].params.music_data: the video plays no music" in line for line in check_project(project))
        with pytest.raises(VidgenError, match="the video plays no music"):
            wm.video_music_data(project, FPS)


# ----- keys ----------------------------------------------------------------------------------------


def test_only_scenes_with_music_data_get_a_music_key(make_project: Any) -> None:
    from vidgen.render.fingerprint import fingerprint_inputs
    from vidgen.web.clip import clip_inputs
    from vidgen.web.entry import entry_of

    project = _project(make_project, {"source": "tune", "fade_in": 0, "fade_out": 0}, score=SCORE)
    with extensions.project_session(project):
        assert "music" not in fingerprint_inputs(project, "s1")["web"]
        key = fingerprint_inputs(project, "s3")["web"]["music"]
        assert key == wm.music_data_key(project, FPS)
        entry = entry_of({"script": "x.js"})
        plain = clip_inputs(project.root, entry, scene_id="s1", size=(160, 90), fps=FPS, frames=20)
        assert "music" not in plain
        data = wm.scene_music(project, "s3", FPS, wm.MusicDataSettings())
        with_music = clip_inputs(project.root, entry, scene_id="s3", size=(160, 90), fps=FPS, frames=20, music=data)
        assert with_music["music"] == {"data": wm.payload_digest(data), "helper": wm.helper_digest()}


def test_preparing_skips_scenes_without_music_data(make_project: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(make_project, {"source": "tune", "fade_in": 0, "fade_out": 0}, score=SCORE)
    asked: list[int] = []
    monkeypatch.setattr(wm, "video_music_data", lambda p, fps, bands: asked.append(bands))
    with extensions.project_session(project):
        wm.prepare_music_data(project, False, ["s1", "s2"])
        assert asked == []
        wm.prepare_music_data(project, True, ["s1", "s3"])
        assert asked == [wm.DEFAULT_BANDS]


# ----- the page --------------------------------------------------------------------------------------


PAGE = """
const out = {};
export function load(ctx) {
  const m = ctx.music;
  out.load = {t0: m.t0, first: m.first, bands: m.bandCount, tracks: Object.keys(m.tracks), kind: m.tracks.kick.kind,
              section: m.section(m.t0).name, score: m.score.file, kicks: m.hits('kick', 0, 4).length, all: m.hits().length,
              notes: m.notes('cello', 0, 4).map((e) => [e.time, e.pitch, e.stroke, e.slur]), now: m.now(),
              last: m.last('kick', 5.2).time, sounding: m.sounding('cello', 1.7).map((e) => e.pitch),
              pulse: [m.pulse('kick', 0.1, 5.0), m.pulse('kick', 0.1, 5.1)], level: m.level(), band: m.band(0)};
  try { m.hits('nope'); } catch (e) { out.error = e.message; }
  window.__out = out;
}
export function frame(t, ctx) {
  (out.frames = out.frames || []).push([t, ctx.music.now(), ctx.music.time(t), ctx.music.level()]);
  const g = ctx.canvas.getContext('2d');
  const v = Math.round(ctx.music.low() * 255);
  g.fillStyle = `rgb(${v}, 0, 0)`; g.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
}
"""


@pytest.mark.slow
@pytest.mark.render
def test_the_page_reads_ctx_music(make_project: Any) -> None:
    from vidgen.browser import chromium
    from vidgen.web.entry import entry_of
    from vidgen.web.page import WebPage

    pytest.importorskip("playwright.sync_api")
    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    project = _project(make_project, {"source": "tune", "start": 1.0, "fade_in": 0, "fade_out": 0}, score=SCORE)
    (project.root / "x.js").write_text(PAGE, encoding="utf-8")
    with extensions.project_session(project):
        data = wm.scene_music(project, "s3", FPS, wm.MusicDataSettings())
    low = _series(data, "low")
    with WebPage(project.root, entry_of({"script": "x.js"}), scene_id="s3", size=(32, 18), fps=FPS, frames=20, music=data) as page:
        pixels = [page.frame(n) for n in (0, 5)]
        out = page._page.evaluate("window.__out")
    loaded = out["load"]
    assert loaded["t0"] == pytest.approx(5.0) and loaded["first"] == 40 and loaded["bands"] == 16
    assert loaded["tracks"] == ["kick", "clap", "cello", "pad"] and loaded["kind"] == "drum" and loaded["score"] == "tune.yaml"
    assert loaded["section"] == "a" and loaded["kicks"] == 8 and loaded["now"] == pytest.approx(5.0)
    assert loaded["notes"][:2] == [[0, 50, "pizzicato", False], [0.5, 52, "spiccato", False]] and loaded["notes"][3][3] is True
    assert loaded["last"] == 5.0 and loaded["sounding"] == [55]
    assert loaded["pulse"][0] == pytest.approx(1.0) and loaded["pulse"][1] == pytest.approx(np.exp(-1.0), rel=1e-3)
    assert "no track 'nope'" in out["error"] and loaded["all"] > loaded["kicks"]
    assert loaded["level"] == pytest.approx(_series(data, "level")[40 - data["from"]], abs=1e-6)
    t, now, at, _ = out["frames"][1]
    assert t == 0.5 and now == pytest.approx(5.5) and at == pytest.approx(5.5)
    for n, picture in zip((0, 5), pixels):
        assert abs(int(picture[0, 0, 0]) - round(low[40 + n - data["from"]] * 255)) <= 1

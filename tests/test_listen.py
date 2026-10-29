"""The Listen page (``vidgen music page``, DESIGN.md §92): the clips cover every bed and every
built-in sound, the committed ``docs/music`` is current, links only files that exist, stays within
its size budget, and the command writes the same files twice."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from vidgen import ambience, cli, listen, music, sfx

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "music"
#: What the committed page may weigh (page + MP3s + PNGs), see HANDOFF.md Step 183 (5.5 MB then;
#: 6.3 MB with the two score beds of Step 190; 6.6 MB with the story sounds and beds of Step 246).
BUDGET = 6_800_000


def test_clips_start_where_the_bed_shows_itself() -> None:
    assert listen.bed_clip_start("calm") == 0.0
    lift = music.BUILTIN_BEDS["breakthrough"].seconds / 2   # 25.714 s
    assert listen.bed_clip_start("breakthrough") == pytest.approx(lift - listen.CLIP_LEAD_SECONDS, abs=0.01)
    assert listen.bed_clip_start("momentum") == pytest.approx(48.0 - listen.CLIP_LEAD_SECONDS)
    assert set(listen.CLIP_MOMENTS) <= set(music.BUILTIN_BEDS)
    # Step 190: the score beds' clips lead into their lift (tidewater 26.664 s, skyline 30 s)
    assert listen.bed_clip_start("tidewater") == pytest.approx(26.664 - listen.CLIP_LEAD_SECONDS, abs=0.01)
    assert listen.bed_clip_start("skyline") == pytest.approx(30.0 - listen.CLIP_LEAD_SECONDS)
    # Step 192: time_of_flight's too (26.664 s), where its Step 189 piece clip started
    assert listen.bed_clip_start("time_of_flight") == pytest.approx(26.664 - listen.CLIP_LEAD_SECONDS, abs=0.01) == 20.66


def test_sound_rows_play_every_builtin_sound_inside_the_clip() -> None:
    played = {name for row in listen.SOUND_ROWS for _, name, _, _ in row.events}
    assert played == set(sfx.BUILTIN_SOUNDS)
    for row in listen.SOUND_ROWS:
        times = [at for at, _, _, _ in row.events]
        assert times == sorted(times), row.name
        for at, name, _, duration in row.events:
            assert at + (duration or sfx.BUILTIN_SOUNDS[name].duration) <= row.seconds, (row.name, name)


def test_events_text_groups_a_run_of_one_sound() -> None:
    row = listen.SoundRow("x", "x", 3.0, ((0.3, "whoosh", 0.0, None), (1.0, "pop", 0.0, None), (1.4, "pop", 2.0, None), (2.0, "tick", 0.0, None)))
    assert listen._events_text(row) == "0.3 s `whoosh`, 1, 1.4 s `pop` (pitch 0, +2), 2 s `tick`"


def test_spectrogram_puts_a_tone_on_its_row() -> None:
    t = np.arange(2 * sfx.RATE) / sfx.RATE
    tone = 0.1 * np.sin(2 * np.pi * 1000.0 * t)
    levels = listen.spectrogram_levels(tone)
    assert levels.shape == (listen.SPECTROGRAM_HEIGHT, 2 * listen.SPECTROGRAM_PX_PER_SECOND)
    sound = np.where(levels == listen._GRID_INDEX, 0, levels)
    rows = np.geomspace(listen.SPECTROGRAM_HZ[1], listen.SPECTROGRAM_HZ[0], listen.SPECTROGRAM_HEIGHT)
    assert abs(rows[int(np.argmax(sound[:, 32]))] - 1000.0) < 60
    silent = listen.spectrogram_levels(np.zeros(sfx.RATE))
    assert set(np.unique(silent)) == {0, listen._GRID_INDEX}


def test_gain_keeps_the_peak_under_the_ceiling() -> None:
    loud = np.full((10, 1), 0.5)
    assert np.max(listen._gained(loud, 12.0)) == pytest.approx(10 ** (listen.PEAK_CEILING_DB / 20))
    quiet = np.full((10, 1), 0.01)
    assert np.max(listen._gained(quiet, 12.0)) == pytest.approx(0.01 * 10 ** 0.6)


# ----- the committed page ------------------------------------------------------------------------


def _page() -> str:
    return (DOCS / "README.md").read_text(encoding="utf-8")


def test_committed_page_is_current() -> None:
    page = _page()
    expected = listen.page_text([], "x")
    common = expected[: expected.index("No clips here")]
    assert page.startswith(common), "docs/music/README.md is old: run `vidgen music page`"
    assert "Do not edit by hand" in page
    for name in music.BUILTIN_BEDS:
        assert f"| `{name}` | {listen._bed_facts(music.BUILTIN_BEDS[name])} |" in page


def test_committed_page_links_only_files_that_exist_and_every_file_is_linked() -> None:
    page = _page()
    linked = set(re.findall(r"\]\((media/[^)]+)\)", page)) | set(re.findall(r'src="(media/[^"]+)"', page))
    for rel in linked:
        assert (DOCS / rel).is_file(), rel
    on_disk = {p.relative_to(DOCS).as_posix() for p in (DOCS / "media").iterdir()}
    assert on_disk == linked, f"not linked: {sorted(on_disk - linked)}"
    names = [f"bed-{n}" for n in music.BUILTIN_BEDS]
    names += [row.name for row in listen.SOUND_ROWS] + ["ambience"]
    for name in names:
        assert f"media/{name}.mp3" in linked and f"media/{name}.png" in linked


def test_committed_media_sizes_and_formats() -> None:
    files = [p for p in DOCS.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    assert total < BUDGET, f"docs/music is {total / 1e6:.1f} MB (budget {BUDGET / 1e6:g} MB)"
    assert {p.suffix for p in files} <= {".md", ".mp3", ".png"}
    for mp3 in DOCS.glob("media/*.mp3"):
        head = mp3.read_bytes()[:2]
        assert head[0] == 0xFF and head[1] & 0xE0 == 0xE0, f"{mp3.name}: not a bare MP3 frame (tags?)"
        if mp3.name.startswith(("bed-", "composed-")):
            assert 200_000 <= mp3.stat().st_size <= 320_000, mp3.name
    for png in DOCS.glob("media/*.png"):
        assert png.stat().st_size <= 80_000, png.name
        with Image.open(png) as image:
            assert image.mode == "P" and image.height == listen.SPECTROGRAM_HEIGHT
            if png.name.startswith("bed-"):
                assert image.width == round(listen.CLIP_SECONDS * listen.SPECTROGRAM_PX_PER_SECOND)


def test_score_pieces_are_beds_and_the_page_shows_how_they_were_made() -> None:
    """Step 192: the showcase's pieces are score beds; their rows link the example (its log) and
    the bed's own clip (no second copy of the media)."""
    page = _page()
    section = page[page.index("## Made with the score format"): page.index("## Sound effects")]
    for anchor in ("score-files-vidgen-music-render", "templates-of-the-built-in-beds-vidgen-music-template",
                   "checking-a-piece-vidgen-music-check", "project-pieces-score-files-in-a-video"):
        assert f"(../CONFIG.md#{anchor})" in section
    assert "(../COOKBOOK-MUSIC.md)" in section and "<img" not in section
    assert [p.name for p in listen.SCORE_PIECES] == ["time_of_flight"]
    for piece in listen.SCORE_PIECES:
        assert music.BUILTIN_BEDS[piece.name].score
        example = ROOT / "examples" / piece.example
        assert (example / "README.md").is_file() and f"music: {piece.name}" in (example / "video.yaml").read_text(encoding="utf-8")
        assert f"| `{piece.name}`<br>" in section and f"(../../examples/{piece.example}/README.md)" in section
        assert f"(media/bed-{piece.name}.mp3)" in section
        assert listen.piece_score(piece).title == "Time of Flight"
    assert not list(DOCS.glob("media/piece-*"))


def test_readme_names_the_real_counts_and_links_the_page() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    headline = readme[: readme.index("schu-video-generator is a tool")]
    assert f"{len(music.BUILTIN_BEDS)} original music beds" in headline
    assert f"{len(sfx.BUILTIN_SOUNDS)} sound effects" in headline
    assert "(docs/music/README.md)" in headline
    assert "music studio" in headline and "(docs/CONFIG.md#music-studio-vidgen-studio)" in headline
    section = readme[readme.index("**Music and sound.**"): readme.index("Everything is built around")]
    assert f"**{len(music.BUILTIN_BEDS)} synthesised music beds**" in section
    assert f"**{len(sfx.BUILTIN_SOUNDS)} synthesised sound effects" in section
    assert "docs/music/README.md" in section and "docs/CONFIG.md#background-music-music" in section
    assert all(bed.replace("_", " ") in section for bed in ambience.AMBIENCE_BEDS)


# ----- the command -------------------------------------------------------------------------------


def test_music_page_command_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(music, "BUILTIN_BEDS", {"calm": music.BUILTIN_BEDS["calm"]})
    monkeypatch.setattr(listen, "SOUND_ROWS", (listen.SoundRow("sfx-two", "Two", 1.0, ((0.1, "pop", 0.0, None), (0.5, "click", 0.0, None))),))
    monkeypatch.setattr(ambience, "AMBIENCE_BEDS", ("rain",))
    monkeypatch.setattr(listen, "SCORE_PIECES", ())
    monkeypatch.setattr(listen, "CLIP_SECONDS", 2.0)
    outputs = []
    for name in ("a", "b"):
        assert cli.main(["music", "page", "--out", str(tmp_path / name), "--no-composed", "--json"]) == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["ok"] and doc["action"] == "page" and doc["composed"] is False and doc["composed_note"]
        assert [Path(p).name for p in doc["clips"]] == ["bed-calm.mp3", "sfx-two.mp3", "ambience.mp3"]
        outputs.append({Path(p).name: Path(p).read_bytes() for p in doc["clips"] + doc["spectrograms"] + [doc["page"]]})
    assert outputs[0] == outputs[1]
    page = outputs[0]["README.md"].decode("utf-8")
    assert "No clips here: when this page was made, composed clips were turned off." in page
    with Image.open(tmp_path / "a" / "media" / "bed-calm.png") as image:
        assert image.size == (2 * listen.SPECTROGRAM_PX_PER_SECOND, listen.SPECTROGRAM_HEIGHT)

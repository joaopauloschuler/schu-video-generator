"""``vidgen music plan`` (Step 359, DESIGN.md §121.2): a music video's scenes proposed from a score
file without playing it: roles of the sections, cuts on bar lines (long sections split on a phrase
line, short ones joined), moments (drops, breaths, silent bars, risers), a colour per scene, the
tracks each scene follows, and the draft project it writes (validated, not rendered). The three
film scores' plans against their real cuts. In Chromium (``slow``): one still of a drafted page."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from vidgen.cli import main
from vidgen.errors import VidgenError
from vidgen.music_video_plan import (
    LOOK_WORDS,
    ROLE_LOOKS,
    ROLES,
    plan_dict,
    plan_music_video,
    plan_text,
    role_colours,
    starter_page,
    write_music_video,
)
from vidgen.project import Project

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

# 120 BPM: a bar is 2 s. intro 4 | verse 16 (a hat and a bell come in at its bar 9) | rise 4 (a riser) |
# drop 8 | quiet 4 (a silent bar, then a lone note) | coda 2 (joined to quiet: 4 s is under 5 s)
SCORE = """
version: 1
title: Test Form
key: A minor
tempo: 120
time: 4/4
loop: false
progression: "i VI III VII"
sections:
  - {name: intro, bars: 4}
  - {name: verse, bars: 8}
  - {name: verse_b, bars: 8, progression: "i VI III VII"}
  - {name: rise, bars: 4}
  - {name: drop, bars: 8}
  - {name: quiet, bars: 4}
  - {name: coda, bars: 2}
tracks:
  pad:
    instrument: pad
    play: chords
    rest: [quiet]
  kick:
    instrument: kick
    steps: "x... x... x... x..."
    only: [verse, verse_b, rise, drop]
  hat:
    instrument: hat
    steps: "x.x. x.x. x.x. x.x."
    only: [verse_b, rise, drop]
  clap:
    instrument: clap
    steps: "....x.......x..."
    only: [drop]
  bell:
    instrument: bell
    steps: "1.3. 5... 3.1. 8..."
    only: [verse_b, drop, coda]
  riser:
    instrument: riser
    steps: "x............... | ................ | ................ | ................"
    only: [rise]
  lone:
    instrument: bell
    steps: "................ | ................ | ................ | 1..............."
    only: [quiet]
"""


QUIET8 = " | ".join(["................"] * 8)


def _score(tmp_path: Path, text: str = SCORE, name: str = "form.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_sections_get_roles_from_their_names_and_their_energy(tmp_path: Path) -> None:
    plan = plan_music_video(_score(tmp_path))
    roles = {s.name: (s.role, s.why) for s in plan.sections}
    assert roles["intro"][0] == "intro" and roles["drop"][0] == "drop" and roles["coda"][0] == "outro"
    assert roles["rise"][0] == "build"
    assert roles["quiet"] == ("breakdown", "much sparser than the one before")
    assert plan.mode == "minor" and plan.bar_seconds == pytest.approx(2.0) and plan.tail == 3.0
    assert all(s.role in ROLES and 0 <= s.energy <= 1 for s in plan.sections)


def test_cuts_are_on_bar_lines_long_sections_split_short_ones_joined(tmp_path: Path) -> None:
    plan = plan_music_video(_score(tmp_path))
    cuts = [(c.id, c.first_bar, c.bars) for c in plan.scenes]
    assert cuts == [("01_intro", 0, 4), ("02_verse", 4, 8), ("03_verse_b", 12, 8), ("04_rise", 20, 4), ("05_drop", 24, 8), ("06_quiet", 32, 6)]
    assert "with coda" in plan.scenes[-1].why
    # whole frames from bar line to bar line; the last scene holds the tail
    assert [c.frames for c in plan.scenes] == [240, 480, 480, 240, 480, 450]
    assert plan.scenes[-1].end == pytest.approx(76 + 3)
    # one 16-bar section longer than --max-scene is cut in two on its phrase line; a shorter one only
    # where the material changes
    long_one = SCORE.replace("  - {name: verse, bars: 8}\n  - {name: verse_b, bars: 8, progression: \"i VI III VII\"}\n",
                             "  - {name: verse, bars: 16}\n").replace("only: [verse_b, rise, drop]", "only: [rise, drop]") \
        .replace("only: [verse, verse_b, rise, drop]", "only: [verse, rise, drop]").replace("only: [verse_b, drop, coda]", "only: [drop, coda]")
    plan = plan_music_video(_score(tmp_path, long_one, "long.yaml"))
    assert [(c.first_bar, c.bars) for c in plan.scenes if c.section == "verse"] == [(4, 8), (12, 8)]
    assert "longer than 16 s" in plan.scenes[1].why
    steady = plan_music_video(_score(tmp_path, long_one, "long.yaml"), max_seconds=40)
    assert [(c.first_bar, c.bars) for c in steady.scenes if c.section == "verse"] == [(4, 16)]      # nothing changes in it
    # a 16-bar section whose second half brings in new tracks: split for the material even under --max-scene
    two_halves = SCORE.replace("  - {name: verse, bars: 8}\n  - {name: verse_b, bars: 8, progression: \"i VI III VII\"}\n",
                               "  - {name: verse, bars: 16}\n").replace("[verse, verse_b, rise, drop]", "[verse, rise, drop]") \
        .replace("only: [verse_b, rise, drop]", f"only: [verse, rise, drop]\n    sections: {{verse: {{steps: \"{QUIET8} | x.x. x.x. x.x. x.x.\"}}}}") \
        .replace("only: [verse_b, drop, coda]", f"only: [verse, drop, coda]\n    sections: {{verse: {{steps: \"{QUIET8} | 1.3. 5... 3.1. 8...\"}}}}")
    plan = plan_music_video(_score(tmp_path, two_halves, "halves.yaml"), max_seconds=40)
    assert [(c.first_bar, c.bars) for c in plan.scenes if c.section == "verse"] == [(4, 8), (12, 8)]
    assert "the material changes" in plan.scenes[1].why


def test_moments_drops_breaths_silent_bars_and_risers(tmp_path: Path) -> None:
    plan = plan_music_video(_score(tmp_path))
    kinds = {(m.kind, m.bar) for m in plan.moments}
    assert ("riser", 20) in kinds
    assert ("silent", 32) in kinds and ("silent", 33) in kinds         # the pad rests in quiet; its first bars are empty
    assert any(k == "drop" for k, _ in kinds)
    drops = sorted(b for k, b in kinds if k == "drop")
    assert all(b2 - b1 > 2 for b1, b2 in zip(drops, drops[1:]))       # one drop, not one per bar of it
    rise = next(c for c in plan.scenes if c.section == "rise")
    assert [m.kind for m in rise.moments] == ["riser"]
    beats = " | ".join(["x... x... x... x..."] * 3 + ["................", "x... x... x... x..."] + ["x... x... x... x..."] * 3)
    breath = SCORE.replace("only: [verse, verse_b, rise, drop]", f"only: [verse, verse_b, rise, drop]\n    sections: {{verse_b: {{steps: \"{beats}\"}}}}")
    breath = breath.replace("only: [verse_b, rise, drop]", "only: [rise, drop]").replace("only: [verse_b, drop, coda]", "only: [drop, coda]")
    found = [(m.kind, m.bar) for m in plan_music_video(_score(tmp_path, breath, "breath.yaml")).moments if m.kind == "breath"]
    assert ("breath", 15) in found


def test_reactions_follow_what_each_track_is(tmp_path: Path) -> None:
    plan = plan_music_video(_score(tmp_path))
    drop = next(c for c in plan.scenes if c.section == "drop")
    assert drop.react == {"pulse": ("kick",), "ring": ("clap",), "glint": ("bell",), "glow": ("pad",)}
    assert plan.track_reactions["hat"] is None and plan.track_reactions["riser"] is None
    intro = plan.scenes[0]
    assert intro.react["pulse"] == () and intro.react["glow"] == ("pad",) and intro.tracks == ["pad"]
    assert set(plan.scenes[2].enters) >= {"bell", "hat"}


def test_the_colour_script_runs_cool_to_warm_and_the_mode_tints_it() -> None:
    def hue(hex_colour: str) -> float:
        import colorsys

        r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return colorsys.rgb_to_hls(r, g, b)[0] * 360

    intro, climax = role_colours("intro", 0.3, "minor"), role_colours("climax", 1.0, "minor")
    assert 180 < hue(intro["base"]) < 240 and hue(climax["base"]) < 60
    assert hue(role_colours("intro", 0.3, "minor")["base"]) > hue(role_colours("intro", 0.3, "major")["base"])   # minor: bluer
    assert all(re.fullmatch(r"#[0-9a-f]{6}", v) for v in climax.values())
    assert set(ROLE_LOOKS) == set(ROLES) and set(ROLE_LOOKS.values()) == set(LOOK_WORDS)


def test_every_look_is_a_starter_page_on_the_kit() -> None:
    for look in LOOK_WORDS:
        text = starter_page(look).read_text(encoding="utf-8")
        assert 'from "vidgen/music-time"' in text and 'from "vidgen/three-kit"' in text and 'from "vidgen/three-finish"' in text
        assert "reactions(M, D.react" in text and "colourScript(D.script)" in text and "Math.random" not in text
        assert "export function load(ctx)" in text and "export function frame(t)" in text
    with pytest.raises(VidgenError, match="no starter page 'nope'"):
        starter_page("nope")


def test_the_plan_in_words_and_as_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    score = _score(tmp_path)
    text = plan_text(plan_music_video(score))
    assert "05_drop" in text and "reacts to brightness pulse: kick; rings of light: clap; glints: bell; glow level: pad" in text
    assert main(["music", "plan", str(score), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "music" and doc["action"] == "plan" and doc["ok"] and doc["draft"] is None
    assert [s["first_bar"] for s in doc["scenes"]] == [1, 5, 13, 21, 25, 33] and doc["scenes"][4]["react"]["ring"] == ["clap"]
    assert doc["tracks"]["clap"] == "ring" and {m["kind"] for m in doc["moments"]} >= {"riser", "silent", "drop"}
    assert doc["scenes"] == plan_dict(plan_music_video(score))["scenes"]


def test_user_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    score = _score(tmp_path)
    assert main(["music", "plan"]) == 1
    assert "give the score file" in capsys.readouterr().err
    audio = tmp_path / "x.mp3"
    audio.write_bytes(b"")
    assert main(["music", "plan", str(audio)]) == 1
    assert "is not a score file" in capsys.readouterr().err
    assert main(["music", "plan", "calm"]) == 1
    assert "vidgen music template calm --out calm.yaml" in capsys.readouterr().err
    with pytest.raises(VidgenError, match="--min-scene"):
        plan_music_video(score, max_seconds=4, min_seconds=8)
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "x.txt").write_text("x", encoding="utf-8")
    with pytest.raises(VidgenError, match="not empty"):
        write_music_video(plan_music_video(score), busy)


def test_the_draft_project_validates(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    score = _score(tmp_path)
    out = tmp_path / "draft"
    assert main(["music", "plan", str(score), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "created" in printed and "next: vidgen still" in printed
    config = yaml.safe_load((out / "video.yaml").read_text(encoding="utf-8"))
    assert config["music"]["source"] == "assets/music/form.yaml" and (out / "assets" / "music" / "form.yaml").is_file()
    assert config["transition"] == "cut" and (out / "extensions" / "web_cut.py").is_file()
    scenes = config["scenes"]
    assert [s["type"] for s in scenes] == ["web_cut"] * 6 and [s["duration"] for s in scenes] == [8, 16, 16, 8, 16, 15]
    drop = scenes[4]["params"]
    assert drop["script"] == "extensions/05_drop.js" and drop["music_data"] == {"tracks": ["kick", "clap", "bell", "pad"]}
    assert drop["data"]["look"] == "swarm" and drop["data"]["start"] == 48 and drop["data"]["script"][4]["at"] == 48
    assert scenes[5]["params"]["data"]["until"] == 79 and scenes[5]["params"]["data"]["end"] == 76
    for s in scenes:
        assert (out / s["params"]["script"]).read_text(encoding="utf-8") == starter_page(s["params"]["data"]["look"]).read_text(encoding="utf-8")
    project = Project.load(out)
    assert [s.id for s in project.config.scenes] == [s["id"] for s in scenes]
    assert main(["validate", str(out)]) == 0
    capsys.readouterr()
    # the score inside the folder is used where it is; --force writes again
    inside = tmp_path / "own"
    (inside / "assets" / "music").mkdir(parents=True)
    shutil.copyfile(score, inside / "assets" / "music" / "form.yaml")
    assert main(["music", "plan", str(inside / "assets" / "music" / "form.yaml"), "--out", str(inside), "--force", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["draft"]["problems"] == [] and "assets/music/form.yaml" not in doc["draft"]["files"]


def _cut_bars(config: Path, bar: float) -> list[int]:
    """The bar lines (0-based) where a film's scenes start."""
    scenes = yaml.safe_load(config.read_text(encoding="utf-8"))["scenes"]
    starts, t = [], 0.0
    for s in scenes:
        starts.append(round(t / bar))
        t += s["duration"]
    return starts


@pytest.mark.parametrize("example, score, relation", [
    ("escapement", "escapement.yaml", "same"),
    ("signal-fire", "signal_fire.yaml", "same"),
    ("parallel-space", "parallel_space.yaml", "more"),     # the film keeps pulse and heart + heart2 as 16-bar scenes
])
def test_the_film_scores_plans_against_their_real_cuts(example: str, score: str, relation: str) -> None:
    plan = plan_music_video(EXAMPLES / example / "assets" / "music" / score)
    proposed = [c.first_bar for c in plan.scenes]
    real = _cut_bars(EXAMPLES / example / "video.yaml", plan.bar_seconds)
    if relation == "same":
        assert proposed == real
    else:
        assert set(real) < set(proposed) and len(proposed) == len(real) + 2


@pytest.mark.slow
@pytest.mark.render
def test_a_drafted_page_draws_a_still(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    short = SCORE.replace("tempo: 120", "tempo: 240")
    out = tmp_path / "draft"
    assert main(["music", "plan", str(_score(tmp_path, short)), "--out", str(out), "--min-scene", "2"]) == 0
    png = tmp_path / "drop.png"
    assert main(["still", str(out), "--scene", "05_drop", "--at", "1", "--size", "160x90", "--out", str(png)]) == 0
    import numpy as np
    from PIL import Image

    pixels = np.asarray(Image.open(png).convert("RGB")).astype(float)
    assert pixels.shape == (90, 160, 3) and pixels.mean() > 5 and pixels.std() > 5     # crystals and a sky, not a blank frame

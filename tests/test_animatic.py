"""``vidgen animatic`` (Step 138): the still timing plan, captions, and one tiny animatic."""

from __future__ import annotations

from pathlib import Path

import av
import numpy as np
import pytest
from PIL import Image

from test_json_output import documented, run_json
from test_render import make_tone, streams, write_project
from vidgen import cli
from vidgen.animatic import AnimaticStill, Hold, captions_default, draw_captions, hold_plan, with_captions
from vidgen.project import Project
from vidgen.render.ffmpeg import write_concat_list
from vidgen.subtitles import Cue


def still(scene: str, time: float, beat: str | None = "b", mid: str | None = None) -> AnimaticStill:
    return AnimaticStill(scene, beat, time, Path(f"{scene}-{time}.png"), mid)


def spans(holds: list[Hold]) -> list[tuple[str, float, int, int]]:
    return [(h.still.scene_id, h.still.time, h.start, h.end) for h in holds]


# ----- the plan (no rendering) ---------------------------------------------------------------------


def test_each_still_is_held_until_the_next_one() -> None:
    # beat ends at 2.0 and 5.0, a mid-action still at 3.5; 10 fps, 6 s
    holds = hold_plan([(0.0, [still("a", 5.0), still("a", 2.0), still("a", 3.5, mid="walk_to pip")])], 60, 10)
    assert spans(holds) == [("a", 2.0, 0, 35), ("a", 3.5, 35, 50), ("a", 5.0, 50, 60)]
    assert holds[1].still.mid == "walk_to pip"


def test_a_scene_opens_on_its_own_first_still() -> None:
    holds = hold_plan([(0.0, [still("a", 1.0), still("a", 2.0)]), (3.0, [still("b", 4.5), still("b", 6.0)])], 70, 10)
    # b's first still is shown from b's start (3.0 s), not after a's last still runs on to 4.5 s
    assert spans(holds) == [("a", 1.0, 0, 20), ("a", 2.0, 20, 30), ("b", 4.5, 30, 60), ("b", 6.0, 60, 70)]


def test_overlapping_scenes_and_shared_frames() -> None:
    # b starts at 2.5 s (a crossfade): a's still at 2.8 s would show inside b and is left out;
    # two stills on one frame: the later one wins
    b_stills = [still("b", 3.0), still("b", 3.01), still("b", 3.02), still("b", 4.0)]
    holds = hold_plan([(0.0, [still("a", 1.0), still("a", 2.8)]), (2.5, b_stills)], 50, 10)
    assert spans(holds) == [("a", 1.0, 0, 25), ("b", 3.0, 25, 30), ("b", 3.02, 30, 40), ("b", 4.0, 40, 50)]
    # a silent scene's single still (beat None) and a video with one still
    assert spans(hold_plan([(0.0, [still("q", 0.8, beat=None)])], 9, 10)) == [("q", 0.8, 0, 9)]
    assert hold_plan([], 10, 10) == []


def test_captions_cut_the_holds() -> None:
    a, b = still("a", 1.0), still("a", 3.0)
    holds = [Hold(a, 0, 10), Hold(b, 10, 30)]
    cues = [Cue(0.2, 1.4, "One"), Cue(1.4, 2.0, "Two"), Cue(1.8, 2.5, "Over"), Cue(2.5, 2.5, "Empty")]
    got = [(h.still.time, h.start, h.end, h.captions) for h in with_captions(holds, cues, 10)]
    assert got == [
        (1.0, 0, 2, ()), (1.0, 2, 10, ("One",)),
        (3.0, 10, 14, ("One",)), (3.0, 14, 18, ("Two",)), (3.0, 18, 20, ("Two", "Over")), (3.0, 20, 25, ("Over",)),
        (3.0, 25, 30, ()),
    ]
    assert with_captions(holds, [], 10) == holds


def test_drawn_captions_stay_at_the_bottom() -> None:
    image = Image.new("RGB", (320, 180), (40, 90, 160))
    drawn = np.asarray(draw_captions(image, ["A short line\nand a second one"]), dtype=int)
    changed = np.argwhere(np.abs(drawn - np.asarray(image, dtype=int)).sum(axis=2) > 0)
    assert len(changed) and changed[:, 0].min() > 90 and changed[:, 0].max() < 180 - 5
    assert draw_captions(image, []) is image


def test_concat_list_with_durations(tmp_path: Path) -> None:
    files = [tmp_path / "a.png", tmp_path / "b's.png"]
    write_concat_list(files, tmp_path / "list.txt", [1.5, 0.25])
    assert (tmp_path / "list.txt").read_text(encoding="utf-8") == (
        "file 'a.png'\nduration 1.500000\nfile 'b'\\''s.png'\nduration 0.250000\nfile 'b'\\''s.png'\n"
    )


def test_names_options_and_defaults(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"scenes": [{"id": "s", "type": "text_card", "params": {"text": "A"}, "beats": [{"text": "Hi."}]}],
                                          "variants": {"v": {}}})
    assert Project.load(root).animatic_path() == root / "output" / "out_animatic.mp4"
    assert Project.load(root, variant="v", output_dir=tmp_path / "o").animatic_path() == tmp_path / "o" / "out_v_animatic.mp4"
    assert captions_default(Project.load(root))
    write_project(root, {"scenes": [{"id": "s", "type": "text_card", "params": {"text": "A"}, "beats": [{"text": "Hi."}]}],
                         "overlays": [{"type": "captions"}]})
    assert not captions_default(Project.load(root))
    parser = cli.build_parser()
    assert parser.parse_args(["animatic"]).captions is None
    args = parser.parse_args(["animatic", "x", "--no-captions", "--no-audio", "--variant", "v", "--output-dir", "o", "-j", "auto"])
    assert (args.captions, args.no_audio, args.variant, args.output_dir, args.jobs) == (False, True, "v", "o", "auto")
    assert parser.parse_args(["animatic", "--captions"]).captions is True


# ----- a tiny animatic -------------------------------------------------------------------------------


@pytest.mark.render
@pytest.mark.slow
def test_tiny_animatic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {"scenes": [
        {"id": "m", "type": "bullets", "params": {"items": ["First point", "Second point"]},
         "beats": [{"text": "One point."}, {"text": "And a second, longer point to read."}]},
        {"id": "q", "type": "text_card", "params": {"text": "Quiet"}, "duration": 1.0},
    ]})
    make_tone(root / "audio" / "m_b1.mp3", 0.8)
    code, doc, _ = run_json(["animatic", str(root), "--json"], capsys)
    assert code == 0 and doc["command"] == "animatic"
    assert doc["rendered"] == ["m", "q"] and doc["reused"] == [] and doc["captions"] is True and doc["audio"] is True
    assert doc["format"] == {"width": 96, "height": 54, "fps": 5}
    output = Path(doc["output"])
    assert output == (root / "output" / "out_animatic.mp4").resolve()
    stills = doc["stills"]
    assert [(s["scene"], s["beat"]) for s in stills] == [("m", "m_b1"), ("m", "m_b2"), ("q", None)]
    assert stills[0]["start"] == 0 and stills[-1]["end"] == pytest.approx(doc["duration"])
    assert all(a["end"] == b["start"] for a, b in zip(stills, stills[1:]))
    assert stills[1]["start"] == pytest.approx(stills[1]["time"], abs=0.2)  # held from its time
    info = streams(output)
    assert info["types"] == ["video", "audio"] and (info["width"], info["height"]) == (96, 54)
    with av.open(str(output)) as container:
        assert container.streams.video[0].frames == round(doc["duration"] * 5)
    assert info["audio"] == pytest.approx(doc["duration"], abs=0.05)
    documented("captions", "stills", "output")

    # the stills are current: nothing is rendered, only ffmpeg runs; without captions the
    # frame in a hold is its still
    stamp = (root / "build" / "preview" / "scenes" / "m.mp4").stat().st_mtime_ns
    code, doc, _ = run_json(["animatic", str(root), "--json", "--no-captions", "--no-audio"], capsys)
    assert doc["rendered"] == [] and doc["reused"] == ["m", "q"] and doc["mix"] is None
    assert (root / "build" / "preview" / "scenes" / "m.mp4").stat().st_mtime_ns == stamp
    last = stills[-1]
    with av.open(str(output)) as container:
        frame = list(container.decode(video=0))[round(last["start"] * 5) + 1].to_ndarray(format="rgb24").astype(int)
    with Image.open(last["path"]) as image:
        expected = np.asarray(image.convert("RGB"), dtype=int)
    assert np.abs(frame - expected).mean() < 6

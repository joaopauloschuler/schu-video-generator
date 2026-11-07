"""Generated video in the film (DESIGN.md §113.4): QA of returned clips (synthetic MP4s made by
FFmpeg: a moving pattern, colour bars, black, frozen, flickering, a cut), contact sheets, takes
and picks, placing takes over their beats (cover crop, fades, colour matching, overlays on top,
fingerprints), the run / status / takes / pick workflow with the mock provider (budget, stop on
the first failure, no second payment), the credit line and the disclosure lint. Nothing is sent
or paid: the model list is the fixture of 2026-11-07, the provider the mock."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import av
import numpy as np
import pytest
import yaml
from conftest import minimal_config

from vidgen import cli
from vidgen.errors import VidgenError
from vidgen.generated_layer import color_gains
from vidgen.project import Project
from vidgen.videogen.compose import credit_line, scene_placements
from vidgen.videogen.ledger import Ledger
from vidgen.videogen.mock import MockOpenRouter, MockVideoProvider, clip_size, synthetic_clip
from vidgen.videogen.models import Catalog, parse_models
from vidgen.videogen.qa import check_clip, contact_sheet
from vidgen.videogen.run import ledger_path
from vidgen.videogen.shots import project_shots
from vidgen.videogen.takes import add_take, chosen_take, load_picks, pick_take, takes_of
from vidgen.videogen.workflow import DISCLOSURE, run_shots, status_lines

DATA = Path(__file__).parent / "data" / "openrouter_video_models.json"
CATALOG = Catalog(tuple(parse_models(json.loads(DATA.read_text(encoding="utf-8")))), 0.0, "cache")
W, H = 90, 160   # a 9:16 video


def clip(tmp_path: Path, name: str, pattern: str = "testsrc", seconds: float = 2.0, size: tuple[int, int] = (72, 128), audio: bool = False) -> Path:
    return synthetic_clip(tmp_path / "clips" / f"{name}.mp4", *size, seconds, fps=12, pattern=pattern, audio=audio)  # type: ignore[arg-type]


def names(report: Any) -> dict[str, str]:
    return {c.name: c.severity for c in report.checks}


# ----- QA ------------------------------------------------------------------------------------------


def test_qa_passes_a_good_clip_and_notes_its_sound(tmp_path: Path) -> None:
    report = check_clip(clip(tmp_path, "good", audio=True), length=2.0, width=W, height=H)
    assert names(report) == {"sound": "info"} and report.summary() == "QA ok"
    assert report.metrics["flicker"] < 3 and report.metrics["black_share"] == 0


@pytest.mark.parametrize(
    ("pattern", "check", "severity"),
    [("black", "black", "error"), ("bars", "frozen", "error"), ("frozen", "frozen", "warning"), ("flicker", "flicker", "warning"), ("cut", "cuts", "warning")],
)
def test_qa_finds_bad_clips(tmp_path: Path, pattern: str, check: str, severity: str) -> None:
    report = check_clip(clip(tmp_path, pattern, pattern, seconds=3.0), length=3.0, width=W, height=H)
    assert names(report).get(check) == severity, report.lines()
    assert ("flicker" in names(report)) == (pattern == "flicker")


def test_qa_duration_aspect_and_size(tmp_path: Path) -> None:
    wide = clip(tmp_path, "wide", size=(64, 36), seconds=1.0)
    report = check_clip(wide, length=2.0, width=W, height=H)
    found = names(report)
    assert found["duration"] == found["aspect"] == found["size"] == "warning"
    assert "cuts off 68% of the picture" in report.lines()[2] or any("68%" in c.message for c in report.checks)
    assert any("its last frame holds for 1.00 s" in c.message for c in report.checks)


def test_contact_sheet(tmp_path: Path) -> None:
    path = clip(tmp_path, "good")
    report = check_clip(path, length=2.0, width=W, height=H)
    out = contact_sheet(path, tmp_path / "sheet.png", title="shot x, take 1", report=report, count=6, columns=3, thumb=64)
    from PIL import Image

    with Image.open(out) as image:
        assert image.width == 3 * (36 + 6) + 6 and image.height > 2 * 64


def test_mock_returns_a_playable_clip_shaped_like_the_request() -> None:
    assert clip_size("9:16", "480p") == (480, 853) and clip_size("16:9", None) == (640, 360) and clip_size(None, None, "320x240") == (320, 240)
    api = MockOpenRouter()
    provider = MockVideoProvider(api)
    from vidgen.videogen import VideoRequest

    job = provider.submit(VideoRequest(model="google/veo-3.1-lite", prompt="x", duration=2, resolution="360p", aspect_ratio="9:16"), ())
    data = api.content(job.id)
    assert data[4:8] == b"ftyp"
    import io

    with av.open(io.BytesIO(data)) as container:
        stream = container.streams.video[0]
        assert (stream.codec_context.width, stream.codec_context.height) == (360, 640)
        assert not container.streams.audio


# ----- takes and picks -------------------------------------------------------------------------------


def test_takes_dedupe_number_and_pick(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    good, black = clip(tmp_path, "good"), clip(tmp_path, "black", "black")
    one, new = add_take(root, "s1", good, key="k1", model="a/b", provider="mock", job_id="j1", cost=0.1, length=2.0, width=W, height=H)
    again, new2 = add_take(root, "s1", good, key="k1", model="a/b", provider="mock", job_id="j1", cost=0.1, length=2.0, width=W, height=H)
    two, _ = add_take(root, "s1", black, key="k2", model="a/b", provider="mock", job_id="j2", cost=0.1, length=2.0, width=W, height=H)
    assert (one.number, new, again.number, new2, two.number) == (1, True, 1, False, 2)
    assert one.path == root / "takes" / "s1" / "1.mp4" and one.contact.is_file() and two.qa_errors == 1
    assert chosen_take(root, "s1").number == 1            # the newest without QA errors
    assert pick_take(root, "s1", "2", ["s1"]).number == 2  # picked by hand: shown anyway
    assert load_picks(root) == {"s1": 2}
    assert pick_take(root, "s1", "none", ["s1"]) is None and chosen_take(root, "s1") is None
    assert pick_take(root, "s1", "auto", ["s1"]).number == 1 and load_picks(root) == {}
    with pytest.raises(VidgenError, match="no take '7'; takes: 1, 2"):
        pick_take(root, "s1", "7", ["s1"])
    with pytest.raises(VidgenError, match=r"did you mean s1\?"):
        pick_take(root, "s1x", "1", ["s1"])
    assert [t.number for t in takes_of(root, "s1")] == [1, 2]


# ----- placing ---------------------------------------------------------------------------------------


def test_color_gains() -> None:
    grey = np.full((4, 4, 3), 118, dtype=np.uint8)
    assert np.allclose(color_gains(grey, 1.0), 1.0)
    cast = np.dstack([np.full((4, 4), v, dtype=np.uint8) for v in (135, 118, 100)])
    gains = color_gains(cast, 1.0)
    balanced = cast[0, 0] * gains
    assert balanced.max() - balanced.min() < 2          # the cast is evened out
    strong = np.dstack([np.full((4, 4), v, dtype=np.uint8) for v in (150, 118, 90)])
    spread = strong[0, 0] * color_gains(strong, 1.0)
    assert spread.max() - spread.min() < 60 / 5         # a strong one partly: each gain stays within 0.8-1.25
    half = color_gains(cast, 0.5)
    assert 1.0 > half[0] > gains[0] and np.allclose(color_gains(cast, 0.0), 1.0)
    dark = np.full((2, 2, 3), 40, dtype=np.uint8)
    assert np.allclose(color_gains(dark, 1.0), 1.25)     # exposure, within the limits


def film_config(**videogen: Any) -> dict[str, Any]:
    """A tiny 9:16 film: a card, then a beat with an establishing shot, then a closing beat."""
    return minimal_config(
        format={"width": W, "height": H, "fps": 5},
        preview={"width": W, "height": H, "fps": 5},
        narration={"pad": 0.2, "words_per_second": 4.0},
        videogen={"provider": "mock", "budget_usd": 1.0, **videogen},
        overlays=[{"type": "watermark", "image": "assets/logo.png", "opacity": 1.0}],
        scenes=[
            {"id": "a", "type": "text_card", "params": {"text": "Hi"}, "beats": [
                {"id": "one", "text": "One two three four five six."},
                {"id": "wide", "text": "Seven eight nine ten eleven twelve.",
                 "generated_shot": {"kind": "establishing", "model": "google/veo-3.1-lite", "setting": "a harbour"}},
                {"id": "end", "text": "Thirteen fourteen fifteen sixteen."},
            ]},
            {"id": "b", "type": "text_card", "params": {"text": "Bye"}, "beats": [
                {"id": "last", "text": "Seventeen eighteen nineteen twenty.",
                 "generated_shot": {"kind": "establishing", "model": "google/veo-3.1-lite", "setting": "a quay", "fit": "contain"}},
            ]},
        ],
    )


def logo(root: Path) -> None:
    from PIL import Image

    (root / "assets").mkdir(exist_ok=True)
    Image.new("RGBA", (40, 40), (255, 255, 255, 255)).save(root / "assets" / "logo.png")


def test_placements_windows_fades_and_fingerprints(make_project, tmp_path: Path) -> None:
    from vidgen.render.fingerprint import scene_fingerprint

    root = make_project(film_config())
    logo(root)
    project = Project.load(root)
    before = scene_fingerprint(project, "a")
    assert scene_placements(project) == [] and credit_line(project) == ""
    add_take(root, "wide", clip(tmp_path, "good", seconds=4.0), key="k1", model="google/veo-3.1-lite", provider="mock", job_id="j", cost=0.12, length=1.8, width=W, height=H)
    add_take(root, "last", clip(tmp_path, "good2", seconds=4.0), key="k2", model="google/veo-3.1-lite", provider="mock", job_id="j2", cost=0.12, length=1.2, width=W, height=H)
    project = Project.load(root)
    placed = scene_placements(project)
    wide, last = placed
    shots = {s.id: s for s in project_shots(project, CATALOG)}
    assert wide.scene == "a" and wide.start == pytest.approx(shots["wide"].start) and wide.length == pytest.approx(shots["wide"].length)
    assert (wide.fade_in, wide.fade_out) == (0.25, 0.25)       # vidgen's picture on both sides
    assert last.start == 0 and (last.fade_in, last.fade_out) == (0.0, 0.0)   # the scene's only beat: through its end
    assert last.length == pytest.approx(shots["last"].scene_end - shots["last"].scene_start) and last.fit == "contain"
    after = scene_fingerprint(project, "a")
    assert after != before
    pick_take(root, "wide", "none", ["wide", "last"])
    assert scene_fingerprint(Project.load(root), "a") == before and [p.shot for p in scene_placements(Project.load(root))] == ["last"]
    assert credit_line(Project.load(root)) == "Includes AI-generated footage (google/veo-3.1-lite)."
    assert scene_placements(Project.load(root, draft=True)) == []       # drafts and guide renders: vidgen's own picture
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["scenes"][1]["beats"][0]["generated_shot"]["place"] = False
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert scene_placements(Project.load(root)) == []


def frames_of(path: Path) -> list[tuple[float, np.ndarray]]:
    with av.open(str(path)) as container:
        return [(float(f.time), f.to_ndarray(format="rgb24").astype(int)) for f in container.decode(video=0)]


@pytest.mark.render
def test_render_lays_takes_under_the_overlays(make_project, tmp_path: Path) -> None:
    from vidgen.render.pipeline import current_render, render_project

    root = make_project(film_config(color_match=0.0))
    logo(root)
    plain = render_project(Project.load(root), preview=True)
    timings = plain.timings
    bare = frames_of(plain.output)
    import shutil
    import subprocess

    blue = tmp_path / "blue.mp4"   # a solid colour, 16:9, with a sound of its own (never used)
    subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x2060c0:s=160x90:r=12:d=4",
                    "-f", "lavfi", "-i", "sine=f=440:d=4", "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv444p", "-c:a", "aac", "-shortest", str(blue)], check=True)
    add_take(root, "wide", blue, key="k1", model="google/veo-3.1-lite", provider="mock", job_id="j", cost=0.12, length=1.8, width=W, height=H)
    project = Project.load(root)
    assert scene_placements(project) == []                  # a still picture is a QA error: not shown unless picked
    pick_take(root, "wide", "1", ["wide", "last"])
    project = Project.load(root)
    assert not current_render(project, True, "a", False) and current_render(project, True, "b", False)
    result = render_project(project, preview=True)
    assert result.rendered == ["a"] and result.duration == pytest.approx(plain.duration)
    beat = next(b for b in result.timings["scenes"][0]["beats"] if b["id"] == "wide")
    nxt = next(b for b in result.timings["scenes"][0]["beats"] if b["id"] == "end")
    middle = (beat["start"] + nxt["start"]) / 2
    shown = frames_of(result.output)
    t, frame = min(shown, key=lambda f: abs(f[0] - middle))
    pixels = frame.reshape(-1, 3)
    near = np.abs(pixels - np.array([0x20, 0x60, 0xC0])).max(axis=1) < 24
    white = (pixels > 235).all(axis=1)
    assert near.mean() > 0.8, "the take fills the frame (cover crop of a 16:9 clip)"
    assert white.sum() >= 8, "the watermark (a 4 x 4 px square at this size) is drawn over the take"
    first = min(shown, key=lambda f: abs(f[0] - 0.6))[1]
    same = min(bare, key=lambda f: abs(f[0] - 0.6))[1]
    assert np.abs(first - same).max() <= 2, "the beats without a shot keep vidgen's picture"
    assert not (np.abs(min(bare, key=lambda f: abs(f[0] - middle))[1].reshape(-1, 3) - [0x20, 0x60, 0xC0]).max(axis=1) < 24).mean() > 0.5
    from vidgen.render.worker import scene_timings_path

    scene_timings = json.loads(scene_timings_path(project, True, "a").read_text(encoding="utf-8"))
    assert scene_timings["generated"] == [{"shot": "wide", "take": 1, "model": "google/veo-3.1-lite", "start": pytest.approx(beat["start"], abs=0.21),
                                           "length": pytest.approx(nxt["start"] - beat["start"], abs=0.21)}]
    assert timings["duration"] == pytest.approx(result.timings["duration"])
    description = project.chapters_path(True).read_text(encoding="utf-8")
    assert "Includes AI-generated footage (google/veo-3.1-lite)." in description


# ----- the workflow ------------------------------------------------------------------------------------


def wide_config(budget: float | None = 1.0) -> dict[str, Any]:
    beats = [
        {"id": "w1", "text": "One two three four.", "generated_shot": {"kind": "establishing", "model": "google/veo-3.1-lite", "setting": "a harbour"}},
        {"id": "w2", "text": "Five six seven eight.", "generated_shot": {"kind": "establishing", "model": "google/veo-3.1-lite", "setting": "a quay"}},
    ]
    return minimal_config(format={"width": W, "height": H, "fps": 5}, videogen={"provider": "mock", "budget_usd": budget},
                          scenes=[{"id": "s", "type": "text_card", "params": {"text": "x"}, "beats": beats}])


def quiet(line: str) -> None:
    return None


def test_run_dry_then_pay_then_cached(make_project) -> None:
    project = Project.load(make_project(wide_config()))
    api = MockOpenRouter(cost=0.12)
    lines: list[str] = []
    report = run_shots(project, catalog=CATALOG, provider=MockVideoProvider(api), out=lines.append)
    assert [s.status for s in report.shots] == ["would_generate", "would_generate"] and api.requests == []
    assert not (project.root / "takes").exists() and "dry run: nothing was sent or paid" in lines[-1]
    report = run_shots(project, pay=True, catalog=CATALOG, provider=MockVideoProvider(api), out=lines.append)
    assert [s.status for s in report.shots] == ["paid", "paid"] and len(api.submits) == 2 and report.cost_usd == pytest.approx(0.24)
    assert [s.take.number for s in report.shots] == [1, 1] and all(s.take.qa["summary"] == "QA ok" for s in report.shots)
    assert api.submits[0].body["generate_audio"] is False
    again = run_shots(project, pay=True, catalog=CATALOG, provider=MockVideoProvider(api), out=quiet)
    assert [s.status for s in again.shots] == ["cached", "cached"] and len(api.submits) == 2 and not any(s.new_take for s in again.shots)
    lines, doc = status_lines(project, CATALOG)
    assert doc["credit"] == "Includes AI-generated footage (google/veo-3.1-lite)." and DISCLOSURE in lines
    assert [s["shown"] for s in doc["shots"]] == [1, 1]


def test_run_refuses_without_budget_or_over_it(make_project) -> None:
    api = MockOpenRouter()
    project = Project.load(make_project(wide_config(budget=None)))
    with pytest.raises(VidgenError, match="--pay needs a budget"):
        run_shots(project, pay=True, catalog=CATALOG, provider=MockVideoProvider(api), out=quiet)
    with pytest.raises(VidgenError, match="nothing was paid"):
        run_shots(project, pay=True, budget_usd=0.2, catalog=CATALOG, provider=MockVideoProvider(api), out=quiet)   # 2 x $0.12
    assert api.requests == []


def test_run_stops_at_the_first_failure_without_retrying(make_project) -> None:
    project = Project.load(make_project(wide_config()))
    api = MockOpenRouter(states=("pending", "failed"), error="Output flagged by moderation", cost=None)
    with pytest.raises(VidgenError, match="shot w1 failed, the run stopped") as caught:
        run_shots(project, pay=True, catalog=CATALOG, provider=MockVideoProvider(api), out=quiet)
    assert len(api.submits) == 1 and caught.value.details["shots"][0]["status"] == "failed"
    jobs = Ledger(ledger_path(project.root, "mock")).jobs()
    assert [j.status for j in jobs] == ["failed"]


def test_cli_run_status_takes_pick(make_project, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_project(wide_config())
    monkeypatch.setattr("vidgen.videogen.workflow.load_catalog", lambda: CATALOG)
    monkeypatch.setattr("vidgen.videogen.models.load_catalog", lambda *a, **k: CATALOG)
    assert cli.main(["generate", "run", str(root)]) == 0
    assert "would generate" in capsys.readouterr().out
    assert cli.main(["generate", "run", str(root), "--pay", "--shot", "w1"]) == 0
    out = capsys.readouterr().out
    assert "shot w1: paid, $0.250: new take 1 (takes/w1/1.mp4, QA ok)" in out and "w2" not in out
    assert cli.main(["generate", "takes", str(root), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["shots"][0]["takes"][0]["contact_sheet"] == "takes/w1/1.contact.png" and doc["shots"][1]["takes"] == []
    assert cli.main(["generate", "pick", str(root), "--shot", "w1", "--take", "none"]) == 0
    assert "shows vidgen's own picture" in capsys.readouterr().out
    assert cli.main(["generate", "status", str(root)]) == 0
    assert "vidgen's own picture is shown (picked none)" in capsys.readouterr().out
    assert cli.main(["generate", "pick", str(root), "--shot", "w1x", "--take", "1"]) == 1
    assert "did you mean w1?" in capsys.readouterr().err
    assert cli.main(["generate", "status", str(root), "--pay"]) == 1


def test_disclosure_lint_rule() -> None:
    from vidgen.lint.rules import RULES, SceneContext

    entry = RULES["generated_footage"]
    assert entry.default == "info" and entry.scope == "scene"
    ctx = SceneContext("s", {"beats": []}, Path("."))
    from vidgen.config import GeneratedFootageRule

    assert list(entry.check(ctx, GeneratedFootageRule())) == []
    ctx.generated = [("w1", 2, "google/veo-3.1-lite")]
    issue = next(iter(entry.check(ctx, GeneratedFootageRule())))
    assert "w1 (take 2, google/veo-3.1-lite)" in issue.message and "Altered or synthetic content" in issue.message

"""``vidgen studio`` Step 197 (DESIGN.md §94.15): the check from kept stems (the same report as
``vidgen music check``) with advice that carries machine-applicable edits, the background checker
that newer versions supersede, versions / undo / redo / rename / star, exports (YAML, WAV, MP3,
lengths and levels) and saving into a project's ``assets/music/`` with the Step 188 name rule."""

from __future__ import annotations

import json
import threading
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from tests.test_studio_app import TINY, request
from vidgen import loudness
from vidgen.errors import VidgenError
from vidgen.sfx import RATE
from vidgen.studio import check_music_score, music_check_text, parse_music_score
from vidgen.studio.check import Finding, Fix, check_dict
from vidgen.studio.render import render_track_stem
from vidgen.studio_app.app import StudioApp, check_text
from vidgen.studio_app.checks import Checker
from vidgen.studio_app.edits import apply_edits
from vidgen.studio_app.exports import export_audio, file_name, save_to_project
from vidgen.studio_app.server import start_in_thread

#: A piano too loud in the voice's range in the lift (the check advises lowering it or an octave up).
LOUD = {
    "title": "Loud piano",
    "key": "A minor", "tempo": 120, "progression": "i VI III VII",
    "sections": [{"name": "intro", "bars": 2}, {"name": "build", "bars": 4}, {"name": "lift", "bars": 4}],
    "tracks": {
        "pad": {"instrument": "pad", "play": "chords", "volume": -6},
        "piano": {"instrument": "piano", "steps": "* . * . * . * .", "octave": 4, "volume": 4, "only": ["lift"]},
    },
}


@pytest.fixture
def app(tmp_path: Path) -> Any:
    studio = StudioApp(None, studio=tmp_path / "studio")
    yield studio
    studio.close()


def _wait(app: StudioApp, version: int | None = None) -> dict[str, Any]:
    for _ in range(20):
        doc = app.check(version, wait=30)
        if doc["status"] == "done":
            return doc
    raise AssertionError(f"no check: {doc}")


# ----- the check's advice as edits ------------------------------------------------------------------


def test_a_fix_is_text_that_carries_edits() -> None:
    fix = Fix("lower `pad.volume: -8`", [("lower pad by 2 dB", [{"op": "set", "path": "tracks.pad.volume", "value": -8}]), None, ("empty", [])])
    assert fix == "lower `pad.volume: -8`" and isinstance(fix, str) and json.dumps([fix]) == '["lower `pad.volume: -8`"]'
    finding = Finding("bass", "fix", "boomy", ["plain words", fix])
    assert finding.edits == [{"fix": 1, "label": "lower pad by 2 dB", "ops": [{"op": "set", "path": "tracks.pad.volume", "value": -8}]}]


def test_advice_edits_apply_to_the_score_and_the_cli_report_is_unchanged() -> None:
    text = yaml.safe_dump(LOUD, sort_keys=False)
    report = check_music_score(parse_music_score(LOUD, "loud.yaml"))
    voice = next(f for f in report.findings if f.topic == "voice range")
    assert voice.level == "fix"
    labels = [e["label"] for e in voice.edits]
    assert any(label.startswith("lower piano by ") for label in labels) and "move piano an octave up (octave 5)" in labels
    assert all(0 <= e["fix"] < len(voice.fixes) for e in voice.edits)
    for edit in voice.edits:  # each applies and gives a valid score that changed what it says
        new = apply_edits(text, edit["ops"])
        data, score, problems = check_text(new)
        assert problems == [] and new != text
        if "octave" in edit["label"]:
            assert data["tracks"]["piano"]["octave"] == 5
        else:
            assert data["tracks"]["piano"]["volume"] < 4
    doc = check_dict(report)
    assert set(doc["findings"][0]) == {"topic", "level", "text", "fixes"}  # `music check --json` as before
    assert "Apply" not in music_check_text(report)


def test_build_advice_adds_a_riser_with_a_free_name() -> None:
    data = {**LOUD, "tracks": {"pad": {"instrument": "pad", "play": "chords"}, "riser": {"instrument": "pad", "play": "chords", "only": ["intro"]}}}
    report = check_music_score(parse_music_score(data, "flat.yaml"))
    edits = [e for f in report.findings if f.topic == "sections" for e in f.edits]
    add = next(e for e in edits if e["label"].startswith("add a riser"))
    assert add["ops"][0]["path"] == "tracks.riser_2" and add["ops"][0]["value"]["only"] == ["build"]
    assert any(e["ops"][0]["value"] == {"from": -6, "to": 0} for e in edits)
    text = yaml.safe_dump(data, sort_keys=False)
    for edit in edits:
        assert check_text(apply_edits(text, edit["ops"]))[2] == [], edit


def test_the_check_from_kept_stems_is_the_cli_check() -> None:
    score = parse_music_score(LOUD, "loud.yaml")
    whole = check_dict(check_music_score(score))
    calls: list[int] = []
    stems = [render_track_stem(score, t.name) for t in score.tracks]
    kept = check_dict(check_music_score(score, tracks=stems, between=lambda: calls.append(1)))
    whole.pop("timings")
    kept.pop("timings")
    assert kept == whole and len(calls) >= len(score.tracks) + 3

    def stop() -> None:
        raise RuntimeError("stop")

    with pytest.raises(RuntimeError):
        check_music_score(score, tracks=stems, between=stop)


# ----- the background check in the studio -----------------------------------------------------------


def test_studio_check_is_kept_and_its_advice_applied_as_a_version(app: StudioApp) -> None:
    app.load(text=yaml.safe_dump(LOUD, sort_keys=False))
    app.render()
    doc = _wait(app)
    assert doc["version"] == 1 and doc["level"] == "fix" and doc["verdict"].startswith("needs work")
    names = [h["name"] for h in doc["headline"]]
    assert names[:3] == ["voice", "bass", "highs"] and "lift" in names and names[-1] == "loudness"
    assert next(h for h in doc["headline"] if h["name"] == "voice")["level"] == "fix"
    assert doc["text"].startswith("Loud piano:") and doc["image"]["url"] == f"/media/{doc['key']}-check.png"
    assert app.media_file(f"{doc['key']}-check.png") is not None and app.media_file("../session.json") is None
    began = time.perf_counter()
    assert app.check(1)["status"] == "done" and time.perf_counter() - began < 0.5  # kept: not made again
    edit = next(e for f in doc["findings"] for e in f["edits"] if "octave" in e["label"])
    state = app.apply_check(1, doc["key"], edit["id"])
    v2 = state["session"]["versions"][-1]
    assert state["score"]["version"] == 2 and v2["origin"] == "check" and v2["label"] == "check: move piano an octave up (octave 5)" and v2["parent"] == 1
    with pytest.raises(VidgenError, match="other notes"):
        app.apply_check(2, doc["key"], edit["id"])
    with pytest.raises(VidgenError, match="no advice"):
        app.apply_check(1, doc["key"], "99.0")


def test_a_newer_check_supersedes_one_waiting_for_renders(tmp_path: Path) -> None:
    idle = threading.Event()
    asked: list[str] = []

    def stems(data: Any, score: Any, key: str) -> tuple[list[Any], None]:
        asked.append(key)
        return [render_track_stem(score, t.name) for t in score.tracks], None

    checker = Checker(idle.is_set, stems)
    _, score, _ = check_text(TINY)
    first = checker.want(tmp_path, "a" * 20, None, score)
    time.sleep(0.2)  # waiting: a render is under way
    second = checker.want(tmp_path, "b" * 20, None, score)
    idle.set()
    assert first.result(timeout=30) is None  # superseded before it measured anything
    doc = second.result(timeout=60)
    assert doc is not None and doc["key"] == "b" * 20 and asked == ["b" * 20]
    assert checker.kept(tmp_path, "b" * 20) == doc and checker.kept(tmp_path, "a" * 20) is None
    checker.close()


# ----- versions -------------------------------------------------------------------------------------


def test_undo_redo_branches_rename_and_star(app: StudioApp) -> None:
    app.load(text=TINY)
    for tempo in (100, 110):
        app.edit(None, [{"op": "set", "path": "tempo", "value": tempo}])
    s = app.session
    assert s is not None and s.current == 3 and app.state()["session"]["can_undo"] and not app.state()["session"]["can_redo"]
    assert app.undo()["score"]["version"] == 2
    assert app.undo()["score"]["version"] == 1
    assert app.undo()["score"]["version"] == 1  # nothing before the first
    assert app.redo()["score"]["version"] == 2
    assert app.state()["session"]["can_redo"]
    # an edit after an undo starts a branch: redo is forgotten, nothing deleted
    state = app.edit(None, [{"op": "set", "path": "tempo", "value": 90}])
    assert state["score"]["version"] == 4 and state["session"]["versions"][-1]["parent"] == 2
    assert not state["session"]["can_redo"] and app.redo()["score"]["version"] == 4
    assert app.set_current(3)["score"]["version"] == 3 and app.undo()["score"]["version"] == 2
    session = app.update_version(3, label="  the  fast one ", starred=True)["session"]
    v3 = next(v for v in session["versions"] if v["number"] == 3)
    assert v3["label"] == "the fast one" and v3["starred"] is True
    with pytest.raises(VidgenError):
        app.update_version(3, label=" ")
    with pytest.raises(VidgenError):
        app.set_current(9)


def test_sessions_are_listed_and_reopened(app: StudioApp) -> None:
    first = app.load(text=TINY)["session"]["id"]
    time.sleep(1.05)  # session ids have a second's resolution
    app.load(text=TINY.replace("Tiny", "Second"))
    listed = app.sessions()
    assert [s["title"] for s in listed][:2] == ["Second", "Tiny"] and listed[0]["open"]
    assert app.open_session(first)["session"]["id"] == first
    with pytest.raises(VidgenError):
        app.open_session("../x")


# ----- exports ----------------------------------------------------------------------------------------


def test_export_lengths_and_levels() -> None:
    score = parse_music_score(yaml.safe_load(TINY), "tiny.yaml")
    once, facts = export_audio(score, "once", None, "video")
    assert len(once) == score.samples and facts["loudness"] == pytest.approx(-28.0, abs=0.1)
    loops, _ = export_audio(score, "loops", 3, "video")
    assert len(loops) == 3 * score.samples and np.array_equal(loops[: score.samples], once)
    secs, facts = export_audio(score, "seconds", 10, "listening")
    assert len(secs) == 10 * RATE and abs(float(secs[-1].max())) < 1e-3
    assert facts["true_peak"] <= -1.0 + 0.05 and facts["loudness"] > -20
    for length, count in (("loops", 0), ("loops", 2.5), ("seconds", 0.5), ("sometimes", 1)):
        with pytest.raises(VidgenError):
            export_audio(score, length, count, "video")
    with pytest.raises(VidgenError, match="level"):
        export_audio(score, "once", None, "loud")
    one_pass = parse_music_score({**yaml.safe_load(TINY), "loop": False}, "x.yaml")
    with pytest.raises(VidgenError, match="plays once"):
        export_audio(one_pass, "loops", 2, "video")
    assert file_name("Momentum (template)", 3, "yaml") == "momentum-template-v3.yaml"
    assert file_name("Tiny", 2, "mp3", "seconds", 12.5, "listening") == "tiny-v2-12_5s-listening.mp3"
    assert file_name("", 1, "wav", "loops", 4) == "piece-v1-4loops-video.wav"


def test_exports_are_written_in_the_session_and_downloaded(app: StudioApp) -> None:
    app.load(text=TINY)
    yaml_doc = app.export(None, "yaml")
    assert yaml_doc["url"] == "/download/tiny-v1.yaml"
    path = app.download_file("tiny-v1.yaml")
    assert path is not None and path.read_text(encoding="utf-8") == TINY and path.parent == app.session.folder / "exports"
    wav_doc = app.export(1, "wav", "loops", 2, "video")
    with wave.open(str(app.download_file(wav_doc["name"])), "rb") as w:
        assert w.getnframes() == 2 * 4 * RATE and w.getnchannels() == 2
    assert app.download_file("../session.json") is None and app.download_file(".partial-x.wav") is None
    with pytest.raises(VidgenError, match="format"):
        app.export(1, "flac")


def test_save_to_project_follows_the_name_rule(tmp_path: Path) -> None:
    with pytest.raises(VidgenError, match="without a project"):
        save_to_project(None, "x", TINY)
    root = tmp_path / "proj"
    root.mkdir()
    with pytest.raises(VidgenError, match="built-in bed"):
        save_to_project(root, "calm", TINY)
    for bad in ("My Theme", "../x", "a/b", ""):
        with pytest.raises(VidgenError, match="not a piece name"):
            save_to_project(root, bad, TINY)
    done = save_to_project(root, "my_theme", TINY)
    assert done["saved"] and done["path"] == "assets/music/my_theme.yaml" and done["snippet"] == "music: my_theme"
    assert (root / "assets" / "music" / "my_theme.yaml").read_text(encoding="utf-8") == TINY
    again = save_to_project(root, "my_theme", "title: other\n")
    assert again == {"saved": False, "exists": True, "path": "assets/music/my_theme.yaml", "name": "my_theme", "message": "assets/music/my_theme.yaml exists: overwrite it?"}
    assert save_to_project(root, "my_theme", "title: other\n", overwrite=True)["exists"]
    (root / "assets" / "music" / "old.yml").write_text("x: 1\n", encoding="utf-8")
    assert save_to_project(root, "old", TINY, overwrite=True)["path"] == "assets/music/old.yml"


def test_routes(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "video.yaml").write_text("title: t\n", encoding="utf-8")
    app = StudioApp(root, studio=tmp_path / "studio")
    srv, thread = start_in_thread(app)
    try:
        app.load(text=TINY)
        app.edit(None, [{"op": "set", "path": "tempo", "value": 100}])
        status, _, body = request(srv, "POST", "/api/undo", {})
        assert status == 200 and json.loads(body)["result"]["score"]["version"] == 1
        status, _, body = request(srv, "POST", "/api/current", {"version": 2})
        assert json.loads(body)["result"]["score"]["version"] == 2
        status, _, body = request(srv, "POST", "/api/version", {"version": 2, "starred": "yes"})
        assert status == 400
        status, _, body = request(srv, "POST", "/api/export", {"format": "yaml"})
        name = json.loads(body)["result"]["name"]
        status, headers, data = request(srv, "GET", f"/download/{name}")
        assert status == 200 and headers["content-disposition"] == f'attachment; filename="{name}"' and b"tempo: 100" in data
        assert request(srv, "GET", "/download/..%2Fsession.json")[0] == 404
        status, _, body = request(srv, "POST", "/api/save", {"name": "calm"})
        assert status == 400 and "built-in bed" in json.loads(body)["error"]
        status, _, body = request(srv, "POST", "/api/save", {"name": "tiny_theme"})
        assert json.loads(body)["result"]["snippet"] == "music: tiny_theme" and (root / "assets" / "music" / "tiny_theme.yaml").is_file()
        app.render()
        status, _, body = request(srv, "POST", "/api/check", {"version": 2, "wait": 30})
        doc = json.loads(body)["result"]
        while doc["status"] == "pending":
            doc = json.loads(request(srv, "POST", "/api/check", {"version": 2, "wait": 30})[2])["result"]
        status, headers, data = request(srv, "GET", doc["image"]["url"])
        assert status == 200 and headers["content-type"] == "image/png" and data[:4] == b"\x89PNG"
        assert request(srv, "GET", "/api/sessions")[0] == 200
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(5)
        app.close()

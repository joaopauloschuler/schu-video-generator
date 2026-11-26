"""The WebGL backend in a render's identity (Step 436): a scene drawn in Chromium is reused only
when it was drawn with the backend asked for now (``VIDGEN_WEBGL``); ``vidgen remote`` passes this
computer's ``VIDGEN_WEBGL`` to the run on the VM. No rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vidgen import colab_vm
from vidgen.browser.chromium import WEBGL_ENV
from vidgen.project import Project
from vidgen.remote import run_webgl
from vidgen.render.pipeline import _record_webgl, _usable_render, scene_webgl
from vidgen.render.worker import scene_timings_path, scene_video_path


def _rendered(make_project: Any, webgl: str | None) -> Project:
    """A project with a ``web`` scene ``w`` and a ``text_card`` scene ``t``, each with a finished
    render on disk whose record says ``webgl`` (``None``: says nothing, as before Step 436)."""
    from conftest import minimal_config

    root = make_project(minimal_config(scenes=[
        {"id": "w", "type": "web", "params": {"script": "page.js"}, "beats": [{"text": "A page."}]},
        {"id": "t", "type": "text_card", "params": {"text": "x"}, "beats": [{"text": "A card."}]},
    ]))
    (root / "page.js").write_text("export function frame() {}\n", encoding="utf-8")
    project = Project.load(root)
    fmt = project.render_format(False)
    for sid in ("w", "t"):
        video, timings = scene_video_path(project, False, sid), scene_timings_path(project, False, sid)
        video.parent.mkdir(parents=True, exist_ok=True)
        timings.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"mp4")
        meta: dict[str, Any] = {"width": fmt.width, "height": fmt.height, "fps": fmt.fps, "audio": True, "frames": 0, "guide_passes": []}
        if webgl is not None:
            meta["webgl"] = webgl
        timings.write_text(json.dumps({"beats": [], "render": meta}), encoding="utf-8")
    return project


def test_scenes_drawn_in_chromium_record_the_backend_after_a_render(make_project: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _rendered(make_project, None)
    monkeypatch.delenv(WEBGL_ENV, raising=False)
    assert scene_webgl(project, "w") == "swiftshader" and scene_webgl(project, "t") is None
    monkeypatch.setenv(WEBGL_ENV, "GPU")
    assert scene_webgl(project, "w") == "gpu" and scene_webgl(project, "t") is None
    assert _record_webgl(project, False, "w")["render"]["webgl"] == "gpu"
    assert "webgl" not in _record_webgl(project, False, "t")["render"]
    saved = json.loads(scene_timings_path(project, False, "w").read_text(encoding="utf-8"))
    assert saved["render"]["webgl"] == "gpu" and saved["render"]["width"] == project.render_format(False).width


@pytest.mark.parametrize(("recorded", "asked", "reused"), [
    ("gpu", "swiftshader", False),       # the Phase 3 case: a GPU render is not reused for software WebGL
    ("gpu", "gpu", True),
    ("swiftshader", "gpu", False),
    ("swiftshader", "", True),           # unset: swiftshader
    (None, "", True),                    # an older render (no record): counted as swiftshader
    (None, "swiftshader", True),
    (None, "gpu", False),
])
def test_a_web_render_is_reused_only_under_the_backend_it_was_drawn_with(
        make_project: Any, monkeypatch: pytest.MonkeyPatch, recorded: str | None, asked: str, reused: bool) -> None:
    project = _rendered(make_project, recorded)
    monkeypatch.setenv(WEBGL_ENV, asked)
    assert _usable_render(project, False, "w", False) is reused
    assert _usable_render(project, False, "t", False) is True   # not drawn in Chromium: the backend does not matter


def test_vidgen_remote_passes_this_computers_backend_to_the_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(WEBGL_ENV, raising=False)
    assert run_webgl() == {"VIDGEN_RUN_WEBGL": ""}
    monkeypatch.setenv(WEBGL_ENV, " SwiftShader ")
    assert run_webgl() == {"VIDGEN_RUN_WEBGL": "swiftshader"}
    env_file = tmp_path / "vidgen.env"
    env_file.write_text("VIDGEN_WEBGL=gpu\nLD_LIBRARY_PATH=/nv\n", encoding="utf-8")
    monkeypatch.delenv(WEBGL_ENV, raising=False)
    assert colab_vm.child_env({"VIDGEN_RUN_WEBGL": ""}, env_file)["VIDGEN_WEBGL"] == "gpu"       # the VM's own
    child = colab_vm.child_env({"VIDGEN_RUN_WEBGL": "swiftshader"}, env_file)
    assert child["VIDGEN_WEBGL"] == "swiftshader" and child["LD_LIBRARY_PATH"] == "/nv"

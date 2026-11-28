"""Step 341: a scene of an extension type that subclasses ``Web`` is
rendered again when its script, a file the script imports or a file it fetches changes; a
``script:`` whose module waits for several fetches becomes ready.

The project here is laid out like the film that found the fault: ``extensions/webcut.py``
(``class WebCut(Web)`` with ``outro = 0.0``), ``params: {script: extensions/x.js, data: {...}}``,
the script importing ``./helper.js`` and fetching ``./x_audio.json`` beside it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from vidgen import extensions
from vidgen.browser import chromium
from vidgen.project import Project
from vidgen.web.entry import WebEntry, is_web_type
from vidgen.web.page import WebPage

WEBCUT = '''from vidgen.api import scene
from vidgen.scenes.web import Web


@scene("web_cut")
class WebCut(Web):
    outro = 0.0
'''
SCRIPT = '''import {shade} from "./helper.js";
const AU = await (await fetch(new URL("./x_audio.json", import.meta.url))).json();
let extra = 0;
const late = await fetch(new URL("./late.json", import.meta.url));
if (late.ok) extra = (await late.json()).v;
document.body.style.background = shade(AU.level + extra);
'''
FILES = {
    "extensions/webcut.py": WEBCUT,
    "extensions/x.js": SCRIPT,
    "extensions/helper.js": "export function shade(v) { return `rgb(${Math.round(v * 255)}, 40, 40)`; }\n",
    "extensions/x_audio.json": '{"level": 0.5}\n',
}


def film_project(make_project: Any) -> Project:
    """Two ``web_cut`` scenes and one ``web`` scene on the same script, as in the film."""
    scenes = [{"id": sid, "type": kind, "duration": 1, "params": {"script": "extensions/x.js", "data": {"mode": sid}}}
              for sid, kind in (("a_cut", "web_cut"), ("b_cut", "web_cut"), ("c_web", "web"))]
    root = make_project({"title": "F", "format": {"width": 160, "height": 90, "fps": 5},
                         "preview": {"width": 80, "height": 46, "fps": 5}, "transition": "cut", "scenes": scenes})
    for name, text in FILES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return Project.load(root)


def _sha(root: Path, rel: str) -> str:
    return hashlib.sha256((root / rel).read_bytes()).hexdigest()


def _append(path: Path, text: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def test_a_type_that_subclasses_web_is_a_web_type(make_project: Any) -> None:
    project = film_project(make_project)
    assert is_web_type("web") and not is_web_type("web_cut")   # no project active: only web itself is known
    with extensions.project_session(project):
        assert is_web_type("web_cut") and is_web_type("web")
        assert not is_web_type("title") and not is_web_type("3d") and not is_web_type("no_such_type")


@pytest.mark.parametrize("scene_id", ["a_cut", "c_web"])
def test_the_fingerprint_of_a_web_subclass_follows_its_script_and_loaded_files(make_project: Any, scene_id: str) -> None:
    from vidgen.render.fingerprint import drawn_fingerprint, fingerprint_inputs, scene_fingerprint

    project = film_project(make_project)
    root = project.root
    with extensions.project_session(project):
        before = fingerprint_inputs(project, scene_id)   # as the worker takes them when a first render starts
        assert before["web"]["path"] == "extensions/x.js" and before["web"]["sha256"] == _sha(root, "extensions/x.js")
        assert before["web"]["loaded"] == {}
        # the first render's record: the script, what it imports, what it fetches, one file not found
        loaded = {rel: _sha(root, rel) for rel in ("extensions/x.js", "extensions/helper.js", "extensions/x_audio.json")}
        record = root / "build" / "final" / "web" / f"{scene_id}.json"
        record.parent.mkdir(parents=True)
        record.write_text(json.dumps({"key": "k", "loaded": {**loaded, "extensions/late.json": None}}), encoding="utf-8")
        stored = drawn_fingerprint(before, project, False, scene_id)
        assert stored == scene_fingerprint(project, scene_id)   # the next run reuses the render
        for rel, text in (("extensions/x.js", "// edited\n"), ("extensions/helper.js", "// edited\n"),
                          ("extensions/x_audio.json", " "), ("extensions/late.json", '{"v": 0.1}')):
            kept = (root / rel).read_bytes() if (root / rel).exists() else None
            _append(root / rel, text) if kept is not None else (root / rel).write_text(text, encoding="utf-8")
            assert scene_fingerprint(project, scene_id) != stored, rel
            (root / rel).write_bytes(kept) if kept is not None else (root / rel).unlink()
            assert scene_fingerprint(project, scene_id) == stored, rel


def _chromium_or_skip() -> None:
    pytest.importorskip("playwright.sync_api")
    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")


@pytest.mark.slow
@pytest.mark.render
def test_edits_render_the_film_layout_again(make_project: Any) -> None:
    """Real renders: nothing changed -> every scene reused; an edit to the script, to the file it
    imports, to the file it fetches, or a file it asked for appearing -> every scene on that
    script rendered again (final, preview and with two jobs); ``--force`` draws the frames again."""
    _chromium_or_skip()
    from vidgen.render.pipeline import render_project

    project = film_project(make_project)
    ext = project.root / "extensions"
    everything = ["a_cut", "b_cut", "c_web"]

    def rendered(**options: Any) -> list[str]:
        return sorted(render_project(project, **options).render_seconds)

    assert rendered() == everything
    assert rendered() == []
    _append(ext / "x.js", "// edited\n")
    assert rendered() == everything
    _append(ext / "helper.js", "// edited\n")
    assert rendered() == everything
    (ext / "x_audio.json").write_text('{"level": 0.7}\n', encoding="utf-8")
    assert rendered(jobs=2) == everything
    (ext / "late.json").write_text('{"v": 0.1}\n', encoding="utf-8")   # asked for and not found until now
    assert rendered() == everything
    (ext / "late.json").write_text('{"v": 0.2}\n', encoding="utf-8")   # in the record only since the last render
    assert rendered() == everything
    assert rendered(preview=True) == everything
    _append(ext / "x.js", "// edited again\n")
    assert rendered(preview=True) == everything   # the edit is seen at the preview size
    assert rendered() == everything               # and at the final size, drawn before the edit
    assert rendered() == [] and rendered(preview=True) == []
    frames = project.root / "build" / "final" / "web" / "a_cut.mkv"
    drawn_at = frames.stat().st_mtime_ns
    assert rendered(scenes=["a_cut"], force=True) == ["a_cut"]
    assert frames.stat().st_mtime_ns > drawn_at   # --force draws a web_cut scene's frames again too


@pytest.mark.slow
@pytest.mark.render
def test_a_module_waiting_for_several_fetches_becomes_ready(tmp_path: Path) -> None:
    """The module is still waiting when vidgen first looks: it must be looked at again."""
    _chromium_or_skip()
    (tmp_path / "d.json").write_text('{"n": 1}', encoding="utf-8")
    (tmp_path / "s.js").write_text(
        'let total = 0;\nfor (let i = 0; i < 12; i++) total += (await (await fetch("d.json?" + i)).json()).n;\n'
        'export function load(ctx) { document.body.dataset.total = String(total); }\n', encoding="utf-8")
    for _ in range(2):
        with WebPage(tmp_path, WebEntry("script", "s.js"), scene_id="w", size=(64, 36), fps=5, frames=2) as page:
            page.frame(0)
            assert page._page.evaluate("() => document.body.dataset.total") == "12"

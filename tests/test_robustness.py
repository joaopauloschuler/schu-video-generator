"""Edge cases found by the Step 7 review: misbehaving extensions, Windows file locking and
encodings, config files with a BOM, packaging of the init template, cross-version audio length."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import minimal_config, write_files
from vidgen import fileio, registry
from vidgen.cli import check_project, main
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render import ffmpeg as ff


def project_with(make_project, files: dict[str, str], scenes: list[dict] | None = None, **extra: Any) -> Path:
    data = minimal_config(**extra)
    if scenes is not None:
        data["scenes"] = scenes
    root = make_project(data)
    write_files(root, files)
    return root


def one_scene(type_: str, beats: int = 1, **params: Any) -> list[dict]:
    return [{"id": "a", "type": type_, "params": params, "beats": [{"text": f"beat {i}"} for i in range(beats)]}]


# ----- misbehaving extensions ---------------------------------------------------------------------


@pytest.mark.parametrize("spec", ["'two'", "(2, 1)", "-1", "True", "(1, 2, 3)", "[1, 2]", "(None, 2)"])
def test_invalid_beat_count_is_a_clear_error(make_project, spec: str) -> None:
    src = f"from vidgen.api import *\n@scene('x')\nclass X(NarratedScene):\n    beat_count = {spec}\n"
    root = project_with(make_project, {"extensions/x.py": src}, one_scene("x"))
    problems = check_project(Project.load(root))
    assert len(problems) == 1 and "beat_count must be None, a number of beats" in problems[0]


@pytest.mark.parametrize("spec", ["None", "0", "3", "(1, None)", "(2, 4)", "(2, 2)"])
def test_valid_beat_counts_register(make_project, spec: str) -> None:
    src = f"from vidgen.api import *\n@scene('x')\nclass X(NarratedScene):\n    beat_count = {spec}\n"
    root = project_with(make_project, {"extensions/x.py": src}, one_scene("x", beats=3))
    problems = check_project(Project.load(root))
    assert not any("beat_count must" in p for p in problems)


def test_validate_project_that_raises_is_reported_per_scene(make_project) -> None:
    src = """
        from vidgen.api import *

        @scene("boom")
        class Boom(NarratedScene):
            @classmethod
            def validate_project(cls, params, project):
                return 1 / 0

        @scene("odd")
        class Odd(NarratedScene):
            @classmethod
            def validate_project(cls, params, project):
                return "not a list"
    """
    scenes = one_scene("boom") + [
        {"id": "b", "type": "odd", "beats": [{"text": "x"}]},
        {"id": "c", "type": "text_card", "params": {"text": "x", "color": "nope"}, "beats": [{"text": "y"}]},
    ]
    root = project_with(make_project, {"extensions/x.py": src}, scenes)
    problems = check_project(Project.load(root))
    assert problems[0].startswith("scenes[0]: validate_project of scene type 'boom' (extensions/x.py) failed: ZeroDivisionError")
    assert "return 1 / 0" in problems[0] and "cli.py" not in problems[0]
    assert problems[1].startswith("scenes[1]: validate_project of scene type 'odd' (extensions/x.py) must return a list")
    assert problems[2].startswith("scenes[2].params.color: unknown theme color 'nope'")


def test_sys_exit_in_extension_is_an_import_error(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = project_with(make_project, {"extensions/quits.py": "import sys\nsys.exit(3)\n"})
    assert main(["validate", str(root)]) == 1
    err = capsys.readouterr().err
    assert "error while importing extension extensions/quits.py" in err and "SystemExit: 3" in err


def test_bare_decorators_explain_themselves(make_project) -> None:
    root = project_with(make_project, {"extensions/x.py": "from vidgen.api import *\n@scene\nclass X(NarratedScene): pass\n"})
    assert 'use @scene("name")' in check_project(Project.load(root))[0]
    root = project_with(make_project, {"extensions/x.py": "from vidgen.api import *\n@hook\ndef f(ctx): pass\n"})
    assert 'use @hook("event")' in check_project(Project.load(root))[0]


def test_register_theme_defaults_rejects_bad_sizes(make_project) -> None:
    root = project_with(make_project, {"extensions/x.py": "from vidgen.api import *\nregister_theme_defaults(sizes={'huge': 'big'})\n"})
    assert "theme default size 'huge' must be a positive number, got 'big'" in check_project(Project.load(root))[0]


def test_extension_modules_may_shadow_stdlib_and_library_names(make_project) -> None:
    files = {
        "extensions/json.py": "import json as real\nassert hasattr(real, 'dumps')\nfrom .yaml import OK\n",
        "extensions/yaml.py": "import yaml\nassert hasattr(yaml, 'safe_load')\nOK = True\n",
        "extensions/manim.py": "from vidgen.api import *\n@scene('m')\nclass M(NarratedScene): pass\n",
        "extensions/café.py": "from vidgen.api import *\n@scene('cafe')\nclass C(NarratedScene): pass\n",
    }
    root = project_with(make_project, files, one_scene("m") + [{"id": "b", "type": "cafe", "beats": [{"text": "x"}]}])
    assert check_project(Project.load(root)) == []
    import json as stdlib_json

    import manim

    assert stdlib_json.__file__ != str(root / "extensions" / "json.py") and hasattr(manim, "Scene")


def test_hook_traceback_starts_in_the_hook(make_project) -> None:
    from vidgen import extensions, hooks

    root = project_with(make_project, {"extensions/h.py": "from vidgen.api import *\n@hook('pre_tts')\ndef boom(ctx):\n    raise RuntimeError('kaboom')\n"})
    project = Project.load(root)
    with extensions.project_session(project), pytest.raises(VidgenError) as info:
        hooks.dispatch("pre_tts", project, beats=[])
    message = str(info.value)
    assert "failed during pre_tts: RuntimeError: kaboom" in message and "extensions/h.py" in message
    assert "hooks.py" not in message


def test_pipeline_checks_beat_count_before_rendering(make_project, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen.render import pipeline

    src = "from vidgen.api import *\n@scene('two')\nclass Two(NarratedScene):\n    beat_count = 2\n"
    root = project_with(make_project, {"extensions/x.py": src}, one_scene("two"))
    monkeypatch.setattr(pipeline.ff, "find_ffmpeg", lambda: pytest.fail("must fail before looking for ffmpeg"))
    with pytest.raises(VidgenError, match=r"scene 'a' \(type two\): needs exactly 2 beats, got 1"):
        pipeline.render_project(Project.load(root))


def test_worker_environment_has_no_api_key(make_project, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen.render import pipeline

    seen: dict[str, Any] = {}

    class FakeProc:
        class stdout:  # noqa: N801 - mimics Popen.stdout
            @staticmethod
            def read1(n: int) -> bytes:
                return b""

        def wait(self) -> int:
            return 0

    def fake_popen(cmd: list[str], **kwargs: Any) -> FakeProc:
        seen.update(kwargs["env"])
        return FakeProc()

    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_secret")
    monkeypatch.setattr(pipeline.subprocess, "Popen", fake_popen)
    pipeline._run_worker(Project.load(make_project()), True, "intro", True, False)
    assert "ELEVENLABS_API_KEY" not in seen and seen["PYTHONUTF8"] == "1"


# ----- config files -------------------------------------------------------------------------------


def test_config_with_bom_and_crlf(tmp_path: Path) -> None:
    data = minimal_config()
    (tmp_path / "j").mkdir()
    (tmp_path / "j" / "video.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8"))
    (tmp_path / "y").mkdir()
    text = yaml.safe_dump(data, sort_keys=False).replace("\n", "\r\n")
    (tmp_path / "y" / "video.yaml").write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    for sub in ("j", "y"):
        assert Project.load(tmp_path / sub).config.title == "Test video"


# ----- Windows: locked files and console encodings ------------------------------------------------


def test_replace_file_retries_then_explains(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fileio, "RETRY_DELAYS", (0.0, 0.0))
    src, dst = tmp_path / "new.mp4", tmp_path / "out.mp4"
    src.write_bytes(b"new")
    dst.write_bytes(b"old")
    real = os.replace
    attempts: list[int] = []

    def locked_twice(a: Any, b: Any) -> None:
        attempts.append(1)
        if len(attempts) <= 2:
            raise PermissionError(13, "Access is denied")
        real(a, b)

    monkeypatch.setattr(fileio.os, "replace", locked_twice)
    fileio.replace_file(src, dst)
    assert dst.read_bytes() == b"new" and len(attempts) == 3

    def always_locked(a: Any, b: Any) -> None:
        raise PermissionError(13, "Access is denied")

    src.write_bytes(b"newer")
    monkeypatch.setattr(fileio.os, "replace", always_locked)
    with pytest.raises(VidgenError, match=r"cannot write .*out\.mp4 \(Access is denied\); is it open in another program"):
        fileio.replace_file(src, dst)
    assert src.read_bytes() == b"newer"


def test_join_keeps_the_new_video_when_the_output_is_locked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_ffmpeg(exe: str, args: list[str], what: str) -> None:
        Path(args[-1]).write_bytes(b"joined")

    def locked(src: Path, dst: Path) -> None:
        raise VidgenError(f"cannot write {dst} (Access is denied)")

    monkeypatch.setattr(ff, "run_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(ff, "replace_file", locked)
    dst = tmp_path / "video.mp4"
    with pytest.raises(VidgenError, match=r"the new video was saved as .*video\.partial\.mp4"):
        ff.join("ffmpeg", [], [], dst, tmp_path / "padded")
    assert (tmp_path / "video.partial.mp4").read_bytes() == b"joined"


def test_cli_survives_a_legacy_console_encoding(make_project) -> None:
    root = make_project(minimal_config(title="Gears → speed ✓"))
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    env.pop("PYTHONUTF8", None)
    result = subprocess.run(
        [sys.executable, "-m", "vidgen", "validate", str(root)], capture_output=True, env=env, timeout=120
    )
    assert result.returncode == 0, result.stderr.decode("cp1252", errors="replace")
    assert b"Gears \\u2192 speed \\u2713" in result.stdout


# ----- init template ------------------------------------------------------------------------------


def test_init_creates_folders_and_gitignore(tmp_path: Path) -> None:
    target = tmp_path / "Café_video"
    assert main(["init", str(target)]) == 0
    assert (target / "assets").is_dir() and (target / "extensions").is_dir()
    assert "build/" in (target / ".gitignore").read_text(encoding="utf-8")
    assert not (target / "gitignore").exists()
    assert 'title: "Café Video"' in (target / "video.yaml").read_text(encoding="utf-8")


def test_template_has_no_dot_files() -> None:
    """Dot files are not included in the wheel (setuptools globs skip them)."""
    from vidgen.cli import TEMPLATES_DIR

    assert not [p for p in TEMPLATES_DIR.rglob(".*")]


# ----- audio length -------------------------------------------------------------------------------


def test_audio_duration_ignores_mp3_encoder_padding(tmp_path: Path) -> None:
    exe = shutil.which("ffmpeg")
    if exe is None:
        pytest.skip("ffmpeg not on PATH")
    from vidgen.scene import audio_duration

    mp3 = tmp_path / "tone.mp3"
    subprocess.run(
        [exe, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.0", "-c:a", "libmp3lame", str(mp3)],
        check=True,
    )
    assert audio_duration(mp3) == pytest.approx(1.0, abs=0.002)
    with pytest.raises(VidgenError, match="cannot read audio file"):
        bad = tmp_path / "bad.mp3"
        bad.write_bytes(b"not audio")
        audio_duration(bad)


def test_registry_unchanged_after_failed_loads() -> None:
    assert all(not e.origin.startswith("extensions/") for e in registry.all())


def test_odd_frame_sizes_are_rejected(make_project) -> None:
    from vidgen.config import FormatConfig

    with pytest.raises(VidgenError, match=r"preview\.width: must be an even number of pixels \(got 161"):
        Project.load(make_project(minimal_config(preview={"width": 161, "height": 90, "fps": 5})))
    assert FormatConfig(width=160, height=90).width == 160

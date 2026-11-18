"""examples/orchestral-shorts (Step 394): seven published portrait orchestral music videos, source
only, one folder per film sharing one scene module (``shared/orch.js``) and one straight-cut scene
type (``shared/web_cut.py``) through ``web_root: ..`` and ``extensions: [../shared]``. Nothing is
rendered by default; the pictures and the sound were proved unchanged against the published projects with
``vidgen still`` and audio-only renders (HANDOFF Step 394). Slow tests draw one still per film."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
import yaml
from PIL import Image

from vidgen import extensions
from vidgen.browser import chromium
from vidgen.cli import validate_all
from vidgen.music_video_plan import plan_dict, plan_music_video
from vidgen.project import Project
from vidgen.studio import load_music_score
from vidgen.studio.render import range_warnings

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "orchestral-shorts"
#: Each film's folder, its score file's SHA-256 (line ends as "\n": the example plays the published
#: score unchanged), its YouTube Short, its tempo and key, its length in bars and its tail (s).
FILMS: dict[str, dict] = {
    "first-light": {"score": "first_light", "sha256": "7e93d4f7149d10bc2866cea3ca7aab2e7c5372019461ae396469368737936cdd",
                    "short": "y1zxGYL9OOE", "tempo": 96, "key": "D major", "bars": 13, "tail": 3.5},
    "the-signal": {"score": "the_signal", "sha256": "1de04eb382d9edb767b01f98c65999f3dd0a0ff08074fde9722f1512f4a9fc7b",
                   "short": "VIaxZaXD56Y", "tempo": 120, "key": "E minor", "bars": 16, "tail": 3.5},
    "gate-of-stars": {"score": "gate_of_stars", "sha256": "a432672253dc5ef69b51d5e91c69b9fa354f22d2804ef6f3d4d3a5ee152a6414",
                      "short": "nSDKRQBD6V4", "tempo": 80, "key": "Eb major", "bars": 10, "tail": 3.5},
    "choir-of-the-void": {"score": "choir_of_the_void", "sha256": "d19185d9cdf2c719301888d33455f3fc8fd62211afb9a476077ec92f8bd27494",
                          "short": "8EZThIyJKOQ", "tempo": 72, "key": "B minor", "bars": 9, "tail": 3.6},
    "ascension": {"score": "ascension", "sha256": "6a116ba5092941912abe3e4995ab1b0ad2bd0fbf7d6dc4afeca724afad261b6e",
                  "short": "cEob9Rqooqo", "tempo": 100, "key": "A major", "bars": 14, "tail": 3.5},
    "eclipse": {"score": "eclipse", "sha256": "e74b134347a2c1fddd0570877659e2fa811b0f30893f6d7bc425852869ee9f0e",
                "short": "gLsKCVGfdz4", "tempo": 90, "key": "F minor", "bars": 12, "tail": 3.5},
    "orchestra": {"score": "orchestra_test", "sha256": "7444fd3b02e003e6eb5edd7af74a9c1131cc6a5973c1866501ce1969b7f9a75e",
                  "short": "rHDSSkKPzPw", "tempo": 90, "key": "D minor", "bars": 12, "tail": 3.2},
}
FPS = 30


def scenes(film: str) -> list:
    project = Project.load(EXAMPLES / film)
    with extensions.project_session(project):
        return list(project.config.scenes)


def test_the_examples_are_source_only_with_one_shared_module() -> None:
    files = sorted(p.relative_to(EXAMPLES).as_posix() for p in EXAMPLES.rglob("*")
                   if p.is_file() and not {"__pycache__", "build", "output", "exports"} & set(p.relative_to(EXAMPLES).parts))
    film_files = [f"{film}/{name}" for film, info in FILMS.items()
                  for name in (f"assets/music/{info['score']}.yaml", "shots.yaml", "video.yaml")]
    assert files == sorted([".gitignore", "README.md", "shared/orch.js", "shared/web_cut.py", "tools/gen.py", *film_files])
    ignored = (EXAMPLES / ".gitignore").read_text(encoding="utf-8").split()
    assert {"build/", "output/", "*.wav", "*.mp4"} <= set(ignored)


@pytest.mark.parametrize("film", FILMS)
def test_each_film_validates_and_draws_with_the_shared_module(film: str) -> None:
    project = Project.load(EXAMPLES / film)
    assert project.config.web_root == ".." and project.config.extensions == ["../shared"]
    problems, _ = validate_all(project, keep_going=True)
    assert not problems, problems
    found = scenes(film)
    assert {s.type for s in found} == {"web_cut"}
    assert {s.params["script"] for s in found} == {"../shared/orch.js"}


def test_the_shared_module_keeps_the_older_films_ribbon() -> None:
    # The five films made with the first version of orch.js (all but Choir of the Void and Eclipse) draw the
    # same pixels with the shared one: its only change reads two options whose defaults are the old constants.
    module = (EXAMPLES / "shared" / "orch.js").read_text(encoding="utf-8")
    assert "age * (D.ribbonSpeed ?? 2.6)" in module and "D.ribbonGain ?? 3.6" in module
    for film in FILMS:
        text = (EXAMPLES / film / "video.yaml").read_text(encoding="utf-8")
        assert "ribbonSpeed" not in text and "ribbonGain" not in text, film
    assert (EXAMPLES / "shared" / "web_cut.py").read_text(encoding="utf-8").rstrip().endswith("class WebCut(Web):\n    outro = 0.0")


@pytest.mark.parametrize("film", FILMS)
def test_the_cuts_fall_on_bar_lines_and_add_up_to_the_score(film: str) -> None:
    info = FILMS[film]
    score_path = EXAMPLES / film / "assets" / "music" / f"{info['score']}.yaml"
    assert hashlib.sha256(score_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == info["sha256"]
    score = load_music_score(score_path)
    assert range_warnings(score) == []
    assert (score.tempo, score.key.name, sum(s.bars for s in score.sections)) == (info["tempo"], info["key"], info["bars"])
    half_bar = Fraction(120, info["tempo"])           # seconds (4/4: a bar is 240 / tempo)
    found = scenes(film)
    frames = [round(Fraction(s.duration).limit_denominator(10**6) * FPS) for s in found]
    assert all(Fraction(s.duration).limit_denominator(10**6) * FPS == n for s, n in zip(found, frames))   # whole frames
    start = 0
    for scene, n in zip(found, frames):
        assert abs(start - round(Fraction(start, FPS) / half_bar) * half_bar * FPS) <= Fraction(1, 2), scene.id   # on a bar or half-bar line
        start += n
    tail = round(info["tail"] * FPS)
    assert start - tail == round(info["bars"] * 2 * half_bar * FPS)        # the score's bars, then its last chord's tail
    tracks = {t.name for t in score.tracks}
    for scene in found:
        assert set(scene.params["music_data"]["tracks"]) <= tracks, scene.id


def test_the_readme_links_each_film_to_its_youtube_short() -> None:
    readme = (EXAMPLES / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"https://(?:www\.)?youtube\.com/shorts/[A-Za-z0-9_-]+|https://youtu\.be/[A-Za-z0-9_-]+", readme)
    assert sorted(set(links)) == sorted(f"https://www.youtube.com/shorts/{info['short']}" for info in FILMS.values())
    for film, info in FILMS.items():
        row = next(line for line in readme.splitlines() if f"]({film}/)" in line)
        assert f"https://www.youtube.com/shorts/{info['short']}" in row and info["key"] in row, film


def load_gen() -> ModuleType:
    spec = importlib.util.spec_from_file_location("orchestral_gen", EXAMPLES / "tools" / "gen.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gen_writes_each_committed_video_yaml() -> None:
    gen = load_gen()
    for film, info in FILMS.items():
        shots = yaml.safe_load((EXAMPLES / film / "shots.yaml").read_text(encoding="utf-8"))
        plan = json.loads(json.dumps(plan_dict(plan_music_video(EXAMPLES / film / "assets" / "music" / f"{info['score']}.yaml"))))
        assert gen.video_text(shots, plan) == (EXAMPLES / film / "video.yaml").read_text(encoding="utf-8"), film


@pytest.mark.slow
@pytest.mark.parametrize("film", FILMS)
def test_a_still_of_the_film_in_chromium(film: str, tmp_path: Path) -> None:
    """A 180x320 still of the film's first shot, drawn from a copy of the film and the shared folder;
    the score is played once for ctx.music first (about 90 s on the development machine)."""
    if chromium.missing_dependency() is not None:
        pytest.skip(chromium.missing_dependency())
    copy = tmp_path / "orchestral-shorts"
    for folder in ("shared", film):
        for file in (EXAMPLES / folder).rglob("*"):
            if file.is_file() and not {"__pycache__", "build", "output", "exports"} & set(file.relative_to(EXAMPLES).parts):
                (copy / file.relative_to(EXAMPLES)).parent.mkdir(parents=True, exist_ok=True)
                (copy / file.relative_to(EXAMPLES)).write_bytes(file.read_bytes())
    out = tmp_path / f"{film}.png"
    subprocess.run([sys.executable, "-m", "vidgen", "still", str(copy / film), "--scene", scenes(film)[0].id, "--at", "2",
                    "--size", "180x320", "--out", str(out)], check=True, capture_output=True, text=True, encoding="utf-8")
    pixels = np.asarray(Image.open(out).convert("RGB"), dtype=float)
    assert pixels.shape == (320, 180, 3) and pixels.mean() > 10 and pixels.std() > 5

"""The drawing style switch (``drawing:``, DESIGN.md §79): resolving the setting, the outline and
shading drawn by a styled camera, the texture, and a plain style drawing as before."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST
from vidgen.cartoon.drawing_style import (
    OUTLINED,
    SHADED,
    TEXTURES,
    DrawingStyle,
    apply_texture,
    mark_outlined,
    mark_shaded,
    resolve_drawing,
    soft_stops,
    style_camera,
    texture_shade,
)
from vidgen.config import DrawingConfig, VideoConfig
from vidgen.project import Project

# ----- the setting ---------------------------------------------------------------------------------


def test_the_scene_setting_wins_key_by_key_over_the_video_setting() -> None:
    assert resolve_drawing() == DrawingStyle("normal", "flat", "none", 0)
    assert resolve_drawing(None, None).is_plain
    video = DrawingConfig(outline="bold", texture="paper", seed=3)
    scene = DrawingConfig(texture="none", shading="soft")
    assert resolve_drawing(video) == DrawingStyle("bold", "flat", "paper", 3)
    assert resolve_drawing(video, scene) == DrawingStyle("bold", "soft", "none", 3)
    assert resolve_drawing(video, None) == resolve_drawing(video)
    assert not resolve_drawing(DrawingConfig(outline="thin")).is_plain


def test_a_draft_keeps_the_outline_and_drops_shading_and_texture() -> None:
    style = DrawingStyle("bold", "soft", "storybook", 5).for_draft()
    assert style == DrawingStyle("bold", "flat", "none", 5)


def test_the_setting_is_checked_at_the_top_level_and_on_a_stage() -> None:
    config = VideoConfig.model_validate(minimal_config(drawing={"outline": "thin", "shading": "soft", "texture": "storybook"}))
    assert config.drawing == DrawingConfig(outline="thin", shading="soft", texture="storybook")
    for bad in ({"outline": "heavy"}, {"texture": "canvas"}, {"shading": "cel"}, {"seed": -1}, {"colour": "soft"}):
        with pytest.raises(ValidationError):
            VideoConfig.model_validate(minimal_config(drawing=bad))
    from vidgen import extensions, registry

    extensions.load_builtins()
    stage = registry.get("stage").cls
    assert stage.parse_params({"drawing": {"outline": "bold"}}).drawing == DrawingConfig(outline="bold")


def test_a_variant_changes_the_drawing(make_project) -> None:
    data = minimal_config(drawing={"outline": "bold"}, variants={"story": {"drawing": {"texture": "storybook"}}})
    root = make_project(data)
    assert Project.load(root).config.drawing == DrawingConfig(outline="bold")
    assert Project.load(root, variant="story").config.drawing == DrawingConfig(outline="bold", texture="storybook")


# ----- shading and texture (no Manim) --------------------------------------------------------------


def test_soft_stops_are_lighter_at_the_top_and_darker_at_the_bottom() -> None:
    (top, light), (middle, base), (bottom, dark) = soft_stops((0.2, 0.5, 0.8))
    assert (top, middle, bottom) == (0.0, 0.5, 1.0)
    assert base == pytest.approx((0.2, 0.5, 0.8))
    assert all(a > b > c for a, b, c in zip(light, base, dark))


@pytest.mark.parametrize("texture", list(TEXTURES))
def test_a_texture_is_the_same_for_the_same_seed_and_size(texture: str) -> None:
    texture_shade.cache_clear()
    first = texture_shade(texture, 0, 160, 90)
    texture_shade.cache_clear()
    again = texture_shade(texture, 0, 160, 90)
    assert first.shape == (90, 160, 4) and first.dtype == np.uint16
    assert np.array_equal(first, again)
    assert not np.array_equal(first, texture_shade(texture, 1, 160, 90))
    assert texture_shade(texture, 0, 90, 160).shape == (160, 90, 4)
    assert 190 <= int(first.min()) and int(first.max()) <= 256   # it darkens a little, never lightens
    assert (first[:, :, 3] == 256).all() and (first[:, :, 0] == first[:, :, 2]).all()   # alpha kept; grey


def test_storybook_is_stronger_than_paper_with_darker_corners() -> None:
    paper, story = texture_shade("paper", 0, 320, 180)[:, :, 0], texture_shade("storybook", 0, 320, 180)[:, :, 0]
    assert story.mean() < paper.mean()
    assert story[:20, :20].mean() < story[80:100, 150:170].mean() - 10
    assert abs(float(paper[:20, :20].mean()) - float(paper[80:100, 150:170].mean())) < 6


def test_applying_a_texture_multiplies_the_colours_and_keeps_alpha() -> None:
    rng = np.random.default_rng(1)
    frame = rng.integers(0, 256, (90, 160, 4), dtype=np.uint8)
    unchanged = np.full((90, 160, 4), 256, dtype=np.uint16)
    assert np.array_equal(apply_texture(frame, unchanged), frame)
    shade = texture_shade("storybook", 0, 160, 90)
    out = apply_texture(frame, shade)
    assert out is not frame and out.dtype == np.uint8 and np.array_equal(out[:, :, 3], frame[:, :, 3])
    expected = (frame[:, :, :3].astype(np.int64) * shade[:, :, :3].astype(np.int64)) // 256
    assert np.array_equal(out[:, :, :3], expected)


# ----- the camera draws the style ------------------------------------------------------------------


def _draw(style: DrawingStyle | None, mobject: Any, *, every_stroke: bool = True) -> np.ndarray:
    """``mobject`` drawn by a 160x90 Cairo camera styled with ``style`` (``None``: unstyled)."""
    from manim import Camera, tempconfig

    from vidgen.render.worker import frame_size

    fw, fh = frame_size(160, 90)
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_width": fw, "frame_height": fh}):
        camera = Camera(background_color="#FFFFFF")
        if style is not None:
            style_camera(camera, style, every_stroke=every_stroke)
        camera.capture_mobjects([mobject])
        return np.asarray(camera.pixel_array[:, :, :3], dtype=int)


def _ink(pixels: np.ndarray) -> int:
    """How much ink is drawn on the white frame (the sum of the darkening)."""
    return int((255 * 3 - pixels.sum(axis=2)).sum())


def test_the_outline_weight_reaches_every_stroke() -> None:
    from manim import Circle

    ring = Circle(radius=1.5).set_stroke("#1F2430", width=30).set_fill(opacity=0)   # about 3 px here
    plain, thin, bold = (_ink(_draw(s, ring)) for s in (None, DrawingStyle(outline="thin"), DrawingStyle(outline="bold")))
    assert thin < plain < bold
    assert bold / plain == pytest.approx(1.7, rel=0.1) and thin / plain == pytest.approx(0.6, rel=0.1)
    hairline = Circle(radius=1.5).set_stroke("#1F2430", width=4).set_fill(opacity=0)   # under 1 px here
    assert _ink(_draw(DrawingStyle(outline="thin"), hairline)) == _ink(_draw(None, hairline))   # never thinner


def test_a_camera_for_a_host_styles_only_what_is_marked() -> None:
    from manim import Circle

    ring = Circle(radius=1.5).set_stroke("#1F2430", width=30).set_fill(opacity=0)
    bold = DrawingStyle(outline="bold")
    assert _ink(_draw(bold, ring, every_stroke=False)) == _ink(_draw(None, ring))
    mark_outlined(ring)
    assert getattr(ring, OUTLINED)
    assert _ink(_draw(bold, ring, every_stroke=False)) > _ink(_draw(None, ring))


def test_soft_shading_reaches_marked_fills_and_keeps_their_silhouette() -> None:
    from manim import Square

    def square() -> Any:
        return Square(side_length=3).set_fill("#3C78D8", opacity=1).set_stroke(width=0)

    soft = DrawingStyle(shading="soft")
    flat = _draw(None, square())
    assert np.array_equal(_draw(soft, square()), flat)   # not marked: flat
    shaded_square = square()
    mark_shaded(shaded_square)
    assert getattr(shaded_square, SHADED)
    shaded = _draw(soft, shaded_square)
    inside = flat.sum(axis=2) < 3 * 250
    assert np.array_equal(shaded.sum(axis=2) < 3 * 250, inside)   # the same pixels filled
    column = shaded[inside.any(axis=1), 80].sum(axis=1)
    assert column[0] > flat[inside.any(axis=1), 80].sum(axis=1)[0] > column[-1]   # lighter top, darker bottom


def test_a_host_gets_the_outline_and_shading_but_no_texture(make_project) -> None:
    from test_host import built_scene, config

    root = make_project(config(host="dot", drawing={"outline": "bold", "shading": "soft", "texture": "paper"}))
    scene, _ = built_scene(root, (160, 90))
    camera = vars(scene.renderer.camera)
    assert scene.drawing == DrawingStyle("bold", "soft", "paper", 0)
    assert "apply_stroke" in camera and "apply_fill" in camera
    assert all(getattr(m, OUTLINED, False) for m in scene.host.get_family())
    assert all(getattr(m, SHADED, False) for m in scene.host.character.get_family())
    assert not scene.renderer.add_frame.__qualname__.startswith("attach_texture")   # no transitions: nothing wraps it outside
    plain = make_project(config(host="dot"), folder="plain")
    scene, _ = built_scene(plain, (160, 90))
    assert scene.drawing.is_plain and "apply_stroke" not in vars(scene.renderer.camera)
    assert not any(getattr(m, OUTLINED, False) for m in scene.host.get_family())


# ----- renders -------------------------------------------------------------------------------------

STAGE: dict[str, Any] = {
    "background": "#CFE3F5",   # a light sky: the texture darkens it
    "props": [{"prop": "tree", "at": 0.2}, {"prop": "box", "at": 0.75}],
    "characters": [{"name": "pip", "at": 0.45}],
}
BEATS = [{"text": "Pip stands by the tree."}]


def _render(make_project, tmp_path: Path, monkeypatch, folder: str, **config: Any) -> tuple[Any, list[np.ndarray]]:
    scenes = [{"id": "home", "type": "stage", "params": dict(STAGE, **config.pop("params", {})), "beats": BEATS}]
    project = Project.load(make_project(minimal_config(characters=CAST, scenes=scenes, **config), folder=folder))
    return frames_of(project, tmp_path / f"media_{folder}", monkeypatch)


@pytest.mark.render
def test_a_plain_style_draws_as_before_and_a_style_reaches_the_stage(make_project, tmp_path: Path, monkeypatch) -> None:
    scene, before = _render(make_project, tmp_path, monkeypatch, "unset")
    assert scene.drawing.is_plain and "apply_stroke" not in vars(scene.renderer.camera)
    plain = {"outline": "normal", "shading": "flat", "texture": "none"}
    scene, written = _render(make_project, tmp_path, monkeypatch, "plain", drawing=plain)
    assert "apply_stroke" not in vars(scene.renderer.camera) and "apply_fill" not in vars(scene.renderer.camera)
    assert len(written) == len(before) and all(np.array_equal(a, b) for a, b in zip(written, before))

    styled = {"outline": "bold", "shading": "soft", "texture": "storybook"}
    scene, frames = _render(make_project, tmp_path, monkeypatch, "styled", params={"drawing": styled})
    assert scene.drawing == DrawingStyle("bold", "soft", "storybook", 0)
    assert scene.renderer.add_frame.__qualname__.startswith("attach_texture")
    assert all(getattr(m, SHADED, False) for m in scene.cast["pip"].get_family())
    middle = len(before) // 2
    assert len(frames) == len(before)
    assert np.abs(frames[middle].astype(int) - before[middle].astype(int)).mean() > 2
    assert frames[middle][:10, :10].mean() < before[middle][:10, :10].mean()   # the storybook's darker corner


@pytest.mark.render
def test_a_draft_has_no_texture(make_project, tmp_path: Path, monkeypatch) -> None:
    scenes = [{"id": "home", "type": "stage", "params": STAGE, "beats": BEATS}]
    root = make_project(minimal_config(characters=CAST, scenes=scenes, drawing={"outline": "bold", "texture": "paper", "shading": "soft"}))
    scene, _ = frames_of(Project.load(root, draft=True), tmp_path / "media", monkeypatch)
    assert scene.drawing == DrawingStyle("bold", "flat", "none", 0)
    assert "apply_stroke" in vars(scene.renderer.camera) and "apply_fill" not in vars(scene.renderer.camera)

"""Step 252 (DESIGN.md §102.8-§102.15): a HUD that keeps off faces and is drawn in pieces, lint
``overlay_face``, plain splashes on an iso place, display patterns ``equations`` and
``timelines``, the ``scanner``, ``takeout`` and ``crystal`` props, the ``medal`` and ``pendant``
accessories, a haze over a spot, sliding doors and the ``kiss`` action."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST, stage_params
from test_overlays import bullets, project, render
from vidgen import extensions, hud, registry
from vidgen.cartoon import haze, holo_display, kiss
from vidgen.cartoon.character import build_character
from vidgen.cartoon.clothes import PENDANT_GLOW
from vidgen.cartoon.figure_fx import KissPlan, head_box, pendant_level
from vidgen.cartoon.foley import place_change_cues
from vidgen.cartoon.iso_scenery import IsoColors, place_pieces
from vidgen.cartoon.living_drawing import SCAN_ROLE, SCANNER_WARNING, LivingProp
from vidgen.cartoon.props import SMALL_PROPS, draw_prop
from vidgen.cartoon.rain import IsoRainGround, RainGround
from vidgen.config import CharacterEntry, CharacterLook, LintRules
from vidgen.lint import RULES
from vidgen.lint.rules import StillContext
from vidgen.particle_field import ParticleField
from vidgen.particles import particle_seeds
from vidgen.project import Project
from vidgen.theme import Theme
from vidgen.world.iso import parse_iso_map

# ----- the HUD keeps off faces ---------------------------------------------------------------------


def test_texts_go_where_they_cover_no_face() -> None:
    places = [(-1.0, 3.0, 1.0, 4.0), (4.0, 3.0, 6.0, 4.0), (-6.0, 3.0, -4.0, 4.0)]
    face = (-0.5, 2.5, 0.5, 4.5)
    assert hud.face_cover(places[0], [face]) > 0.2 and hud.face_cover(places[1], [face]) == 0.0
    assert hud.pick_place(places, []) == 0 and hud.pick_place(places, [face]) == 1
    assert hud.pick_place(places, [face], avoid=[places[1]]) == 2   # the alert stands there
    assert hud.pick_place(places, [(-0.2, 2.0, 0.0, 3.05)], current=2) == 2   # its place stays clear: it stays
    crowded = [face, (4.5, 3.5, 5.0, 4.5), (-5.0, 3.0, -4.5, 3.5)]   # every place covers a face: the least
    assert hud.pick_place(places, crowded) == min(range(3), key=lambda k: hud.face_cover(places[k], crowded))


@pytest.mark.render
def test_the_hud_moves_its_texts_off_a_face_and_draws_in_pieces(make_project, tmp_path: Path) -> None:
    hud_entry = {"type": "hud", "at": 0.0, "duration": 3.0, "alert": "ALERT", "lines": ["ONE", "TWO"], "heart": {"bpm": 80}}
    scene = render(project(make_project, [bullets("s", beats=1, overlays={"implant": hud_entry})], []), "s", tmp_path)
    layer = scene.overlay_layer
    overlay = layer.overlays[0]
    assert overlay.pieces == 4 and overlay.avoids_faces and overlay.faces is not None
    still, texts, heart, scan = layer.states(12)[0]
    assert still == (1.0,) and texts[:2] == (0, 0) and heart is not None and scan is None   # no face on a bullets scene
    x0, y0, x1, y1 = overlay._alert_boxes[0]
    overlay.faces = lambda: [(x0, y0 - 1.0, x1, y1 + 0.5)]   # a head under the alert
    moved = overlay.state(12 / layer.fps)
    assert moved[1][0] != 0 and hud.face_cover(overlay._alert_boxes[moved[1][0]], overlay.faces()) == 0.0
    frames = [key for key in layer._cache if key[1][0] == 2]   # the heart: drawn on every frame
    still = [key for key in layer._cache if key[1][0] == 0]   # the frame: once, and while it boots in
    assert len(frames) > 10 and len(still) < len(frames) / 2
    assert len(layer.posed(14)[0][1].submobjects) == 3   # the frame, the texts, the heart


def _still(objects: list[dict[str, Any]], *, faces: bool = True, shorts: bool = False) -> StillContext:
    layout = {"width": 854, "height": 480, **({"shorts": [0, 0, 700, 380]} if shorts else {})}
    frame = {"overlays": [{"id": "implant", "type": "hud", "settled": True, "skip": [], **({"faces": True} if faces else {})}]}
    return StillContext(layout, frame, objects)


def test_lint_reports_a_hud_text_over_a_face() -> None:
    face = {"kind": "character", "name": "ana", "bbox": [100, 100, 200, 400], "face": [100, 100, 200, 200], "path": "ana"}
    text = {"kind": "text", "text": "ALERT", "bbox": [90, 120, 260, 180], "overlay": "implant", "path": "overlay:implant/t"}
    frame = {"kind": "group", "bbox": [0, 0, 854, 480], "overlay": "implant", "fill": {"color": "#000000", "opacity": 0.6}, "path": "overlay:implant/g"}
    settings = LintRules().overlay_face
    found = list(RULES["overlay_face"].check(_still([face, text, frame]), settings))
    assert len(found) == 1 and "covers 60%" in found[0].message
    assert not list(RULES["overlay_face"].check(_still([face, frame]), settings))   # the frame's lines are no plate
    assert not list(RULES["overlay_face"].check(_still([face, text], faces=False), settings))
    assert not list(RULES["overlay_face"].check(_still([face, text], shorts=True), settings))   # shorts_safe_area's
    assert RULES["overlay_face"].default == "warning" and settings.min_cover == 0.15


# ----- plain splashes on an iso place --------------------------------------------------------------


def test_rain_on_an_iso_place_splashes_in_plain_rings() -> None:
    seeds = particle_seeds("rain", 60, 1)
    common = dict(clock=lambda: 1.0, view=lambda: (-7.0, -4.0, 7.0, 4.0), area=[0.0, 0.0, 1.0, 1.0], short_side=8.0, frame_width=14.0)
    iso = IsoRainGround(-3.0, -3.0, 3.0, 8.0, xs=(-7.0, 7.0), fronts=(-3.0, -3.0), backs=(3.0, 3.0))
    flat = RainGround(-3.0, -3.2, -1.0, 8.0)
    counts = {}
    for name, ground in (("iso", iso), ("flat", flat)):
        field = ParticleField(seeds, ["#5FFFE0"], ground=lambda g=ground: g, **common)   # type: ignore[arg-type]
        field.draw_at(2.5)
        counts[name] = (len(field.splashes.points), len(field._circle))
    (iso_points, circle), (flat_points, _) = counts["iso"], counts["flat"]
    assert iso_points % circle == 0 and flat_points % (3 * circle) == 0 and iso_points > 0   # one ring each; a ring and two droplets


# ----- display patterns -----------------------------------------------------------------------------


def test_floating_formulas_and_timelines() -> None:
    assert {"equations", "timelines"} <= set(holo_display.DISPLAY_PATTERNS)
    early = holo_display.display_frame("equations", 0.0, 0.5)
    late = holo_display.display_frame("equations", 0.0, 4.0)
    assert len(late.glyphs) > len(early.glyphs) and late.wings and len(late.glyphs) <= holo_display.GLYPHS
    left, bottom, right, top = holo_display.FLOAT_BOX
    assert all(left - 0.2 <= x <= right + 0.2 and bottom - 0.2 <= y <= top + 0.2 for wing in late.wings for x, y in wing)
    growing = holo_display.display_frame("timelines", 0.0, 0.5)
    grown = holo_display.display_frame("timelines", 0.0, 3.0)
    assert len(growing.glyphs) < len(grown.glyphs) == 15 and not growing.boxes
    assert len(grown.boxes) == 8 and len(grown.dots) == 16
    with pytest.raises(ValidationError, match="pattern is for a hologram_display"):
        stage_params(props=[{"prop": "lamp", "pattern": "timelines"}])


# ----- small props and accessories ---------------------------------------------------------------


def test_a_scanner_spikes_off_its_scale() -> None:
    assert {"scanner", "takeout", "crystal"} <= set(SMALL_PROPS)
    for kind in ("takeout", "crystal"):
        assert draw_prop(kind, height=0.5, theme=Theme()).height == pytest.approx(0.5)
    prop = draw_prop("scanner", height=1.0, theme=Theme(), living=True, name="scan")
    live = LivingProp(prop, on=True, scan=hud.ScanMeter(0.3, 1.6, 1.0))
    wave = next(m for m in live.overlays if getattr(m, SCAN_ROLE, None) == "wave")
    live.update(0.5)
    calm = wave.get_stroke_color().to_hex().upper()
    spiked = set()
    for t in np.arange(3.0, 4.0, 0.1):
        live.update(float(t))
        spiked.add(wave.get_stroke_color().to_hex().upper())
    assert calm != SCANNER_WARNING.upper() and SCANNER_WARNING.upper() in spiked
    assert stage_params(props=[{"prop": "scanner", "scan": {"to": 1.5, "at": 2}}]).props[0].scan.meter().to == 1.5
    with pytest.raises(ValidationError, match="scan is for a scanner"):
        stage_params(props=[{"prop": "phone", "scan": {"to": 1.5}}])


def test_a_medal_and_a_glowing_pendant() -> None:
    entry = CharacterEntry.model_validate({"name": "ana", "look": {"outfit": "coat", "accessories": ["pendant"]}})
    figure = build_character(entry, theme=Theme())
    roles = {getattr(m, PENDANT_GLOW) for m in figure.get_family() if getattr(m, PENDANT_GLOW, None)}
    assert roles == {"halo", "core"}
    medal = build_character(CharacterEntry.model_validate({"name": "ben", "look": {"accessories": ["medal"]}}), theme=Theme())
    assert len(medal.get_family()) > len(build_character(CharacterEntry(name="ben"), theme=Theme()).get_family())
    with pytest.raises(ValidationError, match="round the neck"):
        CharacterLook.model_validate({"accessories": ["medal", "pendant"]})
    levels = [pendant_level(t) for t in np.arange(0.0, 3.2, 0.05)]
    assert max(levels) == pytest.approx(1.0, abs=0.02) and min(levels) < 0.5


def test_an_echo_is_not_a_look_alike() -> None:
    from vidgen.cartoon.contrast import character_pairs
    from vidgen.config import VideoConfig

    same = {"look": {"body": "pear", "hair": "long"}, "colors": {"skin": "#F0D2B4", "hair": "#2A1810"}}
    characters = [{"name": "ana", **same}, {"name": "ana_twin", **same}, {"name": "ana_other", "echo": True, **same}]
    scenes = [{"id": "s", "type": "stage", "params": {"characters": [{"name": n, "at": 0.3} for n in ("ana", "ana_twin", "ana_other")]},
               "beats": [{"text": "Hi."}]}]
    config = VideoConfig.model_validate(minimal_config(characters=characters, scenes=scenes))
    pairs = [(p.first, p.second) for _, p in character_pairs(config, Theme())]
    assert pairs == [("ana", "ana_twin")]


# ----- haze and sliding doors ----------------------------------------------------------------------


def test_a_haze_ripples_up_and_fades_in() -> None:
    ribbons = haze.haze_ribbons(1.0, seed=2)
    assert len(ribbons) == haze.HAZE_RIBBONS and all(0.35 <= share <= 1.0 for _, share in ribbons)
    assert ribbons != haze.haze_ribbons(1.5, seed=2)
    assert all(0.0 <= v <= 1.0 and -0.6 <= u <= 0.6 for outline, _ in ribbons for u, v in outline)
    assert len(haze.haze_sparks(1.0)) == haze.HAZE_SPARKS
    assert haze.haze_level(0.5, start=1.0) == 0.0 and haze.haze_level(3.0, start=1.0) == 1.0
    room = {"place": "indoor", "map": "####+###\n#..d...#\n#......#\n########", "spots": {"d": "door_in"}}
    params = stage_params(iso={**room, "doors": "slide", "haze": [{"at": "door_in", "height": 3, "from": 1.5}]})
    assert params.iso.haze_foot(params.iso.haze[0])[:2] == (3.5, 1.5) and params.iso.haze[0].start == 1.5
    with pytest.raises(ValidationError, match="no spot 'nowhere'"):
        stage_params(iso={**room, "haze": [{"at": "nowhere"}]})


def test_a_sliding_door_glows_and_hisses() -> None:
    place = parse_iso_map("####+###\n#......#\n########", place="indoor")
    looks: dict[str, Any] = {}
    door = next(p for p in place_pieces(place, IsoColors(doors="slide"), looks) if p.kind == "door")
    plain = next(p for p in place_pieces(place, IsoColors(), looks) if p.kind == "door")
    assert any(getattr(s, "glow", False) for s in door.shapes) and not any(getattr(s, "glow", False) for s in plain.shapes)
    hiss = place_change_cues("door", True, None, 1.0, 0.6, sliding=True)
    assert [c.sound for c in hiss] == ["swoosh"] and [c.sound for c in place_change_cues("door", True, None, 1.0, 0.6)] == ["creak"]
    assert [c.sound for c in place_change_cues("door", False, None, 1.0, 0.6, sliding=True)] == ["swoosh", "thud"]


# ----- a kiss --------------------------------------------------------------------------------------


def test_the_kiss_maths() -> None:
    assert kiss.kiss_share(0.0) == 0.0 and kiss.kiss_share(1.5) == 1.0 and kiss.kiss_share(kiss.KISS_SECONDS) == 0.0
    assert 0.0 < kiss.kiss_share(0.3) < 1.0 and kiss.contact_time() == kiss.KISS_IN
    tall, short = kiss.lean_angles(3.0, 2.5, 0.5)
    assert tall > short == kiss.KISS_LEAN
    assert kiss.step_in(1.0, 0.5) == pytest.approx((1.0 + kiss.KISS_TOUCH * 0.5) / 2) and kiss.step_in(-1.0, 0.5) == 0.0
    burst = kiss.burst(0.5)
    assert {kind for kind, *_ in burst} == {"heart", "sparkle"} and kiss.burst(-0.1) == [] and kiss.burst(kiss.BURST_SECONDS + 0.1) == []


def test_two_kiss_and_stand_back() -> None:
    a = build_character(CharacterEntry.model_validate({"name": "ana", "look": {"body": "tall"}}), theme=Theme())
    b = build_character(CharacterEntry.model_validate({"name": "ben", "look": {"body": "pear"}}), theme=Theme())
    b.shift([2.5, 0.2, 0.0])
    feet = (a.feet().copy(), b.feet().copy())
    plan = KissPlan(a, b, 3.0)
    plan.update(1.5)
    ha, hb = head_box(a), head_box(b)
    width = min(ha[2] - ha[0], hb[2] - hb[0])
    assert hb[0] - ha[2] == pytest.approx(-kiss.KISS_TOUCH * width, abs=0.02 * width)   # the faces touch
    assert a.facing == "right" and b.facing == "left" and a.kissing == "ben"
    assert a.state().parts["body"].angle < 0 and a.shown_shape("eyes") == "closed"
    plan.update(3.0)
    assert np.allclose(a.feet(), feet[0]) and np.allclose(b.feet(), feet[1]) and a.kissing is None
    assert a.state().parts["body"].angle == 0 and a.shown_shape("eyes") != "closed"


def test_kiss_options(make_project) -> None:
    from vidgen.cli import check_project

    extensions.load_builtins()
    assert registry.find_action("kiss") is not None
    params = {"characters": [{"name": "pip", "at": 0.4}, {"name": "kit", "at": 0.6}]}
    for action, message in (({"kiss": "pip", "with": "pip"}, "cannot kiss itself"), ({"kiss": "pip", "with": "zed"}, "not a character of this scene")):
        scenes = [{"id": "home", "type": "stage", "params": params, "beats": [{"text": "Hi.", "actions": [action]}]}]
        problems = check_project(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))))
        assert any(message in p for p in problems), problems


# ----- one render of it all ------------------------------------------------------------------------


@pytest.mark.render
def test_a_kiss_in_a_lab_renders(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    cast = [{"name": "pip", "look": {"body": "bean", "accessories": ["pendant"]}}, {"name": "kit", "look": {"body": "tall", "accessories": ["medal"]}}]
    iso = {"place": "indoor", "doors": "slide", "map": "###+####\n#..d...#\n#.a.b..#\n#......#\n########",
           "spots": {"d": "door_in", "a": "left", "b": "right"}, "haze": [{"at": "door_in"}]}
    props = [{"prop": "hologram_display", "name": "array", "at": "door_in", "on": True, "pattern": "timelines"},
             {"prop": "scanner", "name": "scan", "at": "left", "on": True, "scan": {"to": 1.4, "at": 0.3}}]
    params = {"light": "night", "iso": iso, "props": props, "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}]}
    beats = [{"text": "They kiss in the lab.", "actions": [{"kiss": "pip", "with": "kit", "at": 0.1, "run_time": 1.5}]}]
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    scene, frames = frames_of(Project.load(make_project(minimal_config(characters=cast, scenes=scenes))), tmp_path / "lab", monkeypatch)
    names = {type(thing).__name__ for thing in scene.story_things}
    assert "IsoHaze" in names and len(frames) > 5 and np.any(frames[-1] != frames[3])
    assert scene.cast["pip"].kissing is None   # the kiss is over

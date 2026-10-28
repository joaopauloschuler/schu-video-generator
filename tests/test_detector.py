"""Detectors and event displays (Phase Y, Step 240; DESIGN §99.9–§99.10): the bending radius
p_T = 0.3 B R and the sign of the curvature, curlers, the muon's return-field bend, the signature of
every kind of particle, the missing transverse momentum, seeded presets (deterministic, balanced,
masses), the ``detector`` scene's params, targets and the ``switch_view`` action, tiny renders in
16:9 and 9:16. Also Step 240's review fixes of Step 239 (kinematics readout, sqrt TeX, model axis
labels, a centred Feynman diagram before its rule card)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_actions import render
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.particle_physics import PARTICLES
from vidgen.particle_physics import detector as dt
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}


def _one(key: str, pt: float, eta: float = 0.0, phi: float = 0.0) -> dt.EventParticle:
    return dt.EventParticle(PARTICLES[key], pt, eta, math.radians(phi))


def _in_field(path: dt.Trajectory) -> np.ndarray:
    pts = path.points
    r = np.hypot(pts[:, 0], pts[:, 1])
    return pts[(r < dt.FIELD_R) & (np.abs(pts[:, 2]) < dt.FIELD_Z)]


# ----- tracks in the field ------------------------------------------------------------------------


def test_bending_radius_is_pt_over_0_3_b() -> None:
    assert dt.bending_radius(1.0, 1.0) == pytest.approx(1 / 0.3, rel=1e-3)   # 0.2998 exactly
    assert dt.bending_radius(0.6, 2.0) == pytest.approx(1.0, rel=1e-3)
    assert dt.bending_radius(5.0, 2.0, charge=2) == pytest.approx(dt.bending_radius(2.5, 2.0))
    assert dt.bending_radius(1.0, 2.0, charge=0) == math.inf


@pytest.mark.parametrize("key, sign", [("pi+", -1), ("pi-", 1), ("e-", 1), ("mu+", -1)])
def test_tracks_bend_with_the_right_radius_and_sign(key: str, sign: int) -> None:
    """B along +z (out of the x–y view): q > 0 turns clockwise; the stepped path lies on a
    circle of radius p_T / (0.3 B) through the origin, its centre on the side the force points."""
    det = dt.Detector(2.0)
    q = _one(key, 0.9, 0.3, 0.0)
    path = dt.trajectory(q, det)
    pts = _in_field(path)[:, :2]
    radius = dt.bending_radius(0.9, 2.0)
    centre = np.array([0.0, sign * radius])   # moving along +x: the centre is below (q > 0) or above
    assert np.allclose(np.hypot(*(pts - centre).T), radius, rtol=2e-3)
    assert np.sign(pts[len(pts) // 2, 1]) == sign   # curves towards the centre
    # z grows with the transverse path: dz = sinh(η) ds_T
    assert path.points[-1][2] > 0


def test_field_direction_and_strength_matter() -> None:
    q = _one("pi+", 2.0)
    weak, strong = (np.abs(_in_field(dt.trajectory(q, dt.Detector(b)))[:, 1]).max() for b in (1.0, 4.0))
    assert strong > 3 * weak
    with pytest.raises(VidgenError, match="must be positive"):
        dt.Detector(0.0)
    with pytest.raises(VidgenError, match="must be positive"):
        dt.Detector(-2.0)


def test_low_pt_tracks_curl_up_inside_the_tracker() -> None:
    det = dt.Detector(2.0)
    curler = dt.trajectory(_one("pi-", 0.3, 0.05), det)   # 2R = 1.0 m < the ECAL at 1.4 m
    assert curler.curled and "ecal" not in curler.entry
    assert np.hypot(curler.points[:, 0], curler.points[:, 1]).max() == pytest.approx(2 * dt.bending_radius(0.3, 2.0), rel=0.02)
    assert not dt.trajectory(_one("pi-", 1.5), det).curled
    ev = dt.Event((_one("pi-", 0.3, 0.05),))
    assert dt.deposits(ev, [curler]) == []


def test_a_muon_bends_back_in_the_return_field() -> None:
    det = dt.Detector(2.0)
    path = dt.trajectory(_one("mu+", 4.0), det)
    pts = path.points
    r = np.hypot(pts[:, 0], pts[:, 1])
    heading = np.unwrap(np.arctan2(np.diff(pts[:, 1]), np.diff(pts[:, 0])))
    turn = np.diff(heading)
    inside = turn[r[1:-1] < dt.FIELD_R - 0.02]
    iron = turn[[any(layer.in_barrel(x, z) for layer in dt.IRON) for x, z in zip(r[1:-1], pts[1:-1, 2])]]
    assert inside.sum() < 0 < iron.sum()   # clockwise inside the coil, counter-clockwise in the yoke
    assert det.yoke_field == pytest.approx(1.0)
    assert len(path.muon_hits) == 3


# ----- signatures ---------------------------------------------------------------------------------


@pytest.mark.parametrize("key, track, calos, muon", [
    ("e-", True, {"ecal"}, False),
    ("gamma", False, {"ecal"}, False),
    ("mu-", True, set(), True),
    ("pi+", True, {"ecal", "hcal"}, False),
    ("K-", True, {"ecal", "hcal"}, False),
    ("n", False, {"hcal"}, False),
    ("K0_L", False, {"hcal"}, False),
    ("nu_mu", False, set(), False),
])
def test_signatures_per_particle(key: str, track: bool, calos: set[str], muon: bool) -> None:
    det = dt.Detector(2.0)
    q = _one(key, 30.0, 0.4, 70.0)
    path = dt.trajectory(q, det)
    ev = dt.Event((q,))
    assert bool(path.tracker_hits) == track and (path.tracker_end > 0) == track
    assert {d.layer for d in dt.deposits(ev, [path])} == calos
    assert bool(path.muon_hits) == muon
    must, _may, _text = dt.SIGNATURES[dt.signature(q.particle)]
    assert ("track" in must) == track and ("muon" in must) == muon
    if calos:
        total = sum(d.energy for d in dt.deposits(ev, [path]))
        assert total == pytest.approx(q.energy)   # the whole energy is deposited (schematic shares)


def test_what_never_reaches_the_detector_is_refused() -> None:
    for key, match in (("tau-", "decays before it reaches"), ("pi0", "two photons"), ("Z", "decays at the collision point"),
                       ("u", "make a jet"), ("g", "make a jet"), ("K0_S", "decays before it reaches"), ("Lambda", "give its decay products")):
        with pytest.raises(VidgenError, match=match):
            dt.signature(key)
    with pytest.raises(VidgenError, match="did you mean"):
        dt.custom_event([{"particle": "muonn", "pt": 10}])


def test_signature_claims_are_checked() -> None:
    assert dt.signature_problem("gamma", ["ecal"]) is None
    assert "leaves no track (it is neutral)" in dt.signature_problem("gamma", ["track", "ecal"])
    assert "also leaves a track" in dt.signature_problem("e-", ["ecal"])
    assert dt.signature_problem("pi+", ["track", "hcal"]) is None and dt.signature_problem("pi+", ["track", "ecal", "hcal"]) is None
    assert "leaves no muon-chamber hits" in dt.signature_problem("pi+", ["track", "hcal", "muon"])
    assert "shows as missing p_T" in dt.signature_problem("nu_e", [])
    assert dt.signature_problem("nu_e", ["missing"]) is None
    with pytest.raises(VidgenError, match="not a signature part"):
        dt.signature_problem("e-", ["track", "pixels"])


# ----- events ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("preset", dt.PRESETS)
def test_presets_are_deterministic_and_balanced(preset: str) -> None:
    a, b = dt.generate(preset, 7), dt.generate(preset, 7)
    assert a == b
    assert dt.generate(preset, 8) != a
    px = sum(q.px for q in a.particles)
    py = sum(q.py for q in a.particles)
    assert abs(px) < 1e-6 and abs(py) < 1e-6   # the recoil balances the boson; soft pions come in pairs
    # missing p_T is minus the visible sum: the neutrinos' transverse momentum
    nx = sum(q.px for q in a.particles if not q.visible)
    ny = sum(q.py for q in a.particles if not q.visible)
    assert a.missing_pt() == pytest.approx((nx, ny), abs=1e-6)


def test_preset_physics() -> None:
    z = dt.generate("z_to_mumu", 3)
    assert sorted(z.particles[i].particle.key for i in z.products) == ["mu+", "mu-"] and z.parent == "Z"
    gz = PARTICLES["Z"].width_mev / 1e3
    assert abs(z.products_mass() - PARTICLES["Z"].mass_mev / 1e3) <= dt.DISPLAY_WIDTHS * gz + 1e-6
    for seed in range(1, 21):   # every showcase Z lands on the peak (truncated Breit–Wigner draw)
        assert abs(dt.generate("z_to_mumu", seed).products_mass() - 91.188) <= gz + 1e-6
    h = dt.generate("h_to_gammagamma", 5)
    assert h.products_mass() == pytest.approx(125.2, abs=0.05)   # Γ_H ≈ 4 MeV
    four = dt.generate("h_to_4l", 2)
    assert sorted(four.particles[i].particle.key for i in four.products) == ["e+", "e-", "mu+", "mu-"]
    assert four.products_mass() == pytest.approx(125.2, abs=0.05)
    w = dt.generate("w_to_enu", 2)
    assert w.met >= dt.NEUTRINO_PT and 0 < w.transverse_mass() <= PARTICLES["W+"].mass_mev / 1e3 + 3 * PARTICLES["W+"].width_mev / 1e3
    jj = dt.generate("dijet", 4)
    assert len(jj.jets) == 2 and jj.jets[0].pt == pytest.approx(jj.jets[1].pt)
    assert abs(abs(jj.jets[0].phi - jj.jets[1].phi) - math.pi) < 1e-6
    for ev in (z, h, four, w):
        assert all(abs(ev.particles[i].eta) <= dt.LEPTON_ETA for i in ev.products)
    with pytest.raises(VidgenError, match="did you mean 'dijet'"):
        dt.generate("dijets")


def test_custom_events() -> None:
    ev = dt.custom_event([{"particle": "mu+", "pt": 40, "eta": 0.5, "phi": 30}, {"particle": "jet", "pt": 60, "phi": 200},
                          {"particle": "nu_mu", "pt": 35, "phi": 120}], seed=3, products=[1, 2])
    assert [k for k, _ in ev.objects()] == ["particle", "jet"]   # listed order, neutrino not listed
    assert ev.jets[0].pt == pytest.approx(60) and math.degrees(ev.jets[0].phi) % 360 == pytest.approx(200)
    mx, my = ev.missing_pt()
    vis_x = 40 * math.cos(math.radians(30)) + 60 * math.cos(math.radians(200))
    assert mx == pytest.approx(-vis_x)
    assert len(ev.products) == 1 + len(ev.jets[0].members)
    with pytest.raises(VidgenError, match="outside the detector"):
        dt.custom_event([{"particle": "e-", "pt": 10, "eta": 3.5}])
    with pytest.raises(VidgenError, match="pt must be positive"):
        dt.custom_event([{"particle": "e-", "pt": 0}])


def test_towers_bin_and_scale() -> None:
    ev = dt.generate("dijet", 4)
    paths = [dt.trajectory(q, dt.Detector(2.0)) for q in ev.particles]
    deps = dt.deposits(ev, paths)
    for view in ("xy", "rz"):
        towers = dt.towers(ev, deps, view)
        assert sum(t.energy for t in towers) == pytest.approx(sum(d.energy for d in deps))
    assert dt.tower_fraction(50, 100) == 0.5 and dt.tower_fraction(500, 100) == 1.0 and dt.tower_fraction(0.1, 100) == 0.12
    assert dt.tower_fraction(100, 100, "log") == 1.0 and 0.5 < dt.tower_fraction(10, 100, "log") < 0.6


# ----- the scene ----------------------------------------------------------------------------------


def _params(**over: Any) -> Any:
    from vidgen.scenes.detector import Detector

    return Detector.parse_params({"event": {"preset": "z_to_mumu", "seed": 3}, **over}, "d")


def test_scene_params_are_checked() -> None:
    with pytest.raises(VidgenError, match="must be positive"):
        _params(field=0)
    with pytest.raises(VidgenError, match="one of the two"):
        _params(event={"preset": "dijet", "particles": [{"particle": "e-", "pt": 10}]})
    with pytest.raises(VidgenError, match="leaves no track"):
        _params(event={"particles": [{"particle": "gamma", "pt": 40, "leaves": ["track", "ecal"]}]})
    with pytest.raises(VidgenError, match="decays before it reaches"):
        _params(event={"particles": [{"particle": "tau-", "pt": 40}]})
    with pytest.raises(VidgenError, match="unknown preset"):
        _params(event="ttbar")
    with pytest.raises(VidgenError, match="numbered 1–1"):
        _params(event={"particles": [{"particle": "e-", "pt": 40}], "products": [2]})
    assert _params(event="h_to_4l").event == "h_to_4l"


def test_targets_and_switch_view_problems(make_project) -> None:
    from vidgen.scenes.detector import Detector

    names = Detector.target_names(_params())
    assert {"particle:1", "particle:mu+", "particle:mu-", "missing_pt", "layer:ecal", "legend", "soft"} <= set(names)
    assert Detector.target_text(_params(), "particle:mu+") == PARTICLES["mu+"].name

    def problems(*scenes: dict[str, Any]) -> list[str]:
        return [m.message for m in project_problems(Project.load(make_project(minimal_config(scenes=list(scenes), narration=NARRATION))))]

    det = {"id": "d", "type": "detector", "params": {"event": "z_to_mumu"},
           "beats": [{"text": "a muon", "actions": [{"highlight": "particle:mu+"}]}, {"text": "side", "actions": [{"action": "switch_view", "to": "rz"}]}]}
    assert problems(det) == []
    other = {"id": "b", "type": "bullets", "params": {"items": ["a"]}, "beats": [{"text": "go", "actions": [{"action": "switch_view"}]}]}
    assert any("switch_view is an action of detector scenes" in m for m in problems(other))
    photon_track = {**det, "params": {"event": "h_to_gammagamma"}, "beats": [{"text": "x", "actions": [{"highlight": "particle:mu+"}]}]}
    assert any("unknown target 'particle:mu+'" in m for m in problems(photon_track))


def test_the_package_needs_no_manim() -> None:
    import subprocess
    import sys

    code = "import sys; import vidgen.particle_physics.detector as d; d.generate('dijet', 1); print('manim' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert out.stdout.strip() == "False"


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(320, 180), (180, 320)], ids=["landscape", "portrait"])
def test_event_display_renders(size: tuple[int, int], make_project, media: Path) -> None:
    scene = {"id": "d", "type": "detector", "params": {"title": "Z to muons", "event": {"preset": "z_to_mumu", "seed": 3}},
             "beats": [{"text": "the detector"}, {"text": "tracks"}, {"text": "muons", "actions": [{"highlight": "particle:mu+"}]},
                       {"text": "from the side", "actions": [{"action": "switch_view", "to": "rz"}]}]}
    project = Project.load(make_project(minimal_config(scenes=[scene], narration=NARRATION)))
    s = render(project, "d", media, size)
    registered = sorted({n for t in s.targets for n in t.names})
    assert registered == sorted(type(s).target_names(s.params))
    assert all(s.is_shown(n) for n in ("detector", "tracks", "muon_hits", "readout", "legend", "particle:mu+"))
    assert s.current_view() == "rz"
    # every part stays inside the frame
    fw, fh = s.camera.frame_width, s.camera.frame_height
    for m in s.mobjects:
        if m.family_members_with_points():
            assert abs(m.get_x()) + m.width / 2 <= fw / 2 + 1e-3 and abs(m.get_y()) + m.height / 2 <= fh / 2 + 1e-3


@pytest.mark.render
def test_missing_pt_arrow_points_away_from_the_visible(make_project, media: Path) -> None:
    scene = {"id": "w", "type": "detector", "params": {"event": {"particles": [{"particle": "e+", "pt": 40, "phi": 0}, {"particle": "nu_e", "pt": 40, "phi": 180}]},
                                                       "reveal": "all"},
             "beats": [{"text": "an electron and missing momentum"}]}
    project = Project.load(make_project(minimal_config(scenes=[scene], narration=NARRATION)))
    s = render(project, "w", media, (320, 180))
    arrow = s._containers["met"]
    assert arrow.family_members_with_points()
    assert arrow.get_center()[0] < s._drawn.origin[0]   # the electron goes right, the missing p_T left
    assert s._event.met == pytest.approx(40)


# ----- Step 240's review fixes of Step 239 ------------------------------------------------------


def test_sqrt_of_a_sum_is_set_apart_from_the_next_factor() -> None:
    from vidgen.quantities import expr

    def tex(text: str) -> str:
        return expr.to_tex(expr.parse(text), lambda n: None)[0]

    assert tex("sqrt(gamma^2 - 1)*c*tau") == r"\sqrt{{gamma}^{2} - 1}\,c \tau"
    assert tex("sqrt(x)*c") == r"\sqrt{x} c"   # a plain root: unchanged
    assert tex("2*sqrt(a+b)") == r"2\,\sqrt{a + b}"


def test_model_columns_carry_axis_labels() -> None:
    from vidgen.plotcore.models import run_registered

    sim = run_registered("two_body_opening", params={"M": 0.135})
    assert sim.units["theta_min"] == "deg" and sim.units["p"] == "GeV/c"
    assert sim.labels["theta_min"].startswith("smallest opening angle")
    assert run_registered("two_body_opening", params={"M": 0.135}, units={"theta_min": "rad"}).units["theta_min"] == "rad"
    column = next(c for c in sim.table().columns if c.name == "theta_min")
    assert column.label == sim.labels["theta_min"]


@pytest.mark.render
def test_feynman_diagram_is_centred_without_a_rule_card(make_project, media: Path) -> None:
    scene = {"id": "f", "type": "feynman", "params": {"preset": "bhabha"},
             "beats": [{"text": "they meet"}, {"text": "a photon", "actions": [{"vertex_rule": "vertex:v1"}]}, {"text": "and on"}]}
    project = Project.load(make_project(minimal_config(scenes=[scene], narration=NARRATION)))
    s = render(project, "f", media, (320, 180))
    assert s._centred[0] > 0 and np.allclose(s._offset, s._centred)   # docked for the card, back after it
    dots = [parts["dot"] for name, parts in s._parts.items() if name.startswith("vertex:")]
    middle = (min(d.get_x() for d in dots) + max(d.get_x() for d in dots)) / 2
    assert abs(middle - s.safe_area.center[0]) < 0.6


def test_kinematics_key_readout() -> None:
    from vidgen.scenes.kinematics import Kinematics

    p = Kinematics.parse_params({"decay": "pi+ -> mu+ nu_mu", "momentum": "200 MeV/c", "si": True}, "k")
    assert p.readout == "key"
    p_all = Kinematics.parse_params({"decay": "pi+ -> mu+ nu_mu", "momentum": "200 MeV/c", "readout": "all"}, "k")
    assert p_all.readout == "all"

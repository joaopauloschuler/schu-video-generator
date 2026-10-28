"""Step 235: the orbital-mechanics example `examples/mars-transfer` through `vidgen validate` (16:9
and its 9:16 variant), the orbit_* and calc_* lint, and the numbers it narrates computed by its
scenes and by `vidgen.orbits`."""

from __future__ import annotations

import math
import shutil
from pathlib import Path

import pytest

from vidgen.cli import main, validate_all
from vidgen.project import Project

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "mars-transfer"


@pytest.mark.parametrize("variant", [None, "short"])
def test_the_example_validates_and_uses_orbits_and_calculations(variant: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = shutil.copytree(EXAMPLE, tmp_path / "mars", ignore=shutil.ignore_patterns("build", "output", "audio"))
    assert main(["validate", str(root)]) == 0
    capsys.readouterr()
    project = Project.load(root, variant=variant)
    assert validate_all(project, keep_going=True)[0] == []
    types = [s.type for s in project.config.scenes]
    assert types.count("orbit") == 3 and types.count("calculation") == 2
    assert project.config.voice.provider == "kokoro" and project.config.music is not None
    text = (root / "video.yaml").read_text(encoding="utf-8")
    for used in ("transfer: {ship: Ship, to: Mars}", 'date: "2026-10-28"', "event: {kind: opposition, of: Mars}", "from_scene: hohmann.dv1",
                 'burn: "burn:1"', "highlight: phase", "Circular, coplanar orbits (an approximation)", 'at: "@'):
        assert used in text, used


def test_the_lint_is_clean() -> None:
    from vidgen.lint.calc_rule import calc_issues
    from vidgen.lint.orbit_rule import orbit_issues

    for variant in (None, "short"):
        project = Project.load(EXAMPLE, variant=variant)
        rules = project.config.lint.rules
        for scene in project.config.scenes:
            assert calc_issues(project, scene.id, rules) == [], scene.id
            assert orbit_issues(project, scene.id, rules) == [], scene.id


def test_the_numbers_are_the_models() -> None:
    from vidgen.lint.calc_rule import candidates
    from vidgen.orbits import bodies, ephemeris as eph, manoeuvres as man
    from vidgen.orbits.values import AU, DAY

    project = Project.load(EXAMPLE)
    _, results = candidates(project)
    timing = {r.name: r.value.value_text() for r in results["timing"]}
    assert timing == {"a": "1.262 AU", "T": "259 d", "theta": "44.3°"}
    leaving = {r.name: r.value.value_text() for r in results["leaving"]}
    assert leaving == {"v_c": "7.726 km/s", "v_esc": "10.93 km/s", "dv_LEO": "3.59 km/s"}

    r1, r2 = eph.TABLE1["earth"][0][0] * AU, eph.TABLE1["mars"][0][0] * AU
    h = man.hohmann(bodies.GM_SUN, r1, r2, mu_target=bodies.GM_SUN + bodies.BODIES["mars"].gm)
    assert (round(h.dv1 / 1e3, 2), round(h.dv2 / 1e3, 2), round(h.time / DAY), round(math.degrees(h.phase), 1)) == (2.94, 2.65, 259, 44.3)
    assert round(eph.planet_synodic_period("earth", "mars") / DAY) == 780

    # the date scene: Mars 64° ahead on 2026-10-28, the Hohmann lead in early December 2026 and
    # January 2029, the opposition on 2027-02-19
    start = eph.julian_date("2026-10-28")

    def lead(jd: float) -> float:
        return (float(eph.longitude("mars", jd)) - float(eph.longitude("earth", jd)) + 180.0) % 360.0 - 180.0

    assert round(lead(start)) == 64
    need = math.degrees(h.phase)
    assert lead(eph.julian_date("2026-12-01")) > need > lead(eph.julian_date("2026-12-10"))
    assert lead(eph.julian_date("2029-01-01")) > need > lead(eph.julian_date("2029-01-15"))
    assert eph.next_event("opposition", "earth", "mars", start).date == "2027-02-19"


def test_the_readmes_and_the_cookbook_point_to_it() -> None:
    assert "examples/mars-transfer/README.md" in (REPO / "README.md").read_text(encoding="utf-8")
    assert "examples/mars-transfer/README.md" in (REPO / "docs" / "COOKBOOK-ORBITS.md").read_text(encoding="utf-8")
    assert "COOKBOOK-ORBITS.md" in (EXAMPLE / "README.md").read_text(encoding="utf-8")

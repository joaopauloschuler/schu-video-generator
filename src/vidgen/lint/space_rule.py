"""The ``space`` scene's lint rule (DESIGN.md §122.12): ``space_scene``, what its params show before
anything is drawn. A world whose globe turns more than ``degrees`` a frame (the orbit data's turning
under its speed-up, or a stated ``spin``) strobes; a body drawn enlarged that reaches past another's
middle covers it; free-standing worlds placed inside each other. The page's own checks (a subject
under 3 px, the camera inside a world, a jump between moves) are only known where the page stands at
each time: the page reports them as warnings when it is drawn (``vidgen still``, the render).

The scene's narration saying "to scale" while it enlarges bodies or compresses distances is
``orbit_scale``'s (:mod:`vidgen.lint.orbit_rule`), which reads the scene's ``scale:``."""

from __future__ import annotations

import base64
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import numpy as np

from vidgen.lint.rules import Issue, SceneContext, rule
from vidgen.lint.science_rule import ScienceIssue, _issues

if TYPE_CHECKING:
    from vidgen.config import LintRules
    from vidgen.project import Project


def space_params(spec: Any) -> Any | None:
    """A ``space`` scene's checked params, or None (the scene's own validation reports its faults)."""
    if spec.type != "space":
        return None
    from vidgen.scenes.space import Space

    try:
        return Space.Params.model_validate(spec.params)
    except Exception:  # noqa: BLE001 - validate reports it
        return None


def space_picture(spec: Any) -> str | None:
    """What a ``space`` scene keeps to scale, as :data:`vidgen.orbits.accuracy.PICTURES` names it
    (``true``, ``enlarged``, ``log``), for a scene with orbit data; None without (its sizes are the author's)."""
    params = space_params(spec)
    if params is None or params.orbits is None:
        return None
    return params.scale.mode if params.scale is not None else "true"


def _first_frames(params: Any, fps: int, seconds: float | None) -> dict[str, Any]:
    """The orbit data's first two frames (a speed-up's frame step; a span over the scene's frames, 8 s when its length is not known)."""
    from vidgen.scenes.orbit_data import make_orbit_data

    scene_frames = 1 if params.orbits.speedup is not None else max(1, round((seconds or 8.0) * fps))
    return make_orbit_data(params.orbits, fps, 2, scene_frames)


def _vector(text: str, k: int = 0) -> np.ndarray:
    return np.frombuffer(base64.b64decode(text), dtype="<f8").reshape(-1, 3)[k]


def space_issues(project: Project, scene_id: str, rules: LintRules) -> list[ScienceIssue]:
    """Every ``space_scene`` finding of scene ``scene_id``."""
    spec = project.scene(scene_id)
    params = space_params(spec)
    if params is None or rules.space_scene.severity == "off":
        return []
    out: list[ScienceIssue] = []
    fps = int(project.config.format.fps)
    limit = rules.space_scene.degrees
    first = spec.beats[0].id if spec.beats else None

    def add(message: str) -> None:
        out.append(ScienceIssue("space_scene", first, message))

    shown = {b.name: b for b in params.bodies}
    for b in params.bodies:
        if isinstance(b.spin, (int, float)) and not isinstance(b.spin, bool) and b.spin != 0:
            turn = 360.0 / (abs(b.spin) * fps)
            if turn > limit:
                add(f"bodies {b.name}: spin {b.spin:g} s turns the globe {turn:.0f} degrees a frame at {fps} fps (it strobes over {limit:g}); "
                    "give a longer spin")
    if params.orbits is not None:
        data = _first_frames(params, fps, spec.duration)
        times = np.frombuffer(base64.b64decode(data["time"]), dtype="<f8")
        per_frame = (times[1] - times[0]) if len(times) > 1 else 0.0
        enlarge = params.scale.enlarge if params.scale is not None and params.scale.mode == "enlarged" else 1.0
        bodies = {e["name"]: e for e in data["bodies"]}
        for name, body in shown.items():
            entry = bodies.get(name)
            rot = (entry or {}).get("rotation") or {}
            spin = body.spin if body.spin is not None else "true"
            if entry is None or spin not in ("true", True) or not rot.get("period") or rot.get("faces_parent"):
                continue
            turn = 360.0 * per_frame / abs(rot["period"])
            if turn > limit:
                add(f"bodies {name}: under the orbit data's speed-up it turns {turn:.0f} degrees a frame at {fps} fps (one turn in "
                    f"{abs(rot['period']) / per_frame:.1f} frames): it strobes; give spin: locked, spin: SECONDS (a stated artistic rate) "
                    "or a smaller speedup")
        if enlarge != 1.0:
            def factor(n: str) -> float:
                return float(enlarge.get(n, enlarge.get("default", 1.0))) if isinstance(enlarge, dict) else float(enlarge)
            names = [n for n, e in bodies.items() if e.get("radius")]
            for a in names:
                for b in names:
                    if a == b:
                        continue
                    gap = float(np.linalg.norm(_vector(bodies[a]["position"]) - _vector(bodies[b]["position"])))
                    if bodies[a]["radius"] * factor(a) > gap > 0:
                        add(f"scale: {a} enlarged {factor(a):g} times reaches past {b}'s middle ({bodies[a]['radius'] * factor(a) / 1000:,.0f} km "
                            f"against {gap / 1000:,.0f} km): it covers {b}; give {a} a smaller factor (enlarge: {{default: ..., {a}: ...}})")
    else:
        free = [(b.name, b.at, b.radius_m()) for b in params.bodies]
        from vidgen.scenes.space_params import point

        places = {n: np.array(point(at or [0, 0, 0], n)) for n, at, _ in free}
        for i, (a, _, ra) in enumerate(free):
            for b, _, rb in free[i + 1:]:
                gap = float(np.linalg.norm(places[a] - places[b]))
                if gap < ra + rb:
                    add(f"bodies {a} and {b} stand inside each other ({gap / 1000:,.0f} km apart, radii {ra / 1000:,.0f} and {rb / 1000:,.0f} km): move one (at:)")
    return out


@rule("space_scene", scope="scene")
def space_scene(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A space scene's globe turning too fast under its speed-up, an enlarged body covering another, worlds inside each other."""
    yield from _issues(ctx, "space_scene")


__all__ = ["space_issues", "space_params", "space_picture"]

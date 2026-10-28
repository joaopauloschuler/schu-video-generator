"""The orbital accuracy lint rules (Phase X, Step 234, DESIGN §98.8): an ``orbit`` scene's
narration and on-screen text against its model, and its model against physics.

``orbit_period`` (a period against Kepler's third law with the scene's μ), ``orbit_speed``
(vis-viva at the point named, escape and circular speeds), ``orbit_dv`` (a burn's or a transfer's
Δv, a gravity assist's gain and turning angle), ``orbit_transfer`` (transfer times, phase angles,
synodic periods and launch windows), ``orbit_distance`` (distances, altitudes, radii, Lagrange
points, size ratios), ``orbit_date`` (the date of an opposition or conjunction), ``orbit_scale``
(a picture called "to scale" that is not), ``orbit_conserved`` (an n-body run's energy, angular
momentum or Jacobi constant drifting: :meth:`Orbit.diagnostics`) and ``orbit_crash`` (a
periapsis in the atmosphere, an n-body body passing through another). Numbers are read by the
``calc_*`` machinery (:mod:`vidgen.quantities.accuracy`), the orbital knowledge is in
:mod:`vidgen.orbits.accuracy`; this module gathers each scene's values (:class:`Fact`). Other
scenes (cards, captions) are checked against the orbit scenes' values when they name the body.
The runner adds :func:`orbit_issues` to :attr:`SceneContext.science`.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import numpy as np

from vidgen.lint.calc_rule import screen_texts
from vidgen.lint.rules import Issue, SceneContext, rule
from vidgen.lint.science_rule import ScienceIssue, _issues, _params, _scene_class
from vidgen.orbits import accuracy as oa
from vidgen.quantities import accuracy as qa

if TYPE_CHECKING:
    from vidgen.config import LintRules, SceneConfig
    from vidgen.project import Project

ORBIT_RULES = oa.ORBIT_RULES
#: The drawn size below which the orbit scene enlarges a body (Manim units: the central body,
#: an orbiting one; ``scenes/orbit.py``) and the largest drawing scale any layout gives a
#: picture of half-width ``extent`` (units per metre × extent): a body is surely enlarged when
#: even that scale draws it smaller.
_MIN_RADII = (0.12, 0.075)
_MAX_SCALE = 7.0
_cache: dict[int, tuple[Any, dict[str, list[oa.Fact]]]] = {}


# ----- the model's values -------------------------------------------------------------------------------


def _subjects(*names: Any) -> tuple[str, ...]:
    out: list[str] = []
    for n in names:
        n = str(n or "").strip()
        if n and n not in out:
            out.append(n)
    return tuple(out)


def _body_facts(body: Any, subjects: tuple[str, ...], add: Any) -> None:
    """A body's radius, diameter, and the escape and circular speeds at its surface."""
    if body.radius <= 0:
        return
    add("radius", body.radius, f"{_the(body.name)}'s radius", subjects)
    add("diameter", 2 * body.radius, f"{_the(body.name)}'s diameter", subjects)
    if body.gm > 0:
        add("escape", math.sqrt(2 * body.gm / body.radius), f"the escape speed from {_the(body.name)}'s surface", subjects)
        add("circular", math.sqrt(body.gm / body.radius), f"the circular orbital speed at {_the(body.name)}'s surface", subjects)


def _orbit_facts(el: Any, parent: Any, name: str, subjects: tuple[str, ...], add: Any) -> None:
    """Period, speeds (vis-viva), distances and altitudes of one Kepler orbit around ``parent``."""
    from vidgen import orbits

    near, far = orbits.apsis_names(parent.name)
    mu, q = el.mu, el.periapsis
    pn = _the(parent.name)
    v_p = float(orbits.vis_viva(mu, q, el.a))
    add("peri_speed", v_p, f"{_the(name)}'s speed at {near}", subjects)
    add("peri", q, f"{_the(name)}'s {near} distance from {pn}'s centre", subjects)
    if parent.radius > 0:
        add("altitude", (q - parent.radius, q - parent.radius) if not el.closed else (q - parent.radius, el.apoapsis - parent.radius),
            f"{_the(name)}'s altitude above {pn}", subjects)
    if el.closed:
        big_q = el.apoapsis
        v_a = float(orbits.vis_viva(mu, big_q, el.a))
        add("period", el.period, f"{_the(name)}'s orbital period around {pn}", subjects)
        add("speed", (v_a, v_p), f"{_the(name)}'s speed around {pn}", subjects)
        add("apo_speed", v_a, f"{_the(name)}'s speed at {far}", subjects)
        add("apo", big_q, f"{_the(name)}'s {far} distance from {pn}'s centre", subjects)
        add("distance", (q, big_q), f"{_the(name)}'s distance from {pn}", subjects + _subjects(parent.name))
        add("escape", (math.sqrt(2 * mu / big_q), math.sqrt(2 * mu / q)), f"the escape speed from {pn} at {_the(name)}'s distance", subjects)
    else:
        v_inf = el.v_infinity
        add("speed", (v_inf, v_p), f"{_the(name)}'s speed around {pn}", subjects)
        add("v_inf", v_inf, f"{_the(name)}'s speed far from {pn} (v∞)", subjects)


_the = oa.the


def _scene_facts(spec: SceneConfig, params: Any) -> list[oa.Fact]:
    """Every value of an orbit scene a number may be about."""
    from vidgen import orbits

    out: list[oa.Fact] = []

    def add(kind: str, value: Any, what: str, subjects: tuple[str, ...] = (), order: int = 0) -> None:
        lo, hi = value if isinstance(value, tuple) else (value, value)
        if all(isinstance(x, (int, float)) and math.isfinite(x) for x in (lo, hi)):
            out.append(oa.fact(kind, (float(lo), float(hi)), what, subjects, order, spec.id))

    model = params.model()
    system = model.system
    sky = model.sky
    if sky is not None and sky.sizes is not None:   # the sizes picture: radii only
        for b in ([sky.sun] if sky.sun is not None else []) + list(sky.sizes):
            _body_facts(b, _subjects(b.name), add)
        return out
    central_label = getattr(params.central, "label", "") if not isinstance(params.central, str) else ""
    centre = system.central
    _body_facts(centre, _subjects(centre.name, central_label), add)
    many = model.many
    stand_ins = set(many.near) if many is not None else set()
    eight = many is not None and many.eight is not None
    specs = params.body_specs()
    closed: list[tuple[Any, tuple[str, ...]]] = []
    for spec_b, o in zip(specs, system.orbiters):
        subjects = _subjects(o.name, spec_b.label)
        _body_facts(o.body, subjects, add)
        if o.name in stand_ins or eight:
            continue
        parent = system.parent_body(o)
        arcs = [a.elements for a in o.trajectory.arcs] if o.trajectory is not None else [o.elements]
        for el in arcs:
            _orbit_facts(el, parent, o.name, subjects, add)
        if o.trajectory is None and o.elements.closed:
            closed.append((o, subjects))
    # two bodies around the same parent: their distance apart, their synodic period
    for k, (a, sa) in enumerate(closed):
        for b, sb in closed[k + 1:]:
            if a.parent != b.parent:
                continue
            ea, eb = a.elements, b.elements
            inner, outer = (ea, eb) if ea.a <= eb.a else (eb, ea)
            add("between", (max(0.0, outer.periapsis - inner.apoapsis), inner.apoapsis + outer.apoapsis),
                f"the distance between {a.name} and {b.name}", sa + sb)
            if not math.isclose(ea.period, eb.period, rel_tol=1e-9):
                add("synodic", 1.0 / abs(1.0 / ea.period - 1.0 / eb.period), f"the synodic period of {a.name} and {b.name}", sa + sb)
    _manoeuvre_facts(model, add)
    if model.shots:
        r0 = float(np.linalg.norm(model.cannon_at))
        ball = _subjects("ball", "cannonball", "cannon")
        for k, shot in enumerate(model.shots, start=1):
            add("shot", shot.speed, f"shot {k}'s launch speed", ball)
            if shot.elements.closed and shot.kind != "suborbital":
                add("period", shot.elements.period, f"shot {k}'s orbital period", ball)
        add("circular", math.sqrt(centre.gm / r0), "the circular speed at the cannon", ball + _subjects(centre.name))
        add("escape", math.sqrt(2 * centre.gm / r0), "the escape speed at the cannon", ball + _subjects(centre.name))
    if many is not None and many.restricted is not None:
        pair = many.restricted.pair
        mu, sep = pair.mu, pair.separation
        primary, secondary = np.array([-mu * sep, 0.0]), np.array([(1 - mu) * sep, 0.0])
        for name, p in pair.points().items():
            p2 = np.asarray(p, dtype=float)[:2]
            add("lagrange", float(np.linalg.norm(p2 - secondary)), f"{name}'s distance from {_the(pair.secondary.name)}", (name,))
            add("lagrange", float(np.linalg.norm(p2 - primary)), f"{name}'s distance from {_the(pair.primary.name)}", (name,))
    if eight:
        add("period", many.eight.period, "the figure-eight's period", _subjects(*system.names, "figure-eight", "figure of eight"))
    if sky is not None and sky.event is not None:
        ev = sky.event
        add("between", ev.distance, f"the distance between {ev.observer.capitalize()} and {ev.target.capitalize()} at the {ev.kind.replace('_', ' ')} "
                                    f"({ev.date})", _subjects(ev.observer.capitalize(), ev.target.capitalize()))
    return out


def _manoeuvre_facts(model: Any, add: Any) -> None:
    """A transfer's Δv, time, phase angle, synodic period and wait; plain burns; a flyby's speeds,
    gain and turning angle."""
    info = model.transfer
    burns = model.burns()
    if info is not None:
        r = info.result
        who = _subjects(info.ship, info.target)
        kind = {"hohmann": "Hohmann transfer", "bielliptic": "bi-elliptic transfer", "phasing": "phasing"}[info.kind]
        if info.kind == "phasing":
            add("dv", r.dv, f"each burn of the {kind}", who, 1)
            add("dv", r.dv, f"each burn of the {kind}", who, 2)
            add("transfer_time", r.time, f"the {kind}'s time ({r.revolutions} turns)", who)
            add("phase", abs(r.angle), f"{info.target}'s lead over {info.ship} at the first burn", who)
        else:
            dvs = [r.dv1, r.dv2] + ([r.dv3] if info.kind == "bielliptic" else [])
            for n, dv in enumerate(dvs, start=1):
                add("dv", dv, f"Δv{'₀₁₂₃'[n]} of the {kind}", who, n)
            add("transfer_time", info.arrival - info.depart, f"the {kind}'s time of flight", who)
        add("dv_total", r.total, f"the {kind}'s total Δv", who)
        if info.phase_needed is not None:
            from vidgen.scenes.orbit_parts import lead_angle   # the scene's own measure (loaded with the scene type)

            add("phase", abs(info.phase_needed), f"the lead {info.target} needs at departure (the launch window)", who, 1)
            add("phase", abs(lead_angle(model.system, info.ship, info.target, 0.0)), f"{info.target}'s lead over {info.ship} at the start", who)
            add("synodic", 2 * math.pi / abs(info.n_ship - info.n_target), f"the time between launch windows (synodic period of {info.ship} and "
                                                                           f"{info.target})", who)
            if info.depart > 0:
                add("wait", info.depart, "the wait for the launch window", who)
    elif burns:
        for n, (name, b) in enumerate(burns, start=1):
            add("dv", b.magnitude, f"burn {n}'s Δv" + (f" ({b.label})" if b.label else ""), _subjects(name), n)
        add("dv_total", sum(b.magnitude for _, b in burns), "the total Δv of the burns", _subjects(*sorted({name for name, _ in burns})))
    if model.assist is not None:
        ga = model.assist.assist
        fb = ga.flyby
        who = _subjects(model.assist.probe, model.assist.planet)
        add("planet_speed", model.assist.planet_speed, f"{model.assist.planet}'s speed around the Sun", _subjects(model.assist.planet))
        add("sun_speed", ga.speed_before, f"{model.assist.probe}'s speed around the Sun before the pass", who)
        add("sun_speed", ga.speed_after, f"{model.assist.probe}'s speed around the Sun after the pass", who)
        add("gain", abs(ga.gain), f"the speed {model.assist.probe} {'gains' if ga.gain >= 0 else 'loses'} around the Sun", who)
        add("turn", fb.delta, "the turning angle of the pass", who)


def facts(project: Project) -> dict[str, list[oa.Fact]]:
    """Every orbit scene's values (``{scene id: [Fact]}``), computed once per project."""
    key = id(project)
    if key in _cache and _cache[key][0] is project:
        return _cache[key][1]
    found: dict[str, list[oa.Fact]] = {}
    for spec in project.config.scenes:
        if spec.type != "orbit":
            continue
        params = _params(spec)
        if params is None:
            continue
        try:
            found[spec.id] = _scene_facts(spec, params)
        except Exception:  # noqa: BLE001 - validation reports a scene that cannot be resolved
            continue
    _cache.clear()
    _cache[key] = (project, found)
    return found


# ----- the picture and the run ---------------------------------------------------------------------------


def picture_kind(params: Any) -> str:
    """What the scene draws to scale (:data:`vidgen.orbits.accuracy.PICTURES`); ``true`` also
    when it cannot be sure the bodies are enlarged (no finding then)."""
    from vidgen import orbits

    model = params.model()
    if model.sky is not None and model.sky.sizes is not None:
        return "sizes"
    if model.many is not None and model.many.tides is not None:
        return "schematic"
    if model.sky is not None and model.sky.log:
        return "log"
    if params.extent is not None:
        reach = orbits.value_si(params.extent, "length", "extent")
    else:
        ts = np.linspace(0.0, model.span, 200)
        names = [o.name for o in model.system.orbiters]
        reach = max([float(np.max(np.linalg.norm(model.view(n, ts)[:, :2], axis=1))) for n in names] + [0.0])
        reach = max([reach] + [o.elements.apoapsis for o in model.system.orbiters if o.parent is None and o.elements.closed])
    if reach <= 0:
        return "true"
    bodies = [(model.system.central, _MIN_RADII[0])] + [(o.body, _MIN_RADII[1]) for o in model.system.orbiters]
    enlarged = any(b.radius > 0 and _MAX_SCALE * b.radius / reach < smallest for b, smallest in bodies)
    return "enlarged" if enlarged else "true"


def _conserved(params: Any, tolerance: float, add: Any) -> None:
    cls = _scene_class("orbit")
    try:
        found = cls.diagnostics(params)
    except Exception:  # noqa: BLE001 - validation reports a run that fails
        return
    step = f"step {params.step}" if params.step else "the default step"
    names = {"energy_drift": "the total energy", "angular_drift": "the angular momentum", "closure": "the figure-eight's return to its start"}
    for key, drift in found.items():
        if not math.isfinite(drift) or drift <= tolerance:
            continue
        if key.startswith("jacobi_drift:"):
            what = f"{key.partition(':')[2]}'s Jacobi constant"
            fix = "keep method rk45 (the default with a pair) or give a smaller step; a body that passes very close to the secondary needs it"
        else:
            what = names.get(key, key)
            fix = (f"halve the step (now {step})" if params.method == "leapfrog" else
                   f"use method: leapfrog (symplectic: its energy error stays bounded) or a smaller step (now {step}, method {params.method})")
        verb = "misses by" if key == "closure" else "drifts by"
        add("orbit_conserved", f"{what} is conserved by the physics but {verb} {drift:.2%} over the run (more than {tolerance:.2%}): the motion "
                               f"shows the integrator's error, not physics; {fix}")


def _atmosphere(body: Any) -> tuple[float, str] | None:
    from vidgen import orbits

    key = body.name.strip().lower()
    preset = orbits.BODIES.get(key)
    if key not in oa.ATMOSPHERES or preset is None or not math.isclose(body.radius, preset.radius, rel_tol=0.01):
        return None
    return oa.ATMOSPHERES[key]


def _crash(params: Any, add: Any) -> None:
    model = params.model()
    system = model.system
    if model.sky is not None and model.sky.sizes is not None:
        return
    probe = model.assist.probe if model.assist is not None else None
    for o in system.orbiters:
        parent = system.parent_body(o)
        air = _atmosphere(parent)
        if air is None or o.name == probe:   # the flyby's own message below
            continue
        arcs = [(f"after burn {k}" if k else "", a.elements) for k, a in enumerate(o.trajectory.arcs)] if o.trajectory is not None else [("", o.elements)]
        for when, el in arcs:
            height = el.periapsis - parent.radius
            if 0 < height < air[0]:
                add("orbit_crash", f"{o.name}'s periapsis{' ' + when if when else ''} is {height / 1000:,.0f} km above {_the(parent.name)}, inside its "
                                   f"atmosphere ({air[1]}): drag would bring it down within a few passes; raise the periapsis, or say it is a "
                                   f"re-entry or aerobraking pass")
    if model.assist is not None:
        fb = model.assist.assist.flyby
        air = _atmosphere(system.central)
        if air is not None and fb.atmosphere <= 0 and 0 < fb.rp - fb.radius < air[0]:
            add("orbit_crash", f"the flyby passes {(fb.rp - fb.radius) / 1000:,.0f} km above {_the(system.central.name)}, inside its atmosphere ({air[1]}): "
                               f"pass higher, or give flyby.atmosphere to have it checked")
    run = model.run
    if run is None:
        return
    times = np.asarray(run.times, dtype=float)
    names = [system.central.name] + system.names
    bodies = {system.central.name: system.central} | {o.name: o.body for o in system.orbiters}
    paths = {n: model.position(n, times) for n in names}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            reach = bodies[a].radius + bodies[b].radius
            if reach <= 0:
                continue
            d = np.linalg.norm(paths[a] - paths[b], axis=1)
            k = int(np.argmin(d))
            if d[k] < reach:
                from vidgen import orbits

                unit, scale = orbits.time_unit(model.span)
                add("orbit_crash", f"{b} passes within {d[k] / 1000:,.0f} km of {a}'s centre at t ≈ {times[k] / scale:.3g} {unit}, inside "
                                   f"{'it' if bodies[a].radius >= reach else 'their radii'}: the bodies collide (the n-body run treats them as "
                                   f"points); change the starting state, or end the span before it")


# ----- the findings ---------------------------------------------------------------------------------------


def _texts(spec: SceneConfig) -> list[tuple[str | None, str, str | None]]:
    """``(beat, text, where)``: the narration, then the screen texts (with burn labels)."""
    first = spec.beats[0].id if spec.beats else None
    out: list[tuple[str | None, str, str | None]] = [(beat.id, str(beat.text), None) for beat in spec.beats]
    out += [(first, text, where) for where, text in screen_texts(spec)]
    if spec.type == "orbit":
        for k, body in enumerate(spec.params.get("bodies") or [], start=1):
            for n, burn in enumerate((body.get("burns") or []) if isinstance(body, dict) else [], start=1):
                if isinstance(burn, dict) and isinstance(burn.get("label"), str) and burn["label"]:
                    out.append((first, burn["label"], f"bodies[{k}].burns[{n}].label"))
    return out


def orbit_issues(project: Project, scene_id: str, rules: LintRules) -> list[ScienceIssue]:
    """Every orbital finding of scene ``scene_id`` (rules turned off are skipped)."""
    spec = project.scene(scene_id)
    on = {name for name in ORBIT_RULES if getattr(rules, name).severity != "off"}
    if not on:
        return []
    out: list[ScienceIssue] = []
    seen: set[tuple[str, str | None, str]] = set()
    first = spec.beats[0].id if spec.beats else None

    def add(rule_name: str, message: str, beat: str | None = first) -> None:
        if rule_name in on and (rule_name, beat, message) not in seen:
            seen.add((rule_name, beat, message))
            out.append(ScienceIssue(rule_name, beat, message))

    found = facts(project)
    is_orbit = spec.type == "orbit"
    params = _params(spec) if is_orbit else None
    own = found.get(scene_id, []) if is_orbit else []
    has_own_numbers = spec.type == "calculation" or spec.type == "plot" and bool(spec.params.get("fits"))
    others = [] if is_orbit or has_own_numbers else [f for sid, rows in found.items() for f in rows if f.subjects]
    tolerances = {name: getattr(getattr(rules, name), "tolerance", 0.05) for name in ORBIT_RULES}
    picture = scene_event = None
    radii: dict[str, float] = {}
    if params is not None:
        try:
            picture = picture_kind(params)
            sky = params.model().sky
            scene_event = sky.event if sky is not None else None
        except Exception:  # noqa: BLE001 - validation reports it
            params = None
        radii = {f.subjects[0]: f.low for f in own if f.kind == "radius" and f.subjects}
    days = rules.orbit_date.days
    for beat, text, where in _texts(spec):
        def said(sentence: str) -> str:
            return f"{where} '{qa.quote(sentence)}'" if where else f'"{qa.quote(sentence)}"'

        for sentence in qa.statements(text):
            if own or others:
                for claim in oa.orbit_claims(sentence, own or others, tolerances, scene_id, need_name=not own):
                    add(claim.rule, f"{said(sentence)}: {claim.message}", beat)
            for message in oa.ratio_claims(sentence, radii):
                add("orbit_distance", f"{said(sentence)}: {message}", beat)
            if "orbit_date" in on:
                for message in oa.event_claims(sentence, days, scene_event):
                    add("orbit_date", f"{said(sentence)}: {message}", beat)
            if picture is not None:
                message = oa.scale_claims(sentence, picture)
                if message is not None:
                    add("orbit_scale", f"{said(sentence)} claims scale, but {message}", beat)
    if params is not None:
        if "orbit_conserved" in on:
            _conserved(params, rules.orbit_conserved.tolerance, add)
        if "orbit_crash" in on:
            _crash(params, add)
    return out


# ----- the rules -----------------------------------------------------------------------------------------


@rule("orbit_period", scope="scene")
def orbit_period(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A period said or shown for a body that Kepler's third law (with the scene's masses) does not give."""
    yield from _issues(ctx, "orbit_period")


@rule("orbit_speed", scope="scene")
def orbit_speed(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A speed against vis-viva at the point named (perihelion, aphelion...), or an escape or circular speed."""
    yield from _issues(ctx, "orbit_speed")


@rule("orbit_dv", scope="scene")
def orbit_dv(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A Δv said for a burn or a transfer (or a gravity assist's gain or turning angle) that the scene does not compute."""
    yield from _issues(ctx, "orbit_dv")


@rule("orbit_transfer", scope="scene")
def orbit_transfer(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A transfer time, phase angle, synodic period or launch-window wait against the scene's transfer."""
    yield from _issues(ctx, "orbit_transfer")


@rule("orbit_distance", scope="scene")
def orbit_distance(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A distance, altitude, radius, Lagrange point or size ratio against the scene's bodies and orbits."""
    yield from _issues(ctx, "orbit_distance")


@rule("orbit_date", scope="scene")
def orbit_date(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """The date of an opposition or conjunction against JPL's approximate elements (1800–2050)."""
    yield from _issues(ctx, "orbit_date")


@rule("orbit_scale", scope="scene")
def orbit_scale(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A picture called "to scale" that is not: enlarged bodies, a log view, the sizes picture's distances, the tides schematic."""
    yield from _issues(ctx, "orbit_scale")


@rule("orbit_conserved", scope="scene")
def orbit_conserved(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """An n-body run whose energy, angular momentum or Jacobi constant drifts beyond tolerance."""
    yield from _issues(ctx, "orbit_conserved")


@rule("orbit_crash", scope="scene")
def orbit_crash(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A periapsis inside an atmosphere, or bodies of an n-body run passing through each other."""
    yield from _issues(ctx, "orbit_crash")

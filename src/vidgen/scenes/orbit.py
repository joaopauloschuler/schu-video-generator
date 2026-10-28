"""``orbit``: bodies on their orbits, moving in correct timing (Phase X, DESIGN §98). A central
body, bodies from presets, orbital elements or a position and velocity, their orbits drawn as
conics, the bodies moving along them by Kepler's equation (or by n-body integration with
leapfrog / RK45), fading trails, an equal-aspect frame on the plot core (AU or km ticks, or a
scale bar), a side panel with the simulated time, the speed-up and a legend, and a view that can
follow a body. The bodies move from the end of the first beat's entrance to the scene's end at
one constant speed-up, so equal video times are equal simulated times and Kepler's second law
shows as it is. Step 230 adds the overlays of Kepler's laws and orbital speed (the ellipse's
geometry, equal-time sectors, velocity vectors, Newton's cannonball: ``orbit_overlays.py``) and
the actions ``sweep`` and ``launch`` (``orbit_actions.py``). Step 231 adds manoeuvres — burns,
transfers (Hohmann, bi-elliptic, phasing), a flyby with its Sun-frame vector diagram — and a
clock that can run in stretches (a burn on its word, pauses): ``orbit_manoeuvres.py``. Step 232
adds many bodies — a restricted three-body pair in the inertial or rotating frame with its
Lagrange points, the figure-eight, binaries, resonances, the tidal schematic:
``orbit_systems.py`` (params) and ``orbit_many.py`` (drawing). Step 233 adds the Solar System on a
date — JPL's approximate elements, oppositions and conjunctions, the log view, the inset, sizes
to scale — and the compact side panel: ``orbit_sky.py``. The params and the model are in
``orbit_parts.py``; the physics in ``vidgen.orbits``."""

import datetime as dt
import math
from dataclasses import replace
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .orbit_manoeuvres import VECTOR_GAP, OrbitManoeuvres
from .orbit_overlays import (DIAGNOSTIC, PANEL_BUDGET, PANEL_ROWS, OrbitOverlays, PanelMode, Slot, arrow_shape, choose_rows, leader_points, mob_rect,
                             new_arrow, place)
from .orbit_many import OrbitMany, many_target_names
from .orbit_parts import LagrangeName, OrbitBody, OrbitCannon, OrbitCentral, OrbitFlyby, OrbitModel, OrbitTransfer, Value, resolve_model
from .orbit_sky import OrbitEvent, OrbitSizes, OrbitSky, SkySpec, sky_target_names
from .orbit_systems import ManySpec, OrbitResonance, OrbitSystem, OrbitTides

#: Smallest drawn radius (Manim units) of the central body and of an orbiting body: smaller
#: bodies are enlarged to it (and the readout says "sizes not to scale").
MIN_CENTRAL_RADIUS = 0.12
MIN_BODY_RADIUS = 0.075
#: A trail is drawn as this many pieces, fading towards its tail.
TRAIL_PIECES = 8
TRAIL_SAMPLES = 64
#: Points along a drawn conic.
CONIC_SAMPLES = 360
#: A margin around the data, as a share of its span (as the plot scene's equal aspect).
MARGIN = 0.06
#: The margin when bodies burn (their Δv arrows and labels stand at the edge of their orbits).
BURN_MARGIN = 0.13
#: Space between the plot and the side panel.
BOX_GAP = 0.45
#: In a vertical frame a panel of more rows than this is set in two columns, this far apart.
PANEL_ROWS_PORTRAIT = 5
PANEL_COLUMN_GAP = 0.35
#: Space between the x tick labels and the unit written after them (16:9).
UNIT_GAP = 0.25
#: Width kept in a side panel row for the velocity key's arrow and its gap.
KEY_ROOM = 1.25
#: Resolved models by the params' JSON (validation, vidgen validate and the render resolve a
#: scene more than once; an n-body run takes a moment).
_MODELS: dict[str, OrbitModel] = {}
MODEL_CACHE = 32


@scene("orbit")
class Orbit(OrbitSky, OrbitMany, OrbitManoeuvres, OrbitOverlays, NarratedScene):
    """Orbits in correct timing: a central body (``central``: a preset or your own) and
    ``bodies`` on Kepler orbits (presets, elements, or a position and velocity), drawn as conics
    with the bodies moving along them through the whole scene at one speed-up (``span`` or
    ``orbits`` of simulated time), fading trails, an equal-aspect frame in AU or km (``frame``:
    axes, a scale bar or none), a side panel with the time, speed-up and a legend, ``follow`` to
    move with a body, ``dynamics: nbody`` for mutual gravity (leapfrog, with the energy error
    shown). Kepler's laws and orbital speed: a body's ``geometry`` (foci, a, b, apsides),
    ``sectors`` (equal areas in equal times) and ``velocity`` (vectors, vis-viva speed);
    ``cannonball`` (Newton's cannon: one point, increasing speeds). Manoeuvres: a body's
    ``burns`` (Δv prograde, radial, normal...), a ``transfer`` (Hohmann, bi-elliptic, phasing:
    Δv₁, Δv₂, transfer time, phase angle, launch windows), a ``flyby`` (a gravity assist in the
    planet's frame with the Sun-frame vector diagram).

    Action targets: ``title``, ``frame``, ``central``, ``body:<name>``, ``orbit:<name>``,
    ``geometry:<name>``, ``foci:<name>``, ``axes:<name>``, ``periapsis:<name>``,
    ``apoapsis:<name>``, ``sectors:<name>``, ``velocity:<name>``, ``cannon``, ``shot:<n>``,
    ``burn:<n>``, ``transfer``, ``phase``, ``asymptotes``, ``turn``, ``v_inf``, ``motion``,
    ``atmosphere``, ``vectors``, ``v_before``, ``v_after``, ``lagrange``, ``lagrange:<L>``,
    ``zero_velocity``, ``rotation``, ``barycentre``, ``conjunctions``, ``pointer``, ``pull``,
    ``mean``, ``tidal``, ``bulges``, ``face``, ``event``, ``inset``, ``rings``, ``readout``; actions ``sweep`` (sectors),
    ``launch`` (shots), ``burn`` (a burn on its word), ``flyby`` (the periapsis passage on its
    word), ``pause`` and ``coast`` (the clock held and run again), ``corotate`` and ``inertial``
    (the view of a three-body pair turned on a word). Many bodies (Step 232): ``system`` (a
    restricted three-body pair or the figure-eight), ``view``, ``origin``, ``lagrange``,
    ``zero_velocity``, ``resonance``, ``center``, ``tides``. The Solar System on a date (Step
    233): ``date``, ``event``, ``radial``, ``inset``, ``sizes``; the side panel's rows ``panel``.
    """

    outro = 0.5
    orbit_actions = True
    target_patterns = ("title", "frame", "central", "body:<name>", "orbit:<name>", "geometry:<name>", "foci:<name>", "axes:<name>",
                       "periapsis:<name>", "apoapsis:<name>", "sectors:<name>", "velocity:<name>", "cannon", "shot:<n>", "burn:<n>", "transfer",
                       "phase", "asymptotes", "turn", "v_inf", "motion", "atmosphere", "vectors", "v_before", "v_after", "lagrange", "lagrange:<L>",
                       "zero_velocity", "rotation", "barycentre", "conjunctions", "pointer", "pull", "mean", "tidal", "bulges", "face", "event", "inset", "rings", "readout")

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        central: str | OrbitCentral = "sun"
        """The central body: a preset (sun, earth, mars, jupiter, moon...) or {name, gm or mass, radius}."""
        bodies: list[OrbitBody] = Field(default_factory=list)
        """The orbiting bodies: [{preset: earth}, {name: Probe, a: '1.5 AU', e: 0.4}, {name: Ship, r: ['7000 km', 0], v: [0, '8 km/s']}] (may be empty with a cannonball)."""
        cannonball: OrbitCannon | None = None
        """Newton's cannonball: shots from one point above the central body at increasing speeds ({speeds: [0.7, 0.9, 1, 1.2, escape, 1.6], altitude: '600 km'}), each classified by its energy."""
        transfer: OrbitTransfer | None = None
        """A transfer flown by one body between circular coplanar orbits: {kind: hohmann, ship: Ship, to: Mars} (or to: '42164 km'; kind: bielliptic with apoapsis, phasing); its burns, Δv budget, time, phase angle and launch windows computed."""
        flyby: OrbitFlyby | None = None
        """A gravity assist past the central body, in its frame: {v_inf: '5.6 km/s', altitude: '200000 km', side: behind}; the hyperbola, asymptotes, turning angle and the Sun-frame vector diagram."""
        span: Value | None = None
        """Simulated time the scene shows ('1 yr', '92 min', '30 d'); or orbits."""
        orbits: float | None = Field(default=None, gt=0)
        """Simulated time in periods of the first body (default 1 when span is not given; a closed orbit)."""
        dynamics: Literal["kepler", "nbody"] = "kepler"
        """kepler: each body on its two-body orbit (exact, Kepler's equation); nbody: every body with mass pulls on every other (integrated)."""
        method: str = "leapfrog"
        """n-body method: leapfrog (velocity Verlet, symplectic: energy error bounded) or rk45 (adaptive; drifts over long runs; the default with a three-body pair, whose small body may pass close to the secondary)."""
        step: Value | None = None
        """n-body leapfrog step ('1 h'); default 1/1000 of the shortest orbital time scale."""
        frame: Literal["axes", "scale_bar", "none"] = "axes"
        """axes: x and y axes with AU or km ticks (equal aspect); scale_bar: a bar of a round length; none."""
        unit: Literal["auto", "AU", "km"] = "auto"
        """Unit of the axes and scale bar; auto: AU when the view spans more than 0.05 AU, else km."""
        extent: Value | None = None
        """Half-width of the view around its centre ('2 AU'); default: every orbit with a margin."""
        follow: str | None = None
        """A body the view moves with (its satellites' orbits stay still around it); default: the central body stays at the centre."""
        readout: bool = True
        """Show the simulated time and the speed-up (and the energy error with nbody)."""
        energy: bool | None = None
        """Show the n-body energy error ΔE/E (default: on with dynamics: nbody)."""
        legend: bool | Literal["auto"] = "auto"
        """List the bodies with their periods in the side panel; auto: with two or more bodies when the panel has room (16:9); true: always."""
        panel: PanelMode | list[str] = "compact"
        """The side panel's rows: compact (the time, the speed-up and the few values the scene is about, at a readable size; diagnostics such as ΔE/E, ΔL/L and the Jacobi drift left out), full (every row), none (only a 'not to scale' note), or a list of row names ([time, total_dv, phase]; see the guide)."""
        label_size: ThemeSize | None = None
        """Size of tick labels, body labels and the readout (never below the readable minimum); default: caption (the picture gets the room)."""
        caption: TranslatableStr = ""
        """Note under the picture (e.g. the source of the elements)."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""
        caption_color: ThemeColor = "dim"
        """Caption color."""
        title_size: ThemeSize = "heading"
        """Title size."""
        title_color: ThemeColor = "text"
        """Title color."""
        system: OrbitSystem | None = None
        """Many bodies (Step 232): a circular restricted three-body pair — earth_moon, sun_earth, sun_jupiter, or {primary: sun, secondary: jupiter, mu: 0.05} — integrated with every body near it (n-body), or figure_eight (three equal masses, Chenciner–Montgomery)."""
        view: Literal["inertial", "rotating"] = "inertial"
        """With a three-body pair: inertial (the pair goes round) or rotating (the frame turns with the pair: both stand still, the Lagrange points too); the actions corotate and inertial switch on a word."""
        origin: Literal["central", "barycentre"] | None = None
        """What stays at the centre of the view: the central body, or the barycentre of the bodies with mass (default with system; a binary star: both stars go round it)."""
        lagrange: bool | list[LagrangeName] = False
        """With a three-body pair: mark the Lagrange points (true: L1–L5, or some of them) computed for its mass ratio; their distances and Routh's stability test in the panel."""
        zero_velocity: bool | str = False
        """With a three-body pair: draw the zero-velocity curve of a body placed near a Lagrange point (true: the first), for its Jacobi constant: it cannot cross it."""
        resonance: OrbitResonance | None = None
        """A mean-motion resonance: [Io, Europa, Ganymede] or {bodies, conjunctions, keep}: period ratios, the Laplace angle of a 1:2:4 chain, conjunctions marked as they happen."""
        center: str | None = None
        """Centre the view on where this body is halfway through the span (with extent: a close-up; the central body far off is shown by an arrow at the edge)."""
        tides: OrbitTides | bool | None = None
        """The tidal schematic (true or {satellite: moon, locking, points}): the satellite's pull at points of the planet, the differential (tidal) arrows, the two bulges, tidal locking; labelled schematic, not to scale."""
        date: str | dt.date | None = None
        """The Solar System on a date (Step 233): '2020-10-13' (1800–2050) places the planet presets (and Pluto) by JPL's approximate elements and rates on that day; the panel shows the date as the clock runs."""
        event: OrbitEvent | None = None
        """With date: the next conjunction / opposition after it, found by root finding — {kind: opposition, of: Mars} (observer: Earth) — drawn as the line they will stand on; default span: until a little after it."""
        radial: Literal["linear", "log"] = "linear"
        """linear: true distances; log: distances compressed (log10(1 + r/r0)) so Mercury and Neptune fit one picture, with labelled rings instead of axes and 'distances compressed' in the panel."""
        inset: bool | Value | None = None
        """A box beside the picture with the inner Solar System to scale (true: the orbits within 2 AU, or a radius '1.8 AU'); the region it shows is dashed in the main picture."""
        sizes: OrbitSizes | bool | None = None
        """A picture of radii to scale side by side (true: the scene's bodies or the eight planets; {bodies: [earth, moon, mars], sun: true}), the Sun's edge first; distances are not shown."""

        @model_validator(mode="after")
        def _consistent(self) -> "Orbit.Params":
            if self.tides is False:
                self.tides = None
            if self.tides is True:
                self.tides = OrbitTides()
            if self.sizes is False:
                self.sizes = None
            if self.sizes is True:
                self.sizes = OrbitSizes()
            if self.radial == "log" and self.frame == "axes" and "frame" in self.model_fields_set:
                raise ValueError("radial: log has no linear axes; its frame is rings at round distances (leave out frame: axes)")
            if self.energy and self.dynamics != "nbody" and self.system is None:
                raise ValueError("energy: the energy error is shown for dynamics: nbody (Kepler orbits conserve it exactly)")
            if self.method != "leapfrog" and self.dynamics != "nbody" and self.system is None:
                raise ValueError("method is the n-body integrator; it needs dynamics: nbody")
            if self.center is not None and self.extent is None:
                raise ValueError("center: give extent too (the half-width of the close-up around it, '3e6 km')")
            if self.center is not None and self.follow is not None:
                raise ValueError("center: the view stays still around the body's start; leave out follow (or center)")
            if isinstance(self.panel, list):
                for row in self.panel:
                    if row not in PANEL_ROWS:
                        raise ValueError(f"panel: no row '{row}' (rows: {', '.join(PANEL_ROWS)})" + did_you_mean(row, list(PANEL_ROWS)))
            try:
                self.model()
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

        def model(self) -> OrbitModel:
            """The resolved system, span, n-body run, trails and shots (cached)."""
            key = self.model_dump_json()
            if key not in _MODELS:
                if len(_MODELS) >= MODEL_CACHE:   # a long-running process (the MCP server) keeps the recent ones
                    del _MODELS[next(iter(_MODELS))]
                fields = self.model_fields_set
                many = ManySpec(self.system, "central" in fields, "dynamics" in fields, self.resonance, self.origin, self.view, self.center,
                                self.tides if isinstance(self.tides, OrbitTides) else None, self.lagrange, self.zero_velocity, "method" in fields)
                _MODELS[key] = resolve_model(self.central, self.bodies, span=self.span, orbit_count=self.orbits, dynamics=self.dynamics,
                                             method=self.method, step=self.step, follow=self.follow, cannon=self.cannonball, transfer=self.transfer,
                                             flyby=self.flyby, many=many, sky=SkySpec(self.date, self.radial, self.inset, self.sizes, self.event))
            return _MODELS[key]

        def body_specs(self) -> list[OrbitBody]:
            """The bodies as resolved: a system's own first, then those written, then those the
            scene adds (a flyby's probe)."""
            return self.model().specs

        def shows_energy(self) -> bool:
            return self.model().run is not None and self.energy is not False

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        names = (["title"] if params.title else []) + ["frame", "central"]
        model = params.model()
        sky, sizes = sky_target_names(params)
        if sizes:   # Step 233: the sizes picture (the Sun's edge is the central target)
            return (["title"] if params.title else []) + ["frame"] + (["central"] if model.sky.sun is not None else []) + sky
        many, no_orbit = many_target_names(params)
        many = many + sky
        if model.many is not None and model.many.tides is not None:
            return names + [f"body:{model.system.orbiters[0].name}", *many, "readout"]
        for spec, o in zip(params.body_specs(), model.system.orbiters):
            names.append(f"body:{o.name}")
            if spec.orbit and o.name not in no_orbit:
                names.append(f"orbit:{o.name}")
            parts = spec.geometry_parts()
            if parts:
                names.append(f"geometry:{o.name}")
                names += [f"{part}:{o.name}" for part in parts if part != "apsides"]
                if "apsides" in parts:
                    names += [f"periapsis:{o.name}", f"apoapsis:{o.name}"]
            if spec.sector_spec() is not None:
                names.append(f"sectors:{o.name}")
            if spec.velocity_spec() is not None:
                names.append(f"velocity:{o.name}")
        if model.shots:
            names += ["cannon", *[f"shot:{k + 1}" for k in range(len(model.shots))]]
        names += [f"burn:{k}" for k in range(1, len(model.burns()) + 1)]
        if model.transfer is not None:
            names += ["transfer"] + (["phase"] if model.transfer.target is not None else [])
        if model.assist is not None:
            fb = model.assist.assist.flyby
            names += ["asymptotes", "turn", "v_inf", f"periapsis:{model.assist.probe}", "motion"] + (["atmosphere"] if fb.atmosphere > 0 else [])
            if params.flyby.vectors:
                names += ["vectors", "v_before", "v_after"]
        names += many
        if params.readout or params.shows_energy() or any(s.velocity_spec() or s.sector_spec() or s.geometry_parts() for s in params.body_specs()) \
                or model.shots or model.burns() or model.assist is not None:
            names.append("readout")
        return names

    @classmethod
    def target_text(cls, params: Any, name: str) -> str | None:
        """What a target is called on screen (for the narration lint): a body's label, the title."""
        if name == "title":
            return str(params.title) or None
        kind, _, key = name.partition(":")
        sky = params.model().sky
        if sky is not None and sky.sizes is not None:   # the sizes picture: its bodies' names
            return key if kind == "body" else ("Sun" if kind == "central" else None)
        if kind == "body":
            for spec in params.body_specs():
                if spec.display_name() == key:
                    return str(spec.label) or key
        if kind == "central":
            central = params.central
            if params.system is not None or params.tides:   # the system's own primary (the figure-eight's A, the tides' planet)
                return params.model().system.central.name
            return (str(central.label) or central.name or central.preset) if isinstance(central, OrbitCentral) else central.capitalize()
        return None

    @classmethod
    def calc_values(cls, params: Any) -> dict[str, tuple[float, str]]:
        """What a ``calculation`` scene may take from this one (``from_scene: <id>.dv1``): name →
        (SI value, the unit it is shown in). A transfer: ``dv1``, ``dv2`` (``dv3``), ``dv_total``,
        ``t_transfer``, ``r1``, ``r2``, ``v1``, ``v2`` (circular speeds), with a target body
        ``phase_angle``, ``synodic_period``, ``wait``; phasing: ``dv``, ``t_phasing``; burns:
        ``dv_burn1``... and ``dv_spent``; a flyby: ``v_inf``, ``r_p``, ``e``, ``delta``,
        ``v_planet``, ``v_before``, ``v_after``, ``gain``."""
        model = params.model()
        out: dict[str, tuple[float, str]] = {}

        def time(seconds: float) -> tuple[float, str]:
            unit, _ = orbits.time_unit(seconds)
            return seconds, {"yr": "d"}.get(unit, unit)

        info = model.transfer
        if info is not None:
            r = info.result
            if info.kind == "phasing":
                out.update(dv=(r.dv, "km/s"), t_phasing=time(r.time))
            else:
                out.update(dv1=(r.dv1, "km/s"), dv2=(r.dv2, "km/s"))
                if info.kind == "bielliptic":
                    out["dv3"] = (r.dv3, "km/s")
            mu = model.system.orbiter(info.ship).elements.mu
            out.update(dv_total=(r.total, "km/s"), t_transfer=time(info.arrival - info.depart), v1=(math.sqrt(mu / info.r1), "km/s"),
                       v2=(math.sqrt(mu / info.r2), "km/s"))
            length = "AU" if info.r2 > 0.05 * orbits.AU else "km"
            out.update(r1=(info.r1, length), r2=(info.r2, length))
            if info.phase_needed is not None:
                out.update(phase_angle=(info.phase_needed, "deg"), synodic_period=time(2 * math.pi / abs(info.n_ship - info.n_target)),
                           wait=time(info.depart) if info.depart > 0 else (0.0, "d"))
        burns = model.burns()
        for n, (_, b) in enumerate(burns, start=1):
            out[f"dv_burn{n}"] = (b.magnitude, "km/s")
        if burns:
            out["dv_spent"] = (sum(b.magnitude for _, b in burns), "km/s")
        if model.assist is not None:
            ga = model.assist.assist
            fb = ga.flyby
            out.update(v_inf=(fb.v_inf, "km/s"), r_p=(fb.rp, "km"), e=(fb.e, ""), delta=(fb.delta, "deg"), v_planet=(model.assist.planet_speed, "km/s"),
                       v_before=(ga.speed_before, "km/s"), v_after=(ga.speed_after, "km/s"), gain=(ga.gain, "km/s"))
        return out

    @classmethod
    def diagnostics(cls, params: Any) -> dict[str, float]:
        """The run's accuracy diagnostics, whatever the panel shows (for the lint, Step 234): the
        largest |ΔE/E| (``energy_drift``) and |ΔL/L| (``angular_drift``) of an n-body run, each
        near body's largest |ΔC/C| (``jacobi_drift:<name>``), the figure-eight's return error
        (``closure``)."""
        model = params.model()
        out: dict[str, float] = {}
        run = model.run
        if run is not None:
            e0 = float(run.energy[0])
            if e0:
                out["energy_drift"] = float(np.max(np.abs(np.asarray(run.energy) - e0))) / abs(e0)
            if run.angular is not None:
                out["angular_drift"] = max(abs(float(run.angular_error(k))) for k in range(len(run.times)))
        info = model.many
        if info is not None:
            for name, series in (getattr(info, "jacobi", None) or {}).items():
                s = np.asarray(series, dtype=float)
                out[f"jacobi_drift:{name}"] = float(np.max(np.abs(s - s[0]))) / abs(float(s[0]))
            if info.eight is not None and info.closure is not None:
                out["closure"] = float(info.closure)
        return out

    # ----- building ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        self._clock_mob = Mobject().set_z_index(-1000)   # first in the scene: while it updates, every frame is redrawn
        self.add(self._clock_mob)
        begin = float(self.renderer.time)
        model = p.model()
        self._model = model
        self._playback = None
        portrait = self.is_portrait
        size = chart_label_size(p.label_size if p.label_size is not None else "caption", self.theme)
        self._size = size
        self._begin = begin
        self._video_now = begin
        self._panel_mode = p.panel
        if model.sky is not None and model.sky.sizes is not None:   # Step 233: radii to scale, a picture of its own
            self._held = self._held_patterns()
            self._construct_sizes(begin)
            return
        if model.many is not None:
            model.turn = model.many.turn0   # a model is shared by renders: each starts from its own view
            self._switches = self._turn_plan()
            if model.many.tides is not None:
                self._held = self._held_patterns()
                self._construct_tides(begin)
                return
        else:
            self._switches = []
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color, area=self.safe_area)
            body = body.below(title, gap=0.3)
        caption = None
        if p.caption:
            caption = chart_caption(p.caption, body, size=p.caption_size, color=p.caption_color)
            body = body.above(caption, gap=0.2)
        self._colors = {o.name: self.theme.color(spec.color) if spec.color else self.theme.palette_color(k) for k, (spec, o) in enumerate(zip(p.body_specs(), model.system.orbiters))}
        self._shot_colors = self._shot_palette()

        # the extent of what the view must show, in metres, and the unit it is shown in
        xs, ys = self._extent_points(model)
        fixed = orbits.value_si(p.extent, "length", "extent") if p.extent is not None else None
        if fixed is not None and fixed <= 0:
            raise VidgenError(f"scene '{self.spec.id}': extent must be positive")
        reach = fixed if fixed is not None else max(np.max(np.abs(xs)), np.max(np.abs(ys)))
        unit_name, unit_m = orbits.length_unit(reach, p.unit)
        self._log = model.sky is not None and model.sky.log
        if self._log:   # Step 233: distances compressed; the picture is in the log view's own units
            shown = self._radial(np.column_stack([xs, ys, 0 * xs]))
            xs, ys = shown[:, 0], shown[:, 1]
            fixed = self._log_d(fixed) if fixed is not None else None
            unit_name, unit_m = "AU", 1.0
        self._unit_m, self._unit_name = unit_m, unit_name
        self._view_centre = (0.0, 0.0)
        if model.many is not None and model.many.center is not None:
            at = model.view(model.many.center, model.span / 2)
            self._view_centre = (float(at[0]) / unit_m, float(at[1]) / unit_m)

        # the side panel (time, speed-up, energy, the overlays' values, a legend), beside the
        # plot (16:9) or above it (9:16), sized for the widest value it will show
        self._lines_static = [orbits.speedup_text(model.span / self._motion_seconds())] if p.readout else []
        self._t_unit = orbits.time_unit(model.span)
        self._note = ""   # "sizes not to scale", known once the drawing scale is
        slots: list[Slot] = self._sky_head()
        if p.readout:
            slots.append(Slot([self._time_line(model.span * k / 200) for k in range(201)], value=self._time_line, name="time", rank=self._time_rank()))
            rates = ["clock paused", "× 99 million"] if any(self.action_times(k) for k in ("burn", "flyby", "pause")) else []
            slots.append(Slot(list(self._lines_static) + rates, value=lambda t: self._rate_text(), name="speedup", rank=0))
        slots += self._sky_slots()
        if p.shows_energy():
            slots.append(Slot([self._energy_line(-1.23e-10), self._energy_line(-9.99e-9)], value=lambda t: self._energy_line(self._model.energy_error(t)),
                              name="energy", rank=self._energy_rank()))
            if model.many is not None:   # Step 232: the angular momentum's too
                slots += self._angular_slot()
        slots += self._many_slots()
        slots += self._manoeuvre_slots()
        slots += self._overlay_slots()
        slots = choose_rows(slots, p.panel, self._panel_budget())
        has_panel = bool(slots) or p.panel == "none"   # none: a panel only for the "not to scale" note
        slots += self._sky_notes()   # the log view says so whatever the panel
        slots.append(Slot(["sizes not to scale"], value=lambda t: self._note, color="dim", scale=0.85 if p.panel == "full" else 1.0, name="note", rank=0))
        self._slots = slots
        side_w, side_h = self._panel_size(slots) if has_panel else (0.0, 0.0)
        if side_w > body.width:   # wider rows are scaled down to the width when drawn, the panel with them
            side_h *= body.width / side_w
            side_w = body.width
        vec_w, vec_h = self._vector_box_size()   # a flyby's vector diagram: under the panel (16:9), under the picture (9:16)
        column_h = side_h + (VECTOR_GAP + vec_h if vec_h and not portrait else 0.0)
        side_h = min(side_h, body.height - (VECTOR_GAP + vec_h if vec_h and not portrait else 0.0))
        column_h = min(column_h, body.height)
        column_w = max(side_w, vec_w if not portrait else 0.0)
        right, top = (0.0, side_h + BOX_GAP) if portrait and has_panel else ((column_w + BOX_GAP, 0.0) if has_panel else (0.0, 0.0))
        bottom = vec_h + VECTOR_GAP if portrait and vec_h else 0.0
        area = plotcore.Rect(body.x0, body.y0 + bottom, body.x1 - right, body.y1)
        measure = plot_draw.text_measure(size, self.theme)
        lay = self._layout(area, xs / unit_m, ys / unit_m, None if fixed is None else fixed / unit_m, unit_name, measure, top)
        box = vbox = None
        if has_panel:
            if portrait:
                mid = (lay.plot.x0 + lay.plot.x1) / 2
                box = plotcore.Rect(mid - side_w / 2, area.y1 - side_h, mid + side_w / 2, area.y1)
            else:   # beside the plot, its middle level with the plot's
                cy = min(max((lay.plot.y0 + lay.plot.y1) / 2, body.y0 + column_h / 2), body.y1 - column_h / 2)
                x0 = lay.plot.x1 + BOX_GAP + self._unit_room(lay)
                box = plotcore.Rect(x0, cy + column_h / 2 - side_h, x0 + column_w, cy + column_h / 2)
                if vec_h:
                    vbox = plotcore.Rect(x0, cy - column_h / 2, x0 + column_w, cy - column_h / 2 + vec_h)
        if portrait and vec_h:
            mid = (lay.plot.x0 + lay.plot.x1) / 2
            w = min(body.width, max(vec_w, lay.plot.width))
            under = min([lay.plot.y0, *[lab.y - lab.height / 2 for lab in lay.x_labels]]) - VECTOR_GAP
            vbox = plotcore.Rect(mid - w / 2, under - vec_h, mid + w / 2, under)
        x0, y0, x1, y1 = _bounds(lay, box, vbox)
        dx, dy = (body.x0 + body.x1 - x0 - x1) / 2, (body.y0 + body.y1 - y0 - y1) / 2
        lay = _shifted(lay, dx, dy)
        if box is not None:
            box = plotcore.Rect(box.x0 + dx, box.y0 + dy, box.x1 + dx, box.y1 + dy)
        self._vector_box = plotcore.Rect(vbox.x0 + dx, vbox.y0 + dy, vbox.x1 + dx, vbox.y1 + dy) if vbox is not None else None
        self._lay = lay
        self._picture_area = plotcore.Rect(body.x0, body.y0, body.x1, body.y1)   # where overlay labels may stand (the plot, its margins)
        self._scale = lay.plot.width / (lay.x.hi - lay.x.lo) / unit_m   # Manim units per metre
        self._readout_box = box

        frame_parts = self._frame(lay, unit_name, size)
        colors = self._colors
        central_spec = p.central if isinstance(p.central, OrbitCentral) else OrbitCentral(preset=p.central)
        centre = model.system.central
        central_color = self.theme.color(central_spec.color or centre.color or "highlight")
        self._central_color = central_color
        enlarged = False
        true_scale = 0.0 if self._log else self._scale   # the log view has no true size: every body is a dot
        true_r = centre.radius * true_scale
        central_dot = Circle(radius=max(true_r, MIN_CENTRAL_RADIUS)).set_fill(central_color, opacity=1).set_stroke(width=0).set_z_index(3)
        enlarged |= centre.radius > 0 and true_r < MIN_CENTRAL_RADIUS
        central_label = self._label(str(central_spec.label) or centre.name, size) if central_spec.show_label else VGroup()
        self._label_inside = central_spec.show_label and central_dot.width > max(1.4 * central_label.width, 0.7)   # a planet drawn large: its name on it
        if self._label_inside:
            central_label.set_color(self.theme.background)
        self._central = (central_dot, central_label)
        self._leaders: dict[str, VMobject] = {centre.name: self._leader()}

        self._bodies: dict[str, tuple[Any, Any]] = {}
        for spec, o in zip(p.body_specs(), model.system.orbiters):
            r = o.body.radius * true_scale
            enlarged |= o.body.radius > 0 and r < MIN_BODY_RADIUS
            dot = Circle(radius=max(r, MIN_BODY_RADIUS)).set_fill(colors[o.name], opacity=1)
            dot.set_stroke(self.theme.background, width=2).set_z_index(4)
            label = self._label(str(spec.label) or o.name, size) if spec.show_label else VGroup()
            self._bodies[o.name] = (dot, label)
            self._leaders[o.name] = self._leader()
        self._note = "sizes not to scale" if enlarged or self._log else ""
        enlarged = enlarged or self._log
        if not enlarged and box is not None:   # no note: the panel loses its last row
            self._slots = slots[:-1]
            if not self._slots:   # panel: none with sizes true: no panel at all
                box = self._readout_box = None
            else:
                h = min(self._panel_size(self._slots)[1], box.height)
                shift = 0.0 if portrait or self._vector_box is not None else (box.height - h) / 2
                box = plotcore.Rect(box.x0, box.y1 - shift - h, box.x1, box.y1 - shift)
                self._readout_box = box

        # orbits (conics around each body's parent; moved with the parent when it moves in the view)
        self._conics: dict[str, tuple[VGroup, Any, bool]] = {}
        self._conic_points: dict[str, np.ndarray] = {}
        diagonal = math.hypot(lay.plot.width, lay.plot.height) / self._scale
        for spec, o in zip(p.body_specs(), model.system.orbiters):
            if not spec.orbit or o.trajectory is not None:   # a body that burns: its orbits arc by arc (orbit_manoeuvres)
                continue
            if model.many is not None and model.many.origin == "barycentre":   # its Kepler orbit is not its path there (orbit_many draws a binary's)
                continue
            rel = o.elements.conic(CONIC_SAMPLES, r_max=1.5 * diagonal)
            moves = model.run is not None or not (o.parent == model.follow)
            container = VGroup()
            self._conics[o.name] = (container, rel, moves)
        # trails: TRAIL_PIECES pieces fading to the tail
        self._trails = {name: VGroup(*[VMobject() for _ in range(TRAIL_PIECES)]) for name, seconds in model.trails.items() if seconds > 0}
        for name, group in self._trails.items():
            for k, piece in enumerate(group):
                piece.set_stroke(colors.get(name, central_color), width=4, opacity=0.08 + 0.8 * (k + 1) / TRAIL_PIECES)
            group.set_z_index(2)

        self._readout = VGroup()
        self._label_sides: dict[str, int] = {}
        self._last_lines: tuple[str, ...] | None = None
        self._label_cache: dict[str, Any] = {}

        self._build_orbit_overlays()
        self._build_manoeuvres()
        self._build_many()
        self._build_sky()
        self._t = 0.0
        self._draw(0.0)
        self._register(title, caption, frame_parts)

        for i, d in self.timeline():
            if i == 0:
                self.play_steps(d, [lambda: self._intro(d)], fraction=0.8, cap=1.5)
            elif self.capture is not None and self._current_beat is not None:
                fps = config.frame_rate
                self.capture.add_mid_still(self._current_beat, round(float(self.renderer.time) * fps), round(d * fps), "orbit")
        self.finish()
        self._stop()

    def _panel_size(self, slots: list[Slot]) -> tuple[float, float]:
        """Width and height of the side panel holding ``slots``."""
        widths, heights = [], []
        for column in self._panel_columns(slots):
            width, height = 0.0, 0.0
            for slot in column:
                m = plot_draw.text_measure(self._size * slot.scale, self.theme, slot.color)
                dims = [m(t) for t in slot.probes]
                w = max(d[0] for d in dims) + (0.32 if slot.swatch else 0.0) + (KEY_ROOM if slot.key else 0.0)
                width = max(width, w)
                height += max(d[1] for d in dims) + 0.14 * self._size / 24
            widths.append(width)
            heights.append(height)
        pad = plot_draw.PLATE_PAD
        return sum(widths) + PANEL_COLUMN_GAP * (len(widths) - 1) + 0.1 + 2 * pad, max(heights) + 2 * pad

    def _frame_kind(self) -> str:
        """The frame drawn: the param's, or none in the log view (its rings are drawn by the sky mixin)."""
        return "none" if getattr(self, "_log", False) else self.params.frame

    def _panel_budget(self) -> int:
        """Most rows of a compact panel in this frame."""
        return PANEL_BUDGET[1] if self.is_portrait else PANEL_BUDGET[0]

    def _energy_rank(self) -> int:
        """The energy / angular-momentum rows are diagnostics unless ``energy: true`` asks for them."""
        return 0 if self.params.energy is True else DIAGNOSTIC

    def _panel_columns(self, slots: list[Slot]) -> list[list[Slot]]:
        """The panel's rows in one column, or in two side by side in a vertical frame when there
        are many (the picture keeps its height)."""
        if not self.is_portrait or len(slots) <= PANEL_ROWS_PORTRAIT or getattr(self, "_panel_mode", "full") != "full":
            return [slots]   # a compact panel stays one column at full size (the picture is width-limited in 9:16)
        k = math.ceil(len(slots) / 2)
        return [slots[:k], slots[k:]]

    def _unit_room(self, lay: Any) -> float:
        """Extra room right of the plot taken by the unit after the x ticks (16:9 axes)."""
        t = lay.x_title
        if t is None or self.is_portrait:
            return 0.0
        return max(0.0, t.x + t.width / 2 - lay.plot.x1)

    def _motion_seconds(self) -> float:
        """Video seconds the scene lasts before its outro (each beat in whole frames, as
        :meth:`narrate` waits them)."""
        if self.beats:
            fps = config.frame_rate
            return sum(round(self.beat_window(b).window * fps) for b in self.beats) / fps
        return max((self.spec.duration or 0.0) - self.outro, 1 / config.frame_rate)

    def _extent_points(self, model: OrbitModel) -> tuple[np.ndarray, np.ndarray]:
        """x and y (m) of what the view must show: every body over the span in the view's
        frame and the whole closed orbits around a still centre, the cannon's closed shots and
        falling ones whole; an open orbit only out to three times the size of the rest."""
        many = self._many_extent_points()
        if many is not None:   # Step 232: the barycentre's view (inertial and / or rotating)
            return many
        ts = np.linspace(0.0, model.span, 400)
        system = model.system
        follow = model.follow
        if model.assist is not None and follow is None:   # a flyby: the whole pass, the planet with its atmosphere
            fb = model.assist.assist.flyby
            ring = np.linspace(0, 2 * math.pi, 73)
            top = fb.radius + fb.atmosphere
            path = model.view(model.assist.probe, ts)
            disc = np.column_stack([top * np.cos(ring), top * np.sin(ring), 0 * ring])
            c = fb.centre
            around = c + 0.2 * float(np.linalg.norm(c)) * np.column_stack([np.cos(ring), np.sin(ring), 0 * ring])
            pts = np.concatenate([path, disc, around])   # and where the asymptotes cross, with room for the turning angle
            return pts[:, 0], pts[:, 1]
        shown = [o for o in system.orbiters if follow is None or follow in [c.name for c in system.chain(o.name)[1:]]]
        if not shown:
            shown = [o for o in system.orbiters if o.name != follow]
        points = [np.zeros((1, 3))]
        open_points = []
        opens: list[Any] = []   # open orbits drawn around a still centre
        for o in shown:
            path = model.view(o.name, ts)
            still = o.parent == follow and model.run is None
            if o.trajectory is not None:   # a body that burns: its path, and the closed orbits it is on whole
                points.append(path)
                for arc in o.trajectory.arcs:
                    if still and arc.elements.closed and arc.start <= model.span:
                        points.append(arc.elements.conic(120))
                continue
            if o.elements.closed:
                points.append(path)
                if still:
                    points.append(o.elements.conic(120))
            else:
                open_points.append(path)
                if follow is None and o.parent is None:
                    opens.append(o.elements)
        if not shown and follow is not None and system.orbiters:
            points.append(model.view(system.central.name, ts))
        if model.shots and follow is None:   # the planet in the middle, the closed shots whole; open ones leave the view
            shots = [model.cannon_at[None, :]]
            for shot in model.shots:
                if shot.kind == "suborbital":
                    shots.append(shot.positions(np.linspace(0.0, shot.impact, 120)))
                elif shot.elements.closed:
                    shots.append(shot.elements.conic(120))
            reach_shots = max(max(float(np.max(np.linalg.norm(s[:, :2], axis=1))) for s in shots), 1.6 * float(np.linalg.norm(model.cannon_at)))
            ring = np.linspace(0, 2 * math.pi, 73)
            points.append(np.column_stack([reach_shots * np.cos(ring), reach_shots * np.sin(ring), 0 * ring]))
        closed = np.concatenate(points)
        reach = float(np.max(np.linalg.norm(closed[:, :2], axis=1)))
        if open_points or opens:
            peri = max([o.elements.periapsis for o in shown if not o.elements.closed] + [el.periapsis for el in opens])
            cap = 3 * max(reach, peri)
            open_points += [el.conic(120, r_max=cap) for el in opens]   # the open conics out to that distance (a flyby is seen whole)
            pts = np.concatenate(open_points)
            pts = pts[np.linalg.norm(pts[:, :2], axis=1) <= cap * (1 + 1e-9)]
            closed = np.concatenate([closed, pts]) if len(pts) else closed
        return closed[:, 0], closed[:, 1]

    def _layout(self, area: Any, xs: np.ndarray, ys: np.ndarray, extent: float | None, unit: str, measure: Any, top: float) -> Any:
        """The plot rectangle and its axes at an equal aspect: through the plot core with
        ``frame: axes``, else the data's box widened to the area's shape. The axes carry no
        titles (both are lengths in the same unit): the unit is written once — after the x tick
        labels in 16:9, above the y ticks in 9:16 — so the picture gets the height."""
        p = self.params
        portrait = self.is_portrait
        if extent is not None:
            cx, cy = self._view_centre   # Step 232: a close-up around a body's start (else the centre)
            x_lo, x_hi, y_lo, y_hi = cx - extent, cx + extent, cy - extent, cy + extent
        else:   # the data's box with a margin: the plot hugs the orbits (no axis runs on past them)
            x_lo, x_hi, y_lo, y_hi = float(xs.min()), float(xs.max()), float(ys.min()), float(ys.max())
            span = max(x_hi - x_lo, y_hi - y_lo, 1e-12)
            margin = BURN_MARGIN if self._model.burns() else MARGIN   # room for the Δv arrows and their labels
            x_lo, x_hi = x_lo - margin * span, x_hi + margin * span
            y_lo, y_hi = y_lo - margin * span, y_hi + margin * span
        if self._frame_kind() == "axes":
            def spec(lo: float, hi: float, ticks: int) -> Any:
                return plotcore.AxisSpec(lo=lo, hi=hi, unit=unit, label="", max_ticks=ticks, exact=True)
            panel = plotcore.PanelInput((), (), spec(x_lo, x_hi, 4 if portrait else 6), spec(y_lo, y_hi, 6 if portrait else 5))

            def lay_out(box: Any) -> Any:
                try:
                    return plotcore.layout_figure(box, [panel], measure, top=top, aspect="equal")[0]
                except VidgenError as error:
                    raise VidgenError(f"scene '{self.spec.id}': {error}") from None

            first = lay_out(area)
            _, cap = measure("0")
            gap = 0.45 * cap + 0.05
            foot = first.x_title.height + gap * 0.8 if first.x_title is not None else 0.0
            if portrait:   # the unit stays above the y ticks; the x title's row goes to the picture
                lay = lay_out(plotcore.Rect(area.x0, area.y0 - foot, area.x1, area.y1))
                return replace(lay, x_title=None)
            head = first.y_title.height + gap if first.y_title is not None else 0.0
            unit_w = first.x_title.width if first.x_title is not None else 0.0
            lay = lay_out(plotcore.Rect(area.x0, area.y0 - foot, area.x1 - unit_w - UNIT_GAP, area.y1 + head))
            label = lay.x_title
            if label is not None and lay.x_labels:
                row_y = lay.x_labels[0].y
                last = max(lab.x + lab.width / 2 for lab in lay.x_labels)
                x = max(lay.plot.x1, last) + UNIT_GAP + label.width / 2
                label = replace(label, x=x, y=row_y)
            return replace(lay, y_title=None, x_title=label)
        free = plotcore.Rect(area.x0, area.y0, area.x1, area.y1 - top)
        s = min(free.width / (x_hi - x_lo), free.height / (y_hi - y_lo))
        w, h = s * (x_hi - x_lo), s * (y_hi - y_lo)
        cx, cy = free.center
        plot = plotcore.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        return plotcore.PanelLayout(plot, plotcore.Axis("linear", x_lo, x_hi, (), ()), plotcore.Axis("linear", y_lo, y_hi, (), ()), (), (), None, None, (), ())

    def _frame(self, lay: Any, unit: str, size: float) -> VGroup:
        """The axes (``frame: axes``), a scale bar (``scale_bar``) or nothing."""
        p = self.params
        if self._frame_kind() == "axes":
            return plot_draw.draw_panel(lay, size=size, grid="major", theme=self.theme).group
        if self._frame_kind() == "none":
            return VGroup()
        span = (lay.x.hi - lay.x.lo) / 4
        k = math.floor(math.log10(span))
        length = max(m * 10**k for m in (1, 2, 5) if m * 10**k <= span)
        per_unit = lay.plot.width / (lay.x.hi - lay.x.lo)
        text = plotcore.plain_number(length, max(0, -k)) if length < 1e5 else plotcore.sci_number(length, 1)
        label = plot_draw.label_text(f"{text} {unit}", size=size, color="dim", theme=self.theme)
        w, h = max(length * per_unit, label.width), label.height + 0.25
        # the corner of the plot the bodies' paths keep away from (bottom left unless crowded)
        paths = self._paths_in_frame()
        corners = [(lay.plot.x0 + 0.25, lay.plot.y0 + 0.3), (lay.plot.x1 - 0.25 - w, lay.plot.y0 + 0.3), (lay.plot.x0 + 0.25, lay.plot.y1 - 0.15 - h),
                   (lay.plot.x1 - 0.25 - w, lay.plot.y1 - 0.15 - h)]

        def crowd(corner: tuple[float, float]) -> int:
            x, y = corner
            inside = (paths[:, 0] > x - 0.1) & (paths[:, 0] < x + w + 0.1) & (paths[:, 1] > y - 0.15) & (paths[:, 1] < y + h + 0.1)
            return int(np.count_nonzero(inside))

        x0, y0 = min(corners, key=crowd)   # the first of the least crowded
        x1 = x0 + length * per_unit
        dim = self.theme.color("dim")
        bar = VGroup(Line([x0, y0, 0], [x1, y0, 0]), Line([x0, y0 - 0.07, 0], [x0, y0 + 0.07, 0]), Line([x1, y0 - 0.07, 0], [x1, y0 + 0.07, 0]))
        bar.set_stroke(dim, width=3)
        label.next_to(bar, UP, buff=0.1).align_to(bar, LEFT)
        return VGroup(bar, label).set_z_index(2.6)   # over the orbits, trails and sectors, under the bodies

    def _paths_in_frame(self) -> np.ndarray:
        """Frame points along every body's path over the span and its drawn orbit (where the
        scale bar should not stand)."""
        model = self._model
        ts = np.linspace(0.0, model.span, 300)
        pts = [np.zeros((0, 3))]
        for o in model.system.orbiters:
            pts.append(self._frame_points(model.view(o.name, ts)))
            if o.elements.closed:
                parent = model.view(o.parent, 0.0) if o.parent is not None else model.view(model.system.central.name, 0.0)
                pts.append(self._frame_points(o.elements.conic(120) + parent))
        return np.concatenate(pts)

    def _label(self, text: str, size: float) -> Mobject:
        return plot_draw.label_text(text, size=size, theme=self.theme).set_z_index(5)

    def _leader(self) -> VMobject:
        return VMobject().set_stroke(self.theme.color("dim"), width=1.5, opacity=0.9).set_z_index(4.5)

    def _register(self, title: Any, caption: Any, frame_parts: VGroup) -> None:
        p = self.params
        if title is not None:
            self.target("title", title)
        self._title, self._caption = title, caption
        self._frame_parts = frame_parts
        self.target("frame", VGroup(frame_parts, *([caption] if caption is not None else [])))
        centre = self._model.system.central.name
        self.target("central", VGroup(*self._central, self._leaders[centre], *([self._trails[centre]] if centre in self._trails else [])))
        for spec, o in zip(p.body_specs(), self._model.system.orbiters):
            dot, label = self._bodies[o.name]
            parts = [dot, label, self._leaders[o.name]] + ([self._trails[o.name]] if o.name in self._trails else [])
            self.target(f"body:{o.name}", VGroup(*parts))
            if o.name in self._conics:
                self.target(f"orbit:{o.name}", self._conics[o.name][0])
        if self._readout_box is not None:
            self.target("readout", self._readout)

    # ----- motion -----------------------------------------------------------------------------

    def _intro(self, d: float) -> list[Animation]:
        """The first beat's entrance (frame, title, central body, orbits drawn, bodies, the
        overlays no action holds back), then the motion starts and runs in every wait and play
        to the scene's end."""
        anims: list[Animation] = []
        if self._title is not None:
            anims.append(FadeIn(self._title))
        if self._caption is not None:
            anims.append(FadeIn(self._caption))
        if len(self._frame_parts):
            anims.append(FadeIn(self._frame_parts))
        dot, label = self._central
        anims.append(GrowFromCenter(dot))
        if len(label):
            anims.append(FadeIn(label))
        for container, _, _ in self._conics.values():
            if len(container):
                anims.append(Create(container))
        for dot, label in self._bodies.values():
            anims.append(FadeIn(dot))
            if len(label):
                anims.append(FadeIn(label))
        anims += [FadeIn(part) for part in self._intro_parts]
        if len(self._readout):
            anims.append(FadeIn(self._readout))
        self.play(*anims, run_time=min(1.2, max(0.3 * d, 1 / config.frame_rate)))
        self.add(*self._trails.values(), *self._leaders.values())
        start = float(self.renderer.time)
        end = self._begin + self._motion_seconds()
        self._playback = self._clock_plan(start, max(end - start, 1 / config.frame_rate))
        if self.params.readout:
            self._lines_static = [orbits.speedup_text(self._playback.rate(start))]

        def update(_: Mobject, dt: float) -> None:
            # the scene's clock (the frame about to be written), not a sum of dt: manim gives the
            # first frame of every play and wait a dt of 0
            self._video_now = float(self.renderer.time)
            self._draw(self._playback.sim_time(self._video_now))

        self._update = update
        self._clock_mob.add_updater(update)
        if self.capture is not None and self._current_beat is not None:
            fps = config.frame_rate
            left = max(d - (start - self._beat_start), 1 / fps)
            self.capture.add_mid_still(self._current_beat, round(start * fps), round(left * fps), "orbit")
        return []

    def _stop(self) -> None:
        update = getattr(self, "_update", None)
        if update is not None:
            self._clock_mob.remove_updater(update)

    def start_sweep(self, names: list[str], video_time: float) -> None:
        super().start_sweep(names, video_time)
        self.add(*[self._sectors[n]["group"] for n in names if n in self._sectors])

    def launch(self, shots: list[int], video_time: float) -> None:
        super().launch(shots, video_time)
        for k in shots:
            self.add(self.find_targets(f"shot:{k + 1}")[0].mobject)

    def _frame_point(self, metres: np.ndarray) -> np.ndarray:
        lay, u = self._lay, self._unit_m
        if self._log:
            metres = self._radial(metres)
        return np.array([lay.frame_x(float(metres[0]) / u), lay.frame_y(float(metres[1]) / u), 0.0])

    def _frame_points(self, metres: np.ndarray) -> np.ndarray:
        lay, u = self._lay, self._unit_m
        if self._log:
            metres = self._radial(metres)
        x = lay.plot.x0 + (metres[:, 0] / u - lay.x.lo) / (lay.x.hi - lay.x.lo) * lay.plot.width
        y = lay.plot.y0 + (metres[:, 1] / u - lay.y.lo) / (lay.y.hi - lay.y.lo) * lay.plot.height
        return np.column_stack([x, y, np.zeros(len(x))])

    def _draw(self, t: float) -> None:
        """Put everything where it is at simulated time ``t`` (s)."""
        self._t = t
        model = self._model
        if model.many is not None:   # how far the view turns with a three-body pair now (a switch on a word)
            model.turn = self._turn_at(self._video_now)
        plot = self._lay.plot
        centre = model.system.central.name
        anchors = {centre: model.view(centre, t)}
        items = [(centre, *self._central)]
        self._show(*self._central, self._frame_point(anchors[centre]), plot)
        for o in model.system.orbiters:
            anchors[o.name] = model.view(o.name, t)
            dot, label = self._bodies[o.name]
            self._show(dot, label, self._frame_point(anchors[o.name]), plot)
            items.append((o.name, dot, label))
        for name, (container, rel, moves) in self._conics.items():
            if not moves and len(container):
                continue
            o = model.system.orbiter(name)
            parent = anchors[o.parent if o.parent is not None else centre]
            pts = self._frame_points(rel + parent)
            self._conic_points[name] = pts[::4]
            line = plot_draw.series_line(pts, plot, self._colors[name], width=2.5, dashed=not o.elements.closed)
            line.set_stroke(opacity=0.55).set_z_index(1)
            plot_draw.morph_into(container, line)
        for name, group in self._trails.items():
            length = model.trails[name]
            samples = model.many.trail_samples.get(name, TRAIL_SAMPLES) if model.many is not None else TRAIL_SAMPLES
            ts = np.linspace(max(0.0, t - length), t, samples + 1)
            if ts[-1] - ts[0] <= 0:
                for piece in group:
                    piece.clear_points()
                continue
            pts = self._frame_points(model.view(name, ts))
            # a trail starts where the motion started: its pieces cover the length it has
            share = (ts[-1] - ts[0]) / length
            first = TRAIL_PIECES - max(1, math.ceil(share * TRAIL_PIECES - 1e-9))
            bounds = np.linspace(0, samples, TRAIL_PIECES - first + 1).round().astype(int)
            for k, piece in enumerate(group):
                piece.clear_points()
                if k < first:
                    continue
                a, b = bounds[k - first], bounds[k - first + 1]
                seg = pts[a:b + 1]
                inside = bool(np.all((seg[:, 0] >= plot.x0) & (seg[:, 0] <= plot.x1) & (seg[:, 1] >= plot.y0) & (seg[:, 1] <= plot.y1)))
                for run in ([seg] if inside else plotcore.clip_polyline(seg, plot)):   # all inside: the same run, without the per-segment clipping
                    if len(run) >= 2:
                        piece.start_new_path(run[0])
                        piece.add_points_as_corners(run[1:])
        self._draw_orbit_overlays(t, anchors)
        self._draw_manoeuvres(t, anchors)
        self._draw_many(t, anchors)
        self._draw_sky(t)
        self._place_labels(items, plot)
        self._draw_readout(t)

    def _show(self, dot: Mobject, label: Mobject, at: np.ndarray, plot: Any) -> None:
        """Move a body to ``at``; hide it and its label while it is outside the plot."""
        inside = plot.contains(float(at[0]), float(at[1]), 1e-6)
        dot.move_to(at)
        if inside != getattr(dot, "_orbit_shown", True):
            for m in (dot, label):
                m.set_opacity(1.0 if inside else 0.0)
            dot._orbit_shown = inside

    def _place_labels(self, items: list[tuple[str, Mobject, Mobject]], plot: Any) -> None:
        """Put each label near its body where it covers no body, other label, overlay label or
        the side panel, stays in the plot and crosses few orbit lines: beside it on one of eight
        sides, else further out with a thin leader line to it. A label keeps its place while
        that stays about as good (labels move with their bodies without jumping about)."""
        dots = [(name, _rect(dot, 0.03)) for name, dot, _ in items if getattr(dot, "_orbit_shown", True)]
        taken = ([self._panel_rect()] if self._readout_box is not None else []) + list(self._static_boxes) + self._manoeuvre_boxes() + self._many_boxes()
        lines = [pts for pts in self._conic_points.values() if len(pts)] + self._manoeuvre_lines()
        points = np.concatenate(lines)[:, :2] if lines else None
        placed: list[np.ndarray] = []
        for name, dot, label in items:
            leader = self._leaders[name]
            leader.clear_points()
            if not label.has_points() and not len(label):
                continue
            c = dot.get_center()
            # a body where one listed before it is (a spacecraft alongside its planet): one label for both
            twin = any(np.linalg.norm(c[:2] - p[:2]) < 0.02 for p in placed)
            placed.append(c)
            if twin:
                label.set_opacity(0.0)
                label._orbit_twin = True
                continue
            if getattr(label, "_orbit_twin", False):   # apart again: shown as its dot is
                label.set_opacity(1.0 if getattr(dot, "_orbit_shown", True) else 0.0)
                label._orbit_twin = False
            if name == self._model.system.central.name and self._label_inside:
                label.move_to(c)
                continue
            obstacles = taken + [d for n, d in dots if n != name]
            k, box, ring = place(c, dot.width / 2, label.width, label.height, obstacles=obstacles, plot=plot, points=points, prev=self._label_sides.get(name))
            self._label_sides[name] = k
            label.move_to([box.center[0], box.center[1], 0])
            taken.append(box)
            if ring > 0 and getattr(dot, "_orbit_shown", True):
                ends = leader_points(c, dot.width / 2, box)
                if ends is not None:
                    leader.set_points_as_corners(np.array(ends))

    def _time_line(self, t: float) -> str:
        unit, scale = self._t_unit
        return plotcore.readout_text("t", t / scale, unit)

    @staticmethod
    def _energy_line(error: float) -> str:
        return "ΔE/E = " + plotcore.readout_number(error, 2)

    def _draw_readout(self, t: float) -> None:
        box = self._readout_box
        if box is None:
            return
        lines = [slot.text(t) for slot in self._slots]
        key = tuple(lines)
        if key == self._last_lines:
            return
        self._last_lines = key
        rows = []
        used: list[Any] = []
        for slot, text in zip(self._slots, lines):
            size = self._size * slot.scale
            if text:   # the cached text itself (its points put back after the panel is drawn: copying every row each frame is slow)
                mob = self._template(text, size, slot.color)
                if any(m is mob for m in used):   # the same text twice in one panel: the second a copy
                    mob = self._cached(text, size, slot.color)
                else:
                    used.append(mob)
            else:   # an empty row keeps its height (a text without points would not)
                mob = self._cached(slot.probes[0], size, slot.color)
                mob.set_opacity(0)
            if slot.swatch is not None:
                dot = Circle(radius=0.07).set_fill(slot.swatch, opacity=1).set_stroke(width=0)
                mob = VGroup(dot, mob).arrange(RIGHT, buff=0.18)
            elif slot.key:
                length = self._key_speed * self._speed_scale
                arrow = new_arrow(self.theme.color("text"), width=3.5, z=6.6)
                arrow_shape(arrow[0], arrow[1], np.zeros(3), np.array([length, 0.0]), 3.5)
                mob = VGroup(arrow, mob).arrange(RIGHT, buff=0.15)
            rows.append(mob)
        columns, k = [], 0
        for column in self._panel_columns(self._slots):
            columns.append(VGroup(*rows[k:k + len(column)]).arrange(DOWN, buff=0.14 * self._size / 24, aligned_edge=LEFT))
            k += len(column)
        group = columns[0] if len(columns) == 1 else VGroup(*columns).arrange(RIGHT, buff=PANEL_COLUMN_GAP, aligned_edge=UP)
        pad = plot_draw.PLATE_PAD
        fit = min((box.width - 2 * pad) / max(group.width, 1e-9), (box.height - 2 * pad) / max(group.height, 1e-9))
        if fit < 1:
            group.scale(fit)
        group.move_to([box.x0 + pad + group.width / 2, box.y1 - pad - group.height / 2, 0])
        plate = RoundedRectangle(width=box.width, height=box.height, corner_radius=0.08)
        plate.set_fill(self.theme.background, opacity=0.88).set_stroke(self.theme.color("dim"), width=1, opacity=0.5)
        plate.move_to([box.center[0], box.center[1], 0])
        drawing = VGroup(plate.set_z_index(6), group.set_z_index(6.5))
        missing = len(drawing.family_members_with_points()) - len(self._readout.submobjects)
        if missing > 0:   # members of its own, so the cached texts never become the panel's
            self._readout.add(*[VMobject() for _ in range(missing)])
        plot_draw.morph_into(self._readout, drawing)
        for mob in used:
            for member, points in self._template_points[id(mob)]:
                member.points = points.copy()

    def _template(self, text: str, size: float, color: str) -> Mobject:
        """A cached text drawn in place (not copied); :meth:`_draw_readout` puts its points back."""
        key = f"{color}|{size}|{text}"
        if not hasattr(self, "_templates"):
            self._templates, self._template_points = {}, {}
        if key not in self._templates:
            mob = self._cached(text, size, color)
            self._templates[key] = mob
            self._template_points[id(mob)] = [(m, m.points.copy()) for m in mob.family_members_with_points()]
        return self._templates[key]

    def _cached(self, text: str, size: float, color: str) -> Mobject:
        key = f"{color}|{size}|{text}"
        if key not in self._label_cache:
            self._label_cache[key] = plot_draw.label_text(text, size=size, color=color, theme=self.theme)
        return self._label_cache[key].copy()


def _rect(m: Mobject, pad: float = 0.0) -> Any:
    return mob_rect(m, pad)


def _bounds(lay: Any, *boxes: Any) -> tuple[float, float, float, float]:
    """The box around a laid-out panel (plot, tick labels, titles) and the side ``boxes`` (the
    panel, a vector diagram; ``None`` skipped)."""
    xs, ys = [lay.plot.x0, lay.plot.x1], [lay.plot.y0, lay.plot.y1]
    labels = [*lay.x_labels, *lay.y_labels, *[t for t in (lay.x_title, lay.y_title) if t is not None]]
    for lab in labels:
        xs += [lab.x - lab.width / 2, lab.x + lab.width / 2]
        ys += [lab.y - lab.height / 2, lab.y + lab.height / 2]
    for box in boxes:
        if box is not None:
            xs += [box.x0, box.x1]
            ys += [box.y0, box.y1]
    return min(xs), min(ys), max(xs), max(ys)


def _shifted(lay: Any, dx: float, dy: float) -> Any:
    """A laid-out panel moved by ``(dx, dy)``."""
    def label(lab: Any) -> Any:
        return None if lab is None else replace(lab, x=lab.x + dx, y=lab.y + dy)

    plot = plotcore.Rect(lay.plot.x0 + dx, lay.plot.y0 + dy, lay.plot.x1 + dx, lay.plot.y1 + dy)
    return replace(lay, plot=plot, x_labels=tuple(label(lab) for lab in lay.x_labels), y_labels=tuple(label(lab) for lab in lay.y_labels),
                   x_title=label(lay.x_title), y_title=label(lay.y_title))


__all__ = ["BOX_GAP", "CONIC_SAMPLES", "MIN_BODY_RADIUS", "MIN_CENTRAL_RADIUS", "Orbit", "TRAIL_PIECES"]

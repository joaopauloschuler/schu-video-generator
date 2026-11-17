"""The page a ``space`` scene draws (DESIGN.md §122.12): JavaScript written from the scene's params,
built from the shipped modules (``vidgen/space-sky``, ``-bodies``, ``-light``, ``-craft``,
``-phenomena``, ``-camera``, ``-scale``, ``-scene``, ``three-finish``, ``title-cards``).

The same params give the same bytes (no time, no random, no path of this machine), so the page's
SHA-256 is in the clip's key like any ``web`` scene's script, and every param that changes the
picture changes the page. The page is plain code an author can read and go on with
(``vidgen space-page`` writes it out as a ``web`` scene's script). Imports only ``vidgen.api``.
"""

import json
import math
from typing import Any

from vidgen.api import *

from .space_params import length, module_options, names, scene_time, uses_bars

#: Version of what the generator writes (in the page's first line, so it is in the clip's key).
PAGE_VERSION = 1
#: The sun's direction when nothing says where it is (the orbit data's axes, z up).
DEFAULT_SUN = (1.0, 0.25, 0.35)
#: JS names of the camera moves.
MOVE_CALLS = {"arc": "arc", "fly-by": "flyBy", "pass": "pass", "arrive": "arrive", "reveal": "reveal", "follow": "follow", "zoom": "zoom", "look": "look"}
#: Option keys of the moves that hold a length (metres or text with a unit).
LENGTH_KEYS = ("distance", "closest", "altitude")
#: Default horizon radius of a black hole, throat of a wormhole, scale of a rock or a comet (m) when no size is given.
DEFAULT_SIZES = {"black-hole": 1.0e4, "wormhole": 1.0e3, "asteroid": 2.0e3, "comet": 1.0e8}


class Ref(str):
    """JavaScript written as it is (an expression), not as a JSON string."""


def js(value: Any) -> str:
    """``value`` as a JavaScript literal: JSON, with :class:`Ref` written as code and floats as Python's repr (exact)."""
    if isinstance(value, Ref):
        return str(value)
    if isinstance(value, dict):
        return "{" + ", ".join(f"{json.dumps(str(k))}: {js(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(js(v) for v in value) + "]"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise VidgenError(f"space scene: {value} is not a finite number")
        return repr(value) if value != int(value) or abs(value) >= 1e16 else str(int(value))
    return json.dumps(value, ensure_ascii=False)


def pairs(value: dict[str, Any]) -> str:
    """The entries of ``value`` as JavaScript object entries followed by ``, `` (empty for none): ``"seed": 4, ``."""
    return "".join(f"{json.dumps(str(k))}: {js(v)}, " for k, v in value.items())


def three(v: Any) -> list[float]:
    """[x, y, z] of the orbit data's axes (z up) as three.js's (y up): [x, z, -y] (vidgen/space-scale's yUp)."""
    return [float(v[0]), float(v[2]), -float(v[1])]


def subject(name: str) -> Ref:
    return Ref(f"S.subjects[{json.dumps(name)}]")


def when(value: Any) -> Any:
    """A time of the plan (seconds, or {bar, beat}) as the page's expression of scene seconds."""
    if isinstance(value, Ref):
        return value
    value = value if uses_bars(value) else scene_time(value, "a time")
    return Ref(f"T({js(value)})") if uses_bars(value) else float(value)


def _lengths(value: Any, where: str) -> Any:
    """Lengths written with units inside a move's options, in metres (``distance``, ``closest``, ``altitude``)."""
    if isinstance(value, dict):
        return {k: (length(v, f"{where}.{k}") if k in LENGTH_KEYS and isinstance(v, str) else _lengths(v, f"{where}.{k}")) for k, v in value.items()}
    if isinstance(value, list):
        return [_lengths(v, where) for v in value]
    return value


def sun_direction(params: Any) -> list[float] | None:
    """Where the sun is from the middle of a scene with orbits but without the Sun in its data: the real
    direction on the date for orbits around a planet (or the Moon: the Earth's), from JPL's approximate
    elements; None when it cannot be known (the page then uses the default and says so)."""
    data = params.orbits
    central = data.central if isinstance(data.central, str) else getattr(data.central, "preset", None) or getattr(data.central, "name", None)
    key = str(central or "").strip().lower()
    key = "earth" if key == "moon" else key
    if key not in orbits.TABLE1:
        return None
    jd = orbits.ephemeris.julian_date(data.date) if data.date is not None else 2451545.0
    r = orbits.ephemeris.heliocentric(key, jd)
    n = math.sqrt(sum(float(x) ** 2 for x in r))
    return [round(-float(x) / n, 12) for x in r]


def orbit_names(params: Any) -> tuple[list[str], str | None]:
    """The bodies of the scene's orbit data (the central body first) and the name of its Sun, if any."""
    if params.orbits is None:
        return [], None
    system = params.orbits.model(None).system
    names = [system.central.name, *system.names]
    names = list(dict.fromkeys(names))
    return names, next((n for n in names if n.lower() == "sun"), None)


def page_source(params: Any, scene_id: str) -> str:
    """The page's JavaScript for a ``space`` scene's (checked) params."""
    return _Page(params, scene_id).source()


class _Page:
    def __init__(self, p: Any, scene_id: str) -> None:
        self.p, self.id = p, scene_id
        self.orbit = p.orbits is not None
        self.names, self.sun_body = orbit_names(p)
        self.lines: list[str] = []
        self.imports: dict[str, set[str]] = {}

    def use(self, module: str, *names: str) -> None:
        self.imports.setdefault(module, set()).update(names)

    def out(self, line: str = "", indent: int = 1) -> None:
        self.lines.append("  " * indent + line if line else "")

    # ----- the parts -----
    def sky(self) -> None:
        if self.p.sky is False:
            return
        self.use("vidgen/space-sky", "spaceSky")
        self.out("// the sky (vidgen/space-sky)")
        self.out(f"S.sky = spaceSky(renderer, {js(self.p.sky.options(self.p.seed))}); scene.add(S.sky.object);")

    def sun(self) -> None:
        s, p = self.p.sun, self.p
        self.use("vidgen/space-light", "star")
        opts = module_options(s.extras(), names()["star_options"], "sun")
        if s.temperature is not None:
            opts["temperature"] = s.temperature
        if s.seed is not None:
            opts["seed"] = s.seed
        self.out("// the sun (vidgen/space-light)")
        if self.orbit and self.sun_body and s.direction is None:
            self.out(f"S.sun = star(renderer, {js(s.kind)}, {{{pairs(opts)}space, body: {js(self.sun_body)}}});")
            return
        if s.at is not None:
            at = [length(v, "sun.at") for v in s.at]
            radius = length(s.radius, "sun.radius") if s.radius is not None else 6.957e8
            self.out(f"S.sun = star(renderer, {js(s.kind)}, {js(opts)}); space.add(S.sun.object, {{at: {js(at)}, size: {js(radius)}}});")
            self.out(f"S.subjects[\"Sun\"] = freeSubject(\"Sun\", {js(at)}, {js(radius)});")
            return
        d = s.direction or (sun_direction(p) if self.orbit else None)
        if d is None:
            d = list(DEFAULT_SUN)
            if self.orbit:
                self.out(f"pageNote({js('sun: no Sun in the orbit data and no date-known planet in the middle: the sun stands at the default direction [1, 0.25, 0.35]; give sun.direction')});")
        self.use("vidgen/space-scale", "yUp")
        self.out(f"S.sun = star(renderer, {js(s.kind)}, {{{pairs(opts)}direction: yUp({js([float(x) for x in d])})}}); scene.add(S.sun.object);")

    def bodies(self) -> None:
        if not self.p.bodies:
            return
        self.use("vidgen/space-bodies", "planet")
        self.out("// the worlds (vidgen/space-bodies)")
        for b in self.p.bodies:
            what = b.world if b.world is not None else {}
            opts = b.planet_options()
            if isinstance(what, dict):
                what, opts = opts, {}
            ref = f"S.bodies[{json.dumps(b.name)}]"
            if self.orbit:
                self.out(f"{ref} = planet(renderer, {js(what)}, {{{pairs(opts)}space, body: {js(b.name)}}});")
            else:
                at = [length(v, f"bodies {b.name}.at") for v in (b.at or [0, 0, 0])]
                radius = b.radius_m()
                self.out(f"{ref} = planet(renderer, {js(what)}, {js(opts)}); space.add({ref}.object, {{at: {js(at)}, size: {js(radius)}}});")
                self.out(f"S.subjects[{json.dumps(b.name)}] = freeSubject({js(b.name)}, {js(at)}, {js(radius)}); S.worlds.push(S.subjects[{json.dumps(b.name)}]);")

    def craft(self) -> None:
        if not self.p.craft:
            return
        self.use("vidgen/space-craft", "craft")
        self.out("// the craft (vidgen/space-craft)")
        for c in self.p.craft:
            ref = f"S.craft[{json.dumps(c.name)}]"
            opts = c.craft_options()
            if c.fleet:
                self.use("vidgen/space-craft", "fleet")
                f = {**opts, "count": c.fleet, **({"spacing": length(c.spacing, "spacing")} if c.spacing is not None else {})}
                self.out(f"{ref} = fleet({js(c.kind)}, {js(f)});")
                lead = f"{ref}.craft[0]"
                body = c.fly or (c.name if c.name in self.names else None)
                if self.orbit:
                    self.out(f"space.add({ref}.object, {{body: {js(body)}, size: 1}}); S.subjects[{json.dumps(c.name)}] = {{body: {js(body)}, radius: 3 * {lead}.size.radius, name: {js(c.name)}}};")
                else:
                    self._free_craft(c, ref, f"3 * {lead}.size.radius")
                self.out(f"for (const one of {ref}.craft) one.shade(S.sun);")
                continue
            self.out(f"{ref} = craft({js(c.kind)}, {{{pairs(opts)}camera, height: ctx.height}});")
            if self.orbit:
                body = c.fly or c.name
                fly: dict[str, Any] = {"body": body, "attitude": c.attitude or "prograde"}
                if isinstance(c.burn, dict) or c.burn is False:
                    fly["burn"] = c.burn
                if c.target is not None:
                    fly["target"] = c.target
                self.out(f"{ref}.fly(space, {js(fly)}); S.subjects[{json.dumps(c.name)}] = {ref};")
            else:
                self._free_craft(c, ref, f"{ref}.size.radius")
            self.out(f"{ref}.shade(S.sun);")

    def _free_craft(self, c: Any, ref: str, radius: str) -> None:
        at = [length(v, f"craft {c.name}.at") for v in (c.at or [0, 0, 0])]
        v = [float(x) for x in c.velocity] if c.velocity is not None else None
        key = json.dumps(c.name)
        self.out(f"S.subjects[{key}] = freeSubject({js(c.name)}, {js(at)}, {radius}, {js(v)}); space.add({ref}.object, {{at: S.subjects[{key}].at, size: 1}});")

    def phenomena(self) -> None:
        if not self.p.phenomena:
            return
        self.use("vidgen/space-phenomena", "*")
        self.out("// phenomena (vidgen/space-phenomena)")
        for ph in self.p.phenomena:
            ref, key, opts = f"S.phenomena[{json.dumps(ph.name)}]", json.dumps(ph.name), ph.module()
            size = length(ph.size, "size") if ph.size is not None else DEFAULT_SIZES.get(ph.kind, 1.0)
            at = [length(v, "at") for v in (ph.at or [0, 0, 0])]
            k = ph.kind
            if k == "black-hole":
                self.out(f"{ref} = P.blackHole(renderer, {{{pairs(opts)}sky: S.sky}}); space.add({ref}.object, {{at: {js(at)}, size: {js(size)}}});")
            elif k == "wormhole":
                other = ph.other or {"seed": self.p.seed + 10, "look": "rich"}
                self.use("vidgen/space-sky", "spaceSky")
                self.out(f"{ref} = P.wormhole(renderer, {{{pairs(opts)}sky: S.sky, other: spaceSky(renderer, {js(other)})}}); space.add({ref}.object, {{at: {js(at)}, size: {js(size)}}});")
            elif k == "asteroid":
                self.out(f"{ref} = P.asteroid({js(opts)}); space.add({ref}.object, {{at: {js(at)}, size: {js(size)}}});")
            elif k == "warp":
                a, b = (ph.over or [0, Ref("S.seconds")])
                self.out(f"{ref} = P.warp(renderer, {{{pairs(opts)}fps: ctx.fps, seconds: Math.max({js(when(b))} - {js(when(a))}, 0.1)}}); scene.add({ref}.object);")
                self.out(f"{ref}.over = [{js(when(a))}, {js(when(b))}];")
            elif k == "comet":
                if ph.body is not None:
                    self.out(f"{ref} = P.comet(renderer, {{{pairs(opts)}space, body: {js(ph.body)}}}); {ref}.object.scale.setScalar({js(size)});")
                else:
                    self.out(f"{ref} = P.comet(renderer, {js(opts)}); space.add({ref}.object, {{at: {js(at)}, size: {js(size)}}});")
            elif k == "aurora":
                self.out(f"{ref} = P.aurora(S.bodies[{json.dumps(ph.world)}], {js(opts)});")
                continue
            elif k == "asteroids":
                self.out(f"{ref} = P.asteroids(renderer, {{{pairs(opts)}light: S.light}});")
                if ph.around is not None:
                    unit = js(size) if ph.size is not None else (f"space.radius({json.dumps(ph.around)}) / 16" if self.orbit else f"S.subjects[{json.dumps(ph.around)}].radius / 16")
                    place = f"body: {js(ph.around)}" if self.orbit else f"at: S.subjects[{json.dumps(ph.around)}].at(0)"
                    self.out(f"space.add({ref}.object, {{{place}, size: {unit}}});")
                elif ph.at is not None:
                    self.out(f"space.add({ref}.object, {{at: {js(at)}, size: {js(size)}}});")
                else:
                    self.out(f"scene.add({ref}.object);   // a field round the camera (metres)")
                continue
            if k in ("black-hole", "wormhole", "asteroid") or (k == "comet" and ph.body is None):
                self.out(f"S.subjects[{key}] = freeSubject({js(ph.name)}, {js(at)}, {js(size)});")
            elif k == "comet":
                self.out(f"S.subjects[{key}] = {js(ph.body)};")

    def light(self) -> None:
        l = self.p.light
        opts = {"exposure": l.exposure, "ev": l.ev, "falloff": l.falloff, "eclipses": l.eclipses, "shine": l.shine, "ambient": l.ambient,
                **module_options(l.extras(), names()["light_options"], "light")}
        self.out("// the light (vidgen/space-light): one hard sun, planet-shine, no ambient by default")
        lead = f"S.craft[{json.dumps(self.p.craft[0].name)}]" if self.p.craft else None
        if lead and self.p.craft[0].fleet:
            lead += ".craft[0]"
        at = f", at: {lead}.object" + (f", shadows: {lead}.shadows" if l.shadows else "") if lead else ""
        self.out(f"S.light = spaceLight({{{pairs(opts)}scene, camera, renderer, sun: S.sun, bodies: Object.values(S.bodies), sky: S.sky ?? null{at}}});")
        self.use("vidgen/space-light", "spaceLight")

    def moves(self) -> None:
        self.use("vidgen/space-camera", "spaceCamera")
        self.use("vidgen/space-scene", "moveTrack")
        self.out("// the camera (vidgen/space-camera): its moves one after another")
        self.out("S.cam = spaceCamera({space, sun: S.sun, height: ctx.height, bodies: S.worlds});")
        self.out("S.moves = [")
        moves = self.p.camera
        for k, m in enumerate(moves):
            opts = _lengths(m.options(), f"camera {m.move}")
            for key, value in list(opts.items()):
                if key in ("behind", "of", "target", "around", "level", "from", "to") and isinstance(value, str):
                    opts[key] = subject(value)
                elif key in ("from", "to") and isinstance(value, list):
                    opts[key] = [length(v, f"camera {m.move}.{key}") for v in value]
                if key == "stops":
                    opts[key] = [{**s, "subject": subject(s["subject"])} if isinstance(s.get("subject"), str) else s for s in value]
                if key == "at":
                    opts[key] = when(value)
            if m.subject is not None:
                opts["subject"] = subject(m.subject)
            if m.lens is not None:
                opts["lens"] = m.lens
            over = m.over or ([0.0, Ref("S.seconds")] if len(moves) == 1 else None)
            start = when(over[0]) if over else 0.0
            if over and "over" in names_of(m.move):
                opts["over"] = [when(over[0]), when(over[1])]
            name = f"camera[{k + 1}] ({m.move})"
            self.out(f"{{name: {js(name)}, start: {js(start)}, cut: {js(m.cut)}, shot: (t) => S.cam.{MOVE_CALLS[m.move]}(t, {js(opts)})}},", 2)
        self.out("];")
        self.out("S.view = moveTrack(S.moves);")

    def reactions(self) -> None:
        if not self.p.music:
            return
        self.use("vidgen/space-scene", "reaction")
        self.out("// reactions to the music (vidgen/music-time): brightness, glints, throttle; never the camera")
        for i, r in enumerate(self.p.music):
            kind = "level" if r.track == "level" else {"pulse": "hits", "glint": "notes", "glow": "signal"}[r.action]
            self.out(f"S.react[{i}] = reaction(ctx.music, {js({'on': r.track, 'kind': kind, 'decay': r.decay})});")

    def step(self) -> None:
        p = self.p
        self.out("// everything at scene time t: a function of t alone (the same in any order, at sub-frames too)")
        self.out("S.step = (t) => {")
        self.out("S.shot = S.cam.apply(t, S.view(t));", 2)
        bright: dict[str, list[str]] = {}
        craft_set: dict[str, dict[str, str]] = {}
        kinds = {ph.name: ph.kind for ph in p.phenomena}
        craft = {c.name for c in p.craft}
        for i, r in enumerate(p.music):
            v = f"S.react[{i}](t)"
            if r.target in craft:
                prop = r.as_ or ("throttle" if r.action == "glow" else "lights")
                base = {"lights": "1", "throttle": "0", "rcs": "0"}[prop]
                expr = f"Math.min(1, {js(r.amount)} * {v})" if prop != "lights" else f"{base} + {js(r.amount)} * {v}"
                craft_set.setdefault(r.target, {})[prop] = expr
            else:
                key = "sun" if r.target.lower() == "sun" else "sky" if r.target.lower() == "sky" else kinds.get(r.target, "")
                bright.setdefault(f"{key}:{r.target}", []).append(f"(1 + {js(r.amount)} * {v})")
        sky_terms = [t for k, terms in bright.items() if k.startswith("sky:") for t in terms]
        for ph in p.phenomena:
            ref = f"S.phenomena[{json.dumps(ph.name)}]"
            if ph.kind == "warp":
                terms = " * ".join(bright.get(f"warp:{ph.name}", [])) or "1"
                self.out(f"{{ const w = {ref}, u = Math.min(1, Math.max(0, (t - w.over[0]) / (w.over[1] - w.over[0]))); w.state = w.update(t, {{progress: u, camera, intensity: {terms}}}); }}", 2)
                sky_terms.append(f"({ref}.state ? {ref}.state.sky : 1)")
            elif ph.kind == "black-hole" and f"black-hole:{ph.name}" in bright:
                self.out(f"{ref}.set({{brightness: {ref}.base * {' * '.join(bright[f'black-hole:{ph.name}'])}}});", 2)
                self.out(f"{ref}.update(t);", 2)
            elif ph.kind == "asteroids":
                self.out(f"{ref}.update(t, {{camera}});", 2)
            elif ph.kind == "comet" and ph.body is None:
                self.out(f"{ref}.update(t, {{sun: S.sun.direction ?? [1, 0.2, 0.3]}});", 2)
            else:
                self.out(f"{ref}.update(t);", 2)
        if p.sky is not False and sky_terms:
            self.out(f"S.sky.set({{brightness: S.skyBase * {' * '.join(sky_terms)}}});", 2)
        if "sun:Sun" in bright or any(k.startswith("sun:") for k in bright):
            terms = [t for k, v in bright.items() if k.startswith("sun:") for t in v]
            self.out(f"S.sun.options.glare = S.glareBase * {' * '.join(terms)};", 2)
        self.out("for (const b of Object.values(S.bodies)) b.update(t);", 2)
        self.out("S.sun.update(t);", 2)
        for c in p.craft:
            ref = f"S.craft[{json.dumps(c.name)}]"
            o: dict[str, Any] = {"sun": Ref("S.sun")}
            if not self.orbit and not c.fleet:
                if c.velocity is not None:
                    o["velocity"] = three(c.velocity)
                if c.attitude is not None or c.velocity is not None:
                    o["attitude"] = c.attitude or "prograde"
            for key in ("throttle", "rcs"):
                if getattr(c, key) is not None:
                    o[key] = getattr(c, key)
            for prop, expr in craft_set.get(c.name, {}).items():
                o[prop] = Ref(expr)
            self.out(f"{ref}.update(t, {js(o)});", 2)
        self.out("S.light.update(t);", 2)
        if p.script:
            self.out("if (hook.frame) hook.frame(t, S);", 2)
        self.out("};")

    def finish(self) -> None:
        f = self.p.finish
        if f is False:
            return
        self.use("vidgen/three-finish", "Finish")
        opts = f.options()
        dof = opts.pop("dof", None)
        extra = f", dof: () => ({{{pairs(dof)}focus: S.focus()}})" if dof is not None else ""
        self.out("// finishing (vidgen/three-finish): no FXAA by default (it breaks stars and thin rings)")
        self.out(f"S.finish = new Finish(renderer, scene, camera, ctx, {{{pairs(opts)}update: (t) => S.step(t){extra}}});")

    def cards(self) -> None:
        p = self.p
        for key, call in (("title", "titleCard"), ("end_card", "endCard")):
            card = getattr(p, key)
            if card is None:
                continue
            self.use("vidgen/title-cards", call)
            self.out(f"S.{'title' if key == 'title' else 'end'} = await {call}(ctx, {js(card.card_options('title' if key == 'title' else 'end'))});")

    def source(self) -> str:
        p = self.p
        self.out("const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});")
        self.out("renderer.setSize(ctx.width, ctx.height, false);")
        self.out("const scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);")
        self.out("const camera = new THREE.PerspectiveCamera(40, ctx.width / ctx.height, 1, 1e13);")
        view = {"mode": p.scale.mode if p.scale else "true"}
        if p.scale and p.scale.mode == "enlarged":
            view["enlarge"] = p.scale.enlarge
        dof = p.finish is not False and bool(p.finish.depth_of_field)
        self.use("vidgen/space-scale", "SpaceView")
        self.out(f"const space = new SpaceView(ctx, {{{pairs(view)}renderer, scene, camera{', dofFocus: () => S.focus()' if dof else ''}}});")
        self.out("Object.assign(S, {ctx, THREE, renderer, scene, camera, space, seconds: ctx.data.scene_seconds ?? ctx.duration});")
        self.out("const T = (time) => sceneTime(ctx, time);")
        self.use("vidgen/space-scene", "sceneTime", "freeSubject", "pageNote", "checkMoves")
        for o in (self.sky, self.sun, self.bodies, self.craft):
            o()
        self.light()
        self.phenomena()
        self.moves()
        self.reactions()
        if p.script:
            self.out(f"// your code (script: {p.script}): setup(S) once, frame(t, S) every frame")
            self.out(f"hook = await import({js('/' + str(p.script).replace(chr(92), '/'))});")
            self.out("if (hook.setup) await hook.setup(S);")
        self.step()
        self.out("S.skyBase = S.sky ? S.sky.options?.brightness ?? 1 : 1; S.glareBase = S.sun.options.glare;")
        for ph in p.phenomena:
            if ph.kind == "black-hole":
                self.out(f"S.phenomena[{json.dumps(ph.name)}].base = S.phenomena[{json.dumps(ph.name)}].options.brightness;")
        self.out("S.step(0);")
        if p.craft:
            self.use("vidgen/space-craft", "craftEnvironment")
            lead = f"S.craft[{json.dumps(p.craft[0].name)}]" + (".craft[0]" if p.craft[0].fleet else "")
            self.out(f"S.env = craftEnvironment(renderer, scene, {{at: {lead}.object}}); scene.environment = S.env.texture;")
        self.finish()
        self.cards()
        if p.scale is not None and p.scale.mode != "true" and p.scale.note:
            self.out("// the scale's note on screen, in the orbit scene's words: enlarged sizes and compressed distances are stated")
            self.out("S.note = document.createElement(\"div\"); S.note.textContent = space.note().text; S.note.setAttribute(\"data-vidgen-id\", \"scale-note\");")
            self.out("S.note.style.cssText = `position:fixed;right:2.5%;bottom:3.5%;color:rgba(255,255,255,0.72);letter-spacing:0.03em;" +
                     "font:${ctx.theme.sizes.caption ?? 20}px ${JSON.stringify(ctx.theme.fonts.sans)}, sans-serif`;")
            self.out("document.body.appendChild(S.note);")
        self.out("// what only the page can know, as warnings in vidgen's log")
        self.out("checkMoves(S.cam, S.moves, S.seconds, {fps: ctx.fps});")
        self.out("for (const b of Object.values(S.bodies)) for (const p of [].concat(b.problems ? b.problems(0) ?? [] : [])) pageNote(`bodies: ${p}`);")
        self.out("for (const p of [].concat(space.problems() ?? [])) pageNote(`scale: ${p}`);")
        head = [
            f"// The page of the space scene \"{self.id}\" (DESIGN.md §122.12), written by vidgen from video.yaml (generator {PAGE_VERSION}).",
            "// Change the scene in video.yaml; to go on in code, `vidgen space-page` writes this page out as a web scene's script.",
            'import * as THREE from "three";',
        ]
        for module in sorted(self.imports):
            names_ = self.imports[module]
            if "*" in names_:
                head.append(f'import * as P from "{module}";')
                continue
            head.append(f"import {{{', '.join(sorted(names_))}}} from \"{module}\";")
        head += ["", "/** Everything of the scene by name: renderer, scene, camera, space, sky, sun, bodies, craft, phenomena, cam, moves, view, light, finish. */",
                 "export const S = {bodies: {}, craft: {}, phenomena: {}, subjects: {}, worlds: [], react: {}};",
                 *(["let hook = null;"] if p.script else []),
                 f"export const PARAMS = {json.dumps(p.model_dump(mode='json', by_alias=True, exclude_unset=True), ensure_ascii=False, sort_keys=True)};",
                 "S.focus = () => Math.min(Math.max(S.shot && S.shot.focus > 0 ? S.shot.focus : 1e6, 0.01), 1e9);",
                 "",
                 "export async function load(ctx) {"]
        tail = ["}", "",
                "export function frame(t) {",
                "  if (S.finish) S.finish.render(t); else { S.step(t); S.renderer.setRenderTarget(null); S.renderer.render(S.scene, S.camera); }",
                *(["  S.title.update(t);"] if p.title is not None else []),
                *(["  S.end.update(t);"] if p.end_card is not None else []),
                "}", ""]
        return "\n".join(head + self.lines + tail)


def names_of(move: str) -> list[str]:
    """The options the camera move ``move`` takes."""
    return names()["moves"][move]


__all__ = ["DEFAULT_SIZES", "DEFAULT_SUN", "MOVE_CALLS", "PAGE_VERSION", "Ref", "js", "pairs", "orbit_names", "page_source", "sun_direction", "three"]

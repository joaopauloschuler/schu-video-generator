"""The page a ``space`` scene draws: JavaScript written from the scene's params,
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

from .space_params import length, module_options, move_lengths, names, scene_time, uses_bars

#: Version of what the generator writes (in the page's first line, so it is in the clip's key).
PAGE_VERSION = 1
#: The sun's direction when nothing says where it is (the orbit data's axes, z up).
DEFAULT_SUN = (1.0, 0.25, 0.35)
#: JS names of the camera moves.
MOVE_CALLS = {"arc": "arc", "fly-by": "flyBy", "pass": "pass", "arrive": "arrive", "reveal": "reveal", "follow": "follow", "zoom": "zoom", "look": "look"}
#: Option keys of the moves that hold a length (metres or text with a unit).
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


def sun_direction(params: Any) -> list[float] | None:
    """Where the sun is from the middle of a scene with orbits but without the Sun in its data: the real
    direction on the date for orbits around a planet (or the Moon: the Earth's), from JPL's approximate
    elements, in the data's frame (a flyby's turns with the planet's motion: :func:`vidgen.orbits.ephemeris.flyby_axes`); None
    when it cannot be known (the page then uses the default and says so)."""
    data = params.orbits
    central = data.central if isinstance(data.central, str) else getattr(data.central, "preset", None) or getattr(data.central, "name", None)
    key = str(central or "").strip().lower()
    key = "earth" if key == "moon" else key
    if key not in orbits.TABLE1:
        return None
    jd = orbits.ephemeris.julian_date(data.date) if data.date is not None else 2451545.0
    r = orbits.ephemeris.heliocentric(key, jd)
    if data.flyby is not None:   # the flyby's own frame: x along the planet's motion, z its orbit's north
        r = orbits.ephemeris.flyby_axes(key, jd) @ r
    n = math.sqrt(sum(float(x) ** 2 for x in r))
    return [round(-float(x) / n, 12) for x in r]


def orbit_names(params: Any) -> tuple[list[str], str | None]:
    """The bodies of the scene's orbit data (the central body first) and the name of its Sun, if any."""
    if params.orbits is None:
        return [], None
    system = params.orbits.model(None, check_dates=params.orbits.speedup is None).system
    names = [system.central.name, *system.names]
    names = list(dict.fromkeys(names))
    return names, next((n for n in names if n.lower() == "sun"), None)


def page_source(params: Any, scene_id: str) -> str:
    """The page's JavaScript for a ``space`` scene's (checked) params."""
    try:
        return _Page(params, scene_id).source()
    except ValueError as error:   # a value the checks let through: said as the scene's error, not a traceback
        raise VidgenError(f"space scene '{scene_id}': {error}") from None


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
                self.out(f"S.subjects[{json.dumps(b.name)}] = {js(b.name)};")
            else:
                at = [length(v, f"bodies {b.name}.at") for v in (b.at or [0, 0, 0])]
                radius = b.radius_m()
                self.out(f"{ref} = planet(renderer, {js(what)}, {js(opts)}); space.add({ref}.object, {{at: {js(at)}, size: {js(radius)}}});")
                self.out(f"S.subjects[{json.dumps(b.name)}] = freeSubject({js(b.name)}, {js(at)}, {js(radius)}); S.worlds.push(S.subjects[{json.dumps(b.name)}]);")

    def craft(self) -> None:
        if not self.p.craft:
            return
        if any(c.maker == "kit" for c in self.p.craft):
            self.use("vidgen/space-craft", "craft")
        self.out("// the craft (vidgen/space-craft)" if all(c.maker == "kit" for c in self.p.craft) else
                 "// the craft (vidgen/space-craft, vidgen/space-plane, vidgen/space-hull and -hull-detail, vidgen/space-effects)")
        for c in self.p.craft:
            ref = f"S.craft[{json.dumps(c.name)}]"
            opts = c.craft_options()
            if c.maker != "kit":
                self._other_craft(c, ref, opts)
                continue
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
            self._effects(c, ref)

    def _other_craft(self, c: Any, ref: str, opts: dict[str, Any]) -> None:
        """A plane, a giant hull (with its detail and its small craft for size) or a craft of the kit's parts."""
        from .space_air_params import ScaleRefSpec

        key = json.dumps(c.name)
        if c.maker == "plane":
            self.use("vidgen/space-plane", "plane")
            self.out(f"{ref} = plane({js(c.plane)}, {{{pairs(opts)}camera, height: ctx.height}});")
        elif c.maker == "parts":
            self.use("vidgen/space-craft", "craftKit", "attach", "around")
            kit = {k: v for k, v in opts.items() if k not in ("marker", "lights")}
            own = {k: v for k, v in opts.items() if k in ("marker", "lights")}
            self.out(f"{{ const kit = craftKit({js(kit)});   // a craft of the kit's own parts")
            root = parts_lines(self, c.parts, 2)
            self.out(f"{ref} = kit.craft({root}, {{{pairs(own)}name: {js(c.name)}, camera, height: ctx.height}}); }}", 2)
        elif c.fleet:
            self.use("vidgen/space-hull", "hullFleet")
            f = {**opts, "count": c.fleet, **({"spacing": length(c.spacing, "spacing")} if c.spacing is not None else {})}
            self.out(f"{ref} = hullFleet({js(c.hull)}, {{{pairs(f)}camera, height: ctx.height}});")
        else:
            self.use("vidgen/space-hull", "hull")
            self.out(f"{ref} = hull({js(c.hull)}, {{{pairs(opts)}camera, height: ctx.height}});")
        lead = f"{ref}.hulls[0]" if c.fleet else ref
        if self.orbit:
            body = c.fly or c.name
            if c.fleet:
                self.out(f"space.add({ref}.object, {{body: {js(body)}, size: 1}}); S.subjects[{key}] = {{body: {js(body)}, radius: 3 * {lead}.size.radius, name: {js(c.name)}}};")
            else:
                fly: dict[str, Any] = {"body": body, "attitude": c.attitude or "prograde"}
                if isinstance(c.burn, dict) or c.burn is False:
                    fly["burn"] = c.burn
                if c.target is not None:
                    fly["target"] = c.target
                self.out(f"{ref}.fly(space, {js(fly)}); S.subjects[{key}] = {ref};")
        else:
            self._free_craft(c, ref, f"{'3 * ' if c.fleet else ''}{lead}.size.radius")
        self.out(f"for (const one of {ref}.hulls) one.shade(S.sun);" if c.fleet else f"{ref}.shade(S.sun);")
        if c.maker == "hull":
            if c.dress is not False:
                self.use("vidgen/space-hull-detail", "dressFleet" if c.fleet else "dress")
                dress = c.dress if isinstance(c.dress, dict) else {}
                self.out(f"S.detail[{key}] = {'dressFleet' if c.fleet else 'dress'}({ref}, renderer, {js(dress)});   // windows, bays, lamps, plumes (maps baked once: vidgen cache)")
            if c.scale_ref is not None:
                r = ScaleRefSpec.model_validate(c.scale_ref)
                self.out(f"S.refs[{key}] = {ref}.scaleRef({js(r.kind)}, {js(r.options())}); S.refs[{key}].shade(S.sun);   // a small craft beside it, for size")
        self._effects(c, ref)

    def _effects(self, c: Any, ref: str) -> None:
        if c.effects is None:
            return
        spec = c.effects_spec()
        self.use("vidgen/space-effects", "effects")
        opts = {**spec.groups(), "quality": spec.quality, **({"seed": spec.seed} if spec.seed is not None else {})}
        self.out(f"S.fx[{json.dumps(c.name)}] = effects({ref}, {js(opts)});   // in vacuum: the bells' flame (vidgen/space-effects)")

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
            elif k == "warp" and ph.cut is not None:
                self.use("vidgen/space-camera", "warpCut")
                self.out(f"{ref} = P.warp(renderer, {{{pairs(opts)}fps: ctx.fps, seconds: {js(float(ph.cut.get('seconds', 3)))}}}); scene.add({ref}.object);   // a jump across a cut (warpCut)")
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

    def orbit_subjects(self) -> None:
        """A body of the orbit data that the camera names but nothing draws (a comet's body, a moon too far to see) as a subject."""
        if not self.orbit:
            return
        drawn = {b.name for b in self.p.bodies} | {c.name for c in self.p.craft} | {ph.name for ph in self.p.phenomena}
        for name in dict.fromkeys(n for m in self.p.camera for _, n in m.named()):
            if name in self.names and name not in drawn:
                self.out(f"S.subjects[{json.dumps(name)}] = {js(name)};   // a body of the orbit data")

    def light(self) -> None:
        l = self.p.light
        opts = {"exposure": l.exposure, "ev": l.ev, "falloff": l.falloff, "eclipses": l.eclipses, "shine": l.shine, "ambient": l.ambient,
                **module_options(l.extras(), names()["light_options"], "light")}
        self.out("// the light (vidgen/space-light): one hard sun, planet-shine, no ambient by default")
        lead = f"S.craft[{json.dumps(self.p.craft[0].name)}]" if self.p.craft else None
        if lead and self.p.craft[0].fleet:
            lead += ".hulls[0]" if self.p.craft[0].maker == "hull" else ".craft[0]"
        at = f", at: {lead}.object" + (f", shadows: {lead}.shadows" if l.shadows else "") if lead else ""
        self.out(f"S.light = spaceLight({{{pairs(opts)}scene, camera, renderer, sun: S.sun, bodies: Object.values(S.bodies), sky: S.sky ?? null{at}}});")
        self.use("vidgen/space-light", "spaceLight")

    def ship_names(self) -> list[str]:
        """The hulls the moves beside a ship name (the only hull when a move names none)."""
        hulls = [c.name for c in self.p.craft if c.maker == "hull"]
        return list(dict.fromkeys(str(m.options().get("ship") or hulls[0]) for m in self.p.camera if m.ship)) if hulls else []

    def moves(self) -> None:
        self.use("vidgen/space-scene", "moveTrack")
        ships = [c.name for c in self.p.craft if c.maker == "hull" and not c.fleet]
        if any(m.ship for m in self.p.camera):
            self.use("vidgen/space-camera-air", "airCamera")
            self.out("// the camera (vidgen/space-camera-air: vidgen/space-camera's moves and the moves beside a giant ship): its moves one after another")
            rig = ", ".join(f"{json.dumps(n)}: S.craft[{json.dumps(n)}]" for n in ships)
            self.out(f"S.cam = airCamera({{space, sun: S.sun, height: ctx.height, bodies: S.worlds, ships: {{{rig}}}}});")
        else:
            self.use("vidgen/space-camera", "spaceCamera")
            self.out("// the camera (vidgen/space-camera): its moves one after another")
            self.out("S.cam = spaceCamera({space, sun: S.sun, height: ctx.height, bodies: S.worlds});")
        if any(m.match for m in self.p.camera):
            self.use("vidgen/space-camera", "matchDisc", "lens")
            self.use("vidgen/space-scene-air", "once")
        self.out("S.moves = [")
        moves = self.p.camera
        for k, m in enumerate(moves):
            if m.air:
                self._ship_move(k, m)
                continue
            opts = move_lengths(m.options(), f"camera {m.move}")
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
            if m.match is not None:
                before = moves[k - 1]
                lens_name = m.lens if m.lens is not None else "normal"
                fov = f"lens({js(lens_name)}).fov"
                self.out(f"// a match cut: {m.subject} placed and sized as {m.match}'s disc in camera[{k}] at the cut (matchDisc)", 2)
                matched = (f"S.matched[{k}] ??= once(() => {{ const at = {js(start)}, d = S.cam.disc(S.moves[{k - 1}].shot(at), {subject(m.match)}, at); "
                           f"return matchDisc(d, S.cam.subject({subject(str(m.subject))}, at).radius, {fov}); }})")
                self.out(f"{{name: {js(name)}, start: {js(start)}, cut: true, shot: (t) => S.cam.{MOVE_CALLS[m.move]}(t, {{...{js(opts)}, ...({matched})()}})}},", 2)
                continue
            self.out(f"{{name: {js(name)}, start: {js(start)}, cut: {js(m.cut)}, shot: (t) => S.cam.{MOVE_CALLS[m.move]}(t, {js(opts)})}},", 2)
        self.out("];")
        self.out("S.view = moveTrack(S.moves);")
        self.operator(metered=False)

    def operator(self, metered: bool) -> None:
        """The person holding the camera (``operator:``) over the moves' view: written only when
        given, so a page without it is the same. Every cut starts a shot with its own horizon and a settled exposure;
        ``metered``: the rig's own meter (a surface scene's airCamera) for the exposure."""
        o = self.p.operator
        if o is None:
            return
        opts = o.options()
        cuts = [when(m.over[0]) for m in self.p.camera if m.cut and m.over]
        if cuts:
            opts["cuts"] = cuts
        self.out("// the camera operator (vidgen/space-camera-air): a hand on the camera, its automatic exposure, a horizon set level late")
        if metered:
            self.out(f"S.view = S.cam.operator(S.view, {js(opts)});")
        else:
            self.use("vidgen/space-camera-air", "operate")
            self.out(f"S.view = operate(S.view, {js(opts)});")

    def _craft_update(self, c: Any, sets: dict[str, str], burns: set[str] | frozenset[str] = frozenset()) -> dict[str, Any]:
        """The options of a plane's, a hull's or a kit-built craft's update(t, ...) at scene time t."""
        o: dict[str, Any] = {"sun": Ref("S.sun")}
        if not self.orbit and not c.fleet:
            if c.velocity is not None:
                o["velocity"] = three(c.velocity)
            if c.attitude is not None or c.velocity is not None:
                o["attitude"] = c.attitude or "prograde"
        for key in ("throttle", "rcs"):
            if getattr(c, key) is not None:
                o[key] = getattr(c, key)
        for prop, expr in sets.items():
            if prop in ("throttle", "rcs") or (prop == "lights" and c.maker != "hull"):
                o[prop] = Ref(expr)
        if c.name in burns:
            o["throttle"] = Ref(f"S.shot.throttle ?? {js(o.get('throttle', 0))}")
        if c.maker == "plane":
            o.update(plane_controls(self, c))
        return o

    def _ship_move(self, k: int, m: Any) -> None:
        """A move beside a giant ship (vidgen/space-camera-air) in the list of moves."""
        from .space_air_params import MOVE_LENGTHS, TIME_OPTIONS, camel_move

        opts = dict(m.options())
        for key in MOVE_LENGTHS.get(m.move, ()):
            if isinstance(opts.get(key), str):
                opts[key] = length(opts[key], f"camera {m.move}.{key}")
        for key in TIME_OPTIONS.get(m.move, ()):
            if key in opts:
                opts[key] = when(opts[key])
        for key in ("world", "behind"):
            if isinstance(opts.get(key), str):
                opts[key] = subject(opts[key])
        if m.lens is not None:
            opts["lens"] = m.lens
        over = m.over or ([0.0, Ref("S.seconds")] if len(self.p.camera) == 1 else None)
        start = when(over[0]) if over else 0.0
        if over and "over" in names_of(m.move):
            opts["over"] = [when(over[0]), when(over[1])]
        name = f"camera[{k + 1}] ({m.move})"
        self.out(f"{{name: {js(name)}, start: {js(start)}, cut: {js(m.cut)}, shot: (t) => S.cam.{camel_move(m.move)}(t, {js(opts)})}},", 2)

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
        burns = {str(m.options().get("ship") or next((c.name for c in p.craft if c.maker == "hull"), "")) for m in p.camera if m.move == "stern-burn"}
        for name in self.ship_names():
            c = next(x for x in p.craft if x.name == name)
            if self.orbit:
                self.out(f"space.update(t, {{from: {{body: {js(c.fly or c.name)}, offset: [0, 0, 1000]}}, to: {js(c.fly or c.name)}}});   // the ship's attitude at t first: the move reads it", 2)
            self.out(f"S.craft[{json.dumps(name)}].update(t, {js(self._craft_update(c, {}))});", 2)
        self.out("S.shot = S.cam.apply(t, S.view(t));", 2)
        bright: dict[str, list[str]] = {}
        craft_set: dict[str, dict[str, str]] = {}
        kinds = {ph.name: ph.kind for ph in p.phenomena}
        craft = {c.name for c in p.craft}
        for i, r in enumerate(p.music):
            v = f"S.react[{i}](t)"
            if r.target in craft:
                prop = r.as_ or ("throttle" if r.action == "glow" else "lights")
                base = {"lights": "1", "throttle": "0", "rcs": "0", "boost": "0", "pulse": "1"}[prop]
                hull_lights = prop == "lights" and any(c.name == r.target and c.maker == "hull" for c in p.craft)
                expr = (f"Math.min(1, {js(r.amount)} * {v})" if prop not in ("lights", "pulse") or hull_lights else f"{base} + {js(r.amount)} * {v}")
                craft_set.setdefault(r.target, {})[prop] = expr
            else:
                key = "sun" if r.target.lower() == "sun" else "sky" if r.target.lower() == "sky" else kinds.get(r.target, "")
                bright.setdefault(f"{key}:{r.target}", []).append(f"(1 + {js(r.amount)} * {v})")
        sky_terms = [t for k, terms in bright.items() if k.startswith("sky:") for t in terms]
        for ph in p.phenomena:
            ref = f"S.phenomena[{json.dumps(ph.name)}]"
            if ph.kind == "warp" and ph.cut is not None:
                terms = " * ".join(bright.get(f"warp:{ph.name}", [])) or "1"
                cut = {"seconds": float(ph.cut.get("seconds", 3)), "split": float(ph.cut.get("split", 0.5))}
                self.out(f"{{ const w = {ref}, u = warpCut(t, {js(when(ph.cut['at']))}, {js(cut)}); w.state = w.update(t, {{progress: u, camera, intensity: {terms}}}); }}   // the jump across the cut", 2)
                sky_terms.append(f"({ref}.state ? {ref}.state.sky : 1)")
            elif ph.kind == "warp":
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
            if c.maker != "kit":
                o = self._craft_update(c, craft_set.get(c.name, {}), burns)
            self.out(f"{ref}.update(t, {js(o)});", 2)
        self.out("S.light.update(t);", 2)
        for c in p.craft:
            key, sets = json.dumps(c.name), craft_set.get(c.name, {})
            if c.maker == "hull" and c.dress is not False:
                lights = Ref(sets["lights"]) if "lights" in sets else 1 if c.lights is None else min(1.0, float(c.lights))
                self.out(f"S.detail[{key}].update(t, {js({'lights': lights, 'light': Ref('S.light')})});", 2)
            if c.maker == "hull" and c.scale_ref is not None:
                ref = c.scale_ref
                self.out(f"S.refs[{key}].update(t, {{sun: S.sun}});", 2)
                if ref.get("into"):
                    a, b = ref["into"]["over"]
                    self.out(f"S.detail[{key}].fly(S.refs[{key}], {js(ref['into'].get('hangar', 'hangar-1'))}, Math.min(1, Math.max(0, (t - {js(when(a))}) / ({js(when(b))} - {js(when(a))}))));   // into the bay", 2)
                if ref.get("escort"):
                    self.out(f"if (S.shot.escort) S.refs[{key}].object.position.set(...S.shot.escort);   // where the reveal wants it: into the frame last", 2)
            if c.effects is not None:
                fx = {"air": 0, **{prop: Ref(expr) for prop, expr in sets.items() if prop in ("boost", "pulse", "throttle")}}
                self.out(f"S.fx[{key}].update(t, {js(fx)});", 2)
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
        if self.p.flash:
            self.use("vidgen/space-scene-air", "flashes")
            cuts = [{"at": when(f.at), "amount": f.amount, "rise": f.rise, "fall": f.fall} for f in self.p.flash]
            extra += f", flash: (t) => flashes(t, {js(cuts)})"
        if self.p.camera_look is not None:
            self.out(f"// camera look {self.p.camera_look} (vidgen/camera-looks): its finish and operator, this scene's own options over them")
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
        if any(c.maker == "hull" for c in p.craft):
            from .space_air_params import HULL_NEAR

            view["near"] = HULL_NEAR
            self.out(f"// near: {HULL_NEAR:g} m, set by vidgen because a giant hull is in the scene (the default near plane slices a hull and draws the world behind it over it)")
        self.out(f"const space = new SpaceView(ctx, {{{pairs(view)}renderer, scene, camera{', dofFocus: () => S.focus()' if dof else ''}}});")
        stores = [k for k, used in (("detail", any(c.maker == "hull" and c.dress is not False for c in p.craft)), ("refs", any(c.scale_ref for c in p.craft)),
                                    ("fx", any(c.effects for c in p.craft)), ("matched", any(m.match for m in p.camera))) if used]
        if stores:
            self.out("Object.assign(S, {" + ", ".join(f"{k}: {{}}" for k in stores) + "});")
        self.out("Object.assign(S, {ctx, THREE, renderer, scene, camera, space, seconds: ctx.data.scene_seconds ?? ctx.duration});")
        self.out("const T = (time) => sceneTime(ctx, time);")
        self.use("vidgen/space-scene", "sceneTime", "freeSubject", "pageNote", "checkMoves")
        for o in (self.sky, self.sun, self.bodies, self.craft):
            o()
        self.light()
        self.phenomena()
        self.orbit_subjects()
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
            lead = f"S.craft[{json.dumps(p.craft[0].name)}]" + ((".hulls[0]" if p.craft[0].maker == "hull" else ".craft[0]") if p.craft[0].fleet else "")
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
            f"// The page of the space scene \"{self.id}\", written by vidgen from video.yaml (generator {PAGE_VERSION}).",
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
    from .space_air_params import move_option_list

    return move_option_list(move) or names()["moves"][move]


def plane_controls(page: Any, c: Any) -> dict[str, Any]:
    """A plane's gear, bay and cabin (numbers, or ramps over time) and held control surfaces, for its update."""
    from .space_air_params import Ramp

    out: dict[str, Any] = {}
    for key in ("gear", "bay", "cabin"):
        value = getattr(c, key)
        if isinstance(value, dict):
            r = Ramp.model_validate(value)
            page.use("vidgen/space-scene-air", "ramp")
            out[key] = Ref(f"ramp(t, {js({'over': [when(r.over[0]), when(r.over[1])], 'from': r.from_, 'to': r.to})})")
        elif value is not None:
            out[key] = float(value)
    if c.controls is not None:
        out["controls"] = dict(c.controls)
    return out


def parts_lines(page: Any, node: dict[str, Any], indent: int, counter: list[int] | None = None) -> str:
    """The lines that make a ``parts:`` tree with the kit (``kit.hull(...)``, ``attach(...)``, ``around(...)``);
    returns the root part's variable."""
    from .space_air_params import part_options

    counter = counter if counter is not None else [0]
    name = f"p{counter[0]}"
    counter[0] += 1
    page.out(f"const {name} = kit.{node['part']}({js(part_options(node))});", indent)
    for child in node.get("attach") or []:
        if "around" in child:
            ring = {**{k: v for k, v in child["around"].items()}}
            make = f"kit.{child['part']}({js(part_options(child))})"
            if child.get("attach"):
                raise VidgenError(f"parts: a ring of {child['part']} (around:) cannot carry parts of its own: attach them to a single part")
            page.out(f"around({name}, () => {make}, {js(ring)});", indent)
            continue
        sub = parts_lines(page, {k: v for k, v in child.items()}, indent, counter)
        extra = {k: child[k] for k in ("roll", "gap") if k in child}
        page.out(f"attach({name}, {js(child['at'])}, {sub}, {js(child.get('mount', 'mount'))}{', ' + js(extra) if extra else ''});", indent)
    return name


__all__ = ["DEFAULT_SIZES", "DEFAULT_SUN", "MOVE_CALLS", "PAGE_VERSION", "Ref", "js", "pairs", "orbit_names", "page_source", "sun_direction", "three"]

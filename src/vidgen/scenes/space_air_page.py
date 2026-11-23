"""The page a surface ``space`` scene draws (DESIGN.md §123.14): JavaScript written from the scene's
params, one world from orbit to the ground in the place's own frame (``vidgen/space-descent``: the
air, the sea, the ground, the decks and the globe of one planet), the stars behind it
(``vidgen/space-sky``), planes and craft on the scene's flights (``vidgen/space-plane``,
``vidgen/space-craft``, ``ctx.flight``), their effects (``vidgen/space-effects``) and the camera moves
of ``vidgen/space-camera-air``, one after another (``vidgen/space-scene``'s ``moveTrack``).

Like the orbital page (:mod:`vidgen.scenes.space_page`): the same params give the same bytes, every
param that changes the picture changes the page, and the page is plain code ``vidgen space-page``
can hand over. Drawn straight to the canvas unless the scene gives ``finish:`` (the air, sea, ground
and clouds apply the tone curve themselves, as every recipe of Steps 381–391 is measured).
Imports only ``vidgen.api`` and its siblings.
"""

import json
from typing import Any

from vidgen.api import *

from .space_air_params import MOVE_LENGTHS, TIME_OPTIONS, camel_move
from .space_page import PAGE_VERSION, Ref, _Page, js, pairs, parts_lines, plane_controls, when
from .space_params import camel, length, module_options, names

#: What the page looks at the moves with: every sixth of a second (at least 24 times a move); an air move may
#: sample the ground (tens of ms), so the orbital page's every frame would cost seconds when the page opens.
CHECK_FPS = 6


def page_source(params: Any, scene_id: str) -> str:
    """The page's JavaScript for a surface ``space`` scene's (checked) params."""
    try:
        return _AirPage(params, scene_id).source()
    except ValueError as error:
        raise VidgenError(f"space scene '{scene_id}': {error}") from None


def flight_of(p: Any, name: Any) -> Any:
    """A move's ``flight`` as the module takes it: a flight's name (a craft's name is its flight's)."""
    if name is None:
        return None
    craft = {c.name: c for c in p.craft}
    return craft[name].fly if name not in p.flights.names and name in craft else name


class _AirPage(_Page):
    def world(self) -> None:
        p, w = self.p, self.p.world
        if p.sky is not False:
            self.use("vidgen/space-sky", "spaceSky")
            sky = p.sky.options(p.seed)
            sky.setdefault("size", 512)
            self.out("// the stars behind the air (vidgen/space-sky)")
            self.out(f"S.sky = spaceSky(renderer, {js(sky)}); scene.add(S.sky.object);")
        self.use("vidgen/space-descent", "world")
        o: dict[str, Any] = {}
        if w.planet is not None:
            o["planet"] = w.planet
        if w.at is not None:
            o["at"] = [float(v) for v in w.at]
        o["sun"] = w.sun.pair(w.place())
        if w.air is not None:
            o["air"] = w.air if isinstance(w.air, str) else {camel(k): v for k, v in w.air.items()}
        if w.sea_spec is not None:
            o["sea"] = w.sea_spec.module(p.seed)
        if w.land_spec is not None:
            o["land"] = w.land_spec.module()
        if w.cloud_spec is not None:
            o["clouds"] = self.clouds(w.cloud_spec)
        for key in ("globe", "handover"):
            if getattr(w, key) is not None:
                o[key] = getattr(w, key)
        if w.match != 1:
            o["match"] = w.match
        o.update({"exposure": w.exposure, "ev": w.ev, "quality": w.quality})
        if w.shadows is not None:
            o["shadows"] = w.shadows
        adapt = [m for m in p.camera if m.move in ("climb-through", "descend-through") and m.options().get("adapt")]
        metered = p.operator is not None and p.operator.metered
        if adapt or metered:
            o["ev"] = Ref(f"() => (S.shot && Number.isFinite(S.shot.ev) ? S.shot.ev : 0) + {js(w.ev)}")
            if adapt:
                self.out("// eye adaptation of the move through the deck: the air's exposure follows the shot's ev (a look)")
            if metered:
                self.out("// the operator's automatic exposure: the air's exposure follows the shot's ev (vidgen/space-camera-air's meter)")
        self.out("// one world from orbit to the ground, in the place's own frame: x east, y up, z south, metres (vidgen/space-descent)")
        self.out(f"S.world = world(renderer, {{{pairs(o)}{'stars: S.sky, ' if p.sky is not False else ''}scene}}); scene.add(S.world.object);")

    def clouds(self, c: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if c.sky is not None:
            out["sky"] = c.sky
        if c.decks:
            out["decks"] = [{camel(k): v for k, v in d.items()} for d in c.decks]
        if c.towers is not None:
            out["towers"] = {"count": c.towers} if isinstance(c.towers, int) else {camel(k): v for k, v in c.towers.items()}
        out["seed"] = c.seed if c.seed is not None else self.p.seed
        out.update(module_options(c.extras(), [*self_air()["cloud_options"]], "world.clouds"))
        strikes = [r.track for r in self.p.music if r.target.lower() == "lightning"]
        lg = c.lightning
        if lg is True:
            out["lightning"] = {"rate": 10}
        elif lg not in (None, False) or strikes:
            o = module_options(lg.extras(), self_air()["lightning_options"], "lightning") if lg not in (None, False) else {}
            times: list[str] = []
            if lg not in (None, False) and lg.times:
                times.append("..." + js([when(v) for v in lg.times]))
            for track in [*([lg.track] if lg not in (None, False) and lg.track else []), *strikes]:
                self.use("vidgen/space-scene-air", "hitTimes")
                times.append(f"...hitTimes(ctx.music, {js(track)})")
            if times:
                o["times"] = Ref("[" + ", ".join(times) + "].sort((a, b) => a - b)")
            out["lightning"] = o
        return out

    def craft(self) -> None:
        p = self.p
        if not p.craft:
            return
        self.out("// the craft on the scene's flights (ctx.flight): vidgen/space-plane, vidgen/space-craft; the air between them and the camera")
        for c in p.craft:
            ref, key = f"S.craft[{json.dumps(c.name)}]", json.dumps(c.name)
            opts = c.craft_options()
            fly = f".fly(ctx.flight, {{flight: {js(c.fly)}}})"
            if c.maker == "plane":
                self.use("vidgen/space-plane", "plane")
                self.out(f"{ref} = plane({js(c.plane)}, {js(opts)}){fly};")
            elif c.maker == "parts":
                self.use("vidgen/space-craft", "craftKit", "attach", "around")
                kit = {k: v for k, v in opts.items() if k not in ("marker", "lights")}
                own = {k: v for k, v in opts.items() if k in ("marker", "lights")}
                self.out(f"{{ const kit = craftKit({js(kit)});   // a craft of the kit's own parts")
                root = parts_lines(self, c.parts, 2)
                self.out(f"{ref} = kit.craft({root}, {{{pairs(own)}name: {js(c.name)}}}){fly}; }}", 2)
            else:
                self.use("vidgen/space-craft", "craft")
                self.out(f"{ref} = craft({js(c.kind)}, {js(opts)}){fly};")
            self.out(f"scene.add({ref}.object); for (const m of Object.values({ref}.materials ?? {{}})) S.world.sky.haze(m);")
            if c.effects is not None:
                spec = c.effects_spec()
                self.use("vidgen/space-effects", "effects")
                fx = {"flight": Ref("ctx.flight"), "name": c.fly, "sky": Ref("S.world.sky"), **spec.groups(), "quality": spec.quality,
                      **({"seed": spec.seed} if spec.seed is not None else {})}
                self.out(f"S.fx[{key}] = effects({ref}, {js(fx)}); scene.add(S.fx[{key}].object);   // they follow the flight (vidgen/space-effects)")

    def moves(self) -> None:
        p = self.p
        self.use("vidgen/space-camera-air", "airCamera")
        self.use("vidgen/space-scene", "moveTrack")
        crafts = {}
        for c in p.craft:
            crafts.setdefault(c.fly, c.name)
        rig = ", ".join(f"{json.dumps(f)}: S.craft[{json.dumps(n)}]" for f, n in crafts.items())
        self.out("// the camera (vidgen/space-camera-air): its moves one after another, over the world's ground and water")
        self.out(f"S.cam = airCamera({{camera, ...S.world.rig, flight: ctx.flight ?? null, crafts: {{{rig}}}, music: ctx.music ?? null}});")
        self.out("S.moves = [")
        for k, m in enumerate(p.camera):
            opts = dict(m.options())
            for key in MOVE_LENGTHS.get(m.move, ()):
                if isinstance(opts.get(key), str):
                    opts[key] = length(opts[key], f"camera {m.move}.{key}")
            for key in TIME_OPTIONS.get(m.move, ()):
                if key in opts:
                    opts[key] = when(opts[key])
            if "flight" in opts:
                opts["flight"] = flight_of(p, opts["flight"])
            if isinstance(opts.get("craft"), str):
                opts["craft"] = Ref(f"S.craft[{json.dumps(opts['craft'])}]")
            follow = m.continues
            if m.lens is not None:
                opts["lens"] = m.lens
            over = m.over or ([0.0, Ref("S.seconds")] if len(p.camera) == 1 else None)
            start = when(over[0]) if over else 0.0
            if over and "over" in (self_move_options(m.move)):
                opts["over"] = [when(over[0]), when(over[1])]
            call = f"S.cam.{camel_move(m.move)}(t, {js(opts)})"
            if follow:
                before = p.camera[k - 1]
                call = f"S.cam.skim(t, {{...S.ends[{k}], follow: 0, ...{js(opts)}}})"
                self.out(f"// camera[{k + 1}] continues camera[{k}] ({before.move}): its end (place, heading, speed, height) is where this skim starts", 2)
            name = f"camera[{k + 1}] ({m.move})"
            self.out(f"{{name: {js(name)}, start: {js(start)}, cut: {js(m.cut)}, shot: (t) => {call}}},", 2)
        self.out("];")
        self.out("S.view = moveTrack(S.moves);")
        self.operator(metered=True)

    def reactions(self) -> None:
        live = [(i, r) for i, r in enumerate(self.p.music) if r.target.lower() != "lightning"]
        if not live:
            return
        self.use("vidgen/space-scene", "reaction")
        self.out("// reactions to the music (vidgen/music-time): the lava's glow, a craft's lights, throttle and afterburner; never the camera")
        for i, r in live:
            kind = "level" if r.track == "level" else {"pulse": "hits", "glint": "notes", "glow": "signal"}[r.action]
            self.out(f"S.react[{i}] = reaction(ctx.music, {js({'on': r.track, 'kind': kind, 'decay': r.decay})});")

    def step(self) -> None:
        p = self.p
        sets: dict[str, dict[str, str]] = {}
        glow: list[str] = []
        for i, r in enumerate(p.music):
            v = f"S.react[{i}](t)"
            if r.target.lower() == "lava":
                glow.append(f"{js(r.amount)} * {v}")
            elif r.target.lower() != "lightning":
                prop = r.as_ or ("throttle" if r.action == "glow" else "lights")
                sets.setdefault(r.target, {})[prop] = f"Math.min(1, {js(r.amount)} * {v})" if prop in ("throttle", "boost") else f"1 + {js(r.amount)} * {v}"
        self.out("// everything at scene time t: a function of t alone (the craft on their flights, the camera, the world, the effects)")
        self.out("S.step = (t) => {")
        for c in p.craft:
            o: dict[str, Any] = {}
            for key in ("throttle", "lights"):
                if getattr(c, key) is not None:
                    o[key] = getattr(c, key)
            for prop, expr in sets.get(c.name, {}).items():
                if prop in ("throttle", "lights"):
                    o[prop] = Ref(expr)
            if c.maker == "plane":
                o.update(plane_controls(self, c))
            self.out(f"S.craft[{json.dumps(c.name)}].update(t, {js(o)});", 2)
        self.out("S.shot = S.cam.apply(t, S.view(t));", 2)
        self.out("S.world.update(t, {camera});", 2)
        if glow:
            self.out(f"if (S.world.ground) S.world.ground.setGlow(Math.min(20, 1 + {' + '.join(glow)}));   // the lava glows with the music", 2)
        for c in p.craft:
            if c.effects is not None:
                fx = {prop: Ref(expr) for prop, expr in sets.get(c.name, {}).items() if prop in ("boost", "pulse")}
                if c.throttle is not None or "throttle" in sets.get(c.name, {}):
                    fx["throttle"] = Ref(sets[c.name]["throttle"]) if "throttle" in sets.get(c.name, {}) else c.throttle
                self.out(f"S.fx[{json.dumps(c.name)}].update(t, {js(fx)});", 2)
        if p.script:
            self.out("if (hook.frame) hook.frame(t, S);", 2)
        self.out("};")

    def finish(self) -> None:
        if "finish" not in self.p.model_fields_set or self.p.finish is False:
            return
        super().finish()

    def source(self) -> str:
        p = self.p
        self.out("const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});")
        self.out("renderer.setSize(ctx.width, ctx.height, false);")
        self.out("const scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);")
        self.out("const camera = new THREE.PerspectiveCamera(50, ctx.width / ctx.height, 1, 4e7);")
        self.out("Object.assign(S, {ctx, THREE, renderer, scene, camera, seconds: ctx.data.scene_seconds ?? ctx.duration});")
        self.out("const T = (time) => sceneTime(ctx, time);")
        self.use("vidgen/space-scene", "sceneTime", "pageNote", "checkMoves")
        if p.flights is not None:
            self.out("if (!ctx.flight) throw new Error(\"vidgen/space-scene: the scene's flights did not reach the page (ctx.flight)\");")
        self.world()
        self.craft()
        self.moves()
        self.reactions()
        if p.script:
            self.out(f"// your code (script: {p.script}): setup(S) once, frame(t, S) every frame")
            self.out(f"hook = await import({js('/' + str(p.script).replace(chr(92), '/'))});")
            self.out("if (hook.setup) await hook.setup(S);")
        self.step()
        self.out("S.step(0);")
        self.finish()
        self.cards()
        self.out("// what only the page can know, as warnings in vidgen's log")
        self.out(f"checkMoves(S.cam, S.moves, S.seconds, {{fps: {CHECK_FPS}}});")
        self.out("for (const p of S.world.problems(camera)) pageNote(`world: ${p}`);")
        head = [
            f"// The page of the space scene \"{self.id}\" (DESIGN.md §123.14), a surface scene written by vidgen from video.yaml (generator {PAGE_VERSION}).",
            "// Change the scene in video.yaml; to go on in code, `vidgen space-page` writes this page out as a web scene's script.",
            'import * as THREE from "three";',
        ]
        for module in sorted(self.imports):
            head.append(f"import {{{', '.join(sorted(self.imports[module]))}}} from \"{module}\";")
        stores = ", ".join(["craft: {}", "react: {}", *(["fx: {}"] if any(c.effects for c in p.craft) else []),
                            *(["ends: {}"] if any(m.continues for m in p.camera) else [])])
        head += ["", "/** Everything of the scene by name: renderer, scene, camera, sky (the stars), world, craft, fx, cam, moves, view, finish. */",
                 f"export const S = {{{stores}}};",
                 *(["let hook = null;"] if p.script else []),
                 f"export const PARAMS = {json.dumps(p.model_dump(mode='json', by_alias=True, exclude_unset=True), ensure_ascii=False, sort_keys=True)};",
                 "S.focus = () => Math.min(Math.max(S.shot && S.shot.focus > 0 ? S.shot.focus : 1e6, 0.01), 1e9);",
                 "",
                 "export async function load(ctx) {"]
        lines = self.lines
        ends = [k for k, m in enumerate(p.camera) if m.continues]
        if ends:
            at = lines.index("  S.view = moveTrack(S.moves);")
            extra = []
            for k in ends:
                before = p.camera[k - 1]
                end = when(before.over[1]) if before.over else Ref("S.seconds")
                extra.append(f"  S.ends[{k}] = S.moves[{k - 1}].shot({js(end)}).end ?? {{}};   // where camera[{k}] ({before.move}) leaves the camera")
            lines = [*lines[:at], *extra, *lines[at:]]
        tail = ["}", "",
                "export function frame(t) {",
                "  if (S.finish) S.finish.render(t); else { S.step(t); S.renderer.setRenderTarget(null); S.renderer.render(S.scene, S.camera); }",
                *(["  S.title.update(t);"] if p.title is not None else []),
                *(["  S.end.update(t);"] if p.end_card is not None else []),
                "}", ""]
        return "\n".join(head + lines + tail)


def self_air() -> dict[str, Any]:
    from .space_air_params import air

    return air()


def self_move_options(move: str) -> list[str]:
    from .space_air_params import move_option_list

    return move_option_list(move) or names()["moves"].get(move, [])


__all__ = ["CHECK_FPS", "flight_of", "page_source"]

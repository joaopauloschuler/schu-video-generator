"""``space``: a space scene written in ``video.yaml`` alone (DESIGN.md §122.12): a sky, a sun, worlds
free-standing or on their orbits, craft, phenomena, camera moves one after another, finishing,
reactions to the music, an opening title and an end card. vidgen writes the page from these params
and the shipped space modules and draws it exactly as a ``web`` scene (the same clip and cache,
``vidgen still``, ``--draft``, ``--jobs``, ``vidgen motion check``); ``script:`` adds code of your
own, and ``vidgen space-page`` writes the page out to go on in code.
"""

import os
from pathlib import Path
from typing import Any

from vidgen.api import *

from .orbit_data import OrbitData
from .space_air_page import page_source as surface_page_source
from .space_page import orbit_names, page_source as orbital_page_source
from .space_air_params import FlashSpec, FlightsSpec, WorldSpec
from .space_checks import check_orbital_air, check_surface
from .space_params import (BodySpec, CardSpec, CraftSpec, FinishSpec, LightSpec, MoveSpec, OperatorSpec, PhenomenonSpec, ReactionSpec, ScaleSpec,
                           SkySpec, SunSpec, scene_time, uses_bars)
from .web import SPARE_FRAMES, Web

#: Where the pages of space scenes are written, under the project folder (served from there).
PAGE_FOLDER = ("build", "space")
#: What may change on a craft, a star, the sky, a black hole or a warp, by reaction (DESIGN.md §122.12).
REACTS_ON = {"sun", "sky", "black-hole", "warp", "craft"}


@scene("space")
class Space(Web):
    """A space scene written in YAML alone: ``sky`` (from a seed, or the real bright stars),
    ``sun``, ``bodies`` (ready-made worlds or your own, free-standing or the bodies of ``orbits``,
    the orbit data of the ``orbit`` scene's words, true positions and timing), ``scale`` (true,
    enlarged, log), ``light`` (exposure, eclipses), ``craft`` (invented spacecraft, flying a body of
    the orbit data with its burns), ``phenomena`` (black hole, wormhole, warp, asteroids, comet,
    aurora), ``camera`` (moves of vidgen/space-camera, one after another, in seconds or bars),
    ``finish`` (space-safe: no FXAA), ``operator`` (a hand on the camera, its automatic exposure, a horizon
    levelled late; off unless given), ``music`` (pulses, glows and glints; never the camera),
    ``title`` and ``end_card``; ``script`` adds your own code. vidgen writes the page and draws it
    in headless Chromium as a ``web`` scene, full-bleed; ``vidgen space-page`` writes it out as a
    ``web`` scene to go on in code.

    Action targets: ``view`` (the page).
    """

    outro = 0.5
    target_patterns = ("view",)

    @classmethod
    def outro_seconds(cls, params: Any) -> float:
        """No fade-out with ``fade: false`` (scenes on bar lines cut straight into each other)."""
        return 0.0 if params.get("fade") is False else float(cls.outro)

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``view``."""
        return ["view"]

    class Params(SceneParams):
        header_synonyms = False

        seed: int = Field(default=1, ge=0)
        """The scene's seed: the sky's and the worlds' and craft's when they give none."""
        sky: SkySpec | bool = Field(default_factory=SkySpec)
        """The sky (vidgen/space-sky): {seed, look: natural | rich | sparse, stars: seed | real, nebulae, galaxies, ...its options}, a look, real, or false."""
        sun: SunSpec = Field(default_factory=SunSpec)
        """The sun (vidgen/space-light): {kind: sun | red-dwarf | orange | white | blue-giant, temperature, direction, at, radius, glare, spikes, flare...} or a kind."""
        orbits: OrbitData | None = None
        """Bodies on their orbits, in the orbit scene's words (orbit_data of a web scene: central, bodies, date, span or speedup, transfer, flyby...). Positions and timing are true."""
        scale: ScaleSpec | None = None
        """With orbits: true (default), {mode: enlarged, enlarge: 50}, a factor (enlarged by it) or log; the scene says so (space.note())."""
        bodies: list[BodySpec] = Field(default_factory=list)
        """Worlds (vidgen/space-bodies): [{name: Saturn}, {name: Moon, world: moon, at: ['400000 km', 0, 0]}, {name: Mira, type: ocean, seed: 7, rings: true}]."""
        light: LightSpec = Field(default_factory=LightSpec)
        """The light (vidgen/space-light): {exposure: film | camera | auto, ev, falloff, eclipses, shadows, shine, ambient, ...}."""
        craft: list[CraftSpec] = Field(default_factory=list)
        """Craft (vidgen/space-craft): [{name: Ship, kind: ship, fly: Ship}, {name: Probe, kind: probe, at: [0, 0, 0]}]."""
        phenomena: list[PhenomenonSpec] = Field(default_factory=list)
        """Phenomena (vidgen/space-phenomena): [{kind: black-hole, size: '10 km'}, {kind: warp, over: [4, 7]}, {kind: aurora, world: Earth}]."""
        camera: list[MoveSpec] = Field(default_factory=list)
        """Camera moves (vidgen/space-camera), one after another: [{move: arc, subject: Saturn, over: [0, 8], phase: [three-quarter, crescent]}]; one move takes the whole scene."""
        finish: FinishSpec | bool = Field(default_factory=FinishSpec)
        """Finishing (vidgen/three-finish): {bloom, grade, grain, vignette, motion_blur, depth_of_field, antialias: none, noise, range, sharpen, distort, edges, halation}, or false (straight to the canvas)."""
        operator: OperatorSpec | None = None
        """The person holding the camera, over all its moves (off unless given): {hand: handheld | mounted, exposure (surface scenes), horizon, seed}."""
        music: list[ReactionSpec] = Field(default_factory=list)
        """Reactions to the score: [{track: kick, pulse: Sun}, {track: level, glow: Ship}, {track: hook, glint: Station}] (needs music_data)."""
        music_data: bool | WebMusicData = False
        """The video's music for the page as ctx.music (as on a web scene): needed by music: and by times in bars."""
        title: CardSpec | None = None
        """An opening title (vidgen/title-cards): text, or {title, subtitle, side, start, hold, ...}."""
        end_card: CardSpec | None = None
        """An end card (vidgen/title-cards): {title, subtitle, lines, link, side, start, ...}."""
        script: str | None = None
        """Your code: a JavaScript module of the project whose setup(S) runs once after the scene is built and frame(t, S) every frame (S: every object by name)."""
        data: dict[str, Any] = {}
        """Values for your script, as ctx.data."""
        fade: bool = True
        """false: no 0.5 s fade-out at the end (scenes cut straight into each other on bar lines)."""
        world: WorldSpec | None = None
        """A surface scene (DESIGN.md §123.14): one world from orbit to the ground in the place's own frame (vidgen/space-descent): {planet, at: [lat, lon], sun: [elevation, azimuth] or {date, utc}, air, sea, land, clouds, globe, exposure, ev, quality}. Without it the scene is an orbital one (orbits, bodies, scale, light)."""
        flights: FlightsSpec | None = None
        """A surface scene's flights (the flight_data vocabulary, Step 385): [{name: Plane, start: {x, z, above_ground, heading, speed}, legs: [...]}]; the ground is the world's land, else its sea, else its sphere."""
        flash: list[FlashSpec] = Field(default_factory=list)
        """Flashes on cuts (vidgen/space-camera's flashCut through the finish): [{at: 'bar 9', amount: 3, rise: 0.25, fall: 0.6}] or a time; give the same at to the scenes on both sides of the cut."""

        @field_validator("camera", "bodies", "craft", "phenomena", "music", mode="before")
        @classmethod
        def _one(cls, value: Any) -> Any:
            return [value] if isinstance(value, dict) else value

        @field_validator("flash", mode="before")
        @classmethod
        def _one_flash(cls, value: Any) -> Any:
            return value if isinstance(value, list) else [value]

        @field_validator("data", mode="before")
        @classmethod
        def _json_data(cls, value: Any) -> Any:
            problem = web_json_problem(value)
            if problem is not None:
                raise ValueError(problem)
            return value

        @field_validator("sky", mode="before")
        @classmethod
        def _sky(cls, value: Any) -> Any:
            return SkySpec() if value is True else value

        @model_validator(mode="after")
        def _consistent(self) -> "Space.Params":
            check_scene(self)
            return self

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        """``script:`` exists as a ``.js`` file of the project; ``music_data`` with music in the video."""
        problems = []
        if params.script is not None:
            problems += web_served_entry_problems(project, {"script": params.script})
        if params.music_data and not video_has_music(project.config):
            problems.append("music_data: the video plays no music; add music: (a score file, a bed or a music file) or turn music_data off")
        return problems

    def _title(self) -> Mobject | None:
        """No heading drawn by vidgen (``title:`` is the page's opening card)."""
        return None

    def _page_box(self, title: Mobject | None) -> Region:
        w, h = self.frame_width / 2, self.frame_height / 2
        return Region(-w, -h, w, h)

    def page_path(self) -> Path:
        """The page this scene's params give, written now under ``build/space/`` when it changed."""
        source = page_source(self.params, self.spec.id)
        path = self.project.root.joinpath(*PAGE_FOLDER, f"{self.spec.id}.js")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_text(encoding="utf-8") != source:
            # whole or not at all: another render (--jobs) may be serving the page this moment
            data, tmp = source.encode("utf-8"), path.with_name(f".{path.name}.{os.getpid()}.partial")
            tmp.write_bytes(data)
            try:
                os.replace(tmp, path)
            except PermissionError:   # Windows: open in another render, which wrote these same bytes
                tmp.unlink(missing_ok=True)
                if not (path.is_file() and path.read_bytes() == data):
                    raise
        return path

    def page_clip_args(self, box: Region | None = None) -> dict[str, Any]:
        """As a ``web`` scene's (:meth:`Web.page_clip_args`), drawn from the page written from the params
        (``build/space/<id>.js``) with ``ctx.data`` = ``data:`` and the scene's own length (``scene_seconds``)."""
        if box is None:
            box = self._page_box(None)
        spans, frames = clip_plan(self, SPARE_FRAMES)
        frame = (int(config.pixel_width), int(config.pixel_height))
        per_unit = frame[0] / self.frame_width
        size = (max(1, round(box.width * per_unit)), max(1, round(box.height * per_unit)))
        theme, beats = web_page_inputs(self, spans, 1.0)
        fps = int(config.frame_rate)
        p = self.params
        path = self.page_path()
        root = web_served_root(self.project)
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        seconds = (frames - SPARE_FRAMES - round(self.outro * fps)) / fps
        page = {"script": rel, "data": {**p.data, "scene_seconds": round(seconds, 6)}}
        extra: dict[str, Any] = {}
        if p.music_data:
            settings = p.music_data if isinstance(p.music_data, WebMusicData) else WebMusicData()
            extra["music"] = web_scene_music(self.project, self.spec.id, fps, settings)
        if p.orbits is not None:
            extra["orbits"] = web_scene_orbits(self.project, p.orbits, fps, frames, frames - SPARE_FRAMES)
        if p.world is not None and p.flights is not None:
            extra["orbits"] = web_with_flights(None, scene_flights(self.project, self.spec.id, p, fps, frames, extra.get("music")))
        return {**extra, "root": root, "folder": self.project.render_dir(self.is_preview) / "web", "scene_id": self.spec.id,
                "params": page, "size": size, "fps": fps, "frames": frames, "theme": theme, "beats": beats,
                "shape": web_page_shape(frame, "bleed")}


def check_scene(p: Any) -> None:
    """The checks across a space scene's sections (a ValueError naming the section): unique names,
    what goes with orbits and what without, the things the camera and the music name, times in bars.
    A scene with ``world:`` is a surface scene, checked by :func:`~vidgen.scenes.space_checks.check_surface`."""
    if p.world is not None:
        check_surface(p)
        return
    if p.operator is not None and p.operator.metered:
        raise ValueError("operator.exposure is a surface scene's (world:): its meter reads the air, the decks and the ground; "
                         "an orbital scene's film exposure has no stops to move (give light: {exposure: camera, ev} by hand)")
    if p.flights is not None:
        raise ValueError("flights: are a surface scene's (the flight_data vocabulary over a world's ground): give the scene world: {planet, at, land | sea, ...}")
    orbit = p.orbits is not None
    data_names, _ = orbit_names(p)
    own = [*(b.name for b in p.bodies), *(c.name for c in p.craft), *(ph.name for ph in p.phenomena)]
    twice = sorted({n for n in own if own.count(n) > 1})
    if twice:
        raise ValueError(f"the name {twice[0]} is given to two things (bodies, craft and phenomena need names of their own)")
    if p.scale is not None and not orbit:
        raise ValueError("scale: goes with orbits: (it sets how the orbit data's sizes and distances are drawn); a scene without orbits has the sizes you give")
    for b in p.bodies:
        if orbit:
            if b.name not in data_names:
                raise ValueError(f"bodies {b.name}: with orbits a world shows a body of the orbit data{did_you_mean(b.name, data_names)} (bodies: {', '.join(data_names)})")
            if b.at is not None or b.radius is not None:
                raise ValueError(f"bodies {b.name}: with orbits its place and size are the data's; leave out at and radius (scale: enlarges)")
            if b.tilt is not None:
                raise ValueError(f"bodies {b.name}: with orbits its pole is the data's; leave out tilt")
    for c in p.craft:
        if orbit:
            body = c.fly or c.name
            if body not in data_names:
                raise ValueError(f"craft {c.name}: with orbits a craft flies a body of the orbit data: fly: NAME{did_you_mean(body, data_names)} (bodies: {', '.join(data_names)})")
            if c.at is not None or c.velocity is not None:
                raise ValueError(f"craft {c.name}: with orbits its place is the data's (fly: {body}); leave out at and velocity")
        elif c.fly is not None:
            raise ValueError(f"craft {c.name}: fly: needs orbits: (the orbit data it flies); without them give at (and velocity)")
    known = [*own, *data_names, *(["Sun"] if p.sun.at is not None else [])]
    worlds = [b.name for b in p.bodies]
    for ph in p.phenomena:
        if ph.kind in ("black-hole", "wormhole") and p.sky is False:
            raise ValueError(f"phenomena {ph.name}: a {ph.kind} bends the sky: the scene needs one (leave out sky: false)")
        if ph.kind == "aurora" and ph.world not in worlds:
            raise ValueError(f"phenomena {ph.name}: world: {ph.world} is not a world of bodies:{did_you_mean(str(ph.world), worlds)}")
        if ph.kind == "asteroids" and ph.around is not None and ph.around not in worlds:
            raise ValueError(f"phenomena {ph.name}: around: {ph.around} is not a world of bodies:{did_you_mean(ph.around, worlds)}")
        if ph.kind == "comet" and ph.body is not None and (not orbit or ph.body not in data_names):
            raise ValueError(f"phenomena {ph.name}: body: {ph.body} must be a body of orbits:{did_you_mean(ph.body, data_names)}")
    bars = False
    moves = p.camera
    if not moves:
        raise ValueError("camera: give at least one move, e.g. [{move: arc, subject: " + (known[0] if known else "Saturn") + "}]")
    starts: list[Any] = []
    for k, m in enumerate(moves):
        where = f"camera[{k + 1}] ({m.move})"
        for key, name in m.named():
            if name not in known:
                raise ValueError(f"{where}.{key}: no thing named {name}{did_you_mean(name, known)} (names: {', '.join(known) or 'none: give bodies, craft or phenomena'})")
        if m.subject is None and not m.air and m.move not in ("reveal", "zoom", "look"):
            raise ValueError(f"{where}: give subject: what the move looks at (one of {', '.join(known)})")
        if m.over is None and len(moves) > 1:
            raise ValueError(f"{where}: with several moves each gives over: [start, end] (seconds or 'bar N'), so the camera knows when it takes over")
        if m.over is not None:
            times = [scene_time(v, f"{where}.over") for v in m.over]
            bars = bars or any(uses_bars(t) for t in times)
            starts.append(times[0])
        if uses_bars(m.options().get("at")) or uses_bars(m.options().get("light")):
            bars = True
    plain = [s for s in starts if not uses_bars(s)]
    if plain != sorted(plain):
        raise ValueError("camera: give the moves in time order (each over: starts after the one before)")
    for k in range(1, len(moves)):
        a, b = moves[k - 1].over, moves[k].over
        if a and b:
            end, start = scene_time(a[1], "over"), scene_time(b[0], "over")
            if not uses_bars(end) and not uses_bars(start) and start < end - 1e-9:  # type: ignore[operator]
                raise ValueError(f"camera[{k + 1}] ({moves[k].move}) starts at {start:g} s, before camera[{k}] ends ({end:g} s): moves do not overlap")
    for ph in p.phenomena:
        bars = bars or any(uses_bars(scene_time(v, "over")) for v in (ph.over or []))
    if bars and not p.music_data:
        raise ValueError("times in bars ('bar 9') need the score on the page: add music_data: true")
    things = {**{c.name: "craft" for c in p.craft}, **{ph.name: ph.kind for ph in p.phenomena}, **{b.name: "world" for b in p.bodies}}
    for r in p.music:
        if not p.music_data:
            raise ValueError("music: reactions need the music on the page: add music_data: true (or {tracks: [kick, hook]})")
        tracks = getattr(p.music_data, "tracks", None)
        if r.track != "level" and tracks and r.track not in tracks:
            raise ValueError(f"music: {r.track} is not among music_data.tracks{did_you_mean(r.track, tracks)} ({', '.join(tracks)})")
        target = r.target
        kind = "sun" if target.lower() == "sun" else "sky" if target.lower() == "sky" else things.get(target)
        if kind is None:
            raise ValueError(f"music: {r.action}: {target}: no such thing{did_you_mean(target, ['Sun', 'sky', *things])} (the Sun, the sky, or a craft or phenomenon by name)")
        if kind not in REACTS_ON:
            raise ValueError(f"music: {r.action}: {target} is a {kind}: what the music may change is the Sun's glare, the sky, a black hole's disc, "
                             "a warp's intensity, or a craft's lights, throttle or rcs (worlds reflect the sun: they do not pulse; the camera never follows the beat)")
        if r.as_ is not None and kind != "craft":
            raise ValueError(f"music: as: {r.as_} is for a craft, and {target} is not one")
    if p.title is not None:
        p.title.card_options("title")
    if p.end_card is not None:
        p.end_card.card_options("end")
    if p.script is not None and Path(p.script).suffix.lower() not in (".js", ".mjs"):
        raise ValueError(f"script: expected a .js or .mjs file, got {p.script}")
    check_orbital_air(p, known, bars)





def scene_flights(project: Any, scene_id: str, params: Any, fps: int, frames: int, music: dict[str, Any] | None) -> dict[str, Any]:
    """A surface scene's flights for the page (``ctx.flight``), cached as a web scene's ``flight_data`` (Step 385: the key
    holds the flights, the ground, the frames, the code); a fault (a path into a mountain) is said with the scene's name."""
    try:
        return web_scene_flights(project, params.flights.data(params.world), fps, frames, frames - SPARE_FRAMES, music=music, orbits=None)
    except VidgenError as error:
        raise VidgenError(f"space scene '{scene_id}': {error}") from None


def page_source(params: Any, scene_id: str) -> str:
    """The page of a ``space`` scene: a surface scene's (``world:``) or an orbital one's."""
    return surface_page_source(params, scene_id) if params.world is not None else orbital_page_source(params, scene_id)


def written_out(params: Any, scene_id: str, script: str, seconds: float | None) -> tuple[str, dict[str, Any]]:
    """A space scene as a ``web`` scene to go on in code (``vidgen space-page``): the page's source, headed as
    yours now, and the ``web`` scene's params (``script``, ``data`` with the scene's length, ``orbit_data``,
    ``music_data``)."""
    source = page_source(params, scene_id)
    rest = source.split("\n", 2)[2]   # the first two lines say vidgen writes it
    head = (f"// Written out by `vidgen space-page` from the space scene \"{scene_id}\" (DESIGN.md §122.12): the script of a web scene now,\n"
            "// yours to edit. S holds every object by name; load(ctx) builds them, S.step(t) sets them to time t, frame(t) draws.")
    data = dict(params.data)
    if seconds is not None:
        data["scene_seconds"] = round(seconds, 6)
    web: dict[str, Any] = {"script": script, **({"data": data} if data else {})}
    if params.orbits is not None:
        web["orbit_data"] = params.orbits.model_dump(mode="json", exclude_unset=True, by_alias=True)
    if params.world is not None and params.flights is not None:
        web["flight_data"] = params.flights.data(params.world).model_dump(mode="json", exclude_unset=True, by_alias=True)
    if params.music_data:
        web["music_data"] = params.music_data if params.music_data is True else params.music_data.model_dump(mode="json", exclude_unset=True)
    return head + "\n" + rest, web


__all__ = ["PAGE_FOLDER", "Space", "check_scene", "page_source", "scene_flights", "written_out"]

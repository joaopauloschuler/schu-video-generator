"""The checks across a ``space`` scene's sections for the pictures of Phase AO (DESIGN.md §123.14): a
surface scene (``world:``) as a whole, and what an orbital scene gains (giant hulls, planes, the
moves beside a ship, effects, flashes, match cuts, a warp across a cut). Each fault is a ValueError
naming the section, the thing and what is allowed, with did-you-mean. Imports only ``vidgen.api``
and its siblings."""

from pathlib import Path
from typing import Any

from vidgen.api import *

from .space_air_params import MIN_STANDOFF, NEEDS, Ramp, air, air_move_names, hull_point, ship_move_names
from .space_params import length, scene_time, uses_bars

#: What the music may change in a surface scene (DESIGN.md §123.14).
SURFACE_REACTIONS = ("lightning", "lava")
#: Words of an orbital scene a surface scene refuses, and where each one's job is done there.
ORBITAL_ONLY = {"orbits": "a surface scene's frame is the world's place (world.at); orbits belong to an orbital scene",
                "scale": "a surface scene is true to scale in metres",
                "bodies": "the world is world.planet (seen whole from high up as the globe)",
                "phenomena": "phenomena (black holes, warps, auroras) belong to an orbital scene",
                "light": "the light of a surface scene is the air's: world.exposure and world.ev",
                "sun": "the sun of a surface scene is world.sun: [elevation, azimuth] or {date, utc}"}
#: Words of a craft in an orbital scene a craft in a surface scene does not take.
ORBITAL_CRAFT = ("at", "velocity", "attitude", "target", "fleet", "spacing", "marker", "rcs")


def _times_in_order(moves: list[Any]) -> bool:
    """The camera's moves: each with over when there are several, in order, not overlapping (as an orbital scene's). Returns whether any time is in bars."""
    bars, starts = False, []
    for k, m in enumerate(moves):
        if m.over is None and len(moves) > 1:
            raise ValueError(f"camera[{k + 1}] ({m.move}): with several moves each gives over: [start, end] (seconds or 'bar N'), so the camera knows when it takes over")
        if m.over is not None:
            times = [scene_time(v, f"camera[{k + 1}] ({m.move}).over") for v in m.over]
            bars = bars or any(uses_bars(t) for t in times)
            starts.append(times[0])
    plain = [s for s in starts if not uses_bars(s)]
    if plain != sorted(plain):
        raise ValueError("camera: give the moves in time order (each over: starts after the one before)")
    for k in range(1, len(moves)):
        a, b = moves[k - 1].over, moves[k].over
        if a and b:
            end, start = scene_time(a[1], "over"), scene_time(b[0], "over")
            if not uses_bars(end) and not uses_bars(start) and start < end - 1e-9:  # type: ignore[operator]
                raise ValueError(f"camera[{k + 1}] ({moves[k].move}) starts at {start:g} s, before camera[{k}] ends ({end:g} s): moves do not overlap")
    return bars


def _metres(value: Any, where: str) -> float | None:
    """A length given as metres or text with a unit; None for anything else ({radii: 4}, a pair)."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    return length(value, where)


def _flash_bars(p: Any) -> bool:
    if p.flash and p.finish is False:
        raise ValueError("flash: is drawn by the finish (three-finish's flash): leave out finish: false")
    return any(uses_bars(scene_time(f.at, "flash.at")) for f in p.flash)


def _cards_and_script(p: Any) -> None:
    if p.title is not None:
        p.title.card_options("title")
    if p.end_card is not None:
        p.end_card.card_options("end")
    if p.script is not None and Path(p.script).suffix.lower() not in (".js", ".mjs"):
        raise ValueError(f"script: expected a .js or .mjs file, got {p.script}")


def check_orbital_air(p: Any, known: list[str], bars: bool) -> None:
    """What an orbital scene gains in Phase AO: hulls and the moves beside them, planes and kit-built craft,
    effects (exhaust only), flashes, match cuts, a warp across a cut, reactions that drive a hull's lights."""
    hulls = {c.name: c for c in p.craft if c.maker == "hull"}
    for c in p.craft:
        if c.effects is not None:
            groups = c.effects_spec().groups()
            beyond = [g for g in groups if g != "exhaust"]
            if beyond:
                raise ValueError(f"craft {c.name}: effects {', '.join(beyond)} follow a flight through air: give them in a surface scene (world: and flights:); "
                                 "an orbital scene's craft takes effects: {exhaust: true}")
            if c.maker == "hull":
                raise ValueError(f"craft {c.name}: a hull's bells fire by throttle (and dress.engines); effects are for craft and planes")
        if c.maker == "plane" and c.fleet is not None:
            raise ValueError(f"craft {c.name}: a fleet of planes is not reached from YAML")
    ships = list(hulls)
    for k, m in enumerate(p.camera):
        where = f"camera[{k + 1}] ({m.move})"
        if m.move in air_move_names():
            raise ValueError(f"{where}: {m.move} is a move in the air: it needs a surface scene (world: with land, sea or clouds; flights:)")
        o = m.options()
        if m.ship:
            if not ships:
                raise ValueError(f"{where}: a move beside a giant ship needs a hull among craft: ([{{name: Carrier, hull: carrier, ...}}])")
            name = o.get("ship")
            if name is None and len(ships) > 1:
                raise ValueError(f"{where}: give ship: which hull ({', '.join(ships)})")
            if name is not None and name not in hulls:
                raise ValueError(f"{where}.ship: no hull named {name}{did_you_mean(str(name), ships)} (hulls: {', '.join(ships)})")
            if hulls[name or ships[0]].fleet:
                raise ValueError(f"{where}: {name or ships[0]} is a fleet; the moves beside a ship take one hull")
            for key in ("standoff", "close"):
                metres = _metres(o.get(key), f"{where}.{key}")
                if metres is not None and metres < MIN_STANDOFF:
                    raise ValueError(f"{where}.{key}: {metres:g} m is closer to the hull than {MIN_STANDOFF:g} m (the view's near plane beside a hull is 4 m, "
                                     "and that close the plates read as a model): give a larger stand-off")
            if m.move == "into-bay" and isinstance(o.get("hangar"), str):
                hull_point(o["hangar"], f"{where}.hangar")
            if m.move == "hull-reveal" and o.get("mode") == "limb" and o.get("behind") is None:
                raise ValueError(f"{where}: mode limb needs behind: the world the ship comes out from behind")
        elif m.subject in hulls:
            hull = hulls[m.subject]
            for key in ("distance", "closest"):
                metres = _metres(o.get(key), f"{where}.{key}")
                if metres is not None and metres < hull.hull_length() / 2:
                    raise ValueError(f"{where}.{key}: {metres:g} m from the middle of {m.subject} is inside the hull ({hull.hull_length():g} m long or more): "
                                     f"give {{radii: 2}} or more, or a move beside the ship (hull-pass, into-bay)")
        if m.match is not None:
            if k == 0:
                raise ValueError(f"{where}: match matches the disc the move before shows: the first move has none")
            if m.subject is None:
                raise ValueError(f"{where}: match places this move's subject as {m.match}'s disc was: give subject")
    for c in hulls.values():
        ref = c.scale_ref or {}
        if ref.get("escort") and not any(m.move == "hull-reveal" for m in p.camera):
            raise ValueError(f"craft {c.name}: scale_ref.escort places the craft where a hull-reveal move says: the scene has none")
        bars = bars or any(uses_bars(scene_time(v, "over")) for v in (ref.get("into") or {}).get("over", []))
    for ph in p.phenomena:
        if ph.cut is not None:
            bars = bars or uses_bars(scene_time(ph.cut["at"], "cut.at"))
    bars = _flash_bars(p) or bars
    for r in p.music:
        if r.as_ in ("boost", "pulse"):
            craft = next((c for c in p.craft if c.name == r.target), None)
            if craft is None or craft.effects is None:
                raise ValueError(f"music: as: {r.as_} drives a craft's effects: give {r.target} effects: {{exhaust: true}}")
        if r.as_ == "rcs" and r.target in hulls:
            raise ValueError(f"music: as: rcs: a hull has no thrusters to puff; give as: lights or throttle")
    if bars and not p.music_data:
        raise ValueError("times in bars ('bar 9') need the score on the page: add music_data: true")


def _flight_of(name: Any, flights: list[str], craft: dict[str, Any], where: str) -> str:
    """A move's ``flight``: a flight's name, or a craft's (its flight); the only flight when none is named."""
    if name is None:
        if len(flights) == 1:
            return flights[0]
        raise ValueError(f"{where}: give flight: which flight ({', '.join(flights)})")
    if name in flights:
        return str(name)
    if name in craft and craft[name].fly in flights:
        return str(craft[name].fly)
    raise ValueError(f"{where}.flight: no flight named {name}{did_you_mean(str(name), [*flights, *craft])} (flights: {', '.join(flights)})")


def check_surface(p: Any) -> None:
    """A surface scene (``world:``) as a whole: no orbital words; its craft fly its flights; each move has what it
    needs (a flight, ground or water, a deck, land for a peak); names with did-you-mean; times in bars only with
    the score; what the music may change (lightning, the lava's glow, a craft's lights, throttle, boost)."""
    w = p.world
    for key, why in ORBITAL_ONLY.items():
        value = getattr(p, key)
        if key in p.model_fields_set and value not in (None, [], False):
            raise ValueError(f"{key}: is an orbital scene's; this scene has world: (a surface scene): {why}")
    names = [c.name for c in p.craft]
    twice = sorted({n for n in names if names.count(n) > 1})
    if twice:
        raise ValueError(f"the name {twice[0]} is given to two craft")
    flights = p.flights.names if p.flights is not None else []
    craft = {c.name: c for c in p.craft}
    for c in p.craft:
        where = f"craft {c.name}"
        if c.maker == "hull":
            raise ValueError(f"{where}: a giant hull belongs to an orbital scene (no world:); a surface scene's craft is a plane, a craft of the kit or of its parts")
        for key in ORBITAL_CRAFT:
            if key in c.model_fields_set:
                raise ValueError(f"{where}: {key} is an orbital scene's; in a surface scene a craft flies a flight: fly: NAME (of flights:)")
        if "burn" in c.model_fields_set:
            raise ValueError(f"{where}: burn is an orbital scene's (the orbit data's burns)")
        if c.fly is None:
            raise ValueError(f"{where}: give fly: the flight it flies (of flights:{' ' + ', '.join(flights) if flights else ' none yet: add flights:'})")
        if c.fly not in flights:
            raise ValueError(f"{where}.fly: no flight named {c.fly}{did_you_mean(c.fly, flights)} (flights: {', '.join(flights) or 'none: add flights:'})")
    bars = _times_in_order(p.camera) if p.camera else False
    if not p.camera:
        raise ValueError("camera: give at least one move, e.g. [{move: skim, heading: 280, clearance: 20}] or [{move: chase, flight: Plane}]")
    land, sea, clouds = w.land_spec, w.sea_spec, w.cloud_spec
    decks = clouds.deck_names() if clouds is not None else []
    for k, m in enumerate(p.camera):
        where = f"camera[{k + 1}] ({m.move})"
        if m.move not in air_move_names():
            kind = "beside a giant ship (an orbital scene with a hull)" if m.move in ship_move_names() else "of an orbital scene"
            raise ValueError(f"{where}: {m.move} is a move {kind}; a surface scene's moves are {', '.join(air_move_names())}")
        o, need = m.options(), NEEDS.get(m.move)
        if m.continues and (k == 0 or p.camera[k - 1].move not in ("descend", "ascend")):
            raise ValueError(f"{where}: continues follows a descend or an ascend (the move before ends moving, level: the skim takes over there)")
        if m.subject is not None:
            raise ValueError(f"{where}: a move in the air looks at a flight (flight: NAME), a peak (around:) or a deck (deck:), not a subject")
        if need == "surface" and land is None and sea is None:
            raise ValueError(f"{where}: a skim flies low over ground or water: give world.sea or world.land")
        if need == "flight":
            if not flights:
                raise ValueError(f"{where}: follows a plane on a flight: add flights: [{{name: Plane, start: ..., legs: [...]}}] (and a craft flying it)")
            _flight_of(o.get("flight"), flights, craft, where)
            if isinstance(o.get("craft"), str) and o["craft"] not in craft:
                raise ValueError(f"{where}.craft: no craft named {o['craft']}{did_you_mean(o['craft'], list(craft))}")
            if m.move == "wing" and isinstance(o.get("view"), str) and o["view"] not in air()["wing_views"]:
                raise ValueError(f"{where}.view: no view '{o['view']}'{did_you_mean(o['view'], air()['wing_views'])} (views: {', '.join(air()['wing_views'])})")
        if need == "decks":
            deck = o.get("deck", 0)
            if isinstance(deck, dict):
                pass
            elif clouds is None:
                raise ValueError(f"{where}: goes through a cloud deck: give world.clouds, or deck: {{base, top}} in metres")
            elif isinstance(deck, int) and not isinstance(deck, bool):
                if not 0 <= deck < len(decks):
                    raise ValueError(f"{where}.deck: {deck}: the clouds have {len(decks)} deck(s): " + ", ".join(f"{i} ({d})" for i, d in enumerate(decks)))
            elif isinstance(deck, str):
                if deck not in decks:
                    raise ValueError(f"{where}.deck: no deck named {deck}{did_you_mean(deck, decks)} (decks: {', '.join(decks)})")
            else:
                raise ValueError(f"{where}.deck: a deck's index, its name or {{base, top}}, got {deck!r}")
        if need == "peak":
            around = o.get("around", [0, 0])
            if isinstance(around, dict) and "tower" in around:
                if clouds is None or not clouds.has_towers:
                    raise ValueError(f"{where}.around: tower needs cloud towers (world.clouds: {{sky: towers}} or towers: 4)")
            elif land is None:
                raise ValueError(f"{where}: circles a peak of the ground: give world.land (or around: {{tower: 0}} with cloud towers)")
        for key in ("at",) if m.move == "fly-past" else ():
            if key in o:
                bars = bars or uses_bars(scene_time(o[key], f"{where}.{key}"))
    if p.flights is not None:
        try:
            data = p.flights.data(w)
        except VidgenError as error:
            raise ValueError(str(error)) from None
        bars = bars or data.uses_bars
        unused = [f for f in flights if f not in {c.fly for c in p.craft}]
        if unused and not any(NEEDS.get(m.move) == "flight" for m in p.camera):
            raise ValueError(f"flights: {', '.join(unused)} is flown by no craft and followed by no camera move")
    lightning = clouds.lightning if clouds is not None else None
    if lightning not in (None, False, True):
        bars = bars or lightning.uses_bars
        if lightning.track is not None and not p.music_data:
            raise ValueError("world.clouds.lightning.track: strikes on a track's hits need the music on the page: add music_data: true")
    for c in p.craft:
        for key in ("gear", "bay", "cabin"):
            value = getattr(c, key)
            if isinstance(value, dict):
                bars = bars or any(uses_bars(scene_time(v, "over")) for v in Ramp.model_validate(value).over)
    bars = _flash_bars(p) or bars
    if p.flash and "finish" not in p.model_fields_set:
        raise ValueError("flash: is drawn by the finish, and a surface scene is drawn straight to the canvas unless it gives one: add finish: {} (or finish options)")
    for r in p.music:
        if not p.music_data:
            raise ValueError("music: reactions need the music on the page: add music_data: true (or {tracks: [kick, hook]})")
        tracks = getattr(p.music_data, "tracks", None)
        if r.track != "level" and tracks and r.track not in tracks:
            raise ValueError(f"music: {r.track} is not among music_data.tracks{did_you_mean(r.track, tracks)} ({', '.join(tracks)})")
        target = r.target
        if target.lower() == "lightning":
            if clouds is None:
                raise ValueError("music: lightning needs clouds to flash in: give world.clouds")
            if r.action != "pulse":
                raise ValueError("music: lightning strikes on each hit of the track: write pulse: lightning")
        elif target.lower() == "lava":
            if land is None or not land.volcanic:
                raise ValueError("music: lava glows on volcanic ground: give world.land: volcanic (or land with volcanoes)")
        elif target in craft:
            if r.as_ in ("boost", "pulse") and craft[target].effects is None:
                raise ValueError(f"music: as: {r.as_} drives {target}'s effects: give it effects: {{exhaust: true}} (or reentry)")
            if r.as_ == "rcs":
                raise ValueError("music: as: rcs is a spacecraft's thrusters; a craft in the air takes lights, throttle, boost or pulse")
        else:
            raise ValueError(f"music: {r.action}: {target}: no such thing{did_you_mean(target, [*SURFACE_REACTIONS, *craft])} "
                             "(lightning, lava, or a craft by name; the camera never follows the beat)")
        if r.as_ is not None and target not in craft:
            raise ValueError(f"music: as: {r.as_} is for a craft, and {target} is not one")
    if bars and not p.music_data:
        raise ValueError("times in bars ('bar 9') need the score on the page: add music_data: true")
    _cards_and_script(p)


__all__ = ["ORBITAL_CRAFT", "ORBITAL_ONLY", "SURFACE_REACTIONS", "check_orbital_air", "check_surface"]

"""Weather on an iso place (DESIGN.md §105.4): the part of a ``stage`` that mirrors the place's
lights in its puddles at night, lays the stage's ``fog`` over it in bands by depth, and sways its
trees, bushes, flowers, plants, scarecrows and balloons in the stage's ``wind``. Written against
``vidgen.api`` only; :class:`IsoWeather` is a part of :class:`~vidgen.scenes.stage.Stage`.

All three are opt-in: reflections come with puddles (rain with ``puddles: true``), the fog with
``fog``, the swaying with a ``wind`` that blows (the stage's or a ``wind`` action's). A swaying
object is left out of the place's pictures (:attr:`IsoScenery.apart`, it still keeps the rain
off) and drawn as an :class:`IsoSwayer` in the draw order: after the pictures of the objects
behind it and after the bodies it stands in front of, with a *cover* picture of what stands in
front of it.
"""

from dataclasses import replace
from typing import Any

from vidgen.api import *

from .stage_iso import IsoObject, _moving_block


class IsoWeather:
    """The weather part of a ``stage`` on an iso place (DESIGN.md §105.4)."""

    # ----- wind: swaying objects --------------------------------------------------------------------

    def _iso_windy(self) -> bool:
        """Whether a wind ever blows in the scene (the stage's or a ``wind`` action's)."""
        return wind_level(self.params.wind) != 0.0 or any(use.level() for use in self.action_uses("wind"))

    def _iso_swaying(self, place: Any, keep: set[str]) -> dict[str, str]:
        """The objects of the place that sway in the scene's wind: name -> kind
        (:data:`ISO_SWAYS`, outdoors, not in a draft); not those in ``keep`` (the scene changes
        or drives them: they stay in the pictures)."""
        if self.is_draft or self.params.iso.place == "indoor" or not self._iso_windy():
            return {}
        return {item.name: item.kind for item in place.objects if item.kind in ISO_SWAYS and item.name not in keep}

    def _iso_still_looks(self, looks: dict[str, Any], swaying: dict[str, str]) -> None:
        """A swaying balloon bunch is drawn whole, its balloons too (not swung by the stage as a
        working object, §103): its look is not ``moving``."""
        for name in swaying:
            if looks[name].moving:
                looks[name] = replace(looks[name], moving=False)
                self._iso_moving.discard(name)

    def _iso_make_swayers(self, swaying: dict[str, str], density: float) -> list[Mobject]:
        """An :class:`IsoSwayer` for each swaying object (:attr:`iso_swayers`, with its cover
        picture: what stands in front of it), each one of :attr:`story_things`; their mobjects."""
        #: the swaying objects by name: (swayer, cover picture or ``None``)
        self.iso_swayers: dict[str, tuple[IsoSwayer, Mobject | None]] = {}
        if not swaying:
            return []
        scenery, view = self.iso_scenery, self.iso_view
        left, _, right, _ = scenery.bounds
        scale = view.unit * config.pixel_height / self.frame_height * density
        out: list[Mobject] = []
        for name, kind in swaying.items():
            k = scenery.index[name]
            piece = scenery.pieces[k]
            box = piece.box
            u = iso_point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2, box.z0)[0]
            share = (u - left) / max(right - left, 1e-9)
            swayer = IsoSwayer(name, kind, piece.shapes_in(scenery.states[k]), box, view, scale=scale, density=self._iso_density,
                               frame_width=self.frame_width, force=lambda now, share=share: self._iso_wind_force(now, share),
                               blowing=self._iso_wind_blowing, outline=self.drawing.outline_factor, phase=wind_phase(name))
            mark_lit(swayer)
            picture = scenery.front(box)
            cover = None
            if picture is not None:   # it follows the changes of what it shows (_iso_follow_change)
                cover = IsoObject()
                cover.name, cover.iso_box = f"iso_cover_{name}", box
                cover.add(self._iso_tiles(picture, cover.name))
            self.iso_swayers[name] = (swayer, cover)
            self.story_things.append(swayer)
            out += [swayer, *([cover] if cover is not None else [])]
        return out

    def _iso_wind_force(self, now: float, share: float) -> float:
        """The stage's wind force at scene time ``now`` where a gust reaches ``share`` (0..1)
        across the place late (0: calm, or no wind made yet)."""
        blowing = getattr(self, "blowing", None)
        if blowing is None:
            return 0.0
        return blowing.wind.force(now, blowing.wind.delay(share, now))

    def _iso_wind_blowing(self, start: float, end: float) -> bool:
        blowing = getattr(self, "blowing", None)
        return blowing is not None and blowing.wind.blowing(start, end)

    def iso_covers(self) -> list[Mobject]:
        """The pictures of what stands in front of a working object (§103) or a swaying one: they
        follow the place's changes (:meth:`_iso_follow_change`)."""
        found = [cover for _, _, cover in getattr(self, "_iso_gadget_places", [])]
        found += [cover for _, cover in getattr(self, "iso_swayers", {}).values()]
        return [cover for cover in found if cover is not None]

    def _iso_place_swayers(self) -> bool:
        """Keep each swaying object (with its cover) in the draw order: after the place's
        pictures and the layers of the objects drawn before it, and after every body it stands in
        front of (with that body's front picture); in their own draw order. Whether anything
        moved."""
        swayers = getattr(self, "iso_swayers", {})
        if not swayers:
            return False
        scenery = self.iso_scenery
        groups = sorted((scenery.index[name], [m for m in (swayer, cover) if m is not None and m in self.mobjects])
                        for name, (swayer, cover) in swayers.items())
        groups = [(k, group) for k, group in groups if group]
        base = next((j for j, m in enumerate(self.mobjects) if isinstance(m, IsoTiles) and m.name == "iso_place"), None)
        if not groups or base is None:
            return False
        before = [id(m) for m in self.mobjects]
        taken = {id(m) for _, group in groups for m in group}
        self.mobjects[:] = [m for m in self.mobjects if id(m) not in taken]
        bodies = [(name, body) for name, body in self._iso_bodies().items() if body in self.mobjects]
        overs = {name: scenery.over(self._iso_body(body)) for name, body in bodies}
        holders = [(scenery.index[name], holder) for name, holder in self.iso_objects.items()]
        floor = 0
        for k, group in groups:
            at = 1 + max([self.mobjects.index(m) for m in self.mobjects if isinstance(m, IsoTiles) and m.name == "iso_place"]
                         + [self.mobjects.index(holder) for j, holder in holders if j < k and holder in self.mobjects])
            for name, body in bodies:
                if k in overs[name]:
                    front = self._iso_fronts.get(name, (None, None))[1]
                    block = [*_moving_block(self, body), *([front] if front is not None and front in self.mobjects else [])]
                    at = max(at, 1 + max(self.mobjects.index(m) for m in block))
            at = max(at, floor)
            self.mobjects[at:at] = group
            floor = at + len(group)
        return [id(m) for m in self.mobjects] != before

    # ----- fog ------------------------------------------------------------------------------------------

    def _iso_fog(self, setting: Any) -> IsoFog:
        """The stage's ``fog`` over the iso place (:class:`IsoFog`): its bands' lines from the
        place's back edge to its front, across the place's picture and up to its top."""
        place = self.params.iso.parsed()
        cells = [c + r for r in range(place.rows) for c in range(place.columns) if place.ground(c, r) != VOID]
        back, front = min(cells), max(cells) + 2
        depths = iso_fog_depths(front, back)
        view = self.iso_view
        left, top, right, _ = self.iso_scenery.bounds
        pad = 2.0
        bases = [view.point(depth / 2, depth / 2, 0.0)[1] for depth in depths]
        x0, x1 = (left - pad - view.u0) * view.unit, (right + pad - view.u0) * view.unit
        y1 = -(top - pad - view.v0) * view.unit
        color = resolve_color(setting.color, self.theme) if setting.color is not None else FOG_COLOR
        wind = getattr(self, "particle_wind", None)
        fog = IsoFog(density=setting.density, color=color, depths=depths, bases=bases, left=x0, right=x1, top=y1, unit=view.unit,
                     drift=setting.drift, seed=setting.seed if setting.seed is not None else motion_seed(self.spec.id, "fog"),
                     blown=(lambda now: wind(0.0, now)[0]) if wind is not None else None)
        mark_lit(*fog.bands)
        if fog.moves:
            self._watch_living()
        self._watch_draw_order()
        return fog

    def _iso_sort_fog(self) -> bool:
        """Put each fog band right before the first body (in draw order) standing at its depth or
        nearer, else after the place and its bodies: everything further back is seen through it.
        Whether the draw order changed."""
        fog = getattr(self, "fog", None)
        if fog is None or not any(isinstance(m, IsoTiles) and m.name == "iso_place" for m in self.mobjects):
            return False
        before = [id(m) for m in self.mobjects]
        bands = {id(b) for b in fog.bands}
        self.mobjects[:] = [m for m in self.mobjects if id(m) not in bands]
        bodies = {name: body for name, body in self._iso_bodies().items() if body in self.mobjects}
        depth = {id(body): float(body.iso_feet[0] + body.iso_feet[1]) for body in bodies.values() if getattr(body, "iso_feet", None) is not None}
        place_things = {id(m) for m in [*bodies.values(), *(front for _, front in self._iso_fronts.values() if front is not None),
                                         *getattr(self, "story_things", []), *self.iso_covers(), *self.iso_objects.values()]}
        place_things |= {id(m) for m in self.mobjects if isinstance(m, IsoTiles)}
        end = 1 + max((k for k, m in enumerate(self.mobjects) if id(m) in place_things), default=len(self.mobjects) - 1)
        after = 0
        for band in fog.bands:   # back to front
            at = next((k for k, m in enumerate(self.mobjects) if k >= after and id(m) in depth and depth[id(m)] >= band.iso_depth), None)
            if at is None:
                at = max(end, after)
            else:
                block = _moving_block(self, self.mobjects[at])
                at = min([at, *(self.mobjects.index(m) for m in block if m in self.mobjects)])
                at = max(at, after)
            self.mobjects.insert(at, band)
            end += 1 if at <= end else 0
            after = at + 1
        return [id(m) for m in self.mobjects] != before

    # ----- lights mirrored in puddles -----------------------------------------------------------------

    def _iso_wet(self) -> bool:
        """Whether puddles may lie on the place in the scene (a rain field with ``puddles``)."""
        return any(item.kind == "rain" and item.puddles for item in self.params.particles) or any(use.options.puddles for use in self.action_uses("particles"))

    def _iso_glow_watch(self) -> None:
        """When puddles may lie on the place, keep each object's states from the start
        (:attr:`_iso_glow_log`, added to by :meth:`iso_change`): how lit each light mirrored in a
        puddle is at a scene time."""
        #: each object's states from scene times on: (start, seconds of its fade, state)
        self._iso_glow_log: dict[str, list[tuple[float, float, Any]]] = {}
        if self.is_draft or not self._iso_wet():
            return
        scenery = self.iso_scenery
        for k in range(len(scenery.pieces)):
            piece = scenery.pieces[k]
            if piece.kind:
                self._iso_glow_log[piece.name] = [(0.0, 0.0, scenery.states[k])]

    def iso_glow_changed(self, name: str, start: float, seconds: float, state: Any) -> None:
        """Note that the object ``name`` changes to ``state`` from scene time ``start`` over ``seconds``."""
        log = getattr(self, "_iso_glow_log", {}).get(name)
        if log is not None:
            log.append((float(start), max(float(seconds), 1e-3), state))
            log.sort(key=lambda entry: entry[0])

    def _iso_glow_level(self, name: str, now: float) -> float:
        """How lit the object ``name`` is at scene time ``now`` (0..1), fading with its changes:
        on and there (a light that shines also off, as a tower's neon: there)."""
        key = self._iso_glow_keys.get(name, "on")
        log = self._iso_glow_log.get(name) or [(0.0, 0.0, None)]

        def lit(state: Any) -> float:
            return 1.0 if state is not None and state.shown and (state.on or key == "shown") else 0.0

        level = lit(log[0][2])
        for start, seconds, state in log[1:]:
            if now <= start:
                break
            level += (lit(state) - level) * smooth(min((now - start) / seconds, 1.0))
        return level

    def _iso_glow_busy(self, start: float, end: float) -> bool:
        """Whether the light or a lit object may change between scene times ``start`` and ``end``."""
        light = getattr(self, "light", None)
        if light is not None and light.changing(start, end):
            return True
        return any(s <= end and s + d >= start for log in self._iso_glow_log.values() for s, d, _ in log[1:])

    def _iso_night(self) -> float:
        """How dark the stage's light is now (0 by day .. 1 at night)."""
        light = getattr(self, "light", None)
        return darkness(light.grade if light is not None else self.base_light)

    def iso_reflect(self, puddles: IsoPuddles) -> IsoReflections | None:
        """The place's lights mirrored in ``puddles`` at night (:class:`IsoReflections`), laid
        right over them, one of :attr:`story_things`; ``None`` when no light falls in a puddle."""
        scenery = self.iso_scenery
        lights: list[Any] = []
        owners: list[str] = []
        #: whether a mirrored light shines while its object is ``on`` or whenever it is there
        self._iso_glow_keys: dict[str, str] = {}
        driven = set(getattr(self, "iso_vehicles", {})) | set(getattr(self, "iso_swayers", {}))
        for k in range(len(scenery.pieces)):
            piece = scenery.pieces[k]
            if not piece.kind or piece.name in driven or "#" in piece.name:
                continue
            state = scenery.states[k]
            always = glow_outlines(piece.shapes_in(replace(state, on=False, shown=True)))
            found = always or glow_outlines(piece.shapes_in(replace(state, on=True, shown=True)))
            if found:
                self._iso_glow_keys[piece.name] = "shown" if always else "on"
                lights += found
                owners += [piece.name] * len(found)
        if not lights:
            return None
        reflections = IsoReflections(puddles, lights, owners, self.iso_view, night=self._iso_night, lit=self._iso_glow_level,
                                     busy=self._iso_glow_busy)
        if not reflections.pairs:
            return None
        for drawn in (self.mobjects, self._backdrop):
            at = next((j for j, m in enumerate(drawn) if m is puddles), None)
            if at is not None:
                drawn.insert(at + 1, reflections)
                break
        self.story_things.append(reflections)
        self._watch_living()
        return reflections


__all__ = ["IsoWeather"]

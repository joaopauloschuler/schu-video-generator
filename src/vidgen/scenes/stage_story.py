"""The story effects of a ``stage`` (DESIGN.md §100.6-§100.12): what a cartoon in a lab, a rift
and a flashback needs, written against ``vidgen.api`` only; :class:`StoryStaging` is a part of
:class:`~vidgen.scenes.stage.Stage`.

- Characters: a hologram's flicker, an iridescent skin, afterimages, the ``materialise`` /
  ``dematerialise`` actions, holding hands (``hold_hands`` / ``let_go_hands``), and a shot that
  hides the characters it does not frame (``shot: {kind, of, clear: true}``).
- Light on the characters: a stage's ``fill_light`` and an iridescent visitor's ``glow``.
- The set: an alarm (``alarm: start`` / ``stop``: a dark room under a pulsing red light, a siren),
  the shutters over an iso room's windows (``shutters: close`` / ``open``), a flashback's look
  (``flashback``: faded warm colours and a soft vignette).
"""

from fnmatch import fnmatchcase
from typing import Any

from vidgen.api import *


class FlashbackSetting(SceneParams):
    """A stage's ``flashback:`` as a mapping (DESIGN.md §100.12)."""

    tint: ThemeColor = FLASHBACK_TINT
    """The warm colour the set is graded towards (a theme token or #hex)."""
    strength: float = Field(FLASHBACK_STRENGTH, ge=0.0, le=1.0)
    """How strongly it is graded towards the tint (0-1)."""
    saturation: float = Field(FLASHBACK_SATURATION, ge=0.0, le=1.0)
    """How much of the colours' saturation is kept (0 grey .. 1 all)."""
    vignette: float = Field(VIGNETTE_OPACITY, ge=0.0, le=1.0)
    """How dark the soft frame is in the corners (0: none)."""
    color: ThemeColor = VIGNETTE_COLOR
    """The vignette's colour."""

#: A hologram materialising: a rising shimmer as it begins, a soft chime when it stands whole;
#: dematerialising: a falling swoosh (sound, params each).
MATERIALISE_SOUNDS: tuple[tuple[str, dict[str, float]], ...] = (
    ("riser", {"gain": -9.0, "duration": 1.6, "pitch": 5.0}),
)
MATERIALISE_CHIME: tuple[str, dict[str, float]] = ("chime", {"gain": -12.0, "pitch": 7.0, "duration": 1.4})
DEMATERIALISE_SOUNDS: tuple[tuple[str, dict[str, float]], ...] = (
    ("swoosh", {"gain": -8.0, "duration": 1.2, "pitch": 6.0}),
)
#: Shutters: the slam as they hit the sill (closing), the rattle of them rolling up (opening).
SHUTTER_SLAM: tuple[str, dict[str, float]] = ("slam", {"gain": -1.0})
SHUTTER_ROLL: tuple[str, dict[str, float]] = ("swoosh", {"gain": -9.0, "duration": 1.3, "pitch": -8.0})
#: A kiss: a soft, high chime as the faces meet (sound, params; DESIGN.md §102.15).
KISS_CHIME: tuple[str, dict[str, float]] = ("chime", {"gain": -13.0, "pitch": 9.0, "duration": 1.6})


class _Flicker:
    """A hologram's flicker (DESIGN.md §100.9): its opacity factor ``flicker`` on every frame,
    except while it walks in or out through a door (that fade is its own)."""

    def __init__(self, figure: Any, seed: int) -> None:
        self.figure = figure
        self.seed = seed

    def update(self, now: float) -> None:
        if getattr(self.figure, "passage", None) is not None:
            return
        figure_alpha(self.figure).set("flicker", flicker_level(now, self.seed)).apply()


class StoryStaging:
    """The story effects of a stage (see the module docstring)."""

    # ----- the characters (DESIGN.md §100.9, §100.10) -----------------------------------------------

    def _start_story(self) -> None:
        """After the characters are made and lit: each one's flicker, iridescence and afterimages,
        the characters a ``materialise`` brings hidden until then, the lights of a lab unlit, and
        the scene updater driving it all (none when nothing needs it)."""
        #: what changes characters on every frame (flickers, iridescence, afterimages, held hands)
        self.figure_fx: list[Any] = []
        #: the hands held now: (a, b) -> :class:`HandHold`
        self.hand_holds: dict[tuple[str, str], HandHold] = {}
        #: the characters a shot with ``clear`` hid
        self._shot_hidden: list[str] = []
        #: the alarm's changes: (scene time, on, colour, period)
        self._alarm_changes: list[tuple[float, bool, str, float]] = []
        entries = {entry.name: entry for entry in self.project.config.characters}
        fancy = not self.is_draft
        for name, figure in self.cast.items():
            entry = entries.get(name)
            if entry is None or not fancy:
                continue
            hologram = entry.hologram_look() or entry.echo_look()   # an echo flickers like a hologram (§102.6)
            if hologram is not None and hologram.flicker:
                self.figure_fx.append(_Flicker(figure, motion_seed(self.spec.id, name, "flicker")))
            iridescent = entry.iridescent_look()
            if iridescent is not None:
                self.figure_fx.append(Iridescence(figure, strength=iridescent.strength, seconds=iridescent.seconds))
            after = entry.afterimage_look()
            if after is not None:
                self.figure_fx.append(Afterimages(figure, place=lambda ghost, f=figure: self._place_ghost(ghost, f), remove=self._drop_ghost,
                                                  spacing=after.spacing, life=after.life, opacity=after.opacity))
        for name, figure in self.cast.items():   # a glowing pendant shines at night and pulses (§102.14)
            glowing = [(m, getattr(m, PENDANT_GLOW)) for m in figure.get_family() if getattr(m, PENDANT_GLOW, None)]
            if glowing:
                for member, _ in glowing:
                    unmark_lit(member)
                if fancy:
                    self.figure_fx.append(PendantPulse(figure, glowing))
        for name in self._materialising():
            figure_alpha(self.cast[name]).set("appear", 0.0).apply()
        for thing in getattr(self, "story_things", []):
            if isinstance(thing, (IsoBlinkers, IsoScreens, IsoTraffic, IsoHaze)):
                unmark_lit(thing)   # a lab's lights, a city's screens and pods shine at night too
            elif isinstance(thing, IsoGadgets):
                for piece in thing.glowing:   # a quantum core's glow (§103)
                    unmark_lit(piece)
        if getattr(self, "story_things", []):
            self._watch_living()
        #: the scene updater, kept: Manim removes an updater by identity
        self._story_updater = self._story_step
        if self.figure_fx or self.action_uses("hold_hands"):
            self.add_updater(self._story_updater)

    def _fill_lights(self) -> None:
        """Each character's fill light (DESIGN.md §100.15): the stage's ``fill_light``, or an
        iridescent character's own ``glow`` when that is more; holograms are not graded at all."""
        entries = {entry.name: entry for entry in self.project.config.characters}
        for name, figure in self.cast.items():
            entry = entries.get(name)
            iridescent = entry.iridescent_look() if entry is not None else None
            share = max(float(self.params.fill_light), iridescent.glow if iridescent is not None else 0.0)
            if share > 0.0 and not (is_hologram(figure) or is_echo(figure)):
                mark_light_lift(figure, share)

    def _story_step(self, dt: float) -> None:
        """Scene updater: every character effect for the scene time now (after the animations,
        so a held hand stays held while its owner walks)."""
        now = float(self.renderer.time)
        for fx in self.figure_fx:
            fx.update(now)

    def _materialising(self) -> list[str]:
        """The characters whose first ``materialise`` / ``dematerialise`` is a materialise: they
        wait unseen at their spots until then."""
        first: dict[str, str] = {}
        uses = self._actions.uses if self._actions is not None else []
        for use in uses:
            if use.kind.name not in ("materialise", "dematerialise"):
                continue
            for pattern in use.action.config.targets():
                for name in self.cast:
                    if fnmatchcase(name, pattern):
                        first.setdefault(name, use.kind.name)
        return [name for name, kind in first.items() if kind == "materialise"]

    def materialise(self, figure: Any, *, out: bool, run_time: float) -> Animation:
        """The ``materialise`` (``out``: ``dematerialise``) animation of ``figure`` over
        ``run_time`` seconds, with its sounds (foley)."""
        start = float(self.renderer.time)
        if self._foley_on():
            for sound, params in (DEMATERIALISE_SOUNDS if out else MATERIALISE_SOUNDS):
                self.sfx(sound, start, **params)
            if not out:
                self.sfx(MATERIALISE_CHIME[0], start + run_time * 0.85, **MATERIALISE_CHIME[1])
        return Materialise(figure, out=out, seed=motion_seed(self.spec.id, figure.name, "materialise"),
                           clock=lambda: self.renderer.time, run_time=run_time)

    def _place_ghost(self, ghost: Any, figure: Any) -> None:
        """Put an afterimage right behind ``figure`` (not while it is off the scene), in the
        scene and in what the animation playing now redraws on every frame."""
        if figure not in self.mobjects:
            return
        self.mobjects.insert(self.mobjects.index(figure), ghost)
        moving = getattr(self, "moving_mobjects", None)
        if moving:
            family = {id(m) for m in figure.get_family()}
            at = next((k for k, m in enumerate(moving) if id(m) in family), None)
            if at is not None:
                moving.insert(at, ghost)

    def _drop_ghost(self, ghost: Any) -> None:
        for drawn in (self.mobjects, getattr(self, "moving_mobjects", None) or []):
            if ghost in drawn:
                drawn.remove(ghost)

    def hold_hands(self, a: str, b: str) -> None:
        """``a`` and ``b`` hold hands from now on (DESIGN.md §100.10)."""
        key = (a, b) if a < b else (b, a)
        if key in self.hand_holds:
            return
        hold = HandHold(self.cast[key[0]], self.cast[key[1]], float(self.renderer.time))
        self.hand_holds[key] = hold
        self.cast[key[0]].hand_in_hand, self.cast[key[1]].hand_in_hand = key[1], key[0]   # the layout dump: lint lets them stand close
        self.figure_fx.append(hold)
        if not any(f is self._story_updater for f in self.updaters):
            self.add_updater(self._story_updater)

    def kiss(self, a: str, b: str, *, seconds: float, hearts: bool, color: str) -> list[Animation]:
        """``a`` and ``b`` kiss over ``seconds`` from now (DESIGN.md §102.15): both turn to each
        other, lean in until their faces touch, close their eyes and lean back at the end; a small
        burst of hearts and sparkles rises as their faces meet (``hearts``), with a soft chime
        (foley)."""
        plan = KissPlan(self.cast[a], self.cast[b], seconds)
        anims: list[Animation] = [KissMotion(self.cast[a], plan, run_time=seconds), KissMotion(self.cast[b], plan, run_time=seconds)]
        start = float(self.renderer.time)
        if hearts:
            burst = KissBurst(plan, contact_time(seconds), color=color, seed=motion_seed(self.spec.id, a, b, "kiss"), run_time=seconds)
            top = max((m.z_index for m in self.get_mobject_family_members()), default=0)
            burst.mobject.set_z_index(top + 1)
            unmark_lit(burst.mobject)
            anims.append(burst)
        if self._foley_on():
            self.sfx(KISS_CHIME[0], start + contact_time(seconds), **KISS_CHIME[1])
        return anims

    def let_go_hands(self, names: list[str]) -> list[tuple[Any, str]]:
        """Every hold of a character of ``names`` ends now: the (character, hand) that held."""
        freed: list[tuple[Any, str]] = []
        for key in [k for k in self.hand_holds if k[0] in names or k[1] in names]:
            hold = self.hand_holds.pop(key)
            self.figure_fx.remove(hold)
            freed += hold.arms()
            for name in key:
                self.cast[name].hand_in_hand = None
        return freed

    def shot_clear(self, keep: list[str] | None) -> None:
        """A shot with ``clear`` (DESIGN.md §100.6): hide every character but ``keep``; ``None``:
        show the ones hidden again."""
        for name in self._shot_hidden:
            figure_alpha(self.cast[name]).set("shot", 1.0).apply()
            self.cast[name].hidden_by_shot = False
        self._shot_hidden = []
        if keep is None:
            return
        for name, figure in self.cast.items():
            if name not in keep:
                figure_alpha(figure).set("shot", 0.0).apply()
                figure.hidden_by_shot = True   # the layout dump: lint leaves it out
                self._shot_hidden.append(name)

    # ----- the set (DESIGN.md §100.7, §100.12) -----------------------------------------------------

    def alarm(self, on: bool, time: float, color: str, period: float) -> None:
        """The alarm starts (or stops) at scene ``time``: the light pulses in ``color`` every
        ``period`` seconds over a dark room (the siren is the ``alarm`` bed, :meth:`alarm_beds`)."""
        self._alarm_changes.append((float(time), bool(on), color, float(period)))
        self._lit().alarms = alarm_spans(self._alarm_changes)
        self._watch_light()

    def alarm_beds(self, end: float) -> list[dict[str, Any]]:
        """The ``alarm`` bed while each alarm runs in a scene of ``end`` seconds (foley on)."""
        if not getattr(self, "_alarm_changes", None) or not self._foley_on():
            return []
        spans = alarm_spans(self._alarm_changes)
        return [{"bed": "alarm", "start": round(s.start, 6), "end": round(min(end, s.end if s.end is not None else end), 6)}
                for s in spans if s.start < end]

    def move_shutters(self, close: bool, time: float) -> None:
        """The room's shutters close (or open) from scene ``time``, with a slam (or a roll)."""
        shutters = getattr(self, "iso_shutters", None)
        if shutters is None:
            return
        shutters.move(close, time)
        self._watch_living()
        if self._foley_on():
            sound, params = SHUTTER_SLAM if close else SHUTTER_ROLL
            self.sfx(sound, float(time) + (SHUTTER_CLOSE_SECONDS * 0.85 if close else 0.0), **params)

    def flashback_look(self, grade: LightGrade) -> LightGrade:
        """``grade`` as the stage's ``flashback`` shows it (unchanged without one)."""
        look = self.params.flashback
        if look is None or look is False:
            return grade
        settings = FlashbackSetting() if look is True else look
        return flashback_grade(grade, tint=resolve_color(settings.tint, self.theme), strength=settings.strength, saturation=settings.saturation)

    def _flashback_vignette(self) -> list[Any]:
        """A flashback's soft vignette over the view, for the top of the set (over the
        characters); none without a flashback."""
        look = self.params.flashback
        if look is None or look is False:
            return []
        settings = FlashbackSetting() if look is True else look
        if settings.vignette <= 0:
            return []
        return [CameraVignette(self.camera.frame, color=resolve_color(settings.color, self.theme), opacity=settings.vignette)]

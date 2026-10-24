"""Processes in a ``cell`` scene (DESIGN.md §95.10): motors walking along their filaments with
their cargo (``motor_walk``), clathrin-mediated ``endocytosis`` and ``exocytosis`` at the plasma
membrane. A mixin of the :class:`~vidgen.scenes.cell.Cell` scene: the checks ``vidgen
validate`` runs (with the motors' walks replayed in beat order), the animations, the captions.
Written against ``vidgen.api``; the plans are :data:`cell_traffic`'s."""

from typing import Any

import numpy as np

from vidgen.api import *

from .molecule_process import Hold

tf = cell_traffic
#: The actions this mixin plays.
TRAFFIC_ACTIONS = ("motor_walk", "endocytosis", "exocytosis")
#: Captions lie over the cell, under the labels.
CAPTION_Z = 49


class CellTraffic:
    """Motor walks, endocytosis and exocytosis for a cell scene."""

    @classmethod
    def traffic_problem(cls, params: Any, name: str, target: str, options: Any) -> str | None:
        """Why a traffic action cannot act on ``target`` (static checks), or ``None``."""
        world = params.world()
        if name == "motor_walk":
            return tf.walk_problem(world, target, options.distance, options.toward)
        if name == "endocytosis":
            if target != "cell":
                return "endocytosis takes things in at the plasma membrane: endocytosis: cell (site: [x, y] chooses where)"
            return tf.endocytosis_problem(world, options.site)
        if name == "exocytosis":
            problem = tf.exocytosis_problem(world, target)
            if problem is None and len(world.members(target)) != 1:
                return f"exocytosis fuses one vesicle: '{target}' has {len(world.members(target))}; give the vesicle its own object (count: 1)"
            return problem
        return None

    @classmethod
    def action_sequence_problems(cls, spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
        """The motors' walks add up (a motor cannot walk past its filament's end); a vesicle fuses
        only once."""
        world = params.world()
        walked: dict[str, float] = {}
        fused: set[str] = set()
        beats = [b.id for b in spec.beats]
        order = sorted(range(len(uses)), key=lambda i: (beats.index(uses[i].beat) if uses[i].beat in beats else 0, uses[i].config.fraction, i))
        problems = []
        for i in order:
            use = uses[i]
            target = use.config.targets()[0] if use.config.targets() else ""
            if use.kind.name == "motor_walk":
                done = walked.get(target, 0.0)
                problem = tf.walk_problem(world, target, use.action.options.distance, use.action.options.toward, done)
                if problem:
                    problems.append((f"{use.location}.target", f"after its earlier walks: {problem}" if done else problem))
                    continue
                walked[target] = done + tf.walk_distance(world, target, use.action.options.distance, done)
            elif use.kind.name == "exocytosis":
                if target in fused:
                    problems.append((f"{use.location}.target", f"'{target}' has fused with the plasma membrane already"))
                fused.add(target)
        return problems

    # ----- motors ---------------------------------------------------------------------------------

    def _walked(self) -> dict[str, float]:
        if not hasattr(self, "_walked_um"):
            self._walked_um: dict[str, float] = {}
        return self._walked_um

    def walk_time(self, entry_id: str, distance: float | None) -> float:
        """Seconds a walk takes at the motor's real speed (1.5 to 8 s)."""
        world = self.world  # type: ignore[attr-defined]
        kind = world.entry(entry_id).kind
        d = tf.walk_distance(world, entry_id, distance, self._walked().get(entry_id, 0.0))
        return min(8.0, max(1.5, d / tf.MOTOR_SPEEDS[kind]))

    def run_motor_walk(self, entry_id: str, distance: float | None) -> list[Animation]:
        """The motors of ``entry_id`` walk ``distance`` µm (hand over hand)."""
        world = self.world  # type: ignore[attr-defined]
        done = self._walked().get(entry_id, 0.0)
        d = tf.walk_distance(world, entry_id, distance, done)
        if d <= 0:
            return []
        kind = world.entry(entry_id).kind
        tracks = []
        for thing in world.members(entry_id):
            track = tf.motor_track(world, thing)
            tracks.append((thing, MotorTrackAt(track, done)))
        self._walked()[entry_id] = done + d
        return [MotorWalking(self, entry_id, kind, tracks, d)]

    # ----- endocytosis and exocytosis ----------------------------------------------------------------

    def _view_middle(self) -> tuple[float, float]:
        """The world point (µm) at the middle of the body as the camera is now."""
        s, _px, _span = self.screen_scale()  # type: ignore[attr-defined]
        frame = self.camera.frame  # type: ignore[attr-defined]
        scene_point = np.array(frame.get_center()) + s * self.body_center  # type: ignore[attr-defined]
        c = self.start.center  # type: ignore[attr-defined]
        return (c[0] + (scene_point[0] - self.body_center[0]) / self.unit, c[1] + (scene_point[1] - self.body_center[1]) / self.unit)  # type: ignore[attr-defined]

    def run_endocytosis(self, options: Any) -> list[Animation]:
        """Clathrin-mediated endocytosis at the chosen site."""
        site = tf.membrane_site(self.world, options.site or self._view_middle())  # type: ignore[attr-defined]
        event = CellEventDrawing(self.drawing, site, "endo", receptors=options.receptors)  # type: ignore[attr-defined]
        captions = self._captions(tf.ENDO_STEPS) if options.notes else []
        return [MembraneEvent(self, event, lambda t: tf.endocytosis_shape(t), captions, gather=lambda t: _ramp(t, 0.02, 0.2)), *holds(captions)]

    def run_exocytosis(self, entry_id: str, options: Any) -> list[Animation]:
        """The vesicle ``entry_id`` fuses with the plasma membrane."""
        world = self.world  # type: ignore[attr-defined]
        site, r, depth = tf.exocytosis_start(world, entry_id)
        cargo = tf.cargo_points(options.cargo, r, f"{entry_id}:cargo")
        event = CellEventDrawing(self.drawing, site, "exo", cargo=cargo, vesicle_hue=CELL_OBJECT_KINDS["vesicle"].hue)  # type: ignore[attr-defined]
        captions = self._captions(tf.EXO_STEPS) if options.notes else []
        self.drawing.hide_owner(entry_id)  # type: ignore[attr-defined]
        rng = np.random.default_rng(abs(hash(entry_id)) % (2 ** 32))
        spread = [(float(rng.uniform(-90, 90)), float(rng.uniform(12, 70))) for _ in cargo]

        def where(t: float, shape: Any) -> list[tuple[float, float]]:
            if shape.vesicle is not None:
                d_, _ = shape.vesicle
                return [(x, -d_ + y) for x, y in cargo]
            out = _ramp(t, tf.EXO_PORE, 0.9)
            low = -max(-min(p[1] for p in shape.membrane), r)
            return [(x * (1 - out) + sx * out, (low + r + y) * (1 - out) + sy * out) for (x, y), (sx, sy) in zip(cargo, spread)]

        return [MembraneEvent(self, event, lambda t: tf.exocytosis_shape(t, r, depth), captions, cargo=where), *holds(captions)]

    def _captions(self, steps: tuple[tuple[float, str], ...]) -> list[tuple[float, float, Mobject]]:
        """The steps' captions on plates at the top of the body (screen-sized), each with when
        it shows (shares of the action)."""
        body = self.body  # type: ignore[attr-defined]
        out = []
        for k, (start, text) in enumerate(steps):
            end = steps[k + 1][0] if k + 1 < len(steps) else 1.0
            words = self.text(text, size=self.params.label_size, color="text")  # type: ignore[attr-defined]
            if words.width > body.width - 0.4:
                words = _wrap(self, text, body.width - 0.4)
            plate = RoundedRectangle(width=words.width + 0.3, height=words.height + 0.2, corner_radius=0.08, stroke_width=0,
                                     fill_color=self.theme.background, fill_opacity=0.85)  # type: ignore[attr-defined]
            group = VGroup(plate, words.move_to(plate.get_center()))
            group.set_z_index(CAPTION_Z)
            screen = np.array([body.center[0], body.y1 - group.height / 2 - 0.05, 0.0])
            self.pin(group, screen)  # type: ignore[attr-defined]
            self.add(group)  # type: ignore[attr-defined]
            out.append((start, end, group))
        self._camera_state = None  # type: ignore[attr-defined]
        self.on_camera()  # type: ignore[attr-defined]
        return out


def _wrap(scene: Any, text: str, room: float) -> Mobject:
    words = text.split(" ")
    lines: list[str] = []
    for w in words:
        if lines and scene.text(lines[-1] + " " + w, size=scene.params.label_size).width <= room:
            lines[-1] += " " + w
        else:
            lines.append(w)
    return VGroup(*[scene.text(line, size=scene.params.label_size, color="text") for line in lines]).arrange(DOWN, buff=0.08)


def _ramp(t: float, a: float, b: float) -> float:
    u = min(max((t - a) / (b - a), 0.0), 1.0) if b > a else float(t >= b)
    return u * u * (3 - 2 * u)


class MotorTrackAt:
    """A motor's track with the distance it has walked already."""

    def __init__(self, track: Any, walked: float) -> None:
        self.track = track
        self.walked = walked

    def now(self) -> Any:
        t = self.track
        return type(t)(t.line, t.s + t.forward * self.walked, t.side, t.forward)


class MotorWalking(Animation):
    """Motors walking: each frame their pieces get the outlines of their poses."""

    def __init__(self, scene: Any, entry_id: str, kind: str, tracks: list[tuple[Any, MotorTrackAt]], distance: float, **kwargs: Any) -> None:
        super().__init__(scene.drawing.groups[entry_id], rate_func=linear, **kwargs)
        self.scene, self.entry_id, self.kind, self.distance = scene, entry_id, kind, distance
        self.tracks = [(thing, at.now()) for thing, at in tracks]

    def create_starting_mobject(self) -> Mobject:
        return self.mobject

    def interpolate_mobject(self, alpha: float) -> None:
        poses = [(thing, (tf.walk_pose(self.kind, track, self.distance, alpha), track)) for thing, track in self.tracks]
        parts = cell_motor_parts(self.kind, poses)
        drawing = self.scene.drawing
        for key, mob in drawing.motor_pieces.get(self.entry_id, {}).items():
            drawing.reshape(mob, cell_motor_curves(parts, key))


class MembraneEvent(Animation):
    """A membrane event playing: its overlay drawn from the planned shape at each moment, the
    captions shown in turn."""

    def __init__(self, scene: Any, event: Any, shape_at: Any, captions: list[tuple[float, float, Mobject]], gather: Any = None, cargo: Any = None,
                 **kwargs: Any) -> None:
        event.group.scenery = True   # it covers the still membrane: cropped by the view like the world (lint off_frame)
        scene.add(event.group)
        scene.traffic_events.append(event)
        super().__init__(event.group, rate_func=linear, **kwargs)
        self.scene, self.event, self.shape_at, self.captions = scene, event, shape_at, captions
        self.gather, self.cargo = gather, cargo
        self.caption_rest = [[(m, m.get_fill_opacity()) for m in c.get_family() if isinstance(m, VMobject)] for _, _, c in captions]
        for _, _, caption in captions:
            caption.set_opacity(0.0)

    def create_starting_mobject(self) -> Mobject:
        return self.mobject

    def draw(self, alpha: float) -> None:
        scene = self.scene
        s, px_per_um, span = scene.screen_scale()
        weights = scene.drawing.weights(px_per_um, span)
        stroke_unit = s * 100 / scene.ref_pixels
        shape = self.shape_at(alpha)
        if self.gather is not None:
            self.event._gather = self.gather(alpha)
        cargo = self.cargo(alpha, shape) if self.cargo is not None else None
        self.event.draw(shape, weights, px_per_um, stroke_unit, cargo_at=cargo)

    def interpolate_mobject(self, alpha: float) -> None:
        self.draw(alpha)
        for (start, end, caption), rest in zip(self.captions, self.caption_rest):
            ramp = 0.03
            if alpha < start or alpha > end:
                f = 0.0
            else:
                f = min(1.0, (alpha - start) / ramp, (end - alpha) / ramp if end < 1.0 else 1.0 if alpha < 0.985 else (1.0 - alpha) / 0.015)
            for m, base in rest:
                m.set_fill(opacity=base * max(0.0, f), family=False)



def holds(captions: list[tuple[float, float, Mobject]]) -> list[Animation]:
    """The captions marked as changing while an event plays (they are pinned mobjects of the
    scene, not part of the event's own group)."""
    return [Hold(c) for _, _, c in captions]


__all__ = ["CellTraffic", "MembraneEvent", "MotorWalking", "TRAFFIC_ACTIONS"]

"""``3d``: a 3D scene drawn by three.js in headless Chromium (DESIGN.md §114), shown full-bleed under
the scene's title, the overlays and the captions.

Before the scene plays, its frames are drawn into a lossless clip
(``<render_dir>/three_d/<scene_id>.mkv``, with the scene description beside it as ``.json``) and
reused while the description and the page are unchanged (so are the guide passes asked for,
``<scene_id>.<pass>.mkv``); the clip is then a ``ClipMobject``
filling the frame, so stills, fades and the layout dump see it like any picture.
"""

import math
from pathlib import Path
from typing import Any

from vidgen.api import *

#: Extra frames drawn after the planned end (the last one holds if the scene runs longer).
SPARE_FRAMES = 2
#: The beat actions that move the camera (``scene_3d_actions``).
CAMERA_ACTIONS = ("camera_orbit", "camera_dolly", "camera_fly_to", "camera_look_at", "camera_move")
#: The beat actions that change objects (``scene_3d_actions``).
OBJECT_ACTIONS = ("object_move", "object_path", "object_rotate", "object_spin", "object_scale", "object_show",
                  "object_hide", "object_highlight", "object_walk", "object_face")


@scene("3d")
class Scene3D(NarratedScene):
    """Objects in 3D (box, sphere, cylinder, cone, torus, plane, arrow, label, character
    stand-ins; groups whose children move with them) seen by a camera with one default light
    (ambient + sun) over a background colour. The picture fills the frame from the first frame
    and keeps moving (``spin``) through every beat; objects move, turn, grow, appear, glow and
    walk on beats and words (object_move, object_path, object_rotate, object_spin, object_scale,
    object_show, object_hide, object_highlight, object_walk, object_face); the camera stands
    still or moves (camera_orbit, camera_dolly, camera_fly_to, camera_look_at, camera_move),
    following an object that moves; beat 1 fades the title in; the scene fades out at the end. Frames are drawn by three.js in headless
    Chromium (``pip install "schu-video-generator[3d]"`` and ``python -m playwright install
    chromium``).

    Action targets: ``view`` (the 3D picture), ``title`` (if any); the camera and object
    actions name objects by id.
    """

    outro = 0.5
    target_patterns = ("view", "title")
    #: The camera actions work on this type (``scene_3d_actions``).
    three_d_actions = True

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``view`` and, with a title, ``title``."""
        return ["view"] + (["title"] if params.title else [])

    class Params(Scene3DParams):
        pass

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        """Arrows that point nowhere and a camera standing on what it looks at."""
        try:
            check_3d_scene(params)
        except ValueError as exc:
            return [str(exc)]
        return []

    @classmethod
    def action_sequence_problems(cls, spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
        """The camera moves replayed in beat and ``at`` order, each to its end: a dolly past the
        point looked at, an orbit from right above its centre..."""
        beats = [b.id for b in spec.beats]
        camera = [u for u in uses if u.kind.name in CAMERA_ACTIONS]
        order = [(beats.index(u.beat) if u.beat in beats else 0) + u.config.fraction for u in camera]
        moves = [u.action.move(t, t) for u, t in zip(camera, order)]
        try:
            return [(f"{camera[k].location}.action", message) for k, message in camera_problems(params, moves)]
        except ValueError:   # the params' own problem, reported by validate_project
            return []

    def construct(self) -> None:
        view = ClipMobject(self._draw_view())
        view.fit_box(self.frame_width, self.frame_height, "cover").move_to(ORIGIN)
        view.play(self)
        self._view = view
        self.add(view)
        self.target("view", view)
        title = self._title()
        for i, d in self.timeline():
            if i == 0 and title is not None:
                self.play_steps(d, [lambda: self.entrance("title")], fraction=0.6, cap=0.8)
        self.finish()

    def tear_down(self) -> None:
        """Release the clip file, then the usual tear-down."""
        view = getattr(self, "_view", None)
        if isinstance(view, ClipMobject):
            view.close()
        super().tear_down()

    def _title(self) -> Mobject | None:
        """The title on a plate in the header band (registered as target ``title``)."""
        if not self.params.title:
            return None
        header = self.region("header")
        text = fit_text(self.params.title, header.width - 0.6, header.height - 0.2, size="heading", weight=BOLD, font=self.theme.font_for("heading"))
        title = text_plate(text, self.theme.color("surface"))
        place(title, header, fit="none", align="top")
        self.target("title", title)
        return title

    # ----- the 3D frames -----------------------------------------------------------------------

    def _plan(self) -> tuple[list[BeatSpan], int]:
        """The beats on the scene's clock and how many frames to draw (as long as the scene
        plays: its beats or a silent scene's duration, then the fade-out)."""
        fps = int(config.frame_rate)
        spans: list[BeatSpan] = []
        frames = 0
        if self.beats:
            for beat in self.beats:
                window = self.beat_window(beat)
                start = frames / fps
                spans.append(BeatSpan(beat.id, start, start + window.heard))
                frames += round(window.window * fps)
        else:
            frames = round(max((self.spec.duration or 0.0) - self.outro, 1 / fps) * fps)
        return spans, frames + math.ceil(self.outro * fps) + SPARE_FRAMES

    def camera_moves(self) -> list[CameraMove]:
        """The camera actions as moves on the scene's clock: from when each falls due, for its
        ``run_time`` or to the end of its beat."""
        moves = []
        for name in CAMERA_ACTIONS:
            for act, due, beat_end in self.action_times(name, 0.0):
                seconds = act.config.run_time
                moves.append(act.move(due, due + seconds if seconds is not None else max(beat_end, due + 1 / config.frame_rate)))
        return moves

    def object_changes(self) -> list[ObjectChange]:
        """The object actions as changes on the scene's clock: from when each falls due, for its
        ``run_time``, its own length or to the end of its beat."""
        fps = config.frame_rate
        return [act.change(due, act.end(due, beat_end, fps), self.theme)
                for name in OBJECT_ACTIONS for act, due, beat_end in self.action_times(name, 0.0)]

    def description(self) -> dict[str, Any]:
        """The scene description this render draws (DESIGN.md §114.3)."""
        spans, frames = self._plan()
        changes = self.object_changes()
        fps = int(config.frame_rate)
        try:
            described = scene_description(
                self.params, self.theme, width=int(config.pixel_width), height=int(config.pixel_height),
                fps=fps, frames=frames, beats=spans, camera_moves=self.camera_moves(), object_changes=changes,
            )
            self._world = plan_world(self.params, fps, frames, changes)
        except ValueError as exc:
            raise VidgenError(f"scene '{self.spec.id}': {exc}") from None
        self._description = described
        return described

    # ----- lint (DESIGN.md §114.12) -------------------------------------------------------------

    def spoken_objects(self, beat_id: str | None) -> list[str]:
        """The objects a beat is about: those its object and camera actions name, and the
        stand-ins whose voice (default: their id) says it."""
        beat = next((b for b in self.beats if b.id == beat_id), None)
        if beat is None:
            return []
        out: list[str] = []
        for act in beat.actions:
            if act.action in OBJECT_ACTIONS or act.action in CAMERA_ACTIONS:
                out += [t for t in act.targets() if t not in out]
        voice = beat.voice or self.spec.voice
        if voice:
            out += [o.id for o in self.params.objects if o.shape == "standin" and (o.voice or o.id) == voice and o.id not in out]
        return out

    def layout_keys(self, beat_id: str | None) -> dict[str, Any]:
        """What the layout dump adds to a still: ``three_d`` with the objects on screen (their
        projected box, share off the frame, share hidden by nearer objects) and the ids the
        beat is about, for lint ``three_d_off_frame`` and ``three_d_hidden``."""
        description, world = getattr(self, "_description", None), getattr(self, "_world", None)
        if description is None or world is None:
            return {}
        t = min(float(self.renderer.time), description["duration"])
        return {"three_d": {"objects": framing_3d(description, world, t), "spoken": self.spoken_objects(beat_id)}}

    def _draw_view(self) -> Path:
        """The clip of the 3D frames (drawn now, or reused while its description and the page
        are unchanged), and the guide passes asked for (``guide_passes``, ``--guide-passes``)
        beside it (DESIGN.md §114.14)."""
        folder = self.project.render_dir(self.is_preview) / "three_d"
        description = self.description()
        clip = make_3d_clip(folder, self.spec.id, description)
        passes = tuple(p for p in GUIDE_PASSES if p in self.params.passes() or p in self.guide_passes)
        if passes:
            make_guide_passes(folder, self.spec.id, description, self._world, passes)
        self.guide_passes_made = passes
        return clip

"""Where the picked takes go in the film (DESIGN.md §113.4).

:func:`scene_placements` lists, for one scene, every generated shot whose beat shows a take
(``generated_shot.place`` true and a take chosen, :func:`vidgen.videogen.takes.chosen_take`): the
take, the shot's start in the scene's render (its beat's start on the planned timeline, plus the
part's offset), its length (the beat's window, or the part's: the snapped clip is trimmed to it)
and how it is laid in (``fit``, ``color_match``, fades of ``crossfade`` seconds against vidgen's
own picture: none at the scene's start or end, where the film's transitions join scenes, and none
between two takes that meet; the scene's last beat keeps its take through the scene's fade-out
and hold, so vidgen's picture never flashes between takes). The scene's renderer draws them
(:class:`vidgen.generated_layer.GeneratedLayer`) under the overlays and captions; the scene's
fingerprint holds them, so a new pick renders the scene again. Drafts (``--draft``, and the guide
renders of ``vidgen generate inputs``) show vidgen's own picture.

A beat split into parts (longer than the model's longest clip) has a take folder per part
(``takes/<beat>_p<n>``); the parts share the beat's window equally, as planned.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from vidgen.project import Project
from vidgen.videogen.takes import TAKES_DIR, chosen_take


@dataclass(frozen=True)
class Placement:
    """One take laid over its shot's time in ``scene``'s render (scene seconds), fading in from
    and out to vidgen's own picture over ``fade_in`` / ``fade_out`` seconds inside its window."""

    scene: str
    shot: str
    take: Path
    number: int
    model: str
    start: float
    length: float
    fit: str
    fade_in: float
    fade_out: float
    color_match: float

    def fingerprint(self, root: Path) -> list[Any]:
        """What the scene's render depends on (the take by size and modification time)."""
        st = self.take.stat()
        rel = self.take.relative_to(root).as_posix() if self.take.is_relative_to(root) else str(self.take)
        return [self.shot, rel, st.st_size, st.st_mtime_ns, round(self.start, 6), round(self.length, 6), self.fit, self.fade_in, self.fade_out, self.color_match]


def _wants_placing(project: Project) -> bool:
    if getattr(project, "draft", False):
        return False
    if not (project.root / TAKES_DIR).is_dir():
        return False
    return any(b.generated_shot is not None and b.generated_shot.place for s in project.config.scenes for b in s.beats)


def scene_placements(project: Project, scene_id: str | None = None) -> list[Placement]:
    """The takes shown in ``scene_id`` (every scene's when ``None``), in time order; none for
    projects without takes (nothing is computed then)."""
    if not _wants_placing(project):
        return []
    from vidgen.videogen.shots import project_shots

    settings = project.config.videogen
    out: list[Placement] = []
    for shot in project_shots(project, None):   # one shot per beat without the model list
        if scene_id is not None and shot.scene_id != scene_id or not shot.spec.place:
            continue
        crossfade = shot.spec.crossfade if shot.spec.crossfade is not None else settings.crossfade
        parts = _parts(project.root, shot.id)
        length = shot.length / len(parts)
        # the scene's last beat keeps its take through the scene's end (fade-out, hold): no flash
        # of vidgen's own picture between two takes
        last = project.scene(shot.scene_id).beats[-1].id == shot.beat.id
        for k, part in enumerate(parts):
            take = chosen_take(project.root, part)
            if take is None:
                continue
            start = shot.start - shot.scene_start + k * length
            to_end = last and k == len(parts) - 1
            shown = max(length, shot.scene_end - shot.scene_start - start) if to_end else length
            # fades only against vidgen's own picture: not at the scene's start or end (the film's
            # transitions join scenes), not between two takes (a cut)
            fade_in = crossfade if start > 1e-6 else 0.0
            fade_out = 0.0 if to_end else crossfade
            out.append(Placement(shot.scene_id, part, take.path, take.number, take.model, start, shown, shot.spec.fit, fade_in, fade_out, settings.color_match))
    out.sort(key=lambda p: (p.scene, p.start))
    for i in range(len(out) - 1):
        a, b = out[i], out[i + 1]
        if a.scene == b.scene and abs(a.start + a.length - b.start) < 1e-3:
            out[i], out[i + 1] = replace(a, fade_out=0.0), replace(b, fade_in=0.0)
    return out


def _parts(root: Path, beat_shot: str) -> list[str]:
    """The shot ids a beat's takes are under: itself, or ``<id>_p1..n`` when it was split."""
    if (root / TAKES_DIR / beat_shot).is_dir():
        return [beat_shot]
    parts = []
    while (root / TAKES_DIR / f"{beat_shot}_p{len(parts) + 1}").is_dir():
        parts.append(f"{beat_shot}_p{len(parts) + 1}")
    return parts or [beat_shot]


def placed_models(project: Project) -> list[str]:
    """The models whose takes the film shows (sorted, distinct)."""
    return sorted({p.model for p in scene_placements(project)})


def credit_line(project: Project) -> str:
    """``Includes AI-generated footage (model, model).`` when the film shows takes, else ``""``."""
    models = placed_models(project)
    return f"Includes AI-generated footage ({', '.join(models)})." if models else ""


__all__ = ["Placement", "credit_line", "placed_models", "scene_placements"]

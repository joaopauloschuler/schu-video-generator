"""The lint rule on the project pieces a video plays (``music_check``, DESIGN.md §93.10).

``music_check`` reads the config, not a still: every ``music:`` cue playing a project piece (a
score file under ``assets/music``) is checked as ``vidgen music check`` does (without the demo
and the picture; cached per version of the file in ``build/music``), and the findings of the
configured topics are reported on the cue's first scene: the check's fixes at the rule's
severity, its notes as info. The runner fills :attr:`SceneContext.music_issues` with
:func:`music_issues`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from vidgen.config import MusicCheckRule
from vidgen.errors import VidgenError
from vidgen.lint.rules import Issue, SceneContext, rule

if TYPE_CHECKING:
    from vidgen.project import Project


def music_issues(project: Project, scene_id: str, settings: MusicCheckRule) -> list[tuple[str, str | None]]:
    """``(message, severity or None)`` of the ``music_check`` findings of one scene: those of the
    pieces whose cue starts at this scene."""
    from vidgen.music import cue_scene_range
    from vidgen.music_pieces import piece_check, played_pieces

    ids = [s.id for s in project.config.scenes]
    cues = project.config.music_cues
    out: list[tuple[str, str | None]] = []
    for k, path in played_pieces(project.config, project.root):
        if ids[cue_scene_range(cues[k], ids)[0]] != scene_id:
            continue
        rel = path.relative_to(project.root).as_posix()
        try:
            report = piece_check(path, project.build_dir / "music")
        except VidgenError as exc:
            out.append((f"music piece {rel}: cannot check it: {exc}", None))
            continue
        for finding in report["findings"]:
            if finding["topic"] not in settings.topics or finding["level"] == "ok":
                continue
            fixes = f"; try {' or '.join(finding['fixes'][:2])}" if finding["fixes"] else ""
            severity = None if finding["level"] == "fix" else "info"
            out.append((f"music piece {rel} ({finding['topic']}): {finding['text']}{fixes} (vidgen music check {rel})", severity))
    return out


@rule("music_check", scope="scene")
def music_check(ctx: SceneContext, settings: MusicCheckRule) -> Iterator[Issue]:
    """A project piece the video plays that is hard on the voice (vidgen music check's findings)."""
    for message, severity in ctx.music_issues:
        yield Issue(message, None, severity=severity, beat=ctx.beat_at(0.0), time=0.0)

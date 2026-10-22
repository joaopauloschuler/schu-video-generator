"""The lint rule on the project pieces a video plays (``music_check``, DESIGN.md §93.10).

``music_check`` reads the config, not a still: every ``music:`` cue playing a project piece (a
score file under ``assets/music``) is checked as ``vidgen music check`` does (without the demo
and the picture; cached per version of the file in ``build/music``), and the findings of the
configured topics are reported on the cue's first scene: the check's fixes at the rule's
severity, its notes as info. Only what concerns the part of the piece the cue plays is reported
(Step 191): a loop seam it never crosses, sections it never reaches and a voice range loud only
in bars it does not play are left out. The runner fills :attr:`SceneContext.music_issues` with
:func:`music_issues`.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from vidgen.config import MusicCheckRule, MusicCue
from vidgen.errors import VidgenError
from vidgen.lint.rules import Issue, SceneContext, rule

if TYPE_CHECKING:
    from vidgen.project import Project


def music_issues(project: Project, scene_id: str, settings: MusicCheckRule, preview: bool = False) -> list[tuple[str, str | None]]:
    """``(message, severity or None)`` of the ``music_check`` findings of one scene: those of the
    pieces whose cue starts at this scene, about the part of the piece the cue plays (by the
    video plan's times: :func:`played_bars`)."""
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
            played, wraps = played_bars(project, cues[k], report, preview)
        except VidgenError as exc:
            out.append((f"music piece {rel}: cannot check it: {exc}", None))
            continue
        bars = len(report["facts"]["bar_voice_db"])
        part = "" if len(played) == bars else f" (the video plays {_bar_words(played)} of its {bars})"
        for finding in report["findings"]:
            if finding["topic"] not in settings.topics or finding["level"] == "ok" or not _heard(finding, report, played, wraps):
                continue
            fixes = f"; try {' or '.join(finding['fixes'][:2])}" if finding["fixes"] else ""
            severity = None if finding["level"] == "fix" else "info"
            out.append((f"music piece {rel} ({finding['topic']}){part}: {finding['text']}{fixes} (vidgen music check {rel})", severity))
    return out


def played_bars(project: Project, cue: MusicCue, report: dict[str, Any], preview: bool = False) -> tuple[set[int], bool]:
    """The bars of a piece (0-based) a cue plays, by the video plan's scene times, the cue's
    ``start`` / ``section`` and loop, and whether it plays across the loop's seam."""
    from vidgen.music import cue_scene_range
    from vidgen.music_pieces import section_start
    from vidgen.videoplan import VideoPlan

    plan = VideoPlan(project, project.render_format(preview).fps)
    ids = [s.id for s in project.config.scenes]
    first, last = cue_scene_range(cue, ids)
    seconds = plan.scene(ids[last]).end - plan.scene_start(ids[first])
    bars = len(report["facts"]["bar_voice_db"])
    bar = report["seconds"] / bars if report["kind"] == "score" and bars else report["seconds"]
    offset = cue.start + section_start(cue, project.root)
    looped = bool(report["loop"]) and cue.loop
    end = offset + seconds
    if not looped:
        end = min(end, report["seconds"])
    if end - offset >= report["seconds"]:
        return set(range(bars)), looped
    a, z = int(offset // bar), int(math.ceil(end / bar - 1e-9))
    return {k % bars for k in range(a, max(z, a + 1))}, looped and end > report["seconds"]


def _bar_words(bars: set[int]) -> str:
    runs: list[list[int]] = []
    for b in sorted(bars):
        if runs and b == runs[-1][1] + 1:
            runs[-1][1] = b
        else:
            runs.append([b, b])
    return ", ".join(f"bar {a + 1}" if a == z else f"bars {a + 1}-{z + 1}" for a, z in runs)


def _heard(finding: dict[str, Any], report: dict[str, Any], played: set[int], wraps: bool) -> bool:
    """Whether a finding is about a part the video plays: a seam it never crosses, a section it
    does not play or a voice range loud only in bars it does not play are left out."""
    from vidgen.studio.check import LIMITS

    if len(played) == len(report["facts"]["bar_voice_db"]):
        return True
    if finding["topic"] == "loop seam":
        return wraps
    if finding["topic"] == "voice range":
        loudest = max(report["facts"]["bar_voice_db"][b] for b in played)
        return loudest > LIMITS["voice_bar_db"] or report["facts"]["voice_share"] > LIMITS["voice_share"]
    if finding["topic"] == "sections":
        named = [s for s in report["sections"] if finding["text"].startswith(f"the {s['name']} ")]
        return not named or any(b in played for s in named for b in range(s["first_bar"] - 1, s["first_bar"] - 1 + s["bars"]))
    return True


@rule("music_check", scope="scene")
def music_check(ctx: SceneContext, settings: MusicCheckRule) -> Iterator[Issue]:
    """A project piece the video plays that is hard on the voice (vidgen music check's findings)."""
    for message, severity in ctx.music_issues:
        yield Issue(message, None, severity=severity, beat=ctx.beat_at(0.0), time=0.0)

"""The human-readable ``vidgen lint`` report."""

from __future__ import annotations

import os
from pathlib import Path

from vidgen.lint.run import LintResult


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _where(path: Path, root: Path) -> str:
    try:
        return os.path.relpath(path, root)
    except ValueError:  # another drive on Windows
        return str(path)


def report_lines(result: LintResult, root: Path) -> list[str]:
    """Findings grouped by scene (one line each, with the still to look at), then a summary.

    Paths are relative to ``root`` (usually the current directory)."""
    fmt = result.format
    lines = [
        f"lint: {_plural(len(result.scenes), 'scene')}, {_plural(result.stills, 'beat-end still')} "
        f"({'preview' if result.preview else 'final'} {fmt.width}x{fmt.height})"
    ]
    scene = None
    for f in result.findings:
        if f.scene != scene:
            scene = f.scene
            lines.append(f"{scene}:")
        when = f"{f.beat or scene} @ {f.scene_time:.1f}s"
        if len(f.beats) > 1:
            when += f" (+{len(f.beats) - 1} more beat{'s' if len(f.beats) > 2 else ''})"
        lines.append(f"  {f.severity:<7} {f.rule:<12} {when}: {f.message}")
        lines.append(f"          still: {_where(f.still, root)}")
    counts = result.counts()
    summary = ", ".join(_plural(counts[sev], sev) for sev in ("error", "warning")) + f", {counts['info']} info"
    if result.ignored:
        summary += f" ({result.ignored} ignored by lint_ignore)"
    lines.append(summary)
    if result.failed:
        lines.append(f"failed: findings at or above '{result.fail_on}'")
    return lines

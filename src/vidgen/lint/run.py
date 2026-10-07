"""``vidgen lint``: run the rules over a video's beat-end stills (DESIGN.md §16) and its scenes'
activity over time (§17)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidgen.config import FormatConfig, LintIgnore
from vidgen.errors import VidgenError
from vidgen.lint.findings import Finding
from vidgen.lint.rules import RULES, Issue, SceneContext, StillContext, severity_rank
from vidgen.project import Project
from vidgen.render.worker import scene_activity_path, scene_layout_path

#: ``fail_on`` values: the lowest severity that fails the command (``never``: none).
FAIL_ON: tuple[str, ...] = ("error", "warning", "info", "never")


@dataclass
class LintResult:
    """What :func:`lint_project` found. ``findings`` are in config order of the scenes, then by
    time and severity; ``stills`` counts the beat-end stills checked."""

    format: FormatConfig
    preview: bool
    fail_on: str
    rules: list[str]
    scenes: list[str]
    stills: int = 0
    findings: list[Finding] = field(default_factory=list)
    rendered: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    ignored: int = 0
    warnings: list[tuple[str, str]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        """``{"error": n, "warning": n, "info": n}``."""
        return {sev: sum(1 for f in self.findings if f.severity == sev) for sev in ("error", "warning", "info")}

    @property
    def failed(self) -> bool:
        """True if a finding is at least as severe as ``fail_on``."""
        if self.fail_on == "never":
            return False
        return any(severity_rank(f.severity) <= severity_rank(self.fail_on) for f in self.findings)


def _matches(entry: LintIgnore, finding: Finding) -> bool:
    if entry.rule not in ("all", finding.rule):
        return False
    if entry.beat is not None and entry.beat != finding.beat:
        return False
    if entry.object is None:
        return True
    pattern = _pattern(entry.object)
    for obj in finding.objects:
        candidates = [obj.get("name"), obj.get("path"), obj.get("text"), obj.get("icon")]
        if any(isinstance(c, str) and pattern.fullmatch(c) for c in candidates):
            return True
    return False


def _pattern(text: str) -> re.Pattern[str]:
    """``*`` (any text) and ``?`` (one character) wildcards; everything else literal, so paths
    such as ``VGroup[2]/Text[0]`` can be written as they are."""
    return re.compile(re.escape(text).replace(r"\*", ".*").replace(r"\?", "."), re.DOTALL)


def _group(issue: Issue) -> tuple[Any, ...] | None:
    """What makes an issue \"like\" others (see :func:`_group_similar`): the rule's ``group``, or
    the parent of its one object; ``None`` (never grouped) for pairs and top-level objects."""
    if issue.group is not None:
        return issue.group
    if len(issue.objects) != 1 or "/" not in issue.objects[0]["path"]:
        return None
    return ("parent", issue.objects[0]["path"].rsplit("/", 1)[0])


def _severity(issue: Issue, rule_default: str, configured: str | None) -> str:
    return configured or issue.severity or rule_default


def _read(path: Path, scene_id: str, what: str) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VidgenError(f"scene '{scene_id}': cannot read its {what} {path}: {exc}") from None


def _scene_findings(
    project: Project, preview: bool, scene_id: str, start: float | None, rules: list[str]
) -> tuple[list[Finding], int, int]:
    """Findings of one scene (merged across beats), stills checked, findings ignored."""
    path = scene_layout_path(project, preview, scene_id)
    layout = _read(path, scene_id, "layout dump")
    lint = project.config.lint
    ignores = project.scene(scene_id).lint_ignores()
    merged: dict[tuple[Any, ...], Finding] = {}
    stills = ignored = 0
    beat_stills: dict[str | None, Path] = {}
    still_rules = [name for name in rules if RULES[name].scope == "still"]
    for frame in layout["frames"]:
        if frame["k"] != frame["n"]:
            continue  # mid-beat stills show animations in progress; lint the settled beat ends
        stills += 1
        moving = {o["id"] for o in frame.get("overlays", []) if not o.get("settled", True)}  # sliding in or out
        objects = [o for o in frame["objects"] if o["opacity"] >= lint.min_opacity and o.get("overlay") not in moving]
        still = Path(os.path.normpath(path.parent / frame["still"]))
        beat_stills.setdefault(frame["beat"], still)
        skips = {o["id"]: set(o.get("skip", ())) for o in frame.get("overlays", [])}
        for name in still_rules:
            entry = RULES[name]
            settings = entry.settings(lint.rules)
            if settings.severity == "off":
                continue
            # an overlay type may exempt its objects from a rule (a faint watermark: contrast)
            kept = [o for o in objects if name not in skips.get(o.get("overlay"), ())]
            ctx = StillContext(layout, frame, kept, still=still)
            for issue in entry.check(ctx, settings):
                finding = Finding(
                    scene=scene_id,
                    beat=frame["beat"],
                    time=None if start is None else round(start + frame["time"], 6),
                    scene_time=frame["time"],
                    rule=name,
                    severity=_severity(issue, entry.default, settings.severity),
                    message=issue.message,
                    bbox=issue.bbox,
                    still=still,
                    objects=issue.objects,
                    value=issue.value,
                    limit=issue.limit,
                    beats=[frame["beat"]],
                    group=_group(issue),
                )
                if any(_matches(e, finding) for e in ignores):
                    ignored += 1
                    continue
                first = merged.get(finding.key)
                if first is None:
                    merged[finding.key] = finding
                elif finding.beat not in first.beats:
                    first.beats.append(finding.beat)
    findings = _group_similar(list(merged.values()))
    timing, skipped = _timing_findings(project, preview, scene_id, start, rules, beat_stills)
    return findings + timing, stills, ignored + skipped


def _timing_findings(
    project: Project,
    preview: bool,
    scene_id: str,
    start: float | None,
    rules: list[str],
    beat_stills: dict[str | None, Path],
) -> tuple[list[Finding], int]:
    """Findings of the ``scene`` (timing) rules for one scene, findings ignored. Issues sharing
    a ``group`` become one finding listing their beats."""
    names = [name for name in rules if RULES[name].scope == "scene"]
    if not names:
        return [], 0
    lint = project.config.lint
    activity = _read(scene_activity_path(project, preview, scene_id), scene_id, "activity file")
    ctx = SceneContext(scene_id, activity, project.audio_dir)
    ignores = project.scene(scene_id).lint_ignores()
    findings: list[Finding] = []
    groups: dict[tuple[Any, ...], Finding] = {}
    ignored = 0
    for name in names:
        entry = RULES[name]
        settings = entry.settings(lint.rules)
        if settings.severity == "off":
            continue
        for issue in entry.check(ctx, settings):
            finding = Finding(
                scene=scene_id,
                beat=issue.beat,
                time=None if start is None else round(start + issue.time, 6),
                scene_time=round(issue.time, 6),
                rule=name,
                severity=_severity(issue, entry.default, settings.severity),
                message=issue.message,
                bbox=issue.bbox,
                still=beat_stills.get(issue.beat),
                value=issue.value,
                limit=issue.limit,
                beats=[issue.beat],
            )
            if any(_matches(e, finding) for e in ignores):
                ignored += 1
                continue
            key = (name, finding.severity, issue.group)
            first = groups.get(key) if issue.group is not None else None
            if first is None:
                findings.append(finding)
                if issue.group is not None:
                    groups[key] = finding
            elif finding.beat not in first.beats:
                first.beats.append(finding.beat)
    return findings, ignored


def _group_similar(findings: list[Finding]) -> list[Finding]:
    """Merge findings of the same rule and severity, first seen at the same still, that share a
    group (:attr:`Finding.group`: by default the object's parent, e.g. an axis' tick labels) or
    are about the same text (a label repeated in several copies of a component): one finding,
    the other objects listed in ``similar``."""
    from vidgen.lint.layout_rules import describe

    groups: dict[tuple[Any, ...], Finding] = {}
    out: list[Finding] = []
    for finding in findings:
        keys = []
        if finding.group is not None:
            keys.append((finding.rule, finding.severity, finding.beat, "group", finding.group))
        if len(finding.objects) == 1 and finding.objects[0].get("text"):
            keys.append((finding.rule, finding.severity, finding.beat, "text", finding.objects[0]["text"]))
        first = next((groups[k] for k in keys if k in groups), None)
        if first is None:
            groups.update((k, finding) for k in keys)
            out.append(finding)
            continue
        first.similar.append(finding.objects[0])
        first.beats.extend(b for b in finding.beats if b not in first.beats)
        if first.bbox is not None and finding.bbox is not None:
            a, b = first.bbox, finding.bbox
            first.bbox = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
    for finding in {id(f): f for f in groups.values()}.values():
        if finding.similar:
            names = ", ".join(describe(o).split(" ", 1)[1] for o in finding.similar[:3])
            more = "…" if len(finding.similar) > 3 else ""
            finding.message += f"; also {len(finding.similar)} more like it ({names}{more})"
    return out


def lint_project(
    project: Project,
    *,
    preview: bool = True,
    scenes: list[str] | None = None,
    rules: list[str] | None = None,
    fail_on: str | None = None,
    jobs: int = 1,
    force: bool = False,
) -> LintResult:
    """Check the beat-end stills of ``project`` (loaded with its variant) with the lint rules.

    Stills and layout dumps are reused when current (any number of stills per beat, e.g. from
    ``vidgen storyboard``); otherwise the scene is rendered with one still per beat. ``scenes``
    / ``rules`` restrict what is checked; ``fail_on`` overrides the config's ``lint.fail_on``;
    ``force`` renders the selected scenes again.
    """
    from vidgen.render.pipeline import render_scenes
    from vidgen.storyboard import scene_starts, stills_current

    known = [s.id for s in project.config.scenes]
    unknown = [sid for sid in scenes or [] if sid not in known]
    if unknown:
        raise VidgenError(f"unknown scene(s): {', '.join(unknown)}; scenes: {', '.join(known)}")
    unknown = [name for name in rules or [] if name not in RULES]
    if unknown:
        raise VidgenError(f"unknown lint rule(s): {', '.join(unknown)}; rules: {', '.join(RULES)}")
    fail_on = fail_on or project.config.lint.fail_on
    if fail_on not in FAIL_ON:
        raise VidgenError(f"fail_on must be one of {', '.join(FAIL_ON)}")
    if jobs < 1:
        raise VidgenError("--jobs must be at least 1")
    selected = [sid for sid in known if not scenes or sid in scenes]
    names = [name for name in RULES if not rules or name in rules]

    to_render = [sid for sid in selected if force or not stills_current(project, preview, sid, None)]
    runs = render_scenes(project, preview, to_render, jobs=jobs, frames=1)
    result = LintResult(
        format=project.render_format(preview),
        preview=preview,
        fail_on=fail_on,
        rules=names,
        scenes=selected,
        rendered=runs.rendered,
        reused=[sid for sid in selected if sid not in runs.rendered],
        warnings=runs.warnings,
    )
    starts = scene_starts(project, preview)
    for sid in selected:
        findings, stills, ignored = _scene_findings(project, preview, sid, starts[sid], names)
        findings.sort(key=lambda f: (f.scene_time, severity_rank(f.severity), names.index(f.rule)))
        result.findings.extend(findings)
        result.stills += stills
        result.ignored += ignored
    return result


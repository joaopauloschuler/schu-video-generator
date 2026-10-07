"""The lint rule framework: what a rule is, how it is registered, what it reports.

A rule has a ``name`` (one of :data:`vidgen.config.LINT_RULES`, with a settings model in
:class:`vidgen.config.LintRules`), a ``scope`` saying what it looks at and a ``check`` function
yielding :class:`Issue` objects. The runner (:mod:`vidgen.lint.run`) turns issues into
:class:`~vidgen.lint.findings.Finding` objects (scene, beat, time, still, severity...), applies
the config's severities and ``lint_ignore`` entries and merges repeats.

Scopes: ``still`` rules (:mod:`vidgen.lint.layout_rules`) get a :class:`StillContext`, one per
beat-end still of a scene, built from the layout dump (DESIGN.md §15). ``scene`` rules
(:mod:`vidgen.lint.timing_rules`) get a :class:`SceneContext`, one per scene, built from the
scene's activity file (DESIGN.md §17); their issues say which beat and when. The report format
is the same for all.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from vidgen.config import LINT_RULES, RuleConfig

#: Severities from most to least severe (``off`` disables a rule in the config).
SEVERITIES: tuple[str, ...] = ("error", "warning", "info")

Bbox = tuple[float, float, float, float]
Scope = Literal["still", "scene"]


@dataclass(frozen=True)
class Issue:
    """What a rule's check reports: ``objects`` are the layout objects concerned (none, one, or
    a pair), ``bbox`` the region to look at (output px), ``severity`` overrides the rule's
    default (e.g. an escalation), ``value``/``limit`` the measured number and the threshold.
    Issues of one still with the same ``group`` are reported as one finding (default group: the
    object's parent, e.g. the tick labels of an axis).

    ``scene`` rules also set ``beat`` (the beat concerned, ``None`` in a silent scene) and
    ``time`` (seconds from the scene start); their issues with the same ``group`` are reported
    as one finding listing every beat (no group: one finding each)."""

    message: str
    bbox: Bbox | None
    objects: tuple[dict[str, Any], ...] = ()
    severity: str | None = None
    value: float | None = None
    limit: float | None = None
    group: tuple[Any, ...] | None = None
    beat: str | None = None
    time: float = 0.0


@dataclass
class StillContext:
    """One captured still of a scene as the ``still`` rules see it.

    ``layout`` is the scene's layout dump (header keys), ``frame`` its entry for this still,
    ``objects`` the frame's objects at or above the config's ``min_opacity``, ``still`` the PNG.
    """

    layout: dict[str, Any]
    frame: dict[str, Any]
    objects: list[dict[str, Any]] = field(default_factory=list)
    still: Path | None = None
    _pixels: np.ndarray | None = field(default=None, repr=False)

    def region(self, box: Bbox) -> np.ndarray | None:
        """The still's RGB pixels (H x W x 3, uint8) inside ``box`` (clipped to the frame), or
        ``None`` without a readable still. The PNG is read once, when first needed."""
        if self._pixels is None:
            if self.still is None:
                return None
            from PIL import Image

            try:
                with Image.open(self.still) as image:
                    self._pixels = np.asarray(image.convert("RGB"))
            except OSError:
                return None
        height, width = self._pixels.shape[:2]
        x0, y0 = max(int(box[0]), 0), max(int(box[1]), 0)
        x1, y1 = min(int(np.ceil(box[2])), width), min(int(np.ceil(box[3])), height)
        return self._pixels[y0:y1, x0:x1]

    @property
    def width(self) -> int:
        return int(self.layout["width"])

    @property
    def height(self) -> int:
        return int(self.layout["height"])

    @property
    def zoomed(self) -> bool:
        """Whether the camera is zoomed in (``zoom`` action): parts of the scene are cut off by
        the frame on purpose."""
        return float(self.frame.get("camera", {}).get("zoom", 1.0)) > 1.001

    @property
    def short_side(self) -> int:
        """The frame's shorter side in px (the height of landscape video): sizes are measured
        against it, so a 480p preview and the 1080p video (and 16:9 and 9:16) agree."""
        return min(self.width, self.height)


@dataclass
class SceneContext:
    """One scene as the ``scene`` (timing) rules see it.

    ``activity`` is the scene's activity file (:mod:`vidgen.activity`: beats with their
    narration times and ``busy`` time, plays, motion), ``audio_dir`` where the beats' MP3s are,
    ``spoken`` beat id -> the text the TTS says (pronunciation applied; a beat not in it is said
    as written), ``language`` the video's language (BCP-47; ``None``: English rules).
    """

    scene_id: str
    activity: dict[str, Any]
    audio_dir: Path
    spoken: dict[str, str] = field(default_factory=dict)
    language: str | None = None

    def spoken_text(self, beat: dict[str, Any]) -> str:
        """What the narrator says for an activity-file beat."""
        return self.spoken.get(beat["id"], beat["text"])

    @property
    def fps(self) -> int:
        return int(self.activity["fps"])

    @property
    def beats(self) -> list[dict[str, Any]]:
        """``[{id, start, end, busy, source, text}]`` in order (empty for a silent scene)."""
        return list(self.activity["beats"])

    def beat_at(self, time: float) -> str | None:
        """The beat on screen at scene time ``time`` (a beat lasts until the next one starts,
        so its pad counts); ``None`` in a silent scene."""
        current = None
        for beat in self.activity["beats"]:
            if beat["start"] <= time + 1e-6:
                current = beat["id"]
        if current is None and self.activity["beats"]:
            return str(self.activity["beats"][0]["id"])
        return current


#: ``check(context, settings) -> issues``; ``settings`` is the rule's model from the config.
Check = Callable[[Any, Any], Iterable[Issue]]


@dataclass(frozen=True)
class Rule:
    """A registered lint rule. ``default`` is the severity of its issues unless they set one."""

    name: str
    scope: Scope
    default: str
    doc: str
    check: Check

    def settings(self, rules_config: Any) -> RuleConfig:
        """This rule's settings from :class:`vidgen.config.LintRules`."""
        return getattr(rules_config, self.name)


#: Every rule, by name, in :data:`vidgen.config.LINT_RULES` order once all are registered.
RULES: dict[str, Rule] = {}


def rule(name: str, *, scope: Scope = "still", default: str = "warning") -> Callable[[Check], Check]:
    """Register ``check`` as the rule ``name`` (its docstring's first line is the rule's doc)."""
    if name not in LINT_RULES:
        raise ValueError(f"lint rule {name!r} is not in vidgen.config.LINT_RULES")
    if default not in SEVERITIES:
        raise ValueError(f"lint rule {name!r}: unknown default severity {default!r}")

    def register(check: Check) -> Check:
        doc = (check.__doc__ or "").strip().splitlines()[0] if check.__doc__ else ""
        RULES[name] = Rule(name, scope, default, doc, check)
        return check

    return register


def severity_rank(severity: str) -> int:
    """0 for ``error``, 1 for ``warning``, 2 for ``info``."""
    return SEVERITIES.index(severity)

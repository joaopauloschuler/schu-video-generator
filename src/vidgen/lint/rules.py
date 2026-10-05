"""The lint rule framework: what a rule is, how it is registered, what it reports.

A rule has a ``name`` (one of :data:`vidgen.config.LINT_RULES`, with a settings model in
:class:`vidgen.config.LintRules`), a ``scope`` saying what it looks at and a ``check`` function
yielding :class:`Issue` objects. The runner (:mod:`vidgen.lint.run`) turns issues into
:class:`~vidgen.lint.findings.Finding` objects (scene, beat, time, still, severity...), applies
the config's severities and ``lint_ignore`` entries and merges repeats.

Scopes: ``still`` rules (:mod:`vidgen.lint.layout_rules`) get a :class:`StillContext`, one per
beat-end still of a scene, built from the layout dump (DESIGN.md §15). Other scopes (e.g. the
timing rules of Step 14, per beat) add their own context type and a branch in the runner; the
report format is the same for all.
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
Scope = Literal["still"]


@dataclass(frozen=True)
class Issue:
    """What a rule's check reports: ``objects`` are the layout objects concerned (none, one, or
    a pair), ``bbox`` the region to look at (output px), ``severity`` overrides the rule's
    default (e.g. an escalation), ``value``/``limit`` the measured number and the threshold.
    Issues of one still with the same ``group`` are reported as one finding (default group: the
    object's parent, e.g. the tick labels of an axis)."""

    message: str
    bbox: Bbox | None
    objects: tuple[dict[str, Any], ...] = ()
    severity: str | None = None
    value: float | None = None
    limit: float | None = None
    group: tuple[Any, ...] | None = None


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
    def short_side(self) -> int:
        """The frame's shorter side in px (the height of landscape video): sizes are measured
        against it, so a 480p preview and the 1080p video (and 16:9 and 9:16) agree."""
        return min(self.width, self.height)


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

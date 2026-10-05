"""``vidgen lint``: automatic checks of a rendered video's layout (DESIGN.md §16).

The rules read the layout dumps of the beat-end stills (:mod:`vidgen.introspect`) and report
:class:`Finding` objects; thresholds and severities come from the config's ``lint:`` section,
per-scene ``lint_ignore`` entries skip findings. Modules: :mod:`.rules` (framework),
:mod:`.layout_rules` (the rules), :mod:`.color` (WCAG contrast), :mod:`.run`
(:func:`lint_project`), :mod:`.findings`, :mod:`.report` (human output).
"""

from __future__ import annotations

from vidgen.lint import layout_rules as _layout_rules  # noqa: F401 - registers the rules
from vidgen.lint.findings import Finding
from vidgen.lint.report import report_lines
from vidgen.lint.rules import RULES, SEVERITIES, Issue, Rule, StillContext, rule
from vidgen.lint.run import FAIL_ON, LintResult, lint_project

__all__ = [
    "FAIL_ON",
    "RULES",
    "SEVERITIES",
    "Finding",
    "Issue",
    "LintResult",
    "Rule",
    "StillContext",
    "lint_project",
    "report_lines",
    "rule",
]

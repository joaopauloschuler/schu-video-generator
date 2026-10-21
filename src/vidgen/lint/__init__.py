"""``vidgen lint``: automatic checks of a rendered video's layout and timing (DESIGN.md §16, §17).

Layout rules read the layout dumps of the beat-end stills (:mod:`vidgen.introspect`), timing
rules each scene's activity file (:mod:`vidgen.activity`); both report
:class:`Finding` objects; thresholds and severities come from the config's ``lint:`` section,
per-scene ``lint_ignore`` entries skip findings. Modules: :mod:`.rules` (framework),
:mod:`.layout_rules`, :mod:`.cartoon_rules`, :mod:`.timing_rules`, :mod:`.readback_rule`, :mod:`.term_rule`, :mod:`.narration_rule` and :mod:`.iso_rule` (the rules), :mod:`.color` (WCAG contrast), :mod:`.run`
(:func:`lint_project`), :mod:`.findings`, :mod:`.report` (human output).
"""

from __future__ import annotations

from vidgen.lint import layout_rules as _layout_rules  # noqa: F401 - registers the rules
from vidgen.lint import cartoon_rules as _cartoon_rules  # noqa: F401, I001 - registers the rules (after the layout ones, as in LINT_RULES)
from vidgen.lint import timing_rules as _timing_rules  # noqa: F401 - registers the rules
from vidgen.lint import readback_rule as _readback_rule  # noqa: F401, I001 - registers the rules (as in LINT_RULES)
from vidgen.lint import term_rule as _term_rule  # noqa: F401, I001 - registers the rule (as in LINT_RULES)
from vidgen.lint import narration_rule as _narration_rule  # noqa: F401, I001 - registers the rules (as in LINT_RULES)
from vidgen.lint import iso_rule as _iso_rule  # noqa: F401, I001 - registers the rule (last, as in LINT_RULES)
from vidgen.lint.findings import Finding
from vidgen.lint.report import report_lines
from vidgen.lint.rules import RULES, SEVERITIES, Issue, Rule, SceneContext, StillContext, rule
from vidgen.lint.run import FAIL_ON, LintResult, lint_project

__all__ = [
    "FAIL_ON",
    "RULES",
    "SEVERITIES",
    "Finding",
    "Issue",
    "LintResult",
    "Rule",
    "SceneContext",
    "StillContext",
    "lint_project",
    "report_lines",
    "rule",
]

"""``vidgen plan`` output: the draft as a commented ``video.yaml`` and a project folder (DESIGN.md §61).

:func:`plan_yaml` writes the config by hand rather than with a YAML dumper, so that every scene
can carry its ``# plan:`` reason and ``# TODO:`` lines and the layout reads like the examples
(short lists inline, code as a literal block); the text is checked to load back to exactly
:func:`plan_config`. :func:`write_plan` scaffolds the project like ``vidgen init`` (when the
target is a folder), copies the pictures the outline names into ``assets/`` and writes the
config. No manim import.
"""

from __future__ import annotations

import json
import re
import shutil
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from vidgen.errors import VidgenError
from vidgen.fileio import write_text_atomic
from vidgen.plan import CHAPTER_SECONDS, Plan

#: Final and preview sizes per ``--format``.
FORMATS: dict[str, tuple[dict[str, int], dict[str, int]]] = {
    "16:9": ({"width": 1920, "height": 1080, "fps": 30}, {"width": 854, "height": 480, "fps": 15}),
    "9:16": ({"width": 1080, "height": 1920, "fps": 30}, {"width": 480, "height": 854, "fps": 15}),
}
#: The init template's voice (ElevenLabs "Brian", multilingual model).
VOICE: dict[str, str] = {"provider": "elevenlabs", "voice_id": "nPczCjzI2devNBz1zQrb", "model_id": "eleven_multilingual_v2"}
#: Longest line of an inline (flow) list or mapping.
FLOW_WIDTH = 96
_PLAIN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_RESERVED = frozenset({"y", "n", "yes", "no", "on", "off", "true", "false", "null"})


def plan_config(plan: Plan, fmt: str = "16:9", preset: str = "dark_tech") -> dict[str, Any]:
    """The ``video.yaml`` content of ``plan`` (``fmt``: ``16:9`` or ``9:16``; ``preset``: the
    theme preset)."""
    final, preview = FORMATS[fmt]
    config: dict[str, Any] = {"title": plan.title}
    if plan.language:
        config["language"] = plan.language
    config |= {
        "format": dict(final),
        "preview": dict(preview),
        "theme": {"preset": preset},
        "voice": dict(VOICE),
        "narration": {"pad": 0.35},
    }
    if plan.chapters:
        config["overlays"] = [{"type": "progress_bar"}]
    config["scenes"] = [scene.config() for scene in plan.scenes]
    return config


def _scalar(value: Any) -> str:
    """A YAML scalar: plain words unquoted, text double-quoted (single-quoted with backslashes)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = repr(value)
        if "e" in text and "." not in text.split("e")[0]:  # YAML 1.1 floats need a dot: 1.0e-07
            mantissa, exponent = text.split("e")
            text = f"{mantissa}.0e{exponent}"
        return text
    text = str(value)
    if _PLAIN.match(text) and text.lower() not in _RESERVED:
        return text
    if "\\" in text and "\n" not in text:
        return "'" + text.replace("'", "''") + "'"
    return json.dumps(text, ensure_ascii=False)


def _flow(value: Any) -> str | None:
    """``value`` as one inline YAML expression, or ``None`` when it does not fit on a line."""
    if isinstance(value, dict):
        inner = {k: _flow(v) for k, v in value.items()}
        if any(v is None for v in inner.values()):
            return None
        text = "{" + ", ".join(f"{_scalar(k)}: {v}" for k, v in inner.items()) + "}"
    elif isinstance(value, list):
        inner = [_flow(v) for v in value]
        if any(i is None for i in inner):
            return None
        text = "[" + ", ".join(i for i in inner if i is not None) + "]"
    elif isinstance(value, str) and "\n" in value:
        return None
    else:
        return _scalar(value)
    return text if len(text) <= FLOW_WIDTH else None


def _literal(text: str, indent: int) -> list[str]:
    """A multi-line string as a literal block (``|-``) at ``indent`` spaces, two more than its key
    or list dash (the indentation indicator, needed when the first line starts with a space,
    counts from there)."""
    pad = " " * indent
    marker = "|2-" if text[:1] in (" ", "\t") else "|-"
    return [marker, *(f"{pad}{line}" if line else "" for line in text.split("\n"))]


def _block(value: Any, indent: int) -> list[str]:
    """``value`` (a mapping or a list) as block YAML lines at ``indent`` spaces."""
    pad = " " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            lines.extend(_entry(f"{pad}{_scalar(key)}:", item, indent))
        return lines
    for item in value:
        flow = _flow(item) if not isinstance(item, dict) or 2 <= len(item) <= 3 else None
        if flow is not None and not (isinstance(item, str) and "\n" in item):
            lines.append(f"{pad}- {flow}")
        elif isinstance(item, dict):
            sub = _block(item, indent + 2)
            sub[0] = f"{pad}- {sub[0][indent + 2 :]}"
            lines.extend(sub)
        elif isinstance(item, str):
            literal = _literal(item, indent + 2)
            lines.append(f"{pad}- {literal[0]}")
            lines.extend(literal[1:])
        else:
            sub = _block(item, indent + 2)
            sub[0] = f"{pad}- {sub[0][indent + 2 :]}"
            lines.extend(sub)
    return lines


def _entry(head: str, value: Any, indent: int) -> list[str]:
    """``key: value`` lines: inline when it fits, else nested."""
    if isinstance(value, str) and "\n" in value:
        literal = _literal(value, indent + 2)
        return [f"{head} {literal[0]}", *literal[1:]]
    if not isinstance(value, (dict, list)) or not value:
        return [f"{head} {_flow(value) if isinstance(value, (dict, list)) else _scalar(value)}"]
    flow = _flow(value)
    if flow is not None and (not isinstance(value, list) or not any(isinstance(v, dict) for v in value)):
        return [f"{head} {flow}"]
    return [head, *_block(value, indent + 2)]


def _comment(prefix: str, text: str, indent: int, width: int = 100) -> list[str]:
    """A comment ``# prefix text`` wrapped at ``width``."""
    pad = " " * indent
    return textwrap.wrap(
        f"{prefix} {text}", width, initial_indent=f"{pad}# ", subsequent_indent=f"{pad}#   ", break_long_words=False, break_on_hyphens=False
    )


def plan_yaml(plan: Plan, fmt: str = "16:9", preset: str = "dark_tech", source: str = "") -> str:
    """The commented ``video.yaml`` of ``plan`` (see the module doc)."""
    config = plan_config(plan, fmt, preset)
    origin = f" from {source}" if source else ""
    out = [
        f"# Draft written by `vidgen plan`{origin}: a deterministic starting point, not a finished video.",
        "# Every scene says why it got its type (plan) and what to check (TODO). Refine the",
        "# narration and the on-screen texts, then: vidgen validate, vidgen storyboard, vidgen lint.",
        "# How to make a good video (pacing, scene types): `vidgen guide` (AGENTS.md)",
    ]
    for note in plan.notes:
        out.extend(_comment("TODO:", note, 0))
    for key, value in config.items():
        if key == "scenes":
            continue
        if key == "overlays":
            out.append(f"# plan: narration over {CHAPTER_SECONDS / 60:.0f} minutes -> chapter cards and a progress bar")
        out.extend(_entry(f"{key}:", value, 0))
    out.append("")
    out.append("scenes:")
    for scene, entry in zip(plan.scenes, config["scenes"]):
        if scene.reason:
            out.extend(_comment("plan:", scene.reason, 2))
        for todo in scene.todos:
            out.extend(_comment("TODO:", todo, 2))
        out.extend(_block([entry], 2))
        out.append("")
    text = "\n".join(out).rstrip("\n") + "\n"
    loaded = yaml.safe_load(text)
    if loaded != config:  # a bug in the writer, never the user's fault
        raise AssertionError("vidgen plan wrote YAML that does not load back to the planned config")
    return text


@dataclass
class PlanResult:
    """What :func:`write_plan` wrote: the project ``root``, the ``config`` file, the copied
    ``assets`` (project paths) and whether it scaffolded a new project (``created``)."""

    root: Path
    config: Path
    assets: list[str] = field(default_factory=list)
    created: bool = False


def write_plan(plan: Plan, output: Path, *, fmt: str = "16:9", preset: str = "dark_tech", source: str = "", force: bool = False) -> PlanResult:
    """Write ``plan`` to ``output``: a folder (scaffolded like ``vidgen init`` when new or empty;
    its ``video.yaml``) or a ``.yaml`` / ``.yml`` file. An existing config is replaced only with
    ``force``; pictures go to ``assets/`` beside the config."""
    from vidgen.cli import scaffold_project

    if output.suffix.lower() in (".yaml", ".yml"):
        config_file, root = output, output.parent
        if config_file.exists() and not force:
            raise VidgenError(f"{config_file} already exists (use --force to replace it)")
        root.mkdir(parents=True, exist_ok=True)
        created = False
    else:
        root = output
        config_file = root / "video.yaml"
        if root.exists() and not root.is_dir():
            raise VidgenError(f"{root} exists and is not a folder")
        empty = not root.exists() or not any(root.iterdir())
        if not empty and not force:
            raise VidgenError(f"{root} already exists and is not empty (use --force to write its video.yaml anyway)")
        created = empty
        if empty:
            scaffold_project(root)
    text = plan_yaml(plan, fmt, preset, source)
    copied = []
    for rel, src in plan.assets.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or force:
            shutil.copyfile(src, target)
        copied.append(rel)
    write_text_atomic(config_file, text)
    return PlanResult(root, config_file, copied, created)

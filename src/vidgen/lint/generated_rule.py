"""``generated_footage`` (DESIGN.md §113.4): a reminder, on each scene that shows generated video
takes, that platforms ask for AI-generated realistic footage to be disclosed when publishing
(YouTube's "altered or synthetic content" setting, TikTok's AI-generated label). The film's
description file already carries "Includes AI-generated footage (models)."."""

from __future__ import annotations

from collections.abc import Iterator

from vidgen.config import GeneratedFootageRule
from vidgen.lint.rules import Issue, SceneContext, rule


@rule("generated_footage", scope="scene", default="info")
def generated_footage(ctx: SceneContext, settings: GeneratedFootageRule) -> Iterator[Issue]:
    """The scene shows generated takes."""
    if not ctx.generated:
        return
    shots = ", ".join(f"{shot} (take {take}, {model})" for shot, take, model in ctx.generated)
    yield Issue(
        f"shows AI-generated footage: {shots}; when publishing, disclose it where the platform asks (YouTube: "
        "'Altered or synthetic content'; TikTok: the AI-generated label); the description file says so already",
        None,
    )

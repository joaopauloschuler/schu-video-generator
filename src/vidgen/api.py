"""The public surface for project extensions and built-in scenes (DESIGN.md §6.4).

Use ``from vidgen.api import *``: it gives every name of ``from manim import *`` plus the vidgen
names below. Where a manim name and a vidgen name collide, vidgen wins; the only collision is
``scene`` (manim's ``manim.scene`` subpackage, shadowed by vidgen's ``@scene`` decorator).
Anything not exported here is internal and may change.
"""

from __future__ import annotations

_before = set(globals())
from manim import *  # noqa: E402,F403

_MANIM_NAMES = frozenset(n for n in set(globals()) - _before if not n.startswith("_"))
del _before

from pydantic import Field, field_validator, model_validator  # noqa: E402

from vidgen.actions import Action, ActionOptions, Target  # noqa: E402
from vidgen.callouts import (  # noqa: E402
    CALLOUT_KINDS,
    Callout,
    CalloutArea,
    callout,
    callout_area,
    callout_arrow,
    callout_box,
    callout_circle,
    callout_label,
    callout_magnifier,
    callout_spotlight,
    label_spot,
)
from vidgen.clips import CLIP_SUFFIXES, ClipInfo, ClipMobject, ClipTiming, clip_audio, fit_speed, probe_clip  # noqa: E402
from vidgen.cues import CaptionCue, caption_cues, phrase_break_cost, segment_cues  # noqa: E402
from vidgen.charts import (  # noqa: E402
    CHART_MARKERS,
    ChartAxes,
    ChartAxis,
    ColorScale,
    LinearFit,
    auto_legend,
    axis_ticks,
    chart_axes,
    chart_caption,
    chart_label_size,
    chart_legend,
    chart_marker,
    chart_title,
    color_bar,
    color_scale,
    legend_spot,
    linear_fit,
    mix_colors,
    plate_contrast,
    sample_path,
    short_number,
    text_color_on,
    tick_texts,
    value_axis,
)
from vidgen.errors import VidgenError  # noqa: E402
from vidgen.geo import MAP_VIEWS, Country, MapView, equal_earth, find_country, fit_view, view_box, world_countries  # noqa: E402
from vidgen.graph import EdgeRoute, GraphEdge, GraphLayout, GraphNode, NodePlace, layered_layout  # noqa: E402
from vidgen.helpers import MT, Fade, T, column, counter, dense_pairs, edges, fade_out, group_bounds, grouped_pairs, resolve_color, sparse_pairs  # noqa: E402
from vidgen.hooks import HookContext, hook  # noqa: E402
from vidgen.icon_mobject import Icon, icon  # noqa: E402
from vidgen.layout import (  # noqa: E402
    auto_format,
    check_format,
    distribute,
    fit_text,
    format_value,
    latex_available,
    measure_text,
    nice_ticks,
    normalize_text,
    require_latex,
    shrink_to_fit,
    wrap_lines,
)
from vidgen.regions import (  # noqa: E402
    Region,
    frame_region,
    grid,
    grid_shape,
    orientation,
    place,
    readable_size,
    readable_text,
    region,
    safe_area,
)
from vidgen.overlays import Overlay, OverlayContext, OverlayOptions, with_opacity  # noqa: E402
from vidgen.registry import action, overlay, scene  # noqa: E402
from vidgen.runtime import current_project, current_theme  # noqa: E402
from vidgen.scene import IconName, NarratedScene, SceneParams, ThemeColor, ThemeSize, one_or_many  # noqa: E402
from vidgen.pronunciation import Pronunciation, Spoken  # noqa: E402
from vidgen.config import SfxParams  # noqa: E402
from vidgen.sfx import SfxEvent, SoundLibrary, sound_library, synthesize  # noqa: E402
from vidgen.speech import WordTime, beat_word_times, estimate_word_times, map_word_times, speech_bounds, spoken_words, syllables  # noqa: E402
from vidgen.videoplan import Chapter, video_chapters  # noqa: E402
from vidgen.carry import carry_move  # noqa: E402
from vidgen.voices import speaker_color, speaker_label, speaker_prefix  # noqa: E402
from vidgen.translation import TextRef, TranslatableStr  # noqa: E402
from vidgen.languages import LanguageRules, language_rules  # noqa: E402
from vidgen.imagegen import GenerateImage, generated_image  # noqa: E402
from vidgen.vector_mobject import VectorPicture, load_vector  # noqa: E402
from vidgen.cartoon.character import PART_NAMES, Character, CharacterPart, CharacterState, PartPose, character  # noqa: E402
from vidgen.cartoon.transition import Gesture, Jump, KeyedMotion, PoseChange, Walk, feet_of  # noqa: E402
from vidgen.cartoon.visemes import VISEMES, VisemeCue, VisemeTrack  # noqa: E402
from vidgen.cartoon.cast import beat_voice, part_target_names, pose_name_problem, say_problem, speaking_characters  # noqa: E402
from vidgen.cartoon.acting import (  # noqa: E402
    GESTURE_SECONDS,
    GESTURES,
    JUMP_HEIGHT,
    JUMP_SECONDS,
    WALK_SPEED,
    LookPose,
    camera_look,
    enter_path,
    exit_path,
    look_pose,
    nearer_side,
    offstage_x,
    walk_seconds,
)
from vidgen.cartoon.motion import MOTION_LEVELS, jump_motion_seconds, walk_motion_seconds  # noqa: E402
from vidgen.cartoon.spring import Spring  # noqa: E402
from vidgen.cartoon.foley import FoleyCue, PlayedAction, foley_cues  # noqa: E402
from vidgen.cartoon.keyframes import (  # noqa: E402
    CHANNELS,
    DEFAULT_EASE,
    EASE_NAMES,
    EaseName,
    Key,
    KeyFrame,
    MotionPath,
    ease_progress,
    key_seconds,
    key_time_problems,
    keyed_values,
    path_length,
)
from vidgen.config import MotionSetting  # noqa: E402
from vidgen.cartoon.props import PROP_HEIGHTS, PROP_KINDS, PROP_LIFTS, SVG_PROP_HEIGHT, Prop, draw_prop, svg_prop  # noqa: E402
from vidgen.cartoon.stage import (  # noqa: E402
    DEFAULT_FACTORS,
    LAYER_PLACES,
    MARKS,
    StageItem,
    StagePlacement,
    facing_towards_centre,
    feet_point,
    ground_top,
    layer_half_extent,
    layer_transform,
    mark_x,
    stage_layout,
)
from vidgen.camera import view_center_within  # noqa: E402
from vidgen.particles import MAX_PARTICLES, PARTICLE_KINDS, particle_count, particle_seeds, particle_states  # noqa: E402
from vidgen.particle_field import ParticleField, ParticleKindName, ParticleSettings, particle_field  # noqa: E402
from vidgen.scene import CharacterName  # noqa: E402


def register_theme_defaults(colors: dict[str, str] | None = None, sizes: dict[str, float] | None = None) -> None:
    """Add default theme tokens for this project (``video.yaml`` values still win).

    Call at module level in an extension: ``register_theme_defaults({"k2": "#F2A541"})``.
    """
    current_theme().add_defaults(colors=colors, sizes=sizes)


def register_theme_preset(
    name: str,
    *,
    base: str | None = None,
    background: str | None = None,
    font: str | None = None,
    colors: dict[str, str] | None = None,
    palette: list[str] | None = None,
    sizes: dict[str, float] | None = None,
    code_style: str | None = None,
    description: str = "",
    scale: str | None = None,
    fonts: dict[str, str] | None = None,
    font_serif: str | None = None,
    font_mono: str | None = None,
) -> None:
    """Add a project theme preset, selectable with ``theme: {preset: NAME}`` (DESIGN.md §19-20).

    Values left out come from ``base`` (a built-in or earlier registered preset), else from the
    defaults; ``video.yaml`` values still win. ``scale`` is a type scale (``compact``,
    ``standard``, ``large``, ``auto``) applied below ``sizes``; ``font`` / ``font_serif`` /
    ``font_mono`` are the sans / serif / mono families and ``fonts`` maps font roles
    (``heading``, ``quote``, ``code``...) to ``sans``, ``serif``, ``mono`` or a family name, read
    by ``current_theme().font_for(role)``. Call at module
    level in an extension, e.g.
    ``register_theme_preset("acme", base="light_academic", colors={"primary": "#0B5FFF"})``.
    """
    import sys

    from vidgen._origin import origin_of
    from vidgen.presets import make_preset

    preset = make_preset(
        name,
        description=description,
        base=base,
        background=background,
        font=font,
        font_serif=font_serif,
        font_mono=font_mono,
        code_style=code_style,
        colors=colors,
        palette=palette,
        sizes=sizes,
        scale=scale,
        fonts=fonts,
        origin=origin_of(sys._getframe(1).f_globals.get("__name__", "")),
    )
    current_theme().add_preset(preset)


VIDGEN_NAMES: tuple[str, ...] = (
    "NarratedScene",
    "SceneParams",
    "scene",
    "action",
    "Action",
    "ActionOptions",
    "Target",
    "overlay",
    "Overlay",
    "OverlayOptions",
    "OverlayContext",
    "with_opacity",
    "Chapter",
    "video_chapters",
    "carry_move",
    "hook",
    "HookContext",
    "register_theme_defaults",
    "register_theme_preset",
    "current_theme",
    "current_project",
    "VidgenError",
    "T",
    "MT",
    "resolve_color",
    "column",
    "edges",
    "dense_pairs",
    "grouped_pairs",
    "group_bounds",
    "sparse_pairs",
    "counter",
    "Fade",
    "fade_out",
    "ThemeColor",
    "ThemeSize",
    "fit_text",
    "measure_text",
    "wrap_lines",
    "normalize_text",
    "shrink_to_fit",
    "distribute",
    "nice_ticks",
    "auto_format",
    "format_value",
    "check_format",
    "latex_available",
    "require_latex",
    "Region",
    "frame_region",
    "safe_area",
    "region",
    "grid",
    "grid_shape",
    "place",
    "orientation",
    "readable_size",
    "readable_text",
    "icon",
    "Icon",
    "IconName",
    "TranslatableStr",
    "TextRef",
    "LanguageRules",
    "language_rules",
    "one_or_many",
    "layered_layout",
    "GraphLayout",
    "GraphNode",
    "GraphEdge",
    "EdgeRoute",
    "NodePlace",
    "CHART_MARKERS",
    "ChartAxes",
    "ChartAxis",
    "LinearFit",
    "auto_legend",
    "axis_ticks",
    "chart_axes",
    "chart_caption",
    "chart_label_size",
    "chart_legend",
    "chart_marker",
    "chart_title",
    "legend_spot",
    "linear_fit",
    "sample_path",
    "short_number",
    "tick_texts",
    "value_axis",
    "ColorScale",
    "color_scale",
    "color_bar",
    "mix_colors",
    "text_color_on",
    "plate_contrast",
    "CaptionCue",
    "caption_cues",
    "phrase_break_cost",
    "segment_cues",
    "WordTime",
    "beat_word_times",
    "estimate_word_times",
    "speech_bounds",
    "spoken_words",
    "syllables",
    "map_word_times",
    "Pronunciation",
    "Spoken",
    "speaker_color",
    "speaker_label",
    "speaker_prefix",
    "SfxEvent",
    "SfxParams",
    "SoundLibrary",
    "sound_library",
    "synthesize",
    "CALLOUT_KINDS",
    "Callout",
    "CalloutArea",
    "callout",
    "callout_area",
    "callout_arrow",
    "callout_box",
    "callout_circle",
    "callout_label",
    "callout_magnifier",
    "callout_spotlight",
    "label_spot",
    "CLIP_SUFFIXES",
    "ClipInfo",
    "ClipMobject",
    "ClipTiming",
    "clip_audio",
    "fit_speed",
    "probe_clip",
    "MAP_VIEWS",
    "Country",
    "MapView",
    "equal_earth",
    "find_country",
    "fit_view",
    "view_box",
    "world_countries",
    "GenerateImage",
    "generated_image",
    "VectorPicture",
    "load_vector",
    "PART_NAMES",
    "Character",
    "CharacterName",
    "CharacterPart",
    "CharacterState",
    "PartPose",
    "PoseChange",
    "VISEMES",
    "VisemeCue",
    "VisemeTrack",
    "character",
    "pose_name_problem",
    "beat_voice",
    "say_problem",
    "speaking_characters",
    "LookPose",
    "camera_look",
    "look_pose",
    "GESTURES",
    "GESTURE_SECONDS",
    "JUMP_HEIGHT",
    "JUMP_SECONDS",
    "WALK_SPEED",
    "Gesture",
    "Jump",
    "Walk",
    "enter_path",
    "exit_path",
    "nearer_side",
    "offstage_x",
    "walk_seconds",
    "MOTION_LEVELS",
    "MotionSetting",
    "jump_motion_seconds",
    "walk_motion_seconds",
    "Spring",
    "FoleyCue",
    "PlayedAction",
    "foley_cues",
    "CHANNELS",
    "DEFAULT_EASE",
    "EASE_NAMES",
    "EaseName",
    "Key",
    "KeyFrame",
    "KeyedMotion",
    "MotionPath",
    "ease_progress",
    "feet_of",
    "key_seconds",
    "key_time_problems",
    "keyed_values",
    "part_target_names",
    "path_length",
    "feet_point",
    "ground_top",
    "MARKS",
    "StageItem",
    "StagePlacement",
    "facing_towards_centre",
    "mark_x",
    "stage_layout",
    "DEFAULT_FACTORS",
    "LAYER_PLACES",
    "layer_half_extent",
    "layer_transform",
    "PROP_HEIGHTS",
    "PROP_KINDS",
    "PROP_LIFTS",
    "SVG_PROP_HEIGHT",
    "Prop",
    "draw_prop",
    "svg_prop",
    "view_center_within",
    "PARTICLE_KINDS",
    "MAX_PARTICLES",
    "ParticleField",
    "ParticleKindName",
    "ParticleSettings",
    "particle_count",
    "particle_field",
    "particle_seeds",
    "particle_states",
    "Field",
    "field_validator",
    "model_validator",
)

#: manim names replaced by a vidgen name of the same spelling.
SHADOWED_MANIM_NAMES = frozenset(_MANIM_NAMES & set(VIDGEN_NAMES))

__all__ = sorted(_MANIM_NAMES | set(VIDGEN_NAMES))

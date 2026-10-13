"""How clearly two generated characters differ (DESIGN.md §69.49). No manim.

:func:`contrast_score` is a pure function of two :class:`LookFeatures`: a weighted sum
(:data:`WEIGHTS`) of three parts, each from 0 (the same) to 1 (fully different):

- **silhouette** (:data:`SILHOUETTE_WEIGHTS`): body shape, proportions, head size, species (half
  as different within a :data:`SPECIES_FAMILIES` family), ears, hair style, what is worn on the
  head (hat, cap, bow) and a skirt or coat tails;
- **colour** (:data:`COLOUR_WEIGHTS`): the CIEDE2000 difference (CIELAB, the theme's tokens
  resolved) of the clothes, skin (fur), hair and accessory colours, each divided by
  :data:`COLOUR_SPAN` and capped at 1;
- **accessories**: the share of the small things (accessories, facial hair, pattern, shoes,
  eyes, nose) that only one of them has (Jaccard distance; neither has any: 0).

:func:`compare` adds what the two share and what to change; :func:`character_pairs` compares
every two characters of a video, for the lint rule ``look_alike``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import TYPE_CHECKING, Any

from vidgen.config import HEX_COLOR_PATTERN, CharacterColors, CharacterLook, LookAlikeRule
from vidgen.errors import VidgenError
from vidgen.lint.color import delta_e, hex_rgb, lab

if TYPE_CHECKING:
    from vidgen.config import VideoConfig
    from vidgen.theme import Theme

#: Weight of each part of the score (they add up to 1).
WEIGHTS: dict[str, float] = {"silhouette": 0.45, "colour": 0.4, "accessories": 0.15}
#: Weight of each silhouette feature within the silhouette part (they add up to 1).
SILHOUETTE_WEIGHTS: dict[str, float] = {
    "body": 0.25, "hair": 0.2, "species": 0.15, "headwear": 0.1, "proportions": 0.1, "head_size": 0.1, "ears": 0.05, "outfit": 0.05,
}
#: Weight of each colour within the colour part (they add up to 1): bigger areas weigh more.
COLOUR_WEIGHTS: dict[str, float] = {"clothes": 0.4, "skin": 0.3, "hair": 0.2, "accessory": 0.1}
#: CIEDE2000 difference from which two colours count as fully different.
COLOUR_SPAN = 30.0
#: Head sizes this far apart count as fully different.
HEAD_SIZE_SPAN = 0.4
#: Below this score two characters look too alike (lint ``look_alike``'s default ``min_contrast``;
#: ``vidgen cast --random`` and ``vidgen screenplay`` keep their picks above it when they can).
MIN_CONTRAST: float = LookAlikeRule.model_fields["min_contrast"].default
#: Colours closer than this (CIEDE2000) are named as shared in :func:`compare`'s advice.
CLOSE_COLOUR = 10.0
#: Accessories that change the outline of the head (with the costume pieces worn there, §69.58).
HEADWEAR: tuple[str, ...] = ("hat", "cap", "bow", "crown", "wizard_hat", "party_hat")
#: What to change, per shared feature, in :func:`compare`'s advice.
_FIXES: dict[str, str] = {
    "body": "look.body", "hair": "look.hair", "species": "look.species", "headwear": "a hat, cap, bow or crown",
    "proportions": "look.proportions", "head_size": "look.head_size", "ears": "look.ears", "outfit": "look.outfit",
    "clothes": "colors.clothes", "skin": "colors.skin", "hair colour": "colors.hair", "accessory": "colors.accessory",
}

#: Species whose outlines are alike (a beak and a round head; tall pointed ears): two of one
#: family differ in ``species`` by :data:`SPECIES_FAMILY_DIFFERENCE`, not 1.
SPECIES_FAMILIES: dict[str, str] = {"bird": "beaked", "owl": "beaked", "penguin": "beaked", "cat": "pointed ears", "fox": "pointed ears"}
SPECIES_FAMILY_DIFFERENCE = 0.5

#: Silhouette values not named as shared in :func:`compare`'s advice (most characters have them).
_UNREMARKABLE: dict[str, Any] = {"ears": "none", "outfit": "plain", "headwear": "none", "species": "human", "proportions": "adult", "head_size": 1.0}

Lab = tuple[float, float, float]


@dataclass(frozen=True)
class LookFeatures:
    """What :func:`contrast_score` compares of one generated look: silhouette values, the four
    colours (``#hex``, or a token the theme does not know) with their CIELAB values, and the set
    of small details (``"glasses"``, ``"pattern stripes"``...)."""

    silhouette: dict[str, Any]
    colors: dict[str, str]
    details: frozenset[str]
    labs: dict[str, Lab | None] = field(default_factory=dict)


def look_features(look: CharacterLook | Mapping[str, Any], colors: CharacterColors | Mapping[str, Any], theme: Theme | None = None) -> LookFeatures | None:
    """The :class:`LookFeatures` of a generated look (``None`` for an ``svg`` look); colour
    tokens are resolved with ``theme`` (none: only ``#hex`` colours are compared by value)."""
    look = look if isinstance(look, CharacterLook) else CharacterLook.model_validate(dict(look))
    colors = colors if isinstance(colors, CharacterColors) else CharacterColors.model_validate(dict(colors))
    if look.svg is not None:
        return None
    worn = set(look.accessories)
    silhouette = {
        "body": look.body, "proportions": look.proportions, "head_size": look.head_size, "species": look.species,
        "ears": look.ears, "hair": look.hair, "headwear": next((a for a in HEADWEAR if a in worn), "none"),
        "outfit": look.outfit if look.outfit in ("dress", "coat") else "plain",
    }
    details = {a for a in worn if a not in HEADWEAR}
    details |= {f"{key} {getattr(look, key)}" for key in ("facial_hair", "pattern", "shoes") if getattr(look, key) != "none"}
    details |= {f"eyes {look.eyes}", *([f"nose {look.nose}"] if look.nose != "none" else [])}
    if look.species == "robot":   # two robots differ by their build (§69.58)
        robot = look.robot_look()
        details |= {f"robot head {robot.head}", f"robot face {robot.face}", f"robot on {robot.moves_on}", *(["antenna"] if robot.antenna else [])}
    resolved = {key: _resolve(getattr(colors, key), theme) for key in ("clothes", "skin", "hair", "accessory")}
    if look.hair == "none" and look.facial_hair == "none" and look.species != "turtle":
        resolved["hair"] = resolved["skin"]          # a bald head shows skin (a turtle's shell is in the hair colour)
    if not worn and look.shoes == "none":
        resolved["accessory"] = resolved["clothes"]  # no accessory colour is drawn
    labs = {key: lab(hex_rgb(value)) if _is_hex(value) else None for key, value in resolved.items()}
    return LookFeatures(silhouette, resolved, frozenset(details), labs)


def _is_hex(value: str) -> bool:
    return re.fullmatch(HEX_COLOR_PATTERN, value) is not None


def _resolve(value: str, theme: Theme | None) -> str:
    if theme is None or value.startswith("#"):
        return value
    try:
        return theme.color(value)
    except VidgenError:  # an unknown token: compared by name (validate reports it)
        return value


def colour_difference(a: LookFeatures, b: LookFeatures, key: str) -> float:
    """CIEDE2000 difference of colour ``key`` of two looks (unresolved tokens: 0 when the same
    name, else :data:`COLOUR_SPAN`)."""
    lab_a, lab_b = a.labs.get(key), b.labs.get(key)
    if lab_a is None or lab_b is None:
        return 0.0 if a.colors[key] == b.colors[key] else COLOUR_SPAN
    return delta_e(lab_a, lab_b)


def species_difference(a: str, b: str) -> float:
    """How different two species' outlines are: 0 the same, :data:`SPECIES_FAMILY_DIFFERENCE`
    for two of one :data:`SPECIES_FAMILIES` family (a bird and an owl), else 1."""
    if a == b:
        return 0.0
    family = SPECIES_FAMILIES.get(a)
    return SPECIES_FAMILY_DIFFERENCE if family is not None and family == SPECIES_FAMILIES.get(b) else 1.0


def contrast_parts(a: LookFeatures, b: LookFeatures) -> dict[str, float]:
    """``{silhouette, colour, accessories}``, each 0 (the same) to 1 (fully different)."""
    silhouette = 0.0
    for key, weight in SILHOUETTE_WEIGHTS.items():
        if key == "head_size":
            silhouette += weight * min(abs(a.silhouette[key] - b.silhouette[key]) / HEAD_SIZE_SPAN, 1.0)
        elif key == "species":
            silhouette += weight * species_difference(a.silhouette[key], b.silhouette[key])
        else:
            silhouette += weight * (a.silhouette[key] != b.silhouette[key])
    colour = sum(weight * min(colour_difference(a, b, key) / COLOUR_SPAN, 1.0) for key, weight in COLOUR_WEIGHTS.items())
    union = a.details | b.details
    accessories = len(a.details ^ b.details) / len(union) if union else 0.0
    return {"silhouette": silhouette, "colour": colour, "accessories": accessories}


def contrast_score(a: LookFeatures, b: LookFeatures) -> float:
    """How clearly two looks differ: 0 (the same) to 1; :data:`WEIGHTS` of :func:`contrast_parts`."""
    parts = contrast_parts(a, b)
    return sum(WEIGHTS[key] * value for key, value in parts.items())


@dataclass(frozen=True)
class PairContrast:
    """Two characters compared: their ``score``, its ``parts``, the features they share (most
    weighty first) and ``advice``: what to change on one of them."""

    first: str
    second: str
    score: float
    parts: dict[str, float]
    shared: list[str]
    advice: str

    def message(self, minimum: float) -> str:
        """The lint message of a pair scoring below ``minimum``."""
        shared = f": both have {', '.join(self.shared)}" if self.shared else ""
        return (f"characters '{self.first}' and '{self.second}' look alike (contrast {self.score:.2f}, needs {minimum:g}){shared}; "
                f"{self.advice}")


def compare(first: str, a: LookFeatures, second: str, b: LookFeatures) -> PairContrast:
    """:class:`PairContrast` of characters ``first`` and ``second``."""
    shared: list[tuple[float, str, str]] = []   # (weight in the score, text, feature)
    for key, weight in SILHOUETTE_WEIGHTS.items():
        value = a.silhouette[key]
        same = abs(value - b.silhouette[key]) < 0.1 if key == "head_size" else value == b.silhouette[key]
        if same and _UNREMARKABLE.get(key) != value:
            shown = f"head_size {value:g}" if key == "head_size" else f"{key} {value}"
            shared.append((WEIGHTS["silhouette"] * weight, shown, key))
    for key, weight in COLOUR_WEIGHTS.items():
        difference = colour_difference(a, b, key)
        if difference < CLOSE_COLOUR:
            shared.append((WEIGHTS["colour"] * weight, f"{key} colours close (ΔE {difference:.0f})", "hair colour" if key == "hair" else key))
    shared.sort(key=lambda item: -item[0])
    fixes = [_FIXES[feature] for _, _, feature in shared[:3]]
    advice = f"give '{second}' another {', '.join(fixes)}" if fixes else f"give '{second}' another look.body, look.hair or colors.clothes"
    return PairContrast(first, second, contrast_score(a, b), contrast_parts(a, b), [text for _, text, _ in shared], advice)


def min_contrast(candidate: LookFeatures, others: Sequence[LookFeatures]) -> float:
    """The lowest :func:`contrast_score` of ``candidate`` against ``others`` (none: 1)."""
    return min((contrast_score(candidate, other) for other in others), default=1.0)


def character_pairs(config: VideoConfig, theme: Theme | None) -> list[tuple[str, PairContrast]]:
    """``(scene id, pair)`` for each two generated characters on the video's stages (in the
    order they first appear), with the scene where the later of the two first appears
    (characters drawn from an SVG file are not compared)."""
    entries = {entry.name: entry for entry in config.characters}
    first_scene: dict[str, str] = {}
    for scene in config.scenes:
        for member in scene.params.get("characters") or []:
            name = member if isinstance(member, str) else member.get("name") if isinstance(member, Mapping) else None
            if isinstance(name, str) and name in entries:
                first_scene.setdefault(name, scene.id)
    features = {name: look_features(entries[name].look, entries[name].colors, theme) for name in first_scene}
    order = list(first_scene)
    found = []
    for x, y in combinations(order, 2):
        fx, fy = features[x], features[y]
        if fx is None or fy is None:
            continue
        found.append((first_scene[y], compare(x, fx, y, fy)))
    return found

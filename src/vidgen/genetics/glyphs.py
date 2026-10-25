"""Which flat picture shows a phenotype (DESIGN.md §96.7): a pea (round or wrinkled, yellow or
green), a flower (its petal colour), an eye, a fruit fly (body colour, wings, eye colour), an
animal's coat, a feather, a squash fruit (colour, shape), a blood drop with the ABO group, a seed
capsule, an affected / unaffected mark, or a plain colour swatch. Chosen from the trait's name and
the phenotype's words, so authors get pictures without asking; the scene draws them
(``scenes/cross_draw.py``). No manim."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Colours of phenotype words (flat, readable on light and dark backgrounds with an outline).
COLOURS: dict[str, str] = {
    "yellow": "#F2C230", "green": "#6BAA3A", "red": "#D9433B", "pink": "#EE8FB0", "white": "#F4F1EA",
    "purple": "#8E55B8", "violet": "#7A5CC8", "blue": "#3D7DD8", "black": "#2E2A28", "brown": "#8A5A35",
    "chocolate": "#6B4226", "grey": "#9A9A9A", "gray": "#9A9A9A", "orange": "#E8873A", "agouti": "#9C7B52",
    "albino": "#F4F1EA", "chinchilla": "#B8B8BC", "himalayan": "#EFEBE3", "full colour": "#4A3B33", "full color": "#4A3B33",
    "coloured": "#B5651D", "colored": "#B5651D", "ebony": "#2E2A28", "cream": "#EADBB4", "golden": "#D9A441",
    "tan": "#C69C6D", "silver": "#C0C4C8", "sepia": "#704214", "dark": "#3A3A3A", "light": "#E6E1D6",
}
_LIGHT = {"white", "albino", "himalayan", "cream", "light"}
_SHAPES = {"round": "round", "wrinkled": "wrinkled", "smooth": "round", "angular": "wrinkled"}
_FRUIT_SHAPES = {"disc": "disc", "disk": "disc", "sphere": "sphere", "spherical": "sphere", "long": "long", "elongated": "long"}
_CAPSULES = {"triangular": "triangular", "ovoid": "ovoid", "oval": "ovoid"}
_WINGS = {"vestigial": "vestigial", "curled": "curled", "curly": "curled", "normal": "normal", "long": "normal", "short": "vestigial"}
_NORMAL_WORDS = ("normal", "unaffected", "wild type", "wild-type", "healthy")


@dataclass(frozen=True)
class GlyphSpec:
    """A picture: its ``subject`` (``pea``, ``flower``, ``eye``, ``fly``, ``coat``, ``feather``,
    ``fruit``, ``blood``, ``capsule``, ``status``, ``swatch``) and its attributes (``colour``
    hex, ``shape``, ``body``, ``wings``, ``eye``, ``group``, ``affected``, ``light``…)."""

    subject: str
    attrs: dict[str, str] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash((self.subject, tuple(sorted(self.attrs.items()))))


def colour_of(text: str) -> tuple[str, str] | None:
    """The colour named in ``text`` (longest name first: "full colour" before "colour") as
    ``(word, hex)``, or ``None``."""
    low = text.lower()
    for word in sorted(COLOURS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(word)}\b", low):
            return word, COLOURS[word]
    return None


def _word(text: str, table: dict[str, str]) -> str | None:
    low = text.lower()
    return next((v for k, v in table.items() if re.search(rf"\b{re.escape(k)}\b", low)), None)


def trait_attr(trait: str, phenotype: str, normal: str | None = None) -> tuple[str, str, str] | None:
    """``(subject, attribute, value)`` for one trait's phenotype, or ``None`` (no picture)."""
    t, p = trait.lower(), phenotype.lower()
    colour = colour_of(phenotype)
    if "blood" in t or "abo" in t:
        group = phenotype.strip().upper().replace(" AND ", "")
        if group in ("A", "B", "AB", "O"):
            return "blood", "group", group
    if ("seed" in t or "cotyledon" in t or "pea" in t) and _word(p, _SHAPES):
        return "pea", "shape", _word(p, _SHAPES) or "round"
    if ("seed" in t or "cotyledon" in t or "pea" in t) and colour:
        return "pea", "colour", colour[0]
    if "flower" in t or "petal" in t:
        return ("flower", "colour", colour[0]) if colour else None
    if "body" in t and colour:
        return "fly", "body", colour[0]
    if "wing" in t:
        return "fly", "wings", _word(p, _WINGS) or "normal"
    if "eye" in t:
        return ("eye", "colour", colour[0]) if colour else None
    if any(k in t for k in ("coat", "fur", "hair", "pigment")):
        return ("coat", "colour", colour[0]) if colour else None
    if "plumage" in t or "feather" in t:
        return ("feather", "colour", colour[0]) if colour else None
    if "fruit" in t:
        if _word(p, _FRUIT_SHAPES):
            return "fruit", "shape", _word(p, _FRUIT_SHAPES) or "sphere"
        if colour:
            return "fruit", "colour", colour[0]
    if "capsule" in t and _word(p, _CAPSULES):
        return "capsule", "shape", _word(p, _CAPSULES) or "ovoid"
    if _word(p, _SHAPES) and not colour:
        return "pea", "shape", _word(p, _SHAPES) or "round"
    if colour:
        return "swatch", "colour", colour[0]
    unaffected = (normal is not None and phenotype == normal) or any(w in p for w in _NORMAL_WORDS)
    return "status", "affected", "no" if unaffected else "yes"


#: The animals a coat is drawn on (anything else: a neutral patch of fur).
ANIMALS = ("dog", "mouse", "rabbit", "cat", "guinea pig")
_PRESET_ANIMALS = {"labrador": "dog", "yellow_mouse": "mouse", "rabbit_coat": "rabbit"}
_ANIMAL_WORDS = {"dog": ("dog", "dogs", "labrador", "labradors", "retriever", "retrievers", "puppy", "puppies"),
                 "mouse": ("mouse", "mice"), "rabbit": ("rabbit", "rabbits"), "cat": ("cat", "cats", "kitten", "kittens"),
                 "guinea pig": ("guinea pig", "guinea pigs")}


def animal_of(choice: str | None, preset: str | None, texts: list[str]) -> str:
    """The animal a coat is drawn on: ``choice`` when one of ``ANIMALS`` (``none``: the neutral
    patch), else the preset's (labrador → dog), else the first animal named in ``texts`` (title,
    traits), else ``""`` — a neutral patch of fur rather than a guess."""
    if choice and choice != "auto":
        return "" if choice == "none" else choice
    if preset in _PRESET_ANIMALS:
        return _PRESET_ANIMALS[preset]
    low = " ".join(texts).lower()
    for animal, words in _ANIMAL_WORDS.items():
        if any(re.search(rf"\b{re.escape(w)}\b", low) for w in words):
            return animal
    return ""


def class_glyphs(traits: list[str], phenotypes: list[str], normals: list[str | None], animal: str = "") -> list[GlyphSpec]:
    """The pictures of one phenotype class (its phenotype per trait): attributes of one subject
    go into one picture (a pea round and yellow; a fly grey with vestigial wings; an eye colour
    joins a fly when there is one), in the order the subjects first appear; a coat is drawn on
    ``animal`` (``animal_of``)."""
    found: dict[str, dict[str, str]] = {}
    for trait, shown, normal in zip(traits, phenotypes, normals):
        attr = trait_attr(trait, shown, normal)
        if attr is None:
            attr = ("swatch", "colour", "")
        subject, key, value = attr
        if subject == "eye" and "fly" in found:
            subject, key = "fly", "eye"
        found.setdefault(subject, {})[key] = value
    if "eye" in found and "fly" in found:
        found["fly"]["eye"] = found.pop("eye")["colour"]
    out = []
    for subject, attrs in found.items():
        attrs = dict(attrs)
        for key in ("colour", "body", "eye"):
            if key in attrs and attrs[key] in COLOURS:
                attrs[f"{key}_hex"] = COLOURS[attrs[key]]
        if attrs.get("colour") in _LIGHT:
            attrs["light"] = "yes"
        if subject == "coat" and animal:
            attrs["animal"] = animal
        out.append(GlyphSpec(subject, attrs))
    return out


__all__ = ["ANIMALS", "COLOURS", "GlyphSpec", "animal_of", "class_glyphs", "colour_of", "trait_attr"]

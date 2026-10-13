"""Random, well-contrasted casts: ``vidgen cast --random N`` and the looks ``vidgen screenplay``
gives undeclared characters (DESIGN.md §69.49). No manim.

:func:`pick_looks` chooses one look per voice kind, each as unlike the characters before it as it
can: for each character it draws :data:`CANDIDATES` random looks (:func:`random_look`, every choice
through ``Random(seed).random()``, the one call Python keeps stable across versions) and keeps the
one whose lowest :func:`~vidgen.cartoon.contrast.contrast_score` against the characters already
chosen is highest (greedy maximisation of the minimum pairwise contrast). Given ``curated`` looks
(the screenplay's :data:`~vidgen.screenplay.LOOKS`) it takes the first unused one of the kind
whose contrast with the others is at least :data:`~vidgen.cartoon.contrast.MIN_CONTRAST` before
drawing random ones. Each look fits its voice kind (:data:`KIND_EXCLUDES`).
:func:`random_cast` adds original names (:data:`NAMES`) and voices
(:func:`~vidgen.screenplay.assign_voices`); :func:`cast_yaml` writes it as an include file.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar, get_args

from vidgen.cartoon.contrast import MIN_CONTRAST, LookFeatures, look_features, min_contrast
from vidgen.config import SPECIES_OWN_KEYS, Species
from vidgen.errors import VidgenError
from vidgen.screenplay import VOICE_KINDS, assign_voices

if TYPE_CHECKING:
    from vidgen.theme import Theme

T = TypeVar("T")

#: Looks drawn per character; the one least like the others is kept.
CANDIDATES = 48
#: Most characters ``vidgen cast --random`` makes.
MAX_CAST = 24
#: Species ``--species`` takes (``config.Species``).
SPECIES: tuple[str, ...] = get_args(Species)
#: Original names per voice kind: short, common first names, none of them a famous character's.
NAMES: dict[str, tuple[str, ...]] = {
    "feminine": ("ada", "bea", "cora", "fia", "greta", "hana", "ida", "ines", "jade", "lina", "mara", "mei", "nell",
                 "ola", "pia", "rosa", "selma", "tess", "una", "vera", "yara"),
    "masculine": ("ben", "dov", "edo", "elio", "enzo", "gil", "ivo", "jon", "kofi", "lars", "nico", "omar", "otto",
                  "rui", "teo", "vik", "wim"),
    "neutral": ("ari", "dani", "fran", "lou", "paz", "sami", "sol", "tam", "wen", "yan", "noa", "lee"),
}
#: Look values a character of each voice kind is not drawn with (so the voice suits the look).
KIND_EXCLUDES: dict[str, frozenset[str]] = {
    "feminine": frozenset({"moustache", "beard"}),
    "masculine": frozenset({"dress", "bow", "bun", "ponytail", "braids"}),
    "neutral": frozenset({"moustache", "beard", "dress", "bow"}),
}
BODIES: tuple[str, ...] = ("round", "tall", "square", "bean", "pear", "triangle")
HEAD_SIZES: tuple[float, ...] = (0.85, 0.95, 1.05, 1.15, 1.3)
EYES: tuple[str, ...] = ("dot", "oval", "round", "sleepy")
NOSES: tuple[str, ...] = ("none", "dot", "round", "triangle")
EARS: tuple[str, ...] = ("none", "none", "round", "pointy", "floppy")
HAIR: tuple[str, ...] = ("none", "short", "spiky", "long", "bun", "curly", "ponytail", "braids", "afro")
ANIMAL_HAIR: tuple[str, ...] = ("none", "none", "short", "spiky", "curly")
OUTFITS: tuple[str, ...] = ("plain", "dress", "overalls", "coat", "shorts", "apron")
PATTERNS: tuple[str, ...] = ("none", "none", "stripes", "dots")
SHOES: tuple[str, ...] = ("none", "shoes", "boots")
ACCESSORIES: tuple[str, ...] = ("glasses", "hat", "scarf", "bag", "bow", "cap", "backpack", "necklace")
ACCESSORY_COUNTS: tuple[int, ...] = (0, 1, 1, 2)
#: Share of masculine humans with a moustache or a beard.
FACIAL_HAIR_SHARE = 0.4
#: Colours (hex, so a cast looks the same in every theme).
SKIN_COLORS: tuple[str, ...] = (
    "#FFE0BD", "#F5D0B5", "#F2C9A0", "#E8B48A", "#C68B59", "#B97A4E", "#8D5A3B", "#6B4429", "#9BD3AE", "#A7C7E7", "#D9A3E0",
)
FUR_COLORS: tuple[str, ...] = ("#B5652E", "#8A8A8A", "#F2EDE4", "#3A3A3A", "#C8A27A", "#6E4B32", "#E0B860", "#5C6F8A")
#: Natural colours of the species whose fur, feathers or skin differ from :data:`FUR_COLORS`
#: (a turtle's shell is its ``hair`` colour: :data:`SHELL_COLORS`).
SPECIES_COLORS: dict[str, tuple[str, ...]] = {
    "fox": ("#C8642B", "#B5532E", "#D98A4E", "#8A8A8A", "#F2EDE4", "#6E4B32"),
    "owl": ("#8A6E52", "#B39B7A", "#6E5A48", "#C9C2B6", "#5C6F8A"),
    "frog": ("#6FA84A", "#4E8F3A", "#9BBF4C", "#3F8F7A", "#C9B04A", "#7A9A5A"),
    "turtle": ("#9DB06B", "#7FA05A", "#A7A27A", "#6E8F6A", "#B8B07A"),
    "penguin": ("#2F3440", "#3A3A3A", "#3B4A5F", "#4A4F5A", "#5C6F8A"),
}
SHELL_COLORS: tuple[str, ...] = ("#7A5C3E", "#6B4A2B", "#8C6E3F", "#5F6B3A", "#9A7A4E", "#4E5A3A")
CLOTHES_COLORS: tuple[str, ...] = (
    "#D9534F", "#F0AD4E", "#E8D44D", "#5CB85C", "#2E8B8B", "#4A7BD0", "#3B4A8F", "#8E5BB5", "#D96BA0", "#7A5C3E",
    "#5B6C8F", "#2F2F2F", "#E9E4D8", "#8FA35A",
)
HAIR_COLORS: tuple[str, ...] = ("#2B2B2B", "#4A3426", "#6B4226", "#B5532E", "#E0C068", "#E7E1D5", "#1E1A17", "#8A8F99", "#7B4FA0", "#2F6FB0")
ACCESSORY_COLORS: tuple[str, ...] = ("#E04E39", "#F2B134", "#3FA34D", "#2D7DD2", "#9B5DE5", "#F15BB5", "#FFFFFF", "#3A3A3A")
TRIM_COLORS: tuple[str, ...] = ("#E7E1D5", "#3B3B3B", "#A0A0A0", "#C9A27A", "#6C8EBF", "#B04A4A")


def _pick(rng: random.Random, choices: Sequence[T]) -> T:
    """One of ``choices`` from ``rng.random()`` alone (stable across Python versions)."""
    return choices[min(int(rng.random() * len(choices)), len(choices) - 1)]


def _shuffled(rng: random.Random, items: Sequence[T]) -> list[T]:
    """``items`` in a random order (Fisher-Yates on ``rng.random()``)."""
    out = list(items)
    for k in range(len(out) - 1, 0, -1):
        j = min(int(rng.random() * (k + 1)), k)
        out[k], out[j] = out[j], out[k]
    return out


def random_look(rng: random.Random, kind: str, species: Sequence[str] = ("human",)) -> dict[str, Any]:
    """A random generator look of one of ``species`` that fits voice ``kind``:
    ``{"look": {...}, "colors": {...}, "voice_kind": kind}`` (default values left out)."""
    excluded = KIND_EXCLUDES[kind]
    allowed = [s for s in species if s in SPECIES] or ["human"]
    animal = _pick(rng, allowed)
    look: dict[str, Any] = {"body": _pick(rng, BODIES), "head_size": _pick(rng, HEAD_SIZES), "eyes": _pick(rng, EYES)}
    if animal == "human":
        look["nose"] = _pick(rng, NOSES)
        look["ears"] = _pick(rng, EARS)
    look["hair"] = _pick(rng, [h for h in (HAIR if animal == "human" else ANIMAL_HAIR) if h not in excluded])
    look["outfit"] = _pick(rng, [o for o in OUTFITS if o not in excluded])
    look["pattern"] = _pick(rng, PATTERNS)
    look["shoes"] = _pick(rng, SHOES)
    if animal == "human" and "beard" not in excluded and rng.random() < FACIAL_HAIR_SHARE:
        look["facial_hair"] = _pick(rng, ("moustache", "beard"))
    pool = [a for a in ACCESSORIES if a not in excluded]
    worn: list[str] = []
    for _ in range(_pick(rng, ACCESSORY_COUNTS)):
        options = [a for a in pool if a not in worn and not ({a} | set(worn)) >= {"hat", "cap"}]
        worn.append(_pick(rng, options))
    if worn:
        look["accessories"] = worn
    if animal != "human":
        look["species"] = animal
        for key in SPECIES_OWN_KEYS:
            look.pop(key, None)
    defaults = {"head_size": 1.0, "nose": "none", "ears": "none", "hair": "none", "outfit": "plain", "pattern": "none", "shoes": "none"}
    look = {key: value for key, value in look.items() if defaults.get(key) != value}
    colors = {
        "skin": _pick(rng, SKIN_COLORS if animal == "human" else SPECIES_COLORS.get(animal, FUR_COLORS)), "clothes": _pick(rng, CLOTHES_COLORS),
        "hair": _pick(rng, SHELL_COLORS if animal == "turtle" else HAIR_COLORS), "accessory": _pick(rng, ACCESSORY_COLORS),
        "trim": _pick(rng, TRIM_COLORS),
    }
    return {"look": look, "colors": colors, "voice_kind": kind}


def balanced_kinds(count: int, rng: random.Random) -> list[str]:
    """``count`` voice kinds, each round of three a shuffle of :data:`VOICE_KINDS`."""
    kinds: list[str] = []
    while len(kinds) < count:
        kinds.extend(_shuffled(rng, VOICE_KINDS))
    return kinds[:count]


def _fit(own: str, wanted: str | None) -> int:
    """0: a look of the wanted kind (or none wanted), 1: a neutral look, 2: another kind."""
    return 0 if wanted is None or own == wanted else 1 if own == "neutral" else 2


def pick_looks(
    kinds: Sequence[str | None],
    rng: random.Random,
    *,
    species: Sequence[str] = ("human",),
    existing: Sequence[LookFeatures] = (),
    curated: Sequence[Mapping[str, Any]] = (),
    theme: Theme | None = None,
) -> list[dict[str, Any]]:
    """One look per entry of ``kinds`` (a voice kind, or ``None``: any), each unlike ``existing``
    and the looks picked before it (see the module doc); ``{"look", "colors", "voice_kind"}``
    each. ``curated`` looks (``{look, colors, voice_kind}``, colours may be theme tokens resolved
    with ``theme``) come first, in order, while one of the kind keeps
    :data:`~vidgen.cartoon.contrast.MIN_CONTRAST`; with ``None`` a random look takes the voice
    kind picked least so far."""
    chosen: list[LookFeatures] = [f for f in existing if f is not None]
    used: set[int] = set()
    curated_features = [look_features(c["look"], c["colors"], theme) for c in curated]
    picks: list[dict[str, Any]] = []
    for wanted in kinds:
        fitting = sorted((k for k, c in enumerate(curated) if k not in used and _fit(c["voice_kind"], wanted) < 2),
                         key=lambda k: (_fit(curated[k]["voice_kind"], wanted), k))
        found = next((k for k in fitting if min_contrast(curated_features[k], chosen) >= MIN_CONTRAST), None)
        if found is not None:
            used.add(found)
            entry = curated[found]
            pick = {"look": dict(entry["look"]), "colors": dict(entry["colors"]), "voice_kind": entry["voice_kind"]}
            features = curated_features[found]
        else:
            kind = wanted or min(VOICE_KINDS, key=lambda k: sum(p["voice_kind"] == k for p in picks))
            candidates = [random_look(rng, kind, species) for _ in range(CANDIDATES)]
            scored = [(min_contrast(f, chosen), k, f) for k, c in enumerate(candidates) if (f := look_features(c["look"], c["colors"])) is not None]
            best = max(scored, key=lambda item: (item[0], -item[1]))
            pick, features = candidates[best[1]], best[2]
        chosen.append(features)
        picks.append(pick)
    return picks


@dataclass
class RandomCast:
    """What :func:`random_cast` made: ``characters`` and ``voices`` entries (an include file's),
    each character's voice ``kinds``, the lowest pairwise contrast and notes (voices to set by
    hand)."""

    characters: list[dict[str, Any]]
    voices: dict[str, dict[str, Any]]
    kinds: dict[str, str]
    lowest_contrast: float
    notes: list[str] = field(default_factory=list)

    def config(self) -> dict[str, Any]:
        """The include file's mapping: ``characters`` and ``voices``."""
        return {"characters": self.characters, "voices": self.voices}


def parse_species(values: Sequence[str] | None) -> list[str]:
    """``--species`` values (each may be a comma-separated list) checked against :data:`SPECIES`;
    none: ``["human"]``."""
    found = [v.strip().lower() for value in values or () for v in value.split(",") if v.strip()]
    unknown = [v for v in found if v not in SPECIES]
    if unknown:
        raise VidgenError(f"--species: unknown species {', '.join(map(repr, unknown))}; species: {', '.join(SPECIES)}")
    return list(dict.fromkeys(found)) or ["human"]


def random_cast(
    count: int,
    seed: int = 0,
    *,
    species: Sequence[str] = ("human",),
    voice: Mapping[str, Any] | None = None,
    language: str | None = None,
    taken: Sequence[str] = (),
) -> RandomCast:
    """``count`` characters with seeded looks (:func:`pick_looks`, balanced voice kinds), names
    of their kind from :data:`NAMES` not in ``taken`` and distinct voices of ``voice``'s provider (default
    Kokoro with the narrator ``bf_emma``, as ``vidgen screenplay``)."""
    if not 1 <= count <= MAX_CAST:
        raise VidgenError(f"--random: give 1 to {MAX_CAST} characters, not {count}")
    # one stream each for kinds, looks and names, so a bigger cast of the same seed starts with the smaller one
    kinds = balanced_kinds(count, random.Random(seed * 3))
    looks = pick_looks(kinds, random.Random(seed * 3 + 1), species=species)
    names_rng = random.Random(seed * 3 + 2)
    free = {kind: [n for n in _shuffled(names_rng, NAMES[kind]) if n not in set(taken)] for kind in VOICE_KINDS}
    names: list[str] = []
    for k, kind in enumerate(kinds):
        names.append(free[kind].pop(0) if free[kind] else f"{NAMES[kind][k % len(NAMES[kind])]}_{k + 1}")
    base = dict(voice) if voice is not None else {"provider": "kokoro", "voice": "bf_emma"}
    settings, notes = assign_voices(base, language, kinds)
    characters, voices = [], {}
    for name, look, setting in zip(names, looks, settings):
        voices[f"{name}_voice"] = {**setting, "label": name.capitalize()}
        characters.append({"name": name, "look": look["look"], "colors": look["colors"], "voice": f"{name}_voice"})
    features = [look_features(c["look"], c["colors"]) for c in characters]
    lowest = min((min_contrast(f, features[:k]) for k, f in enumerate(features) if k), default=1.0)
    if notes and base.get("provider", "elevenlabs") == "elevenlabs":
        wished = ", ".join(f"{n}: {k}" for n, k in zip(names, kinds))
        notes = [f"{notes[0]} of the kind that suits the character ({wished})", *notes[1:]]
    return RandomCast(characters, voices, dict(zip(names, kinds)), round(lowest, 3), notes)


def cast_yaml(cast: RandomCast, command: str) -> str:
    """The include file of ``cast`` as commented YAML (``command``: how it was made)."""
    from vidgen.plan_yaml import commented_yaml

    header = [
        f"# Written by `{command}`: original characters chosen to differ clearly (silhouette, colours,",
        "# accessories, voice). Use it with `include: [<this file>]` in video.yaml or `vidgen screenplay --cast`.",
    ]
    kinds = ", ".join(f"{name} {kind}" for name, kind in cast.kinds.items())
    comments = {"characters": [f"voice kinds: {kinds}; lowest contrast between two of them: {cast.lowest_contrast:.2f}"]}
    if cast.notes:
        comments["voices"] = [f"TODO: {n}" for n in cast.notes]
    return commented_yaml(cast.config(), header, comments)

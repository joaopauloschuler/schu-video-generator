"""``vidgen story draft``, part 2: places, light, weather and music suggested from a story's words
(DESIGN.md §105.5). No manim import, no AI: keyword tables and ready-made iso places.

Each :class:`StoryPlace` is a small iso place (map, spots, objects of DESIGN.md §89 / §103 / §104)
made for placeholder staging: four spots to stand on (``stands``), spots walks go to (``goals``),
the objects lit at night (``lights``; ``lit`` always), and the flat stage's ready-made set that
stands in for it with ``--style flat`` (DESIGN.md §76 / §77). :func:`choose_place` scores a scene's
words against the places' ``words``; :func:`light_cues`, :func:`weather_of` and :func:`music_of`
read time of day, weather and mood the same way.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StoryPlace:
    """A ready-made place a story scene can stand on (see the module doc)."""

    name: str
    indoor: bool
    flat_set: str
    words: tuple[str, ...]
    map: str
    spots: dict[str, str]
    objects: tuple[dict[str, Any], ...]
    stands: tuple[str, ...]
    goals: tuple[str, ...]
    lights: tuple[str, ...] = ()
    lit: tuple[str, ...] = ()
    weather: dict[str, Any] = field(default_factory=dict)
    #: free cells (column, row) where an object the story names can stand
    free: tuple[tuple[int, int], ...] = ()

    def objects_at(self, night: bool) -> list[dict[str, Any]]:
        """The place's objects; at ``night`` its ``lights`` are switched on."""
        objects = []
        for entry in self.objects:
            item = dict(entry)
            if item.get("name") in self.lit or (night and item.get("name") in self.lights):
                item["on"] = True
            objects.append(item)
        return objects

    def iso(self, night: bool, added: Sequence[tuple[str, str, tuple[int, int]]] = ()) -> dict[str, Any]:
        """The ``iso:`` mapping of the place (see :meth:`objects_at`) with the objects ``added``
        (:func:`objects_named`)."""
        objects = [*self.objects_at(night), *({"object": kind, "at": _cell(*cell)} for _, kind, cell in added)]
        room = {"place": "indoor", "wide": "fill"} if self.indoor else {}   # a room's wide view brought closer
        return {**room, "map": self.map, "spots": dict(self.spots), "objects": objects}

    def kinds(self) -> set[str]:
        """The kinds of objects the place has."""
        return {str(o["object"]) for o in self.objects}


def _cell(column: int, row: int) -> dict[str, int]:
    return {"column": column, "row": row}


#: Day and night skies of the outdoor places (top to bottom).
OUTDOOR_SKIES: dict[str, list[str]] = {
    "day": ["#9CCBEA", "#E4F3FB"], "morning": ["#F6C1A8", "#FBEBD2"], "sunset": ["#8E9AB0", "#F4B183"],
    "night": ["#1E2742", "#3A4566"],
}
#: The background behind a room.
INDOOR_SKY: list[str] = ["#3E4A6B", "#5C6A8E"]

_ROOM_TOP = "###%####%###"
_ROOM_BOTTOM = "##+#########"

#: The places, in the order a tie between their scores is broken.
PLACES: dict[str, StoryPlace] = {p.name: p for p in (
    StoryPlace(
        "village", False, "park",
        ("village", "garden", "cottage", "well", "green", "meadow", "farm", "field", "bridge", "stream", "lane",
         "neighbour", "neighbor", "yard", "park", "outside"),
        "..............\n..............\n..............\n::::::::::::::\n..a...b...c...\n..............\n.d.........e..\n..............\n",
        {"a": "left", "b": "middle", "c": "right", "d": "garden", "e": "lane_end"},
        ({"object": "house", "name": "home", "at": _cell(2, 1)},
         {"object": "house", "name": "cottage", "at": _cell(9, 1), "color": "#B5C99A"},
         {"object": "lamp", "name": "lamp", "at": _cell(7, 3)},
         {"object": "tree", "at": _cell(13, 1)}, {"object": "well", "at": _cell(6, 7)},
         {"object": "bench", "at": _cell(8, 7)}, {"object": "flowers", "at": _cell(4, 8)},
         {"object": "tree", "at": _cell(1, 8)}, {"object": "bush", "at": _cell(14, 8)}),
        ("left", "right", "middle", "garden"), ("middle", "lane_end", "garden", "right", "left"),
        lights=("home", "cottage", "lamp"), free=((6, 1), (13, 3), (11, 8)),
    ),
    StoryPlace(
        "city", False, "city_street",
        ("city", "street", "streets", "roof", "rooftop", "rooftops", "avenue", "traffic", "downtown", "skyscraper", "skyscrapers", "neon", "crosswalk", "taxi",
         "bus", "sidewalk", "pavement", "alley", "subway", "metro", "towers", "apartment block"),
        "..............\n..............\n..............\n::::::::::::::\n::::::::::::::\n..a....b...c..\n.........d....\n",
        {"a": "left", "b": "middle", "c": "right", "d": "stop"},
        ({"object": "tower", "at": _cell(1, 1), "height": 8},
         {"object": "tower", "at": _cell(5, 1), "height": 11, "color": "#3B3F58", "detail": "#FF4FA3"},
         {"object": "tower", "at": _cell(10, 1), "height": 7, "detail": "#4FE3FF"},
         {"object": "tower", "at": _cell(13, 1), "height": 9},
         {"object": "street_lamp", "name": "lamp_1", "at": _cell(4, 3)},
         {"object": "street_lamp", "name": "lamp_2", "at": _cell(9, 3)},
         {"object": "phone_booth", "name": "phone_booth", "at": _cell(12, 3)},
         {"object": "bus_stop", "at": _cell(5, 7)}, {"object": "car", "name": "car", "at": _cell(2, 5)},
         {"object": "mailbox", "at": _cell(14, 6)}),
        ("left", "right", "middle", "stop"), ("middle", "stop", "right", "left"),
        lights=("lamp_1", "lamp_2", "phone_booth"), free=((7, 2), (3, 7), (13, 7)),
    ),
    StoryPlace(
        "lab", True, "classroom",
        ("lab", "laboratory", "experiment", "experiments", "scientist", "scientists", "microscope", "reactor",
         "console", "server", "servers", "terminal", "test tube", "physics", "chemistry", "data", "signal", "sensor"),
        f"{_ROOM_TOP}\n#..........#\n#..........#\n#..a....b..#\n#.c.....d..#\n#..........#\n{_ROOM_BOTTOM}\n",
        {"a": "left", "b": "right", "c": "entry", "d": "bench"},
        ({"object": "console", "name": "console", "at": _cell(2, 2)},
         {"object": "server_rack", "name": "rack_1", "at": _cell(5, 2)},
         {"object": "server_rack", "name": "rack_2", "at": _cell(6, 2)},
         {"object": "whiteboard", "at": _cell(8, 2)}, {"object": "coffee_machine", "at": _cell(11, 2)},
         {"object": "microscope", "at": _cell(11, 4)}, {"object": "lab_stool", "at": _cell(6, 5)},
         {"object": "chemistry_bench", "at": _cell(10, 6)}),
        ("left", "right", "entry", "bench"), ("right", "bench", "entry", "left"), free=((4, 2), (7, 2), (2, 4)),
    ),
    StoryPlace(
        "office", True, "classroom",
        ("office", "desk", "meeting", "boss", "printer", "coworker", "colleague", "colleagues", "cubicle", "email",
         "deadline", "spreadsheet"),
        f"{_ROOM_TOP}\n#..........#\n#..........#\n#..a....b..#\n#.c.....d..#\n#..........#\n{_ROOM_BOTTOM}\n",
        {"a": "left", "b": "right", "c": "entry", "d": "corner"},
        ({"object": "desk_with_pc", "name": "desk_1", "at": _cell(2, 2)},
         {"object": "desk_with_pc", "name": "desk_2", "at": _cell(5, 2)},
         {"object": "water_cooler", "at": _cell(9, 2)}, {"object": "printer", "name": "printer", "at": _cell(10, 2)},
         {"object": "plant", "at": _cell(11, 2)}, {"object": "chair", "at": _cell(11, 5)}),
        ("left", "right", "entry", "corner"), ("right", "corner", "entry", "left"),
        lights=("desk_1", "desk_2"), free=((4, 2), (7, 2), (11, 3)),
    ),
    StoryPlace(
        "home", True, "living_room",
        ("home", "kitchen", "living room", "sofa", "couch", "fireplace", "bedroom", "apartment", "armchair",
         "television", "tv", "mum", "dad", "mom", "dinner", "breakfast", "bed"),
        f"{_ROOM_TOP}\n#..........#\n#..........#\n#.a.....b..#\n#...c...d..#\n#..........#\n{_ROOM_BOTTOM}\n",
        {"a": "left", "b": "right", "c": "middle", "d": "corner"},
        ({"object": "bookshelf_tall", "at": _cell(2, 2)}, {"object": "sofa", "name": "sofa", "at": _cell(4, 2)},
         {"object": "fireplace", "name": "fireplace", "at": _cell(7, 2)},
         {"object": "floor_lamp", "name": "floor_lamp", "at": _cell(10, 2)},
         {"object": "plant", "at": _cell(11, 2)}, {"object": "armchair", "name": "armchair", "at": _cell(11, 4)},
         {"object": "table", "name": "table", "at": _cell(6, 5)}),
        ("left", "right", "middle", "corner"), ("right", "middle", "corner", "left"),
        lights=("fireplace", "floor_lamp"), free=((3, 2), (6, 2), (2, 6)),
    ),
    StoryPlace(
        "cafe", True, "shop",
        ("café", "cafe", "coffee", "coffee shop", "bakery", "shop", "store", "counter", "barista", "cake", "cakes",
         "tea", "restaurant", "waiter", "menu"),
        f"{_ROOM_TOP}\n#..........#\n#..........#\n#.a......b.#\n#....c...d.#\n#..........#\n{_ROOM_BOTTOM}\n",
        {"a": "left", "b": "right", "c": "middle", "d": "corner"},
        ({"object": "counter", "at": _cell(2, 2)}, {"object": "cash_register", "at": _cell(4, 2)},
         {"object": "coffee_machine", "name": "coffee_machine", "at": _cell(5, 2)},
         {"object": "display_case", "at": _cell(7, 2)}, {"object": "plant", "at": _cell(11, 2)},
         {"object": "cafe_table", "name": "table_1", "at": _cell(4, 5)},
         {"object": "cafe_table", "name": "table_2", "at": _cell(8, 5)}),
        ("left", "right", "middle", "corner"), ("right", "middle", "corner", "left"), free=((6, 2), (9, 2), (2, 6)),
    ),
    StoryPlace(
        "forest", False, "forest",
        ("forest", "woods", "wood", "trees", "campfire", "camp", "tent", "clearing", "trail", "pines", "owl", "fox",
         "mushrooms", "fire"),
        "@.....@....@..\n.......d......\n..............\n....a.........\n........b.....\n..............\n"
        "...c..........\n@......@.....@\n",
        {"a": "left", "b": "right", "c": "middle", "d": "path"},
        ({"object": "tent", "at": _cell(2, 2)}, {"object": "campfire", "name": "campfire", "at": _cell(7, 4)},
         {"object": "log", "name": "log", "at": _cell(6, 6)}, {"object": "stump", "at": _cell(9, 3)},
         {"object": "pine", "at": _cell(11, 2)}, {"object": "pine", "at": _cell(13, 4)},
         {"object": "mushroom_ring", "at": _cell(11, 6)}, {"object": "bush", "at": _cell(1, 5)}),
        ("left", "right", "middle", "path"), ("path", "middle", "right", "left"),
        lights=("campfire",), free=((4, 1), (13, 2), (2, 7)),
    ),
    StoryPlace(
        "harbour", False, "beach",
        ("harbour", "harbor", "port", "dock", "pier", "boat", "boats", "ship", "sea", "ocean", "beach", "lighthouse",
         "waves", "sailor", "fisherman", "shore", "tide"),
        "..........~~~~\n..........~~~~\n..........~~~~\n::::::::::~~~~\n..a...b...~~~~\n..........~~~~\n"
        "..c...d...~~~~\n..........~~~~\n",
        {"a": "left", "b": "right", "c": "middle", "d": "quay"},
        ({"object": "lighthouse", "name": "lighthouse", "at": _cell(2, 1)},
         {"object": "dock", "at": _cell(11, 4)}, {"object": "boat", "name": "boat", "at": _cell(12, 2)},
         {"object": "crate_stack", "at": _cell(9, 2)}, {"object": "crate_stack", "at": _cell(9, 7)},
         {"object": "street_lamp", "name": "lamp", "at": _cell(7, 3)}, {"object": "bench", "at": _cell(5, 8)}),
        ("left", "right", "middle", "quay"), ("right", "quay", "middle", "left"),
        lights=("lighthouse", "lamp", "boat"), free=((5, 1), (1, 6), (9, 5)),
    ),
    StoryPlace(
        "castle", True, "living_room",
        ("castle", "king", "queen", "throne", "palace", "knight", "knights", "dungeon", "dragon", "princess", "prince",
         "kingdom", "hall", "crown", "wizard", "treasure"),
        "############\n#..........#\n#..........#\n#..a....b..#\n#..c....d..#\n#..........#\n#####+######\n",
        {"a": "left", "b": "right", "c": "middle", "d": "corner"},
        ({"object": "throne", "name": "throne", "at": _cell(6, 2)},
         {"object": "torch_sconce", "name": "torch_1", "at": _cell(4, 1)},
         {"object": "torch_sconce", "name": "torch_2", "at": _cell(9, 1)},
         {"object": "statue", "at": _cell(2, 2)}, {"object": "statue", "at": _cell(11, 2)},
         {"object": "rug", "at": _cell(6, 4)}, {"object": "treasure_chest", "name": "chest", "at": _cell(11, 6)}),
        ("left", "right", "middle", "corner"), ("right", "middle", "corner", "left"),
        lit=("torch_1", "torch_2"), free=((4, 2), (8, 2), (2, 5)),
    ),
    StoryPlace(
        "school", True, "classroom",
        ("school", "classroom", "teacher", "class", "lesson", "pupil", "pupils", "student", "students", "homework",
         "blackboard", "whiteboard", "exam", "test"),
        f"{_ROOM_TOP}\n#..........#\n#...a...b..#\n#..........#\n#..c.....d.#\n#..........#\n{_ROOM_BOTTOM}\n",
        {"a": "front", "b": "right", "c": "left", "d": "corner"},
        ({"object": "whiteboard", "at": _cell(5, 2)}, {"object": "bookshelf_tall", "at": _cell(2, 2)},
         {"object": "globe", "at": _cell(11, 2)}, {"object": "school_desk", "at": _cell(3, 5)},
         {"object": "school_desk", "at": _cell(5, 5)}, {"object": "school_desk", "at": _cell(7, 5)},
         {"object": "school_desk", "at": _cell(9, 5)}),
        ("front", "right", "left", "corner"), ("right", "corner", "left", "front"), free=((8, 2), (11, 4), (2, 6)),
    ),
    StoryPlace(
        "winter", False, "snowy_hills",
        ("snow", "snowman", "winter", "ice", "icy", "frozen", "christmas", "sledge", "sled", "snowflakes", "frost"),
        "..............\n..............\n..............\n::::::::::::::\n..a...b.......\n..........c...\n"
        "....d.........\n..............\n",
        {"a": "left", "b": "middle", "c": "right", "d": "garden"},
        ({"object": "house", "name": "home", "at": _cell(2, 1)}, {"object": "pine", "at": _cell(8, 1)},
         {"object": "pine", "at": _cell(12, 2)}, {"object": "lamp", "name": "lamp", "at": _cell(6, 3)},
         {"object": "snowman", "at": _cell(9, 5)}, {"object": "pine", "at": _cell(1, 7)},
         {"object": "pine", "at": _cell(13, 7)}),
        ("left", "right", "middle", "garden"), ("middle", "garden", "right", "left"),
        lights=("home", "lamp"), weather={"snow": True}, free=((10, 2), (14, 5), (9, 8)),
    ),
)}
#: The place of a story with no place words.
DEFAULT_PLACE = "village"


def _pattern(words: Sequence[str]) -> re.Pattern[str]:
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\b", re.IGNORECASE)


_PLACE_PATTERNS = {name: _pattern(place.words) for name, place in PLACES.items()}


@dataclass(frozen=True)
class PlaceChoice:
    """The place chosen for a scene, its words found (word -> count) and why."""

    place: str
    hits: dict[str, int]
    reason: str


def place_hits(text: str) -> dict[str, dict[str, int]]:
    """Place name -> {word: count} of the place words in ``text`` (places without any left out)."""
    found: dict[str, dict[str, int]] = {}
    for name, pattern in _PLACE_PATTERNS.items():
        for match in pattern.finditer(text):
            word = match.group(1).lower()
            found.setdefault(name, {}).setdefault(word, 0)
            found[name][word] += 1
    return found


def choose_place(text: str, previous: str | None) -> PlaceChoice:
    """The place for a scene's ``text``: the one with most place words (a tie: the previous
    scene's, then :data:`PLACES` order); none found: the previous scene's, else
    :data:`DEFAULT_PLACE`."""
    hits = place_hits(text)
    if not hits:
        if previous is not None:
            return PlaceChoice(previous, {}, "no place words: the scene before's place")
        return PlaceChoice(DEFAULT_PLACE, {}, f"no place words: the default ({DEFAULT_PLACE})")
    score = {name: sum(words.values()) for name, words in hits.items()}
    best = max(score.values())
    tied = [name for name in PLACES if score.get(name) == best]
    name = previous if previous in tied else tied[0]
    words = ", ".join(f"{w}×{n}" if n > 1 else w for w, n in hits[name].items())
    return PlaceChoice(name, hits[name], f"words: {words}")


# ----- time of day ---------------------------------------------------------------------------------

#: Words naming a time of day -> the light preset (``vidgen.cartoon.lighting.LIGHT_PRESETS``).
LIGHT_WORDS: dict[str, str] = {
    **{w: "night" for w in ("night", "midnight", "moonlight", "moonlit", "the moon", "stars", "starlight", "nightfall",
                            "tonight", "darkness", "pitch dark", "after dark", "in the dark", "lamplight")},
    **{w: "morning" for w in ("dawn", "sunrise", "daybreak", "morning", "first light", "breakfast")},
    **{w: "day" for w in ("noon", "midday", "afternoon", "daylight", "sunny", "sunshine", "lunch")},
    **{w: "sunset" for w in ("sunset", "dusk", "evening", "twilight", "sundown")},
}
_LIGHT_PATTERN = _pattern(list(LIGHT_WORDS))
#: A clock time: ``3 AM``, ``3:15 a.m.``, ``11 PM``, ``three in the morning``.
_CLOCK = re.compile(r"\b(\d{1,2})(?::\d{2})?\s*([ap])\.?\s*m\b\.?", re.IGNORECASE)
_SMALL_HOURS = re.compile(r"\b(one|two|three|four|1|2|3|4)\s+(?:o'clock\s+)?in\s+the\s+morning\b", re.IGNORECASE)


def clock_light(hour: int, half: str) -> str:
    """The light of a clock time (``half``: ``a`` or ``p``)."""
    hour = hour % 12 + (12 if half.lower() == "p" else 0)
    if hour < 5 or hour >= 21:
        return "night"
    if hour < 9:
        return "morning"
    if hour < 17:
        return "day"
    return "sunset"


def light_cues(text: str) -> list[tuple[int, str, str]]:
    """The time-of-day cues of ``text`` in order: ``(offset, preset, words)``."""
    cues = [(m.start(), LIGHT_WORDS[m.group(1).lower()], m.group(0)) for m in _LIGHT_PATTERN.finditer(text)]
    cues += [(m.start(), clock_light(int(m.group(1)), m.group(2)), m.group(0)) for m in _CLOCK.finditer(text)]
    cues += [(m.start(), "night", m.group(0)) for m in _SMALL_HOURS.finditer(text)]
    # "three in the morning" is night, not morning: a small-hours cue wins over the words in it
    small = [(s, s + len(w)) for s, p, w in cues if p == "night" and _SMALL_HOURS.match(w)]
    cues = [c for c in cues if not any(a <= c[0] < b and c[1] == "morning" for a, b in small)]
    return sorted(cues)


# ----- weather and mood -----------------------------------------------------------------------------

#: Weather -> its words.
WEATHER_WORDS: dict[str, tuple[str, ...]] = {
    "rain": ("rain", "raining", "rained", "rainy", "drizzle", "downpour", "raindrops", "puddle", "puddles", "storm", "stormy", "umbrella"),
    "fog": ("fog", "foggy", "mist", "misty", "haze", "hazy"),
    "wind": ("wind", "windy", "gust", "gusts", "gale", "breeze", "storm", "stormy", "blustery"),
    "snow": ("snow", "snowing", "snowed", "snowy", "snowflakes", "blizzard"),
}
_WEATHER_PATTERNS = {kind: _pattern(words) for kind, words in WEATHER_WORDS.items()}
#: Words after a weather word that say it is over (``the rain had stopped``, ``the wind dropped``).
_WEATHER_OVER = re.compile(r"\s+(?:had\s+|has\s+)?(?:stopped|dropped|died|eased|gone|cleared|ceased|lifted|passed|calmed)\b", re.IGNORECASE)


def weather_of(text: str) -> dict[str, list[str]]:
    """Weather kind -> the words of it found in ``text`` (kinds without any left out; a word
    followed by ``stopped``, ``dropped``, ``had gone``... does not count)."""
    found: dict[str, list[str]] = {}
    for kind, pattern in _WEATHER_PATTERNS.items():
        words = list(dict.fromkeys(m.group(1).lower() for m in pattern.finditer(text) if not _WEATHER_OVER.match(text, m.end())))
        if words:
            found[kind] = words
    return found


#: Words naming a thing -> the one-cell iso object that shows it (put on a free cell of the place).
OBJECT_WORDS: dict[str, str] = {
    "dish": "satellite_dish", "satellite": "satellite_dish", "antenna": "satellite_dish", "telescope": "telescope",
    "campfire": "campfire", "bonfire": "campfire", "snowman": "snowman", "pumpkin": "pumpkin", "cake": "birthday_cake",
    "treasure chest": "treasure_chest", "treasure": "treasure_chest", "crystal": "giant_crystal", "cauldron": "cauldron",
    "potion": "cauldron", "bicycle": "bicycle", "bike": "bicycle", "television": "tv", "tv": "tv", "globe": "globe",
    "laptop": "laptop", "microscope": "microscope", "mailbox": "mailbox", "letterbox": "mailbox", "phone box": "phone_booth",
    "phone booth": "phone_booth", "statue": "statue", "signpost": "signpost", "christmas tree": "christmas_tree",
    "gifts": "gift_pile", "balloons": "balloon_bunch", "bees": "beehive", "beehive": "beehive",
    "scarecrow": "scarecrow", "wheelbarrow": "wheelbarrow", "stump": "stump", "fridge": "lab_fridge",
    "coffee machine": "coffee_machine", "vending machine": "vending_machine", "water cooler": "water_cooler",
    "robot arm": "robot_arm", "terminal": "terminal_kiosk", "kiosk": "terminal_kiosk", "servers": "server_rack",
    "racks": "server_rack", "lamp": "lamp", "street lamp": "street_lamp", "lighthouse": "lighthouse",
    "crib": "crib", "cradle": "crib", "armchair": "armchair", "throne": "throne", "printer": "printer",
    "boulder": "rock",
}
_OBJECT_PATTERN = _pattern(list(OBJECT_WORDS))


#: An object the story names: ``(word, kind, (column, row))``.
NamedObject = tuple[str, str, tuple[int, int]]


def objects_named(text: str, place: StoryPlace, added: Sequence[NamedObject] = ()) -> list[NamedObject]:
    """Objects ``text`` names that the place lacks (nor were ``added`` to it before), each on one
    of its free cells left, in the order named."""
    have = place.kinds() | {kind for _, kind, _ in added}
    free = [cell for cell in place.free if cell not in {c for _, _, c in added}]
    found: list[NamedObject] = []
    for match in _OBJECT_PATTERN.finditer(text):
        word = match.group(1).lower()
        kind = OBJECT_WORDS[word]
        if kind in have or len(found) >= len(free):
            continue
        have.add(kind)
        found.append((word, kind, free[len(found)]))
    return found


#: Built-in music beds (``vidgen list-music``) -> mood words that suggest them.
MUSIC_WORDS: dict[str, tuple[str, ...]] = {
    "lullaby": ("bedtime", "sleep", "asleep", "sleepy", "dream", "dreams", "dreamed", "lullaby", "goodnight", "yawned", "pillow"),
    "enigma": ("mystery", "mysterious", "secret", "secrets", "strange", "shadow", "shadows", "clue", "hidden", "missing",
               "vanished", "puzzle", "alarm", "creak", "whispered", "afraid", "fear"),
    "lab": ("experiment", "robot", "computer", "machine", "signal", "data", "code", "algorithm", "laboratory", "lab", "circuit"),
    "neon": ("neon", "city lights", "hologram", "cyber"),
    "tidewater": ("sea", "ocean", "harbour", "harbor", "voyage", "journey", "travel", "sail", "waves", "boat"),
    "calm": ("sad", "sadly", "lonely", "alone", "tears", "grief", "quiet", "quietly", "sorrow", "missed", "goodbye", "cried", "wept"),
    "bright": ("adventure", "excited", "celebrate", "party", "birthday", "cheered", "hooray", "festival", "won", "victory"),
    "cartoon": ("funny", "laughed", "giggled", "silly", "joke", "chuckled", "played", "game", "games", "grinned"),
}
#: The bed of a story without mood words (playful: cartoons).
DEFAULT_MUSIC = "cartoon"
_MUSIC_PATTERNS = {bed: _pattern(words) for bed, words in MUSIC_WORDS.items()}


def music_of(text: str) -> tuple[str, dict[str, int]]:
    """The music bed whose mood words ``text`` has most of, and the counts per bed."""
    counts = {bed: len(pattern.findall(text)) for bed, pattern in _MUSIC_PATTERNS.items()}
    counts = {bed: n for bed, n in counts.items() if n}
    if not counts:
        return DEFAULT_MUSIC, {}
    best = max(counts.values())
    return next(bed for bed in MUSIC_WORDS if counts.get(bed) == best), counts

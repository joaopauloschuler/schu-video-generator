"""Step 115: a random, well-contrasted cast. The contrast score (``cartoon/contrast.py``), the
seeded cast generator (``random_cast.py``), the lint rule ``look_alike``, ``vidgen cast`` and the
looks ``vidgen screenplay`` gives undeclared characters; all without rendering."""

from __future__ import annotations

import json
import math
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest
import yaml

from vidgen import cli, random_cast
from vidgen.cartoon.contrast import (
    COLOUR_WEIGHTS,
    MIN_CONTRAST,
    SILHOUETTE_WEIGHTS,
    WEIGHTS,
    character_pairs,
    compare,
    contrast_parts,
    contrast_score,
    look_features,
    min_contrast,
)
from vidgen.config import CharacterEntry, LintRules, ThemeConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.includes import read_include_file
from vidgen.lint import RULES, SceneContext
from vidgen.lint.run import _timing_findings
from vidgen.project import Project
from vidgen.random_cast import KIND_EXCLUDES, NAMES, balanced_kinds, parse_species, pick_looks, random_look
from vidgen.render.worker import scene_activity_path
from vidgen.screenplay import LOOKS, parse_screenplay, screenplay_project
from vidgen.theme import Theme

ROUND = {"body": "round", "hair": "bun", "accessories": ["scarf"]}
WARM = {"skin": "#F2C9A0", "clothes": "#D9534F", "hair": "#6B4226", "accessory": "#F2B134"}


def features(look: dict[str, Any] | None = None, colors: dict[str, Any] | None = None, theme: Theme | None = None) -> Any:
    return look_features(look if look is not None else ROUND, colors if colors is not None else WARM, theme)


# ----- the contrast score ---------------------------------------------------------------------------


def test_weights_add_up_and_the_score_is_a_symmetric_fraction() -> None:
    for table in (WEIGHTS, SILHOUETTE_WEIGHTS, COLOUR_WEIGHTS):
        assert math.isclose(sum(table.values()), 1.0)
    a, b = features(), features({"body": "tall", "hair": "afro", "species": "cat", "accessories": ["hat"]}, {"skin": "#3A3A3A", "clothes": "#4A7BD0"})
    assert contrast_score(a, a) == 0.0 and contrast_parts(a, a) == {"silhouette": 0.0, "colour": 0.0, "accessories": 0.0}
    assert math.isclose(contrast_score(a, b), contrast_score(b, a)) and 0.6 < contrast_score(a, b) <= 1.0
    assert all(0.0 <= v <= 1.0 for v in contrast_parts(a, b).values())


def test_each_part_counts_by_its_weight() -> None:
    base = features()
    body = features({**ROUND, "body": "tall"})
    assert math.isclose(contrast_score(base, body), WEIGHTS["silhouette"] * SILHOUETTE_WEIGHTS["body"])
    head = features({**ROUND, "head_size": 1.2})   # half of the head-size span
    assert math.isclose(contrast_score(base, head), WEIGHTS["silhouette"] * SILHOUETTE_WEIGHTS["head_size"] * 0.5)
    far = features(colors={**WARM, "clothes": "#2E8B8B"})   # red against teal: far apart in CIELAB
    assert math.isclose(contrast_score(base, far), WEIGHTS["colour"] * COLOUR_WEIGHTS["clothes"])
    near = features(colors={**WARM, "clothes": "#D65450"})  # nearly the same red
    assert 0 < contrast_score(base, near) < 0.01
    glasses = features({**ROUND, "accessories": ["scarf", "glasses"]})   # 1 of the 3 details differs
    assert math.isclose(contrast_score(base, glasses), WEIGHTS["accessories"] / 3)


def test_theme_tokens_are_resolved_and_bald_heads_show_skin() -> None:
    pastel, dark = Theme(ThemeConfig(preset="soft_pastel")), Theme(ThemeConfig(preset="dark_tech"))
    token = features(colors={**WARM, "clothes": "primary"}, theme=pastel)
    assert token.colors["clothes"] == pastel.color("primary")
    assert contrast_score(token, features(colors={**WARM, "clothes": pastel.color("primary")})) == 0.0
    assert contrast_score(token, features(colors={**WARM, "clothes": "primary"}, theme=dark)) > 0   # the same token, other colours
    bald = features({"body": "round"}, {**WARM, "hair": "#000000"})
    assert bald.colors["hair"] == WARM["skin"] and bald.colors["accessory"] == WARM["clothes"]   # nothing drawn in them
    assert look_features({"svg": "assets/kit.svg"}, {}) is None


def test_compare_names_what_the_pair_shares_and_what_to_change() -> None:
    pair = compare("ana", features(), "ben", features({**ROUND, "eyes": "round"}))
    assert pair.score < MIN_CONTRAST
    # by weight in the score: clothes 0.4 x 0.4, skin 0.4 x 0.3, body 0.45 x 0.25, hair 0.45 x 0.2...
    assert pair.shared[:4] == ["clothes colours close (ΔE 0)", "skin colours close (ΔE 0)", "body round", "hair bun"]
    assert pair.advice == "give 'ben' another colors.clothes, colors.skin, look.body"
    message = pair.message(MIN_CONTRAST)
    assert message.startswith(f"characters 'ana' and 'ben' look alike (contrast {pair.score:.2f}, needs {MIN_CONTRAST:g}): both have clothes")
    assert min_contrast(features(), []) == 1.0


def test_the_screenplay_looks_are_well_contrasted() -> None:
    theme = Theme(ThemeConfig(preset="soft_pastel"))
    looks = [features(lk["look"], lk["colors"], theme) for lk in LOOKS]
    assert min(contrast_score(a, b) for a, b in combinations(looks, 2)) >= MIN_CONTRAST + 0.1


# ----- the lint rule -----------------------------------------------------------------------------


def stage_config(characters: list[dict[str, Any]], scenes: list[list[str]]) -> dict[str, Any]:
    return {
        "title": "Cast", "characters": characters,
        "scenes": [{"id": f"s{k}", "type": "stage", "params": {"characters": names}, "beats": [{"text": "Hello there."}]}
                   for k, names in enumerate(scenes)],
    }


TWINS = [
    {"name": "ana", "look": ROUND, "colors": WARM},
    {"name": "ben", "look": {**ROUND, "eyes": "round"}, "colors": WARM},
    {"name": "cy", "look": {"body": "tall", "hair": "afro", "species": "dog"}, "colors": {"skin": "#3A3A3A", "clothes": "#4A7BD0"}},
    {"name": "svg", "look": {"svg": "assets/kit.svg"}},
]


def test_pairs_are_reported_where_the_later_character_first_appears() -> None:
    config = parse_config(stage_config(TWINS, [["ana", "svg"], [{"name": "cy", "at": "left"}, "ana"], ["ben"]]))
    pairs = character_pairs(config, None)
    assert [(where, p.first, p.second) for where, p in pairs] == [("s1", "ana", "cy"), ("s2", "ana", "ben"), ("s2", "cy", "ben")]
    low = [(where, p) for where, p in pairs if p.score < MIN_CONTRAST]
    assert [(where, p.first, p.second) for where, p in low] == [("s2", "ana", "ben")]

    rule = RULES["look_alike"]
    assert rule.scope == "scene" and rule.default == "warning"
    ctx = SceneContext("s2", {"fps": 5, "beats": [{"id": "s2_b1", "start": 0.0}]}, Path("."), character_pairs=[p for w, p in pairs if w == "s2"])
    issues = list(rule.check(ctx, LintRules().look_alike))
    assert len(issues) == 1 and issues[0].beat == "s2_b1" and issues[0].limit == MIN_CONTRAST
    assert "'ana' and 'ben' look alike" in issues[0].message and issues[0].message.endswith("give 'ben' another colors.clothes, colors.skin, look.body")
    assert not list(rule.check(ctx, LintRules.model_validate({"look_alike": {"min_contrast": 0.05}}).look_alike))


def test_lint_runner_fills_the_pairs_of_the_scene(make_project) -> None:
    root = make_project(stage_config(TWINS[:3], [["ana", "cy"], ["ben"]]))
    project = Project.load(root)
    for k in range(2):
        path = scene_activity_path(project, True, f"s{k}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fps": 5, "beats": [{"id": f"s{k}_b1", "start": 0.0}]}), encoding="utf-8")
    first, _ = _timing_findings(project, True, "s0", 0.0, ["look_alike"], {})
    second, _ = _timing_findings(project, True, "s1", 4.0, ["look_alike"], {})
    assert first == [] and [(f.rule, f.severity, f.beat, f.time) for f in second] == [("look_alike", "warning", "s1_b1", 4.0)]
    data = stage_config(TWINS[:3], [["ana", "cy"], ["ben"]])
    data["lint"] = {"rules": {"look_alike": {"severity": "off"}}}
    root = make_project(data, folder="off")
    for k in range(2):
        path = scene_activity_path(Project.load(root), True, f"s{k}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fps": 5, "beats": [{"id": f"s{k}_b1", "start": 0.0}]}), encoding="utf-8")
    assert _timing_findings(Project.load(root), True, "s1", 0.0, ["look_alike"], {})[0] == []


# ----- the generator ---------------------------------------------------------------------------------


def test_random_looks_fit_their_voice_kind_and_species() -> None:
    import random

    rng = random.Random(3)
    for kind in KIND_EXCLUDES:
        for _ in range(60):
            drawn = random_look(rng, kind)
            look = drawn["look"]
            used = {look.get("hair"), look.get("outfit"), look.get("facial_hair"), *look.get("accessories", [])}
            assert not used & KIND_EXCLUDES[kind], (kind, look)
            CharacterEntry.model_validate({"name": "x", "look": look, "colors": drawn["colors"]})   # every draw builds
    animals = [random_look(rng, "neutral", ["cat", "bird"])["look"] for _ in range(40)]
    assert {a["species"] for a in animals} == {"cat", "bird"} and not any({"ears", "nose", "facial_hair"} & set(a) for a in animals)
    assert balanced_kinds(7, random.Random(0)).count("neutral") in (2, 3) and sorted(balanced_kinds(3, random.Random(5))) == sorted(KIND_EXCLUDES)
    assert parse_species(None) == ["human"] and parse_species(["cat,dog", "cat"]) == ["cat", "dog"]
    with pytest.raises(VidgenError, match="unknown species 'unicorn'"):
        parse_species(["unicorn"])


def test_the_same_seed_gives_the_same_cast_and_a_bigger_cast_starts_alike() -> None:
    four, again, six = random_cast.random_cast(4, 7), random_cast.random_cast(4, 7), random_cast.random_cast(6, 7)
    assert four == again and four.characters != random_cast.random_cast(4, 8).characters
    assert six.characters[:4] == four.characters and list(six.voices)[:4] == list(four.voices)
    names = [c["name"] for c in six.characters]
    assert len(set(names)) == 6 and all(name in NAMES[six.kinds[name]] for name in names)   # a name of the character's kind
    voices = [six.voices[c["voice"]]["voice"] for c in six.characters]
    assert len(set(voices)) == 6 and "bf_emma" not in voices                                   # distinct, not the narrator's
    for name, voice in zip(names, voices):
        gender = {"feminine": "f", "masculine": "m"}.get(six.kinds[name])
        assert gender is None or voice[1] == gender
    taken = random_cast.random_cast(3, 7, taken=names[:3])
    assert not {c["name"] for c in taken.characters} & set(names[:3])


def test_greedy_choice_keeps_the_cast_apart(monkeypatch: pytest.MonkeyPatch) -> None:
    for seed in range(4):
        cast = random_cast.random_cast(8, seed, species=["human", "cat", "rabbit"])
        assert cast.lowest_contrast >= MIN_CONTRAST + 0.2
        assert {c["look"].get("species", "human") for c in cast.characters} == {"human", "cat", "rabbit"}
    greedy = sum(random_cast.random_cast(8, seed).lowest_contrast for seed in range(4))
    monkeypatch.setattr(random_cast, "CANDIDATES", 1)   # the first draw each time: no choice
    assert sum(random_cast.random_cast(8, seed).lowest_contrast for seed in range(4)) < greedy - 0.2


def test_other_voice_providers() -> None:
    routed = random_cast.random_cast(2, 1, voice={"provider": "openrouter", "model": "canopylabs/orpheus-3b-0.1-ft", "voice": "tara"})
    assert [v["voice"] for v in routed.voices.values()] == ["leah", "jess"] and not routed.notes
    eleven = random_cast.random_cast(2, 1, voice={"provider": "elevenlabs"})
    assert all(set(v) == {"label"} for v in eleven.voices.values()) and "of the kind that suits the character" in eleven.notes[0]
    with pytest.raises(VidgenError, match="give 1 to 24 characters"):
        random_cast.random_cast(0)


def test_curated_looks_come_first_while_they_stay_distinct() -> None:
    import random

    picks = pick_looks([None, "masculine"], random.Random(0), curated=LOOKS)
    assert [p["look"] for p in picks] == [LOOKS[0]["look"], LOOKS[1]["look"]]
    twin = features(LOOKS[0]["look"], LOOKS[0]["colors"])          # someone already looks like LOOKS[0]
    picks = pick_looks([None], random.Random(0), curated=LOOKS, existing=[twin])
    assert picks[0]["look"] == LOOKS[1]["look"]


# ----- vidgen cast -----------------------------------------------------------------------------------


def test_cast_command_writes_an_include_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "shared" / "cast.yaml"
    assert cli.main(["cast", "--random", "3", "--seed", "2", "--species", "human", "cat", "--out", str(out), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "cast" and doc["ok"] and doc["seed"] == 2 and doc["species"] == ["human", "cat"]
    assert doc["lowest_contrast"] >= MIN_CONTRAST and doc["min_contrast"] == MIN_CONTRAST and doc["provider"] == "kokoro"
    assert [set(c) for c in doc["characters"]] == [{"name", "voice_kind", "voice", "provider_voice", "look", "colors"}] * 3
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Written by `vidgen cast --random 3 --seed 2 --species human cat`")
    included = read_include_file(out)
    assert [c["name"] for c in included["characters"]] == [c["name"] for c in doc["characters"]]
    assert yaml.safe_load(text) == random_cast.random_cast(3, 2, species=["human", "cat"]).config()
    assert cli.main(["cast", "--random", "3", "--out", str(out)]) == 1
    assert "already exists" in capsys.readouterr().err
    assert cli.main(["cast", "--random", "2", "--out", str(out), "--force"]) == 0
    assert "wrote 2 characters" in capsys.readouterr().out
    assert cli.main(["cast", "--random", "2", "--out", str(tmp_path / "cast.txt")]) == 1

    story = tmp_path / "story.md"
    names = [c["name"].upper() for c in yaml.safe_load(out.read_text(encoding="utf-8"))["characters"]]
    story.write_text(f"# Scene: yard\n{names[0]}: Hello.\n{names[1]}: Hi.\nWREN: And me.\n", encoding="utf-8")
    assert cli.main(["screenplay", str(story), "--out", str(tmp_path / "proj"), "--cast", str(out), "--json"]) == 0
    made = json.loads(capsys.readouterr().out)
    assert made["ok"] and {c["name"] for c in made["characters"] if c["generated"]} == {"wren"}   # the cast's characters kept


# ----- vidgen screenplay -------------------------------------------------------------------------------


def _looks(text: str, **options: Any) -> list[dict[str, Any]]:
    return [c for c in screenplay_project(parse_screenplay(text), **options).config["characters"]]


def test_screenplay_takes_the_built_in_looks_then_random_ones() -> None:
    many = _looks("# Scene: a\n" + "".join(f"P{k}: Hi.\n" for k in range(14)))
    assert [c["look"] for c in many[:11]] == [lk["look"] for lk in LOOKS]                  # in order, as before
    theme = Theme(ThemeConfig(preset="soft_pastel"))
    all_features = [features(c["look"], c["colors"], theme) for c in many]
    assert min(min_contrast(f, all_features[:k]) for k, f in enumerate(all_features) if k) >= MIN_CONTRAST
    assert all("seed" not in c["look"] for c in many)                                        # no repeated look
    other = _looks("# Scene: a\n" + "".join(f"P{k}: Hi.\n" for k in range(14)), seed=5)
    assert other[:11] == many[:11] and other[11:] != many[11:]


def test_screenplay_avoids_a_declared_look_and_draws_animals() -> None:
    first = LOOKS[0]
    declared = _looks(f"---\ncharacters:\n  - {{name: ash, look: {json.dumps(first['look'])}, colors: {json.dumps(first['colors'])}}}\n---\n"
                      "# Scene: a\nASH: Hi.\nWREN: Yo.")
    assert declared[1]["look"] == LOOKS[1]["look"]   # LOOKS[0] is taken by a declared twin
    cats = _looks("# Scene: a\nFEN (she): Hi.\nBRAM: Yo.", species=["cat"])
    assert [c["look"]["species"] for c in cats] == ["cat", "cat"] and not {"ears", "nose"} & set(cats[0]["look"])

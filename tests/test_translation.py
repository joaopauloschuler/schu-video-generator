"""Step 51: multi-language variants — ``language:``, language-aware cues / lint / TTS, and
translation files (``vidgen translate-template``, keys, applying, merging, warnings)."""

from __future__ import annotations

import json
import shutil
import subprocess
import typing
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel

from conftest import minimal_config
from test_tts import FakeAPI, api, run  # noqa: F401  (fixture)
from vidgen import extensions, registry, tts
from vidgen.cli import main, validate_warnings
from vidgen.config import NarrationSpeedRule, VoiceConfig, parse_config
from vidgen.cues import COST_CLAUSE, COST_CLINGING, COST_CONJUNCTION, COST_PLAIN, COST_SENTENCE, phrase_break_cost, split_cues
from vidgen.describe import nested_models
from vidgen.errors import VidgenError
from vidgen.languages import elevenlabs_language_code, language_matches, language_rules, normalize_language, primary_language
from vidgen.lint.rules import SceneContext
from vidgen.lint.timing_rules import narration_speed
from vidgen.project import Project
from vidgen.speech import syllables
from vidgen.subtitles import cues_from_timings
from vidgen.translation import (
    TRANSLATABLE,
    TextMarker,
    TranslationEntry,
    TranslationFile,
    apply_translations,
    extract_texts,
    format_key,
    merge_template,
    parse_key,
    project_texts,
    read_text,
    source_hash,
)
from vidgen.tts.elevenlabs import ElevenLabsProvider
from vidgen.voices import resolve_voice

ROOT = Path(__file__).resolve().parents[1]


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def load_doc(path: Path) -> TranslationFile:
    return TranslationFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


# ----- languages ---------------------------------------------------------------------------------


def test_language_tags() -> None:
    assert normalize_language("PT-br") == "pt-BR" and normalize_language("zh-hant-tw") == "zh-Hant-TW"
    assert normalize_language("es-419") == "es-419"
    with pytest.raises(ValueError):
        normalize_language("portuguese brazil")
    assert primary_language("pt-BR") == "pt" and primary_language(None) == "en"
    assert language_matches("pt", "pt-BR") and language_matches("pt-BR", "pt-BR") and not language_matches("pt-BR", "pt-PT")
    assert language_matches("en", None) and not language_matches("pt", None)
    config = parse_config(minimal_config(language="PT-br"))
    assert config.language == "pt-BR"
    with pytest.raises(VidgenError, match="language"):
        parse_config(minimal_config(language="Português"))


def test_language_rules() -> None:
    assert language_rules(None) is language_rules("en-US")
    pt = language_rules("pt-BR")
    assert pt.known and pt.iso639_2 == "por" and pt.words_per_second == (1.7, 3.4)
    other = language_rules("ja")
    assert not other.known and other.words_per_second is None and other.iso639_2 == "jpn"
    assert language_rules("xx").iso639_2 is None


def test_portuguese_break_costs() -> None:
    assert phrase_break_cost("de", "dados", "pt-BR") == COST_CLINGING   # "de | dados": never
    assert phrase_break_cost("vídeo", "que", "pt-BR") == COST_CONJUNCTION
    assert phrase_break_cost("o", "vídeo", "pt-BR") == COST_CLINGING
    assert phrase_break_cost("o", "vídeo", None) == COST_PLAIN       # English rules know no "o"
    assert phrase_break_cost("de", "dados", "ja") == COST_PLAIN       # neutral: punctuation only
    assert phrase_break_cost("fim.", "Depois", "ja") == COST_SENTENCE
    assert phrase_break_cost("終わり。", "次", "ja") == COST_SENTENCE
    assert phrase_break_cost("dijo", "¿qué?", "es") == COST_CLAUSE
    assert phrase_break_cost("the", "video", None) == COST_CLINGING  # English unchanged


def test_portuguese_cues_never_end_on_an_article_or_preposition() -> None:
    text = (
        "Depois você renderiza uma prévia rápida do vídeo com as legendas e, por fim, gera o vídeo "
        "completo para a plataforma de vídeos que escolher"
    )
    clinging = language_rules("pt").clinging
    for width in (20, 26, 32, 42):
        for cue in split_cues(text, width, language="pt-BR"):
            for line in cue:
                assert line.split()[-1].lower() not in clinging, (width, cue)
    # the English rules would cut after "a" / "de" here
    english = [line for cue in split_cues(text, 26) for line in cue]
    assert any(line.split()[-1] in ("a", "de", "o", "do", "com", "as", "para") for line in english)


def test_syllables_by_language() -> None:
    assert syllables("pode", "pt-BR") == 2 and syllables("pode") == 1   # final e: said in Portuguese
    assert syllables("cidade", "pt") == 3


def test_srt_cues_follow_the_timings_language() -> None:
    text = "Escolha um tipo de cena para cada parte do vídeo e gere a voz uma vez só"
    timings = {"language": "pt-BR", "scenes": [{"beats": [{"id": "b", "start": 0.0, "end": 6.0, "text": text}]}]}
    clinging = language_rules("pt").clinging
    for cue in cues_from_timings(timings):
        for line in cue.text.splitlines():
            assert line.split()[-1] not in clinging


def test_narration_speed_by_language(tmp_path: Path) -> None:
    rule = NarrationSpeedRule()
    assert rule.limits(None) == ("words", 1.8, 3.5)
    assert rule.limits("pt-BR") == ("words", 1.7, 3.4)
    assert rule.limits("ja") == ("characters", 8.0, 17.0)
    assert NarrationSpeedRule(unit="characters", max_rate=20).limits("en") == ("characters", 8.0, 20.0)
    beat = {"id": "b1", "start": 0.0, "end": 2.0, "busy": 1.0, "source": "estimate", "text": "um dois três quatro cinco seis sete"}
    doc = {"fps": 10, "beats": [beat], "plays": [], "pad": 0.35}
    found = list(narration_speed(SceneContext("s", doc, tmp_path, {}, "pt-BR"), rule))   # 7 words / 2 s = 3.5 > 3.4
    assert len(found) == 1 and "words/s" in found[0].message and found[0].limit == 3.4
    assert list(narration_speed(SceneContext("s", doc, tmp_path, {}, None), rule)) == []   # English: 3.5 is fine
    long = {**beat, "text": "一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十 x y z w v"}
    found = list(narration_speed(SceneContext("s", {**doc, "beats": [long]}, tmp_path, {}, "ja"), rule))
    assert len(found) == 1 and "characters/s" in found[0].message


# ----- ElevenLabs language_code ------------------------------------------------------------------


def test_language_code_resolution() -> None:
    assert elevenlabs_language_code(None, "eleven_turbo_v2_5", "pt-BR") == "pt"
    assert elevenlabs_language_code(None, "eleven_multilingual_v2", "pt-BR") is None
    assert elevenlabs_language_code("PT", "eleven_multilingual_v2", None) == "pt"
    assert elevenlabs_language_code(False, "eleven_turbo_v2_5", "pt-BR") is None
    config = parse_config(minimal_config(language="pt-BR", voice={"model_id": "eleven_flash_v2_5"}, voices={"x": {"language_code": False}}))
    assert resolve_voice(config, None).language_code == "pt" and resolve_voice(config, "x").language_code is None
    plain = parse_config(minimal_config(language="pt-BR"))
    assert resolve_voice(plain, None) is plain.voice   # nothing sent: the voice is unchanged


def test_language_code_in_request_and_hash() -> None:
    base = ElevenLabsProvider(VoiceConfig())
    coded = ElevenLabsProvider(VoiceConfig(language_code="pt"))
    assert "language_code" not in base.request_body("Olá")
    assert coded.request_body("Olá")["language_code"] == "pt"
    assert coded.cache_key("Olá") != base.cache_key("Olá")
    assert coded.legacy_cache_key("Olá") is None and base.legacy_cache_key("Olá") is not None


def test_language_code_gives_a_variant_its_own_audio(make_project) -> None:
    variants = {"pt": {"language": "pt-BR"}, "turbo": {"language": "pt-BR", "voice": {"model_id": "eleven_turbo_v2_5"}}}
    root = make_project(minimal_config(voice={"model_id": "eleven_turbo_v2_5"}, variants={"pt": {"language": "pt-BR"}}))
    assert Project.load(root, variant="pt").has_own_audio   # the code "pt" is sent and hashed
    root = make_project(minimal_config(variants=variants), folder="other")
    assert not Project.load(root, variant="pt").has_own_audio   # multilingual_v2: nothing sent


# ----- pronunciation per language ----------------------------------------------------------------


def test_pronunciation_entries_by_language(make_project) -> None:
    pron = {"LaTeX": {"say": "lah-tek", "language": "en"}, "JSON": {"say": "djêisson", "language": ["pt", "es"]}}
    data = minimal_config(pronunciation=pron, variants={"pt": {"language": "pt-BR"}})
    data["scenes"][0]["beats"][0]["text"] = "LaTeX and JSON."
    root = make_project(data)
    assert Project.load(root).spoken_texts()["intro_b1"] == "lah-tek and JSON."
    assert Project.load(root, variant="pt").spoken_texts()["intro_b1"] == "LaTeX and djêisson."


def test_variant_keeping_base_pronunciation_warns(make_project) -> None:
    data = minimal_config(pronunciation={"Hello": "heh-low"}, variants={"pt": {"language": "pt-BR"}, "ok": {"language": "pt-BR", "pronunciation": {"Hello": "olá"}}})
    root = make_project(data)
    warnings = validate_warnings(Project.load(root, variant="pt"))
    assert any("pronunciation: 'Hello' from the base config" in w for w in warnings)
    assert not any("from the base config" in w for w in validate_warnings(Project.load(root, variant="ok")))


# ----- keys --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "title",
        "scenes.intro.beats.intro_b1.text",
        "scenes.s.params.items[0].text",
        'scenes.s.params.series["a b"][2][2]',
        'scenes.s.params.series{"a b"}',
        "scenes.d.params.nodes[0]=id.label",
        "scenes.d.params.edges[1]$:",
        "overlays.lower_third.name",
    ],
)
def test_key_round_trip(key: str) -> None:
    assert format_key(parse_key(key)) == key


def test_bad_keys() -> None:
    for key in ("", "[0]", "scenes..x", 'scenes.s{"a"}.b', "scenes.s$:.x"):
        with pytest.raises(ValueError):
            parse_key(key)
    with pytest.raises(Exception, match="not a translation key"):
        TranslationFile.model_validate({"entries": {"scenes..x": "y"}})


# ----- every built-in text is listed -------------------------------------------------------------

BOX = [0.1, 0.1, 0.2, 0.2]
#: Raw params per built-in scene type using every translatable param (all "T:..." strings are
#: texts; ``EXTRA`` lists texts that cannot carry the prefix).
SAMPLES: dict[str, list[dict[str, Any]]] = {
    "bar_chart": [{"title": "T:title", "labels": ["T:a", "T:b"], "values": [1, 2], "unit": "T:unit", "caption": "T:caption", "highlight": "T:b"}],
    "bullets": [{"heading": "T:heading", "items": ["T:one", {"text": "T:two", "icon": "pencil"}]}],
    "chapter": [{"title": "T:chapter", "number": "T:Part II", "subtitle": "T:sub"}],
    "code": [{"code": "print('hi')", "language": "python", "title": "T:title"}],
    "code_walkthrough": [{"code": "a = 1\nb = 2\n", "title": "T:title", "steps": ["1", {"lines": "2", "note": "T:note"}]}],
    "comparison": [
        {
            "columns": [{"heading": "T:left", "points": ["T:p1", {"text": "T:p2"}]}, {"heading": "T:right", "points": ["T:p3"]}],
            "heading": "T:heading",
            "verdict": "T:verdict",
            "vs": "T:vs",
        }
    ],
    "diagram": [
        {
            "nodes": ["Alpha", {"id": "b", "label": "T:b label"}, {"id": "Gamma"}],
            "edges": ["Alpha -> b: T:edge", {"from": "b", "to": "Gamma", "label": "T:edge2"}, "Alpha -> Gamma"],
            "heading": "T:heading",
        }
    ],
    "end_card": [{"title": "T:title", "lines": ["T:line"]}],
    "equation": [{"latex": "x = 1", "caption": "T:caption"}],
    "equation_derivation": [{"steps": ["x + 1 = 2", {"tex": "x = 1", "note": "T:note"}], "title": "T:title"}],
    "heatmap": [
        {
            "rows": ["T:r1", "T:r2"], "columns": ["T:c1", "T:c2"], "values": [[1, 2], [3, 4]], "title": "T:title", "unit": "T:unit",
            "legend_label": "T:legend", "caption": "T:caption", "highlight": ["row:T:r1"],
        }
    ],
    "histogram": [
        {
            "values": [1, 2, 3, 4], "name": "T:name", "compare": {"values": [2, 3], "name": "T:name2"}, "title": "T:title",
            "x_label": "T:x", "y_label": "T:y", "x_unit": "T:u", "caption": "T:caption",
        }
    ],
    "icon_grid": [
        {
            "items": [{"icon": "cpu", "label": "T:a", "sublabel": "T:sa"}, {"icon": "cpu", "label": "T:b"}],
            "heading": "T:heading", "groups": [[0], ["T:b"]], "highlight": "T:a",
        }
    ],
    "image": [{"path": "x.png", "caption": "T:caption"}],
    "line_chart": [
        {"x": ["T:jan", "T:feb"], "series": {"T:s1": [1, 2]}, "title": "T:title", "x_label": "T:x", "y_label": "T:y", "unit": "T:unit", "caption": "T:caption"},
        {"x": [1, 2], "series": [{"name": "T:named", "values": [1, 2]}]},
    ],
    "map": [
        {
            "title": "T:title",
            "countries": ["DE", {"country": "FR", "label": "T:France"}],
            "pins": [{"lon": 0, "lat": 0, "label": "T:pin"}],
            "arcs": [{"from": "T:pin", "to": "FR", "label": "T:arc"}, "DE -> FR"],
            "steps": [["PT"], {"pins": [{"country": "ES", "label": "T:pin2"}]}],
            "caption": "T:caption",
        },
        {"values": {"DE": 1, "FR": 2}, "unit": "T:unit", "legend_label": "T:legend"},
    ],
    "network": [{"layers": [3, {"size": 2, "label": "T:hidden"}], "heading": "T:heading"}],
    "pie": [
        {
            "labels": ["T:a", "T:b"], "values": [1, 2], "donut": True, "title": "T:title", "center": "T:center", "center_label": "T:cl", "unit": "T:unit",
            "other_label": "T:other", "caption": "T:caption", "highlight": "T:a",
        }
    ],
    "process": [
        {
            "stages": ["T:s1", {"label": "T:s2", "text": "T:t2"}], "heading": "T:heading", "loop": True, "loop_label": "T:loop",
            "input": "T:in", "output": "T:out", "token_label": "T:token",
        }
    ],
    "quote": [{"text": "T:text", "author": "T:author", "source": "T:source"}],
    "scatter": [
        {
            "series": {"T:s": [[1, 2, "T:p"], {"x": 2, "y": 3, "label": "T:q"}, [3, 1]]}, "title": "T:title", "x_label": "T:x",
            "y_label": "T:y", "x_unit": "T:xu", "y_unit": "T:yu", "caption": "T:caption", "highlight": "T:p",
        },
        {"series": [{"name": "T:named", "points": [[1, 2], [2, 3, "T:pt"]]}]},
    ],
    "screenshot": [
        {
            "path": "x.png", "title": "T:title", "caption": "T:caption", "url": "example.com",
            "steps": [[{"box": BOX, "label": "T:c1"}], {"box": BOX, "label": "T:c2"}, {"callouts": [{"box": BOX, "label": "T:c3"}]}],
        }
    ],
    "stat": [
        {
            "value": 12, "label": "T:label", "context": "T:context", "prefix": "T:p", "suffix": "T:s", "unit": "T:u",
            "thousands": "T:", "decimal_mark": ",", "comparison": {"value": 10, "label": "T:cmp", "word": "T:word"},
        }
    ],
    "table": [{"rows": [["T:a", 1], ["T:b", 2.5]], "header": ["T:h1", "T:h2"], "title": "T:title", "caption": "T:caption"}],
    "text_card": [{"text": "T:text"}],
    "timeline": [
        {
            "events": [{"date": "T:d1", "title": "T:e1", "text": "T:x1"}, {"date": 2020, "title": "T:e2"}],
            "heading": "T:heading", "highlight": "T:e1", "now": "T:d1", "now_label": "T:now",
        }
    ],
    "title": [{"title": "T:title T:hl", "subtitle": "T:sub", "kicker": "T:kicker", "authors": ["T:a"], "highlight": "T:hl"}],
    "video_clip": [{"path": "x.mp4", "title": "T:title", "caption": "T:caption", "steps": [[{"box": BOX, "label": "T:c"}]]}],
}
SAMPLES["flowchart"] = SAMPLES["diagram"]
EXTRA: dict[str, set[str]] = {"diagram": {"Alpha", "Gamma", "T:edge"}, "flowchart": {"Alpha", "Gamma", "T:edge"}, "stat": {","}}
#: References each sample's TextRef params make (place -> text key, relative to the scene).
REFS: dict[str, dict[str, str]] = {
    "bar_chart": {"params.highlight": "params.labels[1]"},
    "heatmap": {"params.highlight[0]": "params.rows[0]"},
    "icon_grid": {"params.groups[1][0]": "params.items[1].label", "params.highlight": "params.items[0].label"},
    "pie": {"params.highlight": "params.labels[0]"},
    "scatter": {"params.highlight": "params.series[\"T:s\"][0][2]"},
    "timeline": {"params.highlight": "params.events[0].title", "params.now": "params.events[0].date"},
    "map": {"params.arcs[0].from": "params.pins[0].label"},
}


def _strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return {k for k in value if isinstance(k, str)} | {s for v in value.values() for s in _strings(v)}
    if isinstance(value, list):
        return {s for v in value for s in _strings(v)}
    return set()


def _marked(annotation: Any, metadata: Any = ()) -> bool:
    if any(m == TRANSLATABLE for m in metadata):
        return True
    if typing.get_origin(annotation) is typing.Annotated:
        args = typing.get_args(annotation)
        return any(m == TRANSLATABLE for m in args[1:]) or _marked(args[0])
    return any(_marked(a) for a in typing.get_args(annotation))


def _text_fields(model: type[BaseModel], seen: set[type] | None = None) -> set[tuple[str, str]]:
    seen = set() if seen is None else seen
    if model in seen:
        return set()
    seen.add(model)
    out = {(model.__name__, name) for name, info in model.model_fields.items() if _marked(info.annotation, info.metadata)}
    for info in model.model_fields.values():
        for sub in nested_models(info.annotation):
            out |= _text_fields(sub, seen)
    return out


def _lookups() -> tuple[Any, Any, Any]:
    return (
        lambda n: (e.params_model if (e := registry.find(n)) else None),
        lambda n: (e.cls.Options if (e := registry.find_action(n)) else None),
        lambda n: (e.cls.Options if (e := registry.find_overlay(n)) else None),
    )


def _builtins() -> list[str]:
    with registry.isolated():
        extensions.load_builtins()
        return registry.names()


def test_every_builtin_type_has_a_sample() -> None:
    assert sorted(SAMPLES) == sorted(_builtins())


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_every_translatable_param_is_listed(name: str) -> None:
    extensions.load_builtins()
    entry = registry.get(name)
    keys: list[str] = []
    for k, params in enumerate(SAMPLES[name]):
        entry.cls.validate_params(params)   # the sample is a valid config
        data = {"title": "x", "scenes": [{"id": "s", "type": name, "params": params, "duration": 1}]}
        items, refs = extract_texts(data, *_lookups())
        expected = {s for s in _strings(params) if s.startswith("T:")} | EXTRA.get(name, set())
        assert {i.source for i in items} - {"x"} == expected, (name, k)
        for item in items:
            assert read_text(data, item.key) == item.source, item.key   # every key leads back to its text
        keys += [i.key for i in items]
        if k == 0:
            want = {f"scenes.s.{place}": f"scenes.s.{key}" for place, key in REFS.get(name, {}).items()}
            assert refs == want
    # every param marked translatable in the type's models is used by a sample
    used = {seg.value for key in keys for seg in parse_key(key) if seg.kind in ("field", "item")}
    missing = sorted(f"{model}.{field}" for model, field in _text_fields(entry.params_model) if field not in used)
    assert not missing, f"{name}: translatable params not in its sample: {missing}"


def test_actions_overlays_and_top_level_texts_are_listed() -> None:
    extensions.load_builtins()
    data = minimal_config(
        metadata={"title": "Meta", "artist": "Jane"},
        chapters={"intro": "Opening"},
        thumbnail={"title": "Thumb", "subtitle": "Sub"},
        overlays=[{"type": "lower_third", "name": "Ana", "title": "Host", "scene": "intro"}, {"type": "watermark", "text": "Mark"}],
    )
    data["scenes"][0]["chapter"] = "Part one"
    data["scenes"][1]["chapter"] = {"title": "Part two", "number": 2}
    data["scenes"][1]["overlays"] = {"lower_third": {"title": "Guest"}, "tag": {"type": "watermark", "text": "Local"}}
    data["scenes"][0]["beats"][0]["actions"] = [{"callout": "text", "label": "Look"}, {"highlight": "text"}]
    items, _ = extract_texts(data, *_lookups())
    got = {i.key: i.source for i in items}
    assert got == {
        "title": "Test video",
        "metadata.title": "Meta",
        "thumbnail.title": "Thumb",
        "thumbnail.subtitle": "Sub",
        "chapters.intro": "Opening",
        "overlays.lower_third.name": "Ana",
        "overlays.lower_third.title": "Host",
        "overlays.watermark.text": "Mark",
        "scenes.intro.chapter": "Part one",
        "scenes.intro.params.text": "Hello",
        "scenes.intro.beats.intro_b1.text": "Hello there.",
        "scenes.intro.beats.intro_b1.actions[0].label": "Look",
        "scenes.intro.beats.intro_b2.text": "Second beat.",
        "scenes.main.chapter.title": "Part two",
        "scenes.main.params.text": "Main",
        "scenes.main.beats.custom.text": "One two three four.",
        "scenes.main.overlays.lower_third.title": "Guest",
        "scenes.main.overlays.tag.text": "Local",
    }


def test_text_markers_in_the_json_schema() -> None:
    extensions.load_builtins()
    schema = registry.get("bullets").params_model.model_json_schema()
    assert schema["properties"]["heading"]["x-vidgen-text"] == "text"
    assert TextMarker("ref") != TRANSLATABLE


# ----- applying ----------------------------------------------------------------------------------


def chart_config() -> dict[str, Any]:
    """A bar chart and a diagram whose labels are used as targets / references."""
    return minimal_config(
        scenes=[
            {
                "id": "bars",
                "type": "bar_chart",
                "params": {"title": "Speed", "labels": ["Fast", "Slow"], "values": [1, 2], "highlight": "Slow"},
                "beats": [{"text": "Look at the fast bar.", "actions": [{"highlight": "bar:Fast"}, {"action": "dim", "target": ["bar:Slow", "bar1"]}]}],
            },
            {
                "id": "flow",
                "type": "diagram",
                "params": {"nodes": ["Start", {"id": "end", "label": "End"}], "edges": ["Start -> end: go"]},
                "beats": [{"text": "It flows."}],
            },
            {
                "id": "trend",
                "type": "line_chart",
                "params": {"x": [1, 2], "series": {"base": [1, 2]}},
                "beats": [{"text": "A line.", "actions": [{"callout": "point:base@2", "label": "Top"}]}],
            },
        ]
    )


PT = {
    "title": "Vídeo de teste",
    "scenes.bars.params.title": "Velocidade",
    "scenes.bars.params.labels[0]": "Rápido",
    "scenes.bars.params.labels[1]": "Lento",
    "scenes.bars.beats.bars_b1.text": "Veja a barra rápida.",
    "scenes.flow.params.nodes[0]=id.label": "Início",
    "scenes.flow.params.nodes[1]=id.label": "Fim",
    "scenes.flow.params.edges[0]$:": "vai",
    'scenes.trend.params.series{"base"}': "base PT",
    "scenes.trend.beats.trend_b1.actions[0].label": "Topo",
}


def translated_project(make_project, texts: dict[str, str] = PT, data: dict[str, Any] | None = None) -> tuple[Path, Project]:
    data = chart_config() if data is None else data
    data["variants"] = {"pt": {"language": "pt-BR", "translations": "translations/pt.yaml"}}
    root = make_project(data)
    assert main(["translate-template", str(root), "--variant", "pt"]) == 0
    path = root / "translations" / "pt.yaml"
    doc = load_doc(path)
    entries = {k: e.model_copy(update={"text": texts.get(k)}) for k, e in doc.entries.items()}
    write_yaml(path, {"version": 1, "language": "pt-BR", "entries": {k: e.model_dump(exclude_defaults=True) for k, e in entries.items()}, "references": doc.references})
    return root, Project.load(root, variant="pt")


def test_translations_are_applied(make_project) -> None:
    root, project = translated_project(make_project)
    config = project.config
    bars, flow, trend = config.scenes
    assert config.title == "Vídeo de teste"
    assert bars.params["labels"] == ["Rápido", "Lento"] and bars.params["highlight"] == "Lento"
    assert bars.beats[0].text == "Veja a barra rápida."
    assert [a.targets() for a in bars.beats[0].actions] == [["bar:Rápido"], ["bar:Lento", "bar1"]]
    assert flow.params["nodes"] == [{"id": "Start", "label": "Início"}, {"id": "end", "label": "Fim"}]
    assert flow.params["edges"] == ["Start -> end: vai"]
    assert list(trend.params["series"]) == ["base PT"]
    assert trend.beats[0].actions[0].targets() == ["point:base PT@2"] and trend.beats[0].actions[0].options["label"] == "Topo"
    # untranslated texts keep their source; the base config is untouched
    assert flow.beats[0].text == "It flows." and Project.load(root).config.title == "Test video"
    report = project.translation
    assert report is not None and not report.stale and not report.unknown and not report.broken
    assert set(report.applied) == set(PT)
    # the translated project is valid (targets resolve) and its own audio folder holds the new beats
    from vidgen.cli import project_problems

    assert project_problems(project) == []
    assert project.has_own_audio and project.audio_dir == root / "audio" / "pt"


def test_untranslated_and_stale_texts_keep_the_source(make_project) -> None:
    root, project = translated_project(make_project, texts={"scenes.bars.params.title": "Velocidade"})
    assert project.config.scenes[0].params["title"] == "Velocidade" and not project.has_own_audio   # no beat text changed
    warnings = validate_warnings(project)
    assert any("texts are not translated and show the source text: title, scenes.bars.params.labels[0]" in w for w in warnings)
    # the source changes: the translation is stale and not used
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["scenes"][0]["params"]["title"] = "Speed of renders"
    write_yaml(root / "video.yaml", data)
    project = Project.load(root, variant="pt")
    assert project.config.scenes[0].params["title"] == "Speed of renders"
    assert project.translation is not None and project.translation.stale == ["scenes.bars.params.title"]
    assert any("1 translations are not used because their source text changed (stale)" in w for w in validate_warnings(project))


def test_short_entries_unknown_keys_and_a_missing_file(make_project) -> None:
    data = chart_config()
    data["translations"] = "tr.yaml"
    root = make_project(data)
    project = Project.load(root)
    assert project.translation is not None and project.translation.missing
    assert any("the file does not exist" in w for w in validate_warnings(project))
    write_yaml(root / "tr.yaml", {"entries": {"title": "Título", "scenes.nope.params.title": "x", "scenes.bars.params.title": None}})
    project = Project.load(root)
    assert project.config.title == "Título" and project.translation.untranslated == ["scenes.bars.params.title"]
    assert project.translation.unknown == ["scenes.nope.params.title"]
    assert any("1 entries name nothing in the config: scenes.nope.params.title" in w for w in validate_warnings(project))
    write_yaml(root / "tr.yaml", {"entries": {"title": {"txt": "x"}}})
    with pytest.raises(VidgenError) as info:
        Project.load(root)
    assert info.value.problems[0].location.startswith("translations (tr.yaml)")


def test_apply_keeps_spaces_and_needs_no_scene_types() -> None:
    data = {"scenes": [{"id": "s", "params": {"unit": " min", "x": {"a": [1]}}}]}
    doc = TranslationFile(entries={"scenes.s.params.unit": TranslationEntry(source=" min", hash=source_hash(" min"), text=" min.\n")})
    out, report = apply_translations(data, doc)
    assert out["scenes"][0]["params"]["unit"] == " min." and data["scenes"][0]["params"]["unit"] == " min"
    assert list(report.applied) == ["scenes.s.params.unit"]


# ----- the template command and merging ----------------------------------------------------------


def test_translate_template_writes_and_merges(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    data = chart_config()
    data["variants"] = {"pt": {"language": "pt-BR"}}
    root = make_project(data)
    assert main(["translate-template", str(root), "--variant", "pt"]) == 0
    out = capsys.readouterr().out
    path = root / "translations" / "pt.yaml"
    assert path.is_file() and "next: add `translations: translations/pt.yaml` to the variant 'pt'" in out
    doc = load_doc(path)
    assert doc.language == "pt-BR" and doc.entries["title"].source == "Test video" and doc.entries["title"].text is None
    assert doc.entries["title"].hash == source_hash("Test video")
    assert doc.references == {
        "scenes.bars.params.highlight": "scenes.bars.params.labels[1]",
        "scenes.bars.beats.bars_b1.actions[0].highlight": "scenes.bars.params.labels[0]",
        "scenes.bars.beats.bars_b1.actions[1].target[0]": "scenes.bars.params.labels[1]",
        "scenes.trend.beats.trend_b1.actions[0].callout": 'scenes.trend.params.series{"base"}',
    }
    assert path.read_text(encoding="utf-8").startswith("# Translation of 'Test video' (variant 'pt')")
    # translate two texts, then change the config: one source edited, one item inserted before another
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["entries"]["scenes.bars.params.title"]["text"] = "Velocidade"
    raw["entries"]["scenes.bars.params.labels[1]"]["text"] = "Lento"
    raw["entries"]["scenes.bars.beats.bars_b1.text"]["text"] = "Veja."
    raw["entries"]["scenes.trend.beats.trend_b1.actions[0].label"]["text"] = "Topo"
    write_yaml(path, raw)
    data["scenes"].pop()
    data["scenes"][0]["params"]["title"] = "Render speed"
    data["scenes"][0]["params"]["labels"] = ["Fast", "Medium", "Slow"]
    data["scenes"][0]["params"]["values"] = [1, 2, 3]
    data["scenes"][0]["beats"] = [{"text": "New text."}]
    write_yaml(root / "video.yaml", data)
    assert main(["translate-template", str(root), "--variant", "pt", "--json"]) == 0
    doc_json = json.loads(capsys.readouterr().out)
    assert doc_json["stale"] == ["scenes.bars.params.title", "scenes.bars.beats.bars_b1.text"]
    assert doc_json["moved"] == ["scenes.bars.params.labels[2]"] and doc_json["translated"] == 1
    assert doc_json["obsolete"] == ["scenes.trend.beats.trend_b1.actions[0].label"]
    assert "scenes.trend.params.series{\"base\"}" in doc_json["dropped"]
    assert doc_json["linked"] is False and doc_json["language"] == "pt-BR"
    doc = load_doc(path)
    title = doc.entries["scenes.bars.params.title"]
    assert (title.text, title.stale, title.old_source, title.source) == ("Velocidade", True, "Speed", "Render speed")
    assert doc.entries["scenes.bars.params.labels[2]"].text == "Lento" and doc.entries["scenes.bars.params.labels[1]"].text is None
    beat = doc.entries["scenes.bars.beats.bars_b1.text"]
    assert (beat.text, beat.stale, beat.old_source) == ("Veja.", True, "Look at the fast bar.")
    assert doc.entries["scenes.trend.beats.trend_b1.actions[0].label"].obsolete
    # a third run keeps everything as it is
    assert main(["translate-template", str(root), "--variant", "pt", "--lang", "pt-BR"]) == 0
    assert load_doc(path) == doc


def test_merge_template_unit() -> None:
    from vidgen.translation import TextItem

    old = TranslationFile(
        entries={
            "a": TranslationEntry(source="One", hash=source_hash("One"), text="Um"),
            "b": TranslationEntry(source="Two", hash=source_hash("Two"), text=None),
            "c": TranslationEntry(text="Três"),   # hand-written: no source / hash
        }
    )
    doc, stats = merge_template([TextItem("a", "One"), TextItem("c", "Three")], {}, old, "pt", "en")
    assert doc.entries["a"].text == "Um" and doc.entries["c"].text == "Três" and not doc.entries["c"].stale
    assert stats.kept == ["a", "c"] and stats.dropped == ["b"] and doc.language == "pt" and doc.source_language == "en"


def test_template_needs_a_valid_lang(make_project) -> None:
    root = make_project(minimal_config(variants={"pt": {}}))
    assert main(["translate-template", str(root), "--variant", "pt", "--lang", "Portuguese please"]) == 1


def test_validate_json_reports_translations(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root, _ = translated_project(make_project, texts={"title": "Título"})
    capsys.readouterr()
    assert main(["validate", str(root), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    (variant,) = doc["variants"]
    assert variant["language"] == "pt-BR"
    assert variant["translations"]["file"] == "translations/pt.yaml" and variant["translations"]["applied"] == 1
    assert any("texts are not translated" in w["message"] for w in doc["warnings"])


def test_project_texts_of_the_example() -> None:
    project = Project.load(ROOT / "examples" / "minimal", variant="pt")
    report = project.translation
    assert report is not None and report.language == "pt-BR"
    assert not report.stale and not report.unknown and not report.broken and len(report.applied) >= 50
    with extensions.project_session(project):
        items, references = project_texts(project)
    assert {i.key for i in items} == set(load_doc(ROOT / "examples" / "minimal" / "translations" / "pt.yaml").entries)
    assert references == report.references
    trend = project.scene("trend")
    assert trend.beats[1].actions[0].targets() == ["point:esparso@8"]
    assert project.audio_dir.name == "pt"


# ----- outputs -----------------------------------------------------------------------------------


@pytest.mark.render
def test_rendered_variant_outputs_are_translated(make_project) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg / ffprobe not found on PATH")
    from vidgen.render.pipeline import render_project

    scenes = [
        {"id": "a", "type": "text_card", "params": {"text": "Hello"}, "chapter": "Start", "beats": [{"text": "Hello there, how are you?"}]},
        {"id": "b", "type": "text_card", "params": {"text": "Bye"}, "chapter": "End", "duration": 1.0},
    ]
    data = minimal_config(output="out", preview={"width": 160, "height": 90, "fps": 5}, scenes=scenes)
    data["variants"] = {"pt": {"language": "pt-BR", "translations": "pt.yaml"}}
    root = make_project(data)
    write_yaml(root / "pt.yaml", {"entries": {"scenes.a.beats.a_b1.text": "Olá, tudo bem com você?", "scenes.b.chapter": "Fim"}})
    project = Project.load(root, variant="pt")
    result = render_project(project, preview=True, no_audio=True)
    assert "Olá, tudo bem com você?" in result.srt.read_text(encoding="utf-8")
    assert json.loads((project.render_dir(True) / "timings.json").read_text(encoding="utf-8"))["language"] == "pt-BR"
    assert "Fim" in project.chapters_path(True).read_text(encoding="utf-8")
    probe = subprocess.run(
        [shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(result.output)],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    audio = [s for s in json.loads(probe.stdout)["streams"] if s["codec_type"] == "audio"]
    assert audio and audio[0]["tags"]["language"] == "por"


def test_tts_voices_translated_beats_into_the_variant_folder(make_project, api: FakeAPI) -> None:  # noqa: F811
    root, project = translated_project(make_project, texts={"scenes.bars.beats.bars_b1.text": "Veja a barra rápida."})
    assert run(root) == 0   # the base: 3 beats into audio/
    assert main(["tts", str(root), "--variant", "pt"]) == 0
    assert api.texts()[-1] == "Veja a barra rápida."
    assert len(api.requests) == 4   # the two untranslated beats are copied from audio/
    pt = root / "audio" / "pt"
    assert sorted(p.name for p in pt.glob("*.mp3")) == ["bars_b1.mp3", "flow_b1.mp3", "trend_b1.mp3"]
    assert tts.format_audio_summary(tts.audio_status(project)) == "3 ok, 0 stale, 0 missing"

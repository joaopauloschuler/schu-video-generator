"""Config models: defaults, beat ids, validation errors."""

from __future__ import annotations

import pytest

from conftest import minimal_config
from vidgen.config import BeatConfig, format_location, parse_config
from vidgen.errors import VidgenError


def test_defaults() -> None:
    data = minimal_config()
    del data["scenes"][0]["params"]
    cfg = parse_config(data)
    assert cfg.output is None
    assert (cfg.format.width, cfg.format.height, cfg.format.fps) == (1920, 1080, 30)
    assert (cfg.preview.width, cfg.preview.height, cfg.preview.fps) == (854, 480, 15)
    assert cfg.variants == {}
    assert cfg.theme.preset is None and cfg.theme.code_style is None
    assert cfg.theme.background is None and cfg.theme.font is None  # Theme fills in the defaults
    assert cfg.theme.colors == {} and cfg.theme.palette is None
    assert cfg.voice.provider == "elevenlabs"
    assert cfg.voice.voice_id == "nPczCjzI2devNBz1zQrb"
    assert cfg.voice.model_id == "eleven_multilingual_v2"
    assert cfg.voice.output_format == "mp3_44100_128"
    assert cfg.voice.settings.model_dump() == {
        "stability": 0.55, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True,
    }
    assert cfg.voice.context is True
    assert cfg.narration.pad == 0.35 and cfg.narration.words_per_second == 2.6
    assert cfg.extensions == ["extensions"]
    assert cfg.scenes[0].params == {}


def test_beat_ids_default_to_scene_and_index() -> None:
    cfg = parse_config(minimal_config())
    assert [b.id for b in cfg.scenes[0].beats] == ["intro_b1", "intro_b2"]
    assert [b.id for b in cfg.scenes[1].beats] == ["custom"]


def test_beat_id_default_counts_position_including_explicit_ids() -> None:
    data = minimal_config(scenes=[{"id": "s", "type": "t", "beats": [{"id": "x", "text": "a"}, {"text": "b"}]}])
    assert [b.id for b in parse_config(data).scenes[0].beats] == ["x", "s_b2"]


def test_params_and_theme_colors_are_open() -> None:
    data = minimal_config(theme={"colors": {"k2": "#F2A541"}})
    data["scenes"][0]["params"] = {"anything": [1, 2], "nested": {"ok": True}}
    cfg = parse_config(data)
    assert cfg.theme.colors == {"k2": "#F2A541"}
    assert cfg.scenes[0].params["nested"] == {"ok": True}


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda d: d.update(titel="x"), "titel: unknown key 'titel'; did you mean 'title'? (known: title, output, format,"),
        (lambda d: d.update(format={"widht": 3}), "format.widht: unknown key 'widht'; did you mean 'width'? (known: width, height, fps)"),
        (lambda d: d["scenes"][1]["beats"][0].update(txt="x"), "scenes[1].beats[0].txt: unknown key 'txt'; did you mean 'text'?"),
        (lambda d: d["scenes"][1]["beats"][0].update(id="bad id"), "scenes[1].beats[0].id: String should match"),
        (lambda d: d["scenes"][0].update(id="a-b"), "scenes[0].id: String should match"),
        (lambda d: d.update(voice={"provider": "openai"}), "voice.provider: Input should be 'elevenlabs'"),
        (lambda d: d.update(scenes=[]), "scenes: List should have at least 1 item"),
        (lambda d: d.pop("title"), "title: Field required"),
        (lambda d: d.update(theme={"colors": {"x": "red"}}), "theme.colors.x: String should match"),
    ],
)
def test_structural_errors_are_readable(mutate, expected: str) -> None:
    data = minimal_config()
    mutate(data)
    with pytest.raises(VidgenError) as info:
        parse_config(data, "video.yaml")
    message = str(info.value)
    assert message.startswith("video.yaml: invalid config")
    assert expected in message


def test_duplicate_scene_ids() -> None:
    data = minimal_config()
    data["scenes"][1]["id"] = "intro"
    with pytest.raises(VidgenError, match=r"duplicate scene id 'intro' \(scenes\[0\] and scenes\[1\]\)"):
        parse_config(data)


def test_duplicate_beat_ids_across_scenes() -> None:
    data = minimal_config()
    data["scenes"][1]["beats"][0]["id"] = "intro_b2"
    with pytest.raises(VidgenError) as info:
        parse_config(data)
    assert "duplicate beat id 'intro_b2' (scenes[0].beats[1] and scenes[1].beats[0])" in str(info.value)
    assert "Value error" not in str(info.value)


def test_silent_scene_needs_duration() -> None:
    data = minimal_config()
    data["scenes"].append({"id": "pause", "type": "title"})
    with pytest.raises(VidgenError, match=r"scenes\[2\]: a scene without beats"):
        parse_config(data)
    data["scenes"][2]["duration"] = 2.5
    cfg = parse_config(data)
    assert cfg.scenes[2].silent and cfg.scenes[2].duration == 2.5


def test_duration_rejected_on_narrated_scene() -> None:
    data = minimal_config()
    data["scenes"][0]["duration"] = 3
    with pytest.raises(VidgenError, match="only allowed on silent scenes"):
        parse_config(data)


def test_top_level_must_be_mapping() -> None:
    with pytest.raises(VidgenError, match="top level must be a mapping"):
        parse_config(["not", "a", "dict"], "video.yaml")


def test_variant_must_not_nest_variants() -> None:
    with pytest.raises(VidgenError, match="must not contain 'variants'"):
        parse_config(minimal_config(variants={"v": {"variants": {}}}))


def test_format_location() -> None:
    assert format_location(("scenes", 2, "beats", 0, "id")) == "scenes[2].beats[0].id"
    assert format_location(()) == ""


def test_beat_estimated_duration() -> None:
    assert BeatConfig(id="b", text="one two three four five").estimated_duration(2.5) == 2.0

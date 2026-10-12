"""`cartoon_style:` (Step 77): added to the `generate:` prompts of `stage` scenes only, part of
their cache key, changed by a variant; other pictures keep their keys. No network, no render."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from conftest import minimal_config
from vidgen.errors import VidgenError
from vidgen.imagegen import GenerateImage, image_request, scene_images
from vidgen.imagegen.run import plan_imagegen, used_keys
from vidgen.project import Project
from vidgen.scene import NarratedScene

STYLE = "flat colours, thick outlines, soft shadows"
#: The key of "a cat" with the default OpenAI settings, pinned since Step 61
#: (`test_imagegen_openrouter.test_openai_keys_are_unchanged`).
CAT_KEY = "834a61963bcbaf9e"


def scenes(prompt: str = "a cat") -> list[dict[str, Any]]:
    beat = [{"text": "A picture."}]
    return [
        {"id": "set", "type": "stage", "params": {"generate": prompt}, "beats": beat},
        {"id": "pic", "type": "image", "params": {"generate": prompt}, "beats": beat},
    ]


@pytest.fixture
def styled(make_project):
    def make(**overrides: Any) -> Project:
        return Project.load(make_project(minimal_config(scenes=scenes(), **overrides)))

    return make


def requests(project: Project) -> dict[str, Any]:
    return {i.scene_id: i.request for i in scene_images(project)}


def test_without_cartoon_style_every_key_is_unchanged(styled) -> None:
    found = requests(styled())
    assert found["set"].key == found["pic"].key == CAT_KEY


def test_cartoon_style_changes_only_stage_prompts(styled) -> None:
    found = requests(styled(cartoon_style=STYLE))
    assert found["pic"].key == CAT_KEY and found["pic"].text == "a cat."       # image scene untouched
    assert found["set"].text == f"a cat. Style: {STYLE}."
    assert found["set"].style == STYLE and found["set"].key != CAT_KEY


def test_cartoon_style_follows_the_style_words_and_survives_style_none(styled) -> None:
    project = styled(cartoon_style=STYLE + ".", imagegen={"style": "flat", "negative": "text"})
    text = requests(project)["set"].text
    assert text.startswith("a cat. Style: flat vector illustration") and text.endswith(f"; {STYLE}. Avoid: text.")
    own = image_request(project, GenerateImage(prompt="a cat", style="none"), cartoon=True)
    assert own.text == f"a cat. Style: {STYLE}. Avoid: text."
    assert image_request(project, GenerateImage(prompt="a cat", style=STYLE), cartoon=True).style == STYLE   # said once


def test_cartoon_style_is_in_the_cache_key(styled) -> None:
    keys = {requests(styled(cartoon_style=s))["set"].key for s in (STYLE, "pencil sketch", "pencil  sketch.")}
    assert len(keys) == 2   # spacing and a final full stop do not count


def test_a_variant_may_change_it_and_its_pictures_are_not_orphans(styled) -> None:
    project = styled(cartoon_style=STYLE, variants={"sketch": {"cartoon_style": "pencil sketch"}, "plain": {"cartoon_style": None}})
    sketch = Project.load(project.config_file, variant="sketch")
    plain = Project.load(project.config_file, variant="plain")
    base_key, sketch_key = requests(project)["set"].key, requests(sketch)["set"].key
    assert sketch_key != base_key and requests(sketch)["set"].text == "a cat. Style: pencil sketch."
    assert requests(plain)["set"].key == CAT_KEY
    assert {base_key, sketch_key, CAT_KEY} <= used_keys(project)
    assert [r.key for r in plan_imagegen(sketch).todo] == [sketch_key, CAT_KEY]


def test_only_stage_opts_in_and_the_scene_shows_the_same_picture(styled) -> None:
    from vidgen import extensions, registry

    project = styled(cartoon_style=STYLE)
    with extensions.project_session(project):
        assert registry.find("stage").cls.uses_cartoon_style is True
        assert registry.find("image").cls.uses_cartoon_style is False
    assert NarratedScene.uses_cartoon_style is False
    request = requests(project)["set"]
    request.path.parent.mkdir(parents=True)
    request.path.write_bytes(b"stored")
    scene = SimpleNamespace(project=project, theme=None, uses_cartoon_style=True)
    assert NarratedScene.generated_picture(scene, GenerateImage(prompt="a cat")) == request.path   # what imagegen made


def test_cartoon_style_must_not_be_empty(make_project) -> None:
    with pytest.raises(VidgenError, match="cartoon_style"):
        Project.load(make_project(minimal_config(scenes=scenes(), cartoon_style="")))

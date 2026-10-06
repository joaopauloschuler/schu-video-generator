"""Scene registry, hooks and runtime context (no rendering)."""

from __future__ import annotations

import logging

import pytest

from conftest import minimal_config
from vidgen import extensions, hooks, registry, runtime
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.scene import NarratedScene, SceneParams
from vidgen.theme import Theme


@pytest.fixture
def builtins_loaded() -> None:
    extensions.load_builtins()


def test_scene_decorator_registers_extension() -> None:
    @registry.scene("my_scene")
    class MyScene(NarratedScene):
        pass

    entry = registry.get("my_scene")
    assert entry.cls is MyScene
    assert not entry.builtin
    assert entry.origin.endswith("test_registry.py")
    assert entry.params_model is None
    assert "my_scene" in registry.names()


def test_builtin_text_card_is_registered(builtins_loaded: None) -> None:
    entry = registry.get("text_card")
    assert entry.builtin and entry.origin == "builtin"
    assert entry.params_model is not None and "text" in entry.params_model.model_fields


@pytest.mark.parametrize("name", ["bad name", "", "a-b", 3])
def test_invalid_names(name: object) -> None:
    with pytest.raises(VidgenError, match="invalid scene type name"):
        registry.scene(name)(type("X", (NarratedScene,), {}))  # type: ignore[arg-type]


def test_must_subclass_narrated_scene() -> None:
    with pytest.raises(VidgenError, match="subclass of NarratedScene"):

        @registry.scene("plain")
        class Plain:
            pass


def test_params_must_be_scene_params() -> None:
    from pydantic import BaseModel

    with pytest.raises(VidgenError, match="subclass of SceneParams"):

        @registry.scene("bad_params")
        class Bad(NarratedScene):
            class Params(BaseModel):
                x: int


def test_extension_collision_names_both_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    class A(NarratedScene):
        pass

    class B(NarratedScene):
        pass

    monkeypatch.setattr("vidgen.registry.origin_of", lambda module: "extensions/a.py")
    registry.register("dup", A)
    monkeypatch.setattr("vidgen.registry.origin_of", lambda module: "extensions/b.py")
    with pytest.raises(VidgenError) as info:
        registry.register("dup", B)
    assert "extensions/a.py" in str(info.value) and "extensions/b.py" in str(info.value)


def test_builtin_collision_requires_override(builtins_loaded: None) -> None:
    with pytest.raises(VidgenError, match="same name as a built-in.*override=True"):

        @registry.scene("text_card")
        class Mine(NarratedScene):
            pass


def test_override_builtin_warns_and_is_recorded(builtins_loaded: None, caplog: pytest.LogCaptureFixture) -> None:
    builtin = registry.get("text_card")
    with caplog.at_level(logging.WARNING, logger="vidgen.registry"):

        @registry.scene("text_card", override=True)
        class Mine(NarratedScene):
            pass

    assert "overrides the built-in" in caplog.text
    entry = registry.get("text_card")
    assert entry.cls is Mine and entry.overrides is builtin
    assert [e.name for e in registry.all()].count("text_card") == 1
    registry.reset()
    assert registry.get("text_card") is builtin


def test_override_without_builtin_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="vidgen.registry"):

        @registry.scene("nothing_here", override=True)
        class Mine(NarratedScene):
            pass

    assert "no built-in" in caplog.text
    assert registry.get("nothing_here").overrides is None


def test_builtin_layer_and_duplicate_builtins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_builtins", {})
    a = type("A", (NarratedScene,), {"__module__": "vidgen.scenes.fake_a"})
    b = type("B", (NarratedScene,), {"__module__": "vidgen.scenes.fake_b"})
    assert registry.register("fake", a).builtin
    with pytest.raises(VidgenError, match="defined twice.*fake_a.*fake_b"):
        registry.register("fake", b)
    registry.reset()
    assert registry.get("fake").cls is a  # reset keeps built-ins


def test_unknown_type_suggests_close_matches(builtins_loaded: None) -> None:
    with pytest.raises(VidgenError) as info:
        registry.get("text_crd")
    message = str(info.value)
    assert "unknown scene type 'text_crd'" in message
    assert "did you mean 'text_card'" in message
    assert "known types: bar_chart, bullets, chapter, code, " in message and "text_card, timeline, title)" in message


def test_snapshot_restore_and_isolated() -> None:
    @registry.scene("one")
    class One(NarratedScene):
        pass

    saved = registry.snapshot()
    with registry.isolated():
        assert registry.find("one") is None

        @registry.scene("two")
        class Two(NarratedScene):
            pass

    assert registry.find("one") is not None and registry.find("two") is None
    registry.reset()
    assert registry.find("one") is None
    registry.restore(saved)
    assert registry.find("one") is not None


def test_validate_params() -> None:
    class WithParams(NarratedScene):
        class Params(SceneParams):
            values: dict[str, float]
            best: str | None = None

    p = WithParams.validate_params({"values": {"a": 1}})
    assert isinstance(p, WithParams.Params) and p.values == {"a": 1.0} and p.best is None
    with pytest.raises(VidgenError) as info:
        WithParams.parse_params({"values": {"a": "x"}, "extra": 1}, scene_id="s1")
    message = str(info.value)
    assert message.startswith("scene 's1': invalid params")
    assert "params.values.a:" in message and "params.extra: Extra inputs are not permitted" in message

    class Free(NarratedScene):
        pass

    raw = {"anything": [1, 2]}
    assert Free.validate_params(raw) == raw and Free.validate_params(raw) is not raw

    class Child(WithParams):
        pass

    assert Child.params_model() is WithParams.Params


# ----- hooks -------------------------------------------------------------------------------------


@pytest.fixture
def project(make_project) -> Project:
    return Project.load(make_project())


def test_hooks_run_in_registration_order(project: Project) -> None:
    calls: list[str] = []

    @hooks.hook("pre_render")
    def first(ctx: hooks.HookContext) -> None:
        calls.append("first")
        ctx.data["n"] += 1

    @hooks.hook("pre_render")
    def second(ctx: hooks.HookContext) -> None:
        calls.append(f"second:{ctx.data['n']}:{ctx.event}:{ctx.project is project}")

    @hooks.hook("post_render")
    def other(ctx: hooks.HookContext) -> None:
        calls.append("other")

    ctx = hooks.dispatch("pre_render", project, n=0)
    assert calls == ["first", "second:1:pre_render:True"]
    assert ctx.data == {"n": 1}
    assert [h.fn for h in hooks.registered("pre_render")] == [first, second]


def test_unknown_hook_event(project: Project) -> None:
    with pytest.raises(VidgenError, match="unknown hook event 'pre_everything'.*pre_tts"):
        hooks.hook("pre_everything")
    with pytest.raises(VidgenError, match="unknown hook event"):
        hooks.dispatch("nope", project)


def test_hook_exception_is_wrapped(project: Project) -> None:
    @hooks.hook("post_tts")
    def broken(ctx: hooks.HookContext) -> None:
        raise ValueError("boom")

    with pytest.raises(VidgenError) as info:
        hooks.dispatch("post_tts", project)
    message = str(info.value)
    assert "hook test_registry.test_hook_exception_is_wrapped.<locals>.broken" in message
    assert "test_registry.py" in message and "during post_tts" in message
    assert "ValueError: boom" in message and "Traceback" in message


def test_hook_vidgen_error_keeps_message(project: Project) -> None:
    @hooks.hook("pre_tts")
    def picky(ctx: hooks.HookContext) -> None:
        raise VidgenError("missing logo")

    with pytest.raises(VidgenError, match=r"picky .* failed during pre_tts: missing logo$"):
        hooks.dispatch("pre_tts", project)


def test_hooks_isolated_and_reset(project: Project) -> None:
    calls: list[str] = []
    hooks.register("post_scene", lambda ctx: calls.append("a"))
    with hooks.isolated():
        hooks.dispatch("post_scene", project)
        assert calls == []
    hooks.dispatch("post_scene", project)
    assert calls == ["a"]
    hooks.reset()
    assert hooks.registered() == []


# ----- runtime -------------------------------------------------------------------------------------


def test_runtime_unset_errors() -> None:
    with pytest.raises(VidgenError, match="no active vidgen project"):
        runtime.current_project()
    with pytest.raises(VidgenError, match="no active vidgen theme"):
        runtime.current_theme()
    assert not runtime.has_context()


def test_runtime_use_context_nests(make_project) -> None:
    p1 = Project.load(make_project(folder="p1"))
    p2 = Project.load(make_project(minimal_config(theme={"colors": {"text": "#111111"}}), folder="p2"))
    theme1 = runtime.set_context(p1)
    assert runtime.current_project() is p1 and runtime.current_theme() is theme1
    custom = Theme()
    with runtime.use_context(p2) as theme2:
        assert runtime.current_project() is p2 and theme2.color("text") == "#111111"
        with runtime.use_context(p1, custom) as t:
            assert t is custom and runtime.current_theme() is custom
        assert runtime.current_theme() is theme2
    assert runtime.current_project() is p1 and runtime.current_theme() is theme1

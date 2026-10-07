"""Step 59: the JSON modes the MCP tools need (`init`, `tts`, `imagegen --json`, validate's images, plain
`validate` past a broken variant), the server's helpers (root folder policy, command lines,
pictures), and the MCP server itself driven by the SDK's client over stdio (skipped without the
optional `mcp` package). No network: TTS / image APIs are mocked or refused before any call."""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import urllib.request
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml
from PIL import Image

from conftest import minimal_config
from test_json_output import run_json
from vidgen.cli import main
from vidgen.errors import VidgenError
from vidgen.mcp_tools import MAX_IMAGE_SIDE, MAX_IMAGES, PathOutsideRoot, RootPolicy, cli_args, cost_refusal, page_of, prepare_picture

PROMPT = "a lighthouse on a cliff at dawn"


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def png_bytes(size: tuple[int, int] = (24, 16)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (10, 200, 30)).save(out, format="PNG")
    return out.getvalue()


# ----- JSON modes of the commands the tools wrap ------------------------------------------------------


def test_init_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, doc, _ = run_json(["init", str(tmp_path / "new"), "--json"], capsys)
    assert code == 0 and doc["command"] == "init" and doc["example"] == "minimal"
    assert Path(doc["config_file"]).is_file() and Path(doc["project"]) == (tmp_path / "new").resolve()
    code, doc, _ = run_json(["init", str(tmp_path / "new"), "--json"], capsys)
    assert code == 1 and "not an empty directory" in doc["error"]["message"]


def test_tts_json_dry_run_and_run(make_project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(pronunciation={"Hello": "Heh-low"}))
    calls: list[Any] = []

    def fake(request: urllib.request.Request, timeout: float) -> FakeResponse:
        calls.append(request)
        return FakeResponse(b"MP3:" + json.loads(request.data)["text"].encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    code, doc, err = run_json(["tts", str(root), "--dry-run", "--json"], capsys)
    assert code == 0 and doc["command"] == "tts" and doc["dry_run"] is True and calls == []
    assert [(b["scene"], b["beat"], b["action"], b["voice"]) for b in doc["beats"]] == [
        ("intro", "intro_b1", "generate", "default"), ("intro", "intro_b2", "generate", "default"), ("main", "custom", "generate", "default"),
    ]
    assert doc["beats"][0]["says"] == "Heh-low there." and doc["beats"][1]["says"] is None
    assert doc["characters"] == sum(b["characters"] for b in doc["beats"]) == len("Heh-low there.Second beat.One two three four.")
    assert doc["voices"]["default"]["beats"] == 3 and doc["generated"] == [] and doc["up_to_date"] == []
    assert "would generate intro_b1.mp3" in err  # the human lines are the progress, on stderr

    code, doc, _ = run_json(["tts", str(root), "--json"], capsys)
    assert code == 1 and "ELEVENLABS_API_KEY" in doc["error"]["message"] and calls == []
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test_secret_key")
    code, doc, err = run_json(["tts", str(root), "--json"], capsys)
    assert code == 0 and doc["dry_run"] is False and doc["generated"] == ["intro_b1", "intro_b2", "custom"] and len(calls) == 3
    assert "[3/3] generated custom.mp3" in err and "sk_test_secret_key" not in json.dumps(doc)
    code, doc, _ = run_json(["tts", str(root), "--json"], capsys)
    assert code == 0 and doc["beats"] == [] and doc["up_to_date"] == ["intro_b1", "intro_b2", "custom"] and len(calls) == 3


def test_imagegen_json_dry_run_and_run(make_project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    scene = {"id": "pic", "type": "image", "params": {"generate": PROMPT}, "beats": [{"text": "A picture."}]}
    root = make_project(minimal_config(scenes=[scene]))
    body = json.dumps({"created": 1, "data": [{"b64_json": base64.b64encode(png_bytes()).decode(), "revised_prompt": "r"}]}).encode()
    calls: list[Any] = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: calls.append(request) or FakeResponse(body))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    code, doc, _ = run_json(["imagegen", str(root), "--dry-run", "--json"], capsys)
    assert code == 0 and doc["command"] == "imagegen" and doc["dry_run"] is True and calls == []
    [image] = doc["images"]
    assert image["scenes"] == ["pic"] and image["prompt"] == PROMPT and image["sent_prompt"].startswith(PROMPT)
    assert image["estimated_cost"] is not None and doc["estimated_cost"] == round(image["estimated_cost"], 4) and "pricing" in doc["price_note"]
    assert doc["generated"] == [] and not Path(image["path"]).exists()

    code, doc, _ = run_json(["validate", str(root), "--json"], capsys)
    assert doc["images"] == [{"variant": None, "generated": 0, "missing": 1, "pictures": [
        {"key": image["key"], "scenes": ["pic"], "path": image["path"], "exists": False, "prompt": PROMPT}]}]

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    code, doc, _ = run_json(["imagegen", str(root), "--json"], capsys)
    assert code == 0 and doc["generated"] == [image["key"]] and len(calls) == 1 and Path(image["path"]).is_file()
    code, doc, _ = run_json(["validate", str(root), "--json"], capsys)
    assert (doc["images"][0]["generated"], doc["images"][0]["missing"]) == (1, 0)
    code, doc, _ = run_json(["imagegen", str(root), "--json"], capsys)
    assert doc["images"] == [] and doc["up_to_date"] == [image["key"]] and len(calls) == 1


def test_validate_json_images_empty_without_generate(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    code, doc, _ = run_json(["validate", str(make_project()), "--json"], capsys)
    assert code == 0 and doc["images"] == []


def test_human_validate_reports_every_broken_variant(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(variants={"one": {"bogus_key": 1}, "ok": {"title": "Fine"}, "two": {"other_bogus": 2}}))
    assert main(["validate", str(root)]) == 1
    err = capsys.readouterr().err
    assert "bogus_key" in err and "other_bogus" in err and "[variant one]" in err and "[variant two]" in err


def test_mcp_command_without_the_sdk(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    for name in ("mcp", "mcp.server", "mcp.server.mcpserver", "mcp.server.fastmcp"):
        monkeypatch.setitem(sys.modules, name, None)
    assert main(["mcp"]) == 1
    assert 'pip install "vidgen[mcp]"' in capsys.readouterr().err


# ----- helpers (no SDK) ---------------------------------------------------------------------------


def test_root_policy(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "proj").mkdir(parents=True)
    (tmp_path / "secret").mkdir()
    policy = RootPolicy.at(root)
    assert policy.path(".") == root.resolve() and policy.path("proj") == (root / "proj").resolve()
    assert policy.path(str(root / "proj" / "new")) == (root / "proj" / "new").resolve()  # need not exist yet
    for bad in ("..", "../secret", "proj/../../secret", str(tmp_path / "secret"), "/etc/passwd"):
        with pytest.raises(PathOutsideRoot, match="outside the folder"):
            policy.path(bad)
    if hasattr(os, "symlink"):
        (root / "link").symlink_to(tmp_path / "secret", target_is_directory=True)
        with pytest.raises(PathOutsideRoot):
            policy.path("link/file.txt")
    with pytest.raises(VidgenError, match="empty path"):
        policy.path("  ")
    with pytest.raises(VidgenError, match="not a folder"):
        RootPolicy.at(tmp_path / "missing")
    assert policy.inside(root / "proj") and not policy.inside(tmp_path / "secret")


def test_cli_args() -> None:
    args = cli_args(["lint"], ["/p"], {"scene": ["a", "-b"], "final": True, "force": False, "variant": None, "jobs": 2, "rule": []})
    assert args == ["lint", "/p", "--scene=a", "--scene=-b", "--final", "--jobs=2", "--json"]
    assert cli_args(["guide"]) == ["guide", "--json"]
    with pytest.raises(VidgenError, match="may not start with '-'"):
        cli_args(["guide"], ["--list"])


def test_cost_refusal_explains_the_way() -> None:
    message = cost_refusal("tts", "calls the paid text-to-speech API")
    assert "dry_run=true" in message and "confirm_cost=true" in message


def test_prepare_picture(tmp_path: Path) -> None:
    small = tmp_path / "small.png"
    Image.new("RGB", (320, 180), (200, 10, 10)).save(small)
    picture = prepare_picture(small)
    assert (picture.format, picture.width, picture.height) == ("png", 320, 180)
    big = tmp_path / "big.png"
    noise = Image.frombytes("RGB", (2400, 1600), os.urandom(2400 * 1600 * 3))  # incompressible: becomes a JPEG
    noise.save(big)
    picture = prepare_picture(big)
    assert (picture.format, picture.width, picture.height) == ("jpeg", MAX_IMAGE_SIDE, round(1600 * MAX_IMAGE_SIDE / 2400))
    assert Image.open(io.BytesIO(picture.data)).size == (picture.width, picture.height)


def test_page_of() -> None:
    paths = [Path(f"s{i}.png") for i in range(5)]
    chosen, note = page_of(paths, 0, 2)
    assert chosen == paths[:2] and note == {"total": 5, "offset": 0, "returned": ["s0.png", "s1.png"], "next_offset": 2}
    chosen, note = page_of(paths, 4, 3)
    assert chosen == paths[4:] and note["next_offset"] is None
    assert len(page_of([Path("x")] * 20, 0, 50)[0]) == MAX_IMAGES
    with pytest.raises(VidgenError):
        page_of(paths, -1, 1)


# ----- the server over stdio (the SDK's client) ------------------------------------------------------

TOOLS = {
    "guide", "init", "plan", "validate", "schema", "lint", "storyboard", "list_scenes", "list_icons", "list_themes", "list_sfx",
    "list_music", "render", "tts", "imagegen", "readback", "slides", "thumbnail", "export", "gallery", "translate_template",
}


def tiny_project(root: Path) -> Path:
    """A two-scene project rendered at 96x54 @ 5 fps in preview."""
    config = {
        "title": "MCP test",
        "output": "out",
        "format": {"width": 160, "height": 90, "fps": 10},
        "preview": {"width": 96, "height": 54, "fps": 5},
        "narration": {"pad": 0.2, "words_per_second": 4.0},
        "scenes": [
            {"id": "intro", "type": "title", "params": {"title": "Hi"}, "beats": [{"text": "Hello there, viewers."}]},
            {"id": "card", "type": "text_card", "params": {"text": "Card"}, "beats": [{"text": "A short card here."}]},
        ],
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "video.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return root


def attr(obj: Any, *names: str) -> Any:
    """A field of an SDK object under its 2.x (snake_case) or 1.x (camelCase) name."""
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    raise AttributeError(names)


def run_session(root: Path, body: Callable[[Any], Awaitable[None]]) -> None:
    """Start ``vidgen mcp --root ROOT`` and run ``body(session)`` with an initialised client session."""
    pytest.importorskip("mcp")
    import anyio
    from mcp import ClientSession, StdioServerParameters, stdio_client

    @asynccontextmanager
    async def session() -> AsyncIterator[Any]:
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "vidgen", "mcp", "--root", str(root)], env=dict(os.environ), cwd=str(root)
        )
        with open(os.devnull, "w", encoding="utf-8") as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write), ClientSession(read, write) as client:
                await client.initialize()
                yield client

    async def main_() -> None:
        async with session() as client:
            await body(client)

    anyio.run(main_)


def texts(result: Any) -> list[str]:
    return [c.text for c in result.content if c.type == "text"]


def doc_of(result: Any) -> dict[str, Any]:
    assert not attr(result, "is_error", "isError"), texts(result)
    return json.loads(texts(result)[0])


def error_text(result: Any) -> str:
    assert attr(result, "is_error", "isError")
    return "\n".join(texts(result))


def test_server_tools_guide_and_resources(tmp_path: Path) -> None:
    async def body(client: Any) -> None:
        tools = (await client.list_tools()).tools
        assert {t.name for t in tools} == TOOLS
        tts = next(t for t in tools if t.name == "tts")
        schema = attr(tts, "input_schema", "inputSchema")
        assert schema["properties"]["dry_run"]["default"] is True and schema["properties"]["confirm_cost"]["default"] is False
        assert "ctx" not in schema["properties"] and "COSTS MONEY" in tts.description

        doc = doc_of(await client.call_tool("guide", {"topic": "start"}))
        assert doc["command"] == "guide" and doc["topic"] == "start" and doc["text"].startswith("## ")
        assert "did you mean" in error_text(await client.call_tool("guide", {"topic": "pacng"}))
        assert "may not start with '-'" in error_text(await client.call_tool("guide", {"topic": "--list"}))
        assert "scene=TYPE" in error_text(await client.call_tool("schema", {}))  # the whole schema only on request
        stat = doc_of(await client.call_tool("schema", {"scene": "stat"}))
        assert stat["schema"]["properties"]["value"] and len(json.dumps(stat)) < 50_000

        resources = {str(r.uri) for r in (await client.list_resources()).resources}
        assert {"vidgen://guide", "vidgen://guide/start", "vidgen://guide/workflow", "vidgen://schema"} <= resources
        start = (await client.read_resource("vidgen://guide/start")).contents[0]
        assert start.text == doc["text"]
        schema_doc = json.loads((await client.read_resource("vidgen://schema")).contents[0].text)
        assert schema_doc["$schema"].startswith("https://json-schema.org/") and "scenes" in schema_doc["properties"]

    run_session(tmp_path, body)


def test_server_validate_paths_and_cost_guards(tmp_path: Path) -> None:
    root = tmp_path / "root"
    tiny_project(root / "proj")
    tiny_project(tmp_path / "outside")

    async def body(client: Any) -> None:
        doc = doc_of(await client.call_tool("validate", {"project": "proj"}))
        assert doc["ok"] and doc["scenes"] == 2 and doc["project"] == str((root / "proj").resolve())
        for bad in ("../outside", str(tmp_path / "outside")):
            assert "outside the folder" in error_text(await client.call_tool("validate", {"project": bad}))
        assert "outside the folder" in error_text(await client.call_tool("init", {"dir": "../evil"}))
        assert "outside the folder" in error_text(await client.call_tool("export", {"kind": "gif", "project": "proj", "output": "/tmp/x.gif"}))

        message = error_text(await client.call_tool("tts", {"project": "proj", "dry_run": False}))
        assert "confirm_cost=true" in message and not (root / "proj" / "audio").exists()
        assert "confirm_cost=true" in error_text(await client.call_tool("imagegen", {"project": "proj", "dry_run": False}))
        doc = doc_of(await client.call_tool("tts", {"project": "proj"}))  # dry run by default: free
        assert doc["dry_run"] is True and [b["beat"] for b in doc["beats"]] == ["intro_b1", "card_b1"]

        (root / "proj" / "video.yaml").write_text("title: [broken\n", encoding="utf-8")
        failed = json.loads(error_text(await client.call_tool("validate", {"project": "proj"})))
        assert failed["ok"] is False and failed["command"] == "validate"

        doc = doc_of(await client.call_tool("init", {"dir": "fresh"}))
        assert Path(doc["config_file"]) == (root / "fresh" / "video.yaml").resolve()
        result = await client.call_tool("list_icons", {"search": "rocket", "sheet": True})
        doc = doc_of(result)
        assert doc["count"] >= 1 and doc["sheets"] == [str((root / "build" / "mcp" / "icons.png").resolve())]
        assert [c.type for c in result.content] == ["text", "image"]

    run_session(root, body)


@pytest.mark.render
def test_server_storyboard_and_lint_return_pictures(tmp_path: Path) -> None:
    tiny_project(tmp_path / "proj")

    async def body(client: Any) -> None:
        progress: list[Any] = []

        async def on_progress(value: float, total: float | None, message: str | None) -> None:
            progress.append((value, message))

        result = await client.call_tool("storyboard", {"project": "proj", "images": 1}, progress_callback=on_progress)
        doc = doc_of(result)
        images = [c for c in result.content if c.type == "image"]
        assert len(images) == 1 and attr(images[0], "mime_type", "mimeType") == "image/png"
        sheet = Image.open(io.BytesIO(base64.b64decode(images[0].data)))
        assert max(sheet.size) <= MAX_IMAGE_SIDE and sheet.width == doc["sheets"][0]["width"]
        assert doc["mcp_images"]["total"] == len(doc["sheets"]) and doc["mcp_images"]["returned"] == [doc["sheets"][0]["path"]]

        doc = doc_of(await client.call_tool("lint", {"project": "proj", "fail_on": "never"}))
        assert doc["command"] == "lint" and doc["stills"] == 2 and doc["rendered"] == []  # the storyboard's stills reused

    run_session(tmp_path, body)

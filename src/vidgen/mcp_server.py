"""The MCP server: vidgen's commands as tools for AI agents (``vidgen mcp``, DESIGN.md §62).

Every tool call runs ``python -m vidgen <command> ... --json`` in a **fresh subprocess** in the
root folder and returns its JSON document (Step 8 envelope), plus pictures where the command makes
some (storyboard sheets, thumbnail, icon / theme sheets, gallery stills). A subprocess per call
because Manim's configuration and vidgen's registries are process-global and not re-entrant, a
long-lived server must survive a crashing scene or extension, and the CLI already prints exactly
one JSON document; the cost (~1 s of start-up) is small next to rendering. The command's stderr
(its progress lines) becomes MCP progress notifications; cancelling a call kills the process.

Optional extra ``schu-video-generator[mcp]`` (the official MCP Python SDK). Written against its ``MCPServer``
(SDK 2.x; named ``FastMCP`` in 1.x, which is used when that is what is installed).

No ``from __future__ import annotations`` here: the SDK reads the tools' parameter annotations,
which name the SDK's ``Context`` imported inside :func:`build_server`.
"""

import base64
import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from vidgen import DIST_NAME, __version__
from vidgen.errors import VidgenError
from vidgen.mcp_tools import (
    DEFAULT_IMAGES,
    MAX_IMAGES,
    RootPolicy,
    cli_args,
    cost_refusal,
    page_of,
    prepare_picture,
)

#: Folder (under the root) for files the server itself asks a command to write.
WORK_DIR = Path("build") / "mcp"
#: STT providers that bill per use (``readback`` asks for ``confirm_cost``).
PAID_STT = ("elevenlabs",)
#: TTS providers that cost nothing (``tts`` runs without ``confirm_cost``; DESIGN.md §68).
FREE_TTS = ("kokoro",)
#: Seconds between progress notifications (at most).
PROGRESS_INTERVAL = 0.5
#: stderr lines kept for the message of a command that printed no JSON.
TAIL_LINES = 30
#: A project piece's or a built-in bed's name (music_render / music_check pass it on as it is):
#: words joined by '/', no suffix, no '..'.
MUSIC_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*(/[A-Za-z0-9_][A-Za-z0-9_-]*)*$")

INSTRUCTIONS = """\
schu-video-generator (the `vidgen` command) makes narrated, animated videos from a project folder (video.yaml + assets). Paths are \
relative to the server's root folder; nothing outside it can be read or written.
Start with `guide` (topic "start" or "workflow"): it is the author guide. Usual loop: `plan` (from \
an outline), `screenplay` (a cartoon from a screenplay; `cast` writes a well-contrasted cast for it) or `init` -> edit video.yaml -> `validate` -> `storyboard` (look at the sheets it \
returns) -> `lint` -> fix -> repeat; then `tts` with dry_run=true (free), and only after the user \
agreed to the cost `tts` with dry_run=false and confirm_cost=true (voice.provider kokoro is local and \
free: no confirm_cost); then `render`. `schema` with \
scene=TYPE gives one scene type's params as JSON Schema, `list_scenes` / `list_icons` / \
`list_themes` / `list_sfx` / `list_music` what exists, `character_sheet` a cartoon character's \
poses, expressions and mouth shapes, `direct` what auto_direct adds to a cartoon's beats; \
`music_template` / `music_patches` / `music_render` / `music_check` write and check original music as score files \
(assets/music/NAME.yaml, played with music: NAME; the guide's topic "audio" has the recipe). A person shaping music in \
`vidgen studio` may hand you a session with listening notes: `studio_sessions` -> `studio_read` -> `studio_check` -> \
`studio_propose` (one line per note; `studio_variations` gives four variations to start from). Every \
tool returns the command's JSON document (`ok`, `warnings`, `error`...); a document with ok=false comes back as a tool error."""

Progress = Callable[[str], Awaitable[None]]


def _sdk() -> tuple[Any, Any, Any]:
    """``(MCPServer, Context, ToolError)`` of the installed MCP SDK (2.x, else 1.x)."""
    try:
        from mcp.server.mcpserver import Context, MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
    except ImportError:
        try:
            from mcp.server.fastmcp import Context, FastMCP as MCPServer
            from mcp.server.fastmcp.exceptions import ToolError
        except ImportError:
            raise VidgenError(
                f'the MCP server needs the optional MCP SDK: pip install "{DIST_NAME}[mcp]" (or pip install mcp)'
            ) from None
    return MCPServer, Context, ToolError


# ----- running a command ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandRun:
    """A finished ``vidgen`` subprocess: its exit code, JSON document (``None`` if stdout held
    none) and the last lines of its stderr."""

    returncode: int
    doc: dict[str, Any] | None
    stderr_tail: list[str]


def _kill(process: Any) -> None:
    """Stop ``process`` and what it started (render workers): its process group on POSIX, its
    process tree on Windows (``taskkill /T``)."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
            return
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
        process.kill()
    except OSError:  # already gone (or no taskkill)
        pass


async def run_vidgen(args: Sequence[str], cwd: Path, progress: Progress | None = None) -> CommandRun:
    """Run ``python -m vidgen ARGS`` in ``cwd`` and collect its JSON document; every stderr line
    is passed to ``progress``. Cancelled (the client gave up): the process is killed. The files a
    project's config names must lie inside ``cwd`` (``vidgen.project.CONFINE_ENV``)."""
    import anyio
    from anyio.streams.text import TextReceiveStream

    from vidgen.project import CONFINE_ENV

    extra: dict[str, Any] = {"start_new_session": True} if os.name == "posix" else {}
    process = await anyio.open_process(
        [sys.executable, "-m", "vidgen", *args],
        stdin=subprocess.DEVNULL,
        cwd=str(cwd),
        env={**os.environ, CONFINE_ENV: str(cwd)},
        **extra,
    )
    out = bytearray()
    tail: deque[str] = deque(maxlen=TAIL_LINES)

    async def read_stdout() -> None:
        assert process.stdout is not None
        async for chunk in process.stdout:
            out.extend(chunk)

    async def read_stderr() -> None:
        assert process.stderr is not None
        pending = ""
        async for text in TextReceiveStream(process.stderr, errors="replace"):
            *lines, pending = re.split(r"\r\n|\r|\n", pending + text)
            for line in lines:
                if line.strip():
                    tail.append(line)
                    if progress is not None:
                        await progress(line)
        if pending.strip():
            tail.append(pending)

    try:
        async with anyio.create_task_group() as group:
            group.start_soon(read_stdout)
            group.start_soon(read_stderr)
        returncode = await process.wait()
    finally:
        if process.returncode is None:
            _kill(process)
        with anyio.CancelScope(shield=True):
            await process.aclose()
    try:
        doc = json.loads(out.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        doc = None
    return CommandRun(returncode, doc if isinstance(doc, dict) else None, list(tail))


def compact(doc: dict[str, Any]) -> str:
    """A document as compact JSON (fewer tokens for the model than the CLI's indented form)."""
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False)


def stt_provider(project: Path, variant: str | None) -> str | None:
    """The ``stt.provider`` of the project (variant applied), ``None`` if it does not load (the
    command will report why)."""
    from vidgen.project import Project

    try:
        return Project.load(project, variant=variant).config.stt.provider
    except VidgenError:
        return None


def tts_provider(project: Path, variant: str | None) -> str | None:
    """The ``voice.provider`` of the project (variant applied; one provider per video), ``None``
    if it does not load (then ``tts`` still asks for ``confirm_cost``)."""
    from vidgen.project import Project

    try:
        return Project.load(project, variant=variant).config.voice.provider
    except VidgenError:
        return None


# ----- the server ----------------------------------------------------------------------------------


def build_server(root: Path) -> Any:
    """The MCP server (an SDK ``MCPServer`` / ``FastMCP``) whose tools work inside ``root``."""
    MCPServer, Context, ToolError = _sdk()
    from mcp.types import CallToolResult, ToolAnnotations

    policy = RootPolicy.at(root)
    # WARNING: the SDK logs every failed call (with the whole document) at INFO on stderr.
    server = MCPServer(DIST_NAME, instructions=INSTRUCTIONS, log_level="WARNING")
    heavy_lock: list[Any] = []  # created in the server's event loop, on first use

    read_only = ToolAnnotations.model_validate({"readOnlyHint": True, "openWorldHint": False})
    writes = ToolAnnotations.model_validate({"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False})
    paid = ToolAnnotations.model_validate({"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True})

    def tool(description: str, annotations: Any) -> Callable[[Any], Any]:
        return server.tool(description=description, annotations=annotations, structured_output=False)

    def where(value: str, what: str = "project") -> Path:
        try:
            return policy.path(value, what)
        except VidgenError as exc:  # PathOutsideRoot included
            raise ToolError(str(exc)) from None

    def piece(value: str, what: str) -> str:
        """A music piece as ``music_render`` / ``music_check`` take it: a project piece's or a
        built-in bed's name as given (the command finds it under the root), else a path under
        the root."""
        if MUSIC_NAME.match(value) and not (policy.root / value).exists():
            return value
        return str(where(value, what))

    def args_of(command: Sequence[str], positionals: Sequence[str] = (), options: dict[str, Any] | None = None) -> list[str]:
        try:
            return cli_args(command, positionals, options)
        except VidgenError as exc:
            raise ToolError(str(exc)) from None

    async def call(ctx: Any, args: list[str], heavy: bool = False) -> dict[str, Any]:
        """Run the command (heavy ones one at a time: they render and share build folders)."""
        import anyio

        state = {"count": 0, "last": 0.0}

        async def progress(line: str) -> None:
            now = time.monotonic()
            if now - state["last"] < PROGRESS_INTERVAL:
                return
            state["last"] = now
            state["count"] += 1
            with contextlib.suppress(Exception):  # a client that cannot take progress is fine
                await ctx.report_progress(state["count"], None, line[:300])

        if heavy and not heavy_lock:
            heavy_lock.append(anyio.Lock())
        async with heavy_lock[0] if heavy else contextlib.nullcontext():
            run = await run_vidgen(args, policy.root, progress)
        if run.doc is None:
            tail = "\n".join(run.stderr_tail) or "(no output)"
            raise ToolError(f"vidgen {args[0]} printed no JSON document (exit code {run.returncode}); its last output:\n{tail}")
        return run.doc

    def answer(doc: dict[str, Any], pictures: Sequence[Path] = (), note: dict[str, Any] | None = None) -> Any:
        """The tool result: the document as compact JSON text, then the pictures (inside the root
        only); a document with ``ok`` false is an error result (its JSON text alone)."""
        if note is not None:
            doc = {**doc, "mcp_images": note}
        ok = bool(doc.get("ok", False))
        content: list[dict[str, Any]] = [{"type": "text", "text": compact(doc)}]
        for path in pictures if ok else ():
            if path.is_file() and policy.inside(path):
                picture = prepare_picture(path)
                data = base64.b64encode(picture.data).decode("ascii")
                content.append({"type": "image", "data": data, "mimeType": f"image/{picture.format}"})
        # Built from the wire (camelCase) names, which both SDK generations validate.
        return CallToolResult.model_validate({"content": content, "isError": not ok})

    def paged(doc: dict[str, Any], paths: Sequence[Path], offset: int, count: int) -> Any:
        try:
            chosen, note = page_of(paths, offset, count)
        except VidgenError as exc:
            raise ToolError(str(exc)) from None
        return answer(doc, chosen, note if doc.get("ok") else None)

    # Parameter types shared by the tools.
    Project = Annotated[str, Field(description="project folder (or its video.yaml), relative to the root")]
    OptionalProject = Annotated[
        str | None, Field(description="a project folder whose own scene types / theme / assets count (default: the root's, if it has a video.yaml)")
    ]
    Variant = Annotated[str | None, Field(description="apply this named variant of video.yaml (e.g. vertical)")]
    Scenes = Annotated[list[str] | None, Field(description="only these scene ids")]
    AllLanguages = Annotated[
        bool, Field(description="the base config, then every variant in another language (dubbed videos); not with variant")
    ]
    Jobs = Annotated[
        Annotated[int, Field(ge=1, le=16)] | Literal["auto"],
        Field(description="scenes rendered in parallel; auto: as many as the available memory and CPU cores allow"),
    ]
    Images = Annotated[int, Field(ge=0, le=MAX_IMAGES, description="pictures to return in this call (0: none)")]
    Offset = Annotated[int, Field(ge=0, description="first picture to return (to page through many)")]
    from vidgen.config import Species

    # ----- guide, scaffolding --------------------------------------------------------------------

    @tool("The author guide (how to make a good video with vidgen: workflow, pacing, scene types, design, "
          "troubleshooting). No topic: the whole guide (long); list_topics=true: the topics.", read_only)
    async def guide(
        ctx: Context,
        topic: Annotated[str | None, Field(description="a topic or alias, e.g. start, workflow, scenes, pacing, social")] = None,
        list_topics: Annotated[bool, Field(description="list the topics instead")] = False,
    ) -> Any:
        return answer(await call(ctx, args_of(["guide"], [topic] if topic else [], {"list": list_topics})))

    @tool("Create a new project folder from a template (video.yaml, assets/, extensions/).", writes)
    async def init(
        ctx: Context,
        dir: Annotated[str, Field(description="folder to create (must not exist or be empty), relative to the root")],
        example: Annotated[str, Field(description="template name")] = "minimal",
    ) -> Any:
        return answer(await call(ctx, args_of(["init"], [str(where(dir, "dir"))], {"example": example})))

    @tool("Draft a project (video.yaml with scenes, beats and # TODO: comments) from a Markdown outline or a "
          "plain-text script, without AI. Give input_path (a file under the root) or the text itself.", writes)
    async def plan(
        ctx: Context,
        input_path: Annotated[str | None, Field(description="outline (.md) or script (.txt) under the root")] = None,
        markdown_text: Annotated[str | None, Field(description="the outline itself (instead of input_path); pictures it names are not copied")] = None,
        text_format: Annotated[Literal["markdown", "text"], Field(description="markdown_text is a Markdown outline or a plain-text script")] = "markdown",
        output: Annotated[str | None, Field(description="project folder to create, or a .yaml file (default: named after the input; 'outline' for markdown_text)")] = None,
        title: str | None = None,
        format: Annotated[Literal["16:9", "9:16"], Field(description="frame")] = "16:9",
        preset: Annotated[str | None, Field(description="theme preset (list_themes)")] = None,
        language: Annotated[str | None, Field(description="language of the text, BCP-47 (e.g. pt-BR)")] = None,
        force: Annotated[bool, Field(description="write into a non-empty folder / replace a config")] = False,
    ) -> Any:
        if (input_path is None) == (markdown_text is None):
            raise ToolError("give either input_path or markdown_text")
        options = {
            "output": str(where(output, "output")) if output else None,
            "title": title, "format": format, "preset": preset, "language": language, "force": force,
        }
        if input_path is not None:
            return answer(await call(ctx, args_of(["plan"], [str(where(input_path, "input_path"))], options)))
        if options["output"] is None:
            options["output"] = str(policy.root / "outline")
        with tempfile.TemporaryDirectory(prefix="vidgen-plan-") as folder:
            source = Path(folder) / ("outline.md" if text_format == "markdown" else "outline.txt")
            source.write_text(markdown_text or "", encoding="utf-8")
            return answer(await call(ctx, args_of(["plan"], [str(source)], options)))

    @tool("Make a cartoon project (stage scenes, characters with generated looks and voices, auto_direct on) "
          "from a screenplay: # Scene: headings with set: lines, NAME (manner): lines, plain narrator paragraphs, "
          "[stage directions]. Give input_path (a file under the root) or the text itself.", writes)
    async def screenplay(
        ctx: Context,
        input_path: Annotated[str | None, Field(description="screenplay (.md or .txt) under the root")] = None,
        screenplay_text: Annotated[str | None, Field(description="the screenplay itself (instead of input_path)")] = None,
        out: Annotated[str | None, Field(description="project folder to create, or a .yaml file (default: named after the input; 'screenplay' for screenplay_text)")] = None,
        cast: Annotated[str | None, Field(description="an include file under the root (characters, voices, sets) to reuse: the project includes it; set: NAME lines use its sets")] = None,
        species: Annotated[list[Species] | None, Field(description="species of the undeclared characters (default: human; several: a mix)")] = None,
        seed: Annotated[int, Field(description="seed of the random looks given once the built-in ones are used")] = 0,
        force: Annotated[bool, Field(description="write into a non-empty folder / replace a config")] = False,
    ) -> Any:
        if (input_path is None) == (screenplay_text is None):
            raise ToolError("give either input_path or screenplay_text")
        options = {
            "out": str(where(out, "out")) if out else None, "cast": str(where(cast, "cast")) if cast else None,
            "species": species, "seed": seed, "force": force,
        }
        if input_path is not None:
            return answer(await call(ctx, args_of(["screenplay"], [str(where(input_path, "input_path"))], options)))
        if options["out"] is None:
            options["out"] = str(policy.root / "screenplay")
        with tempfile.TemporaryDirectory(prefix="vidgen-screenplay-") as folder:
            source = Path(folder) / "screenplay.md"
            source.write_text(screenplay_text or "", encoding="utf-8")
            return answer(await call(ctx, args_of(["screenplay"], [str(source)], options)))

    @tool("Write a cast of original characters that differ clearly (silhouette, colours, accessories, voice kind and "
          "voice) as an include file: use it with include: in video.yaml or as screenplay's cast. The same seed gives "
          "the same cast.", writes)
    async def cast(
        ctx: Context,
        count: Annotated[int, Field(ge=1, le=24, description="how many characters")],
        seed: Annotated[int, Field(description="the same seed gives the same cast")] = 0,
        species: Annotated[list[Species] | None, Field(description="species to draw from (default: human; several: a mix)")] = None,
        out: Annotated[str, Field(description="the .yaml file to write, relative to the root")] = "cast.yaml",
        provider: Annotated[Literal["kokoro", "openrouter", "elevenlabs"], Field(description="the video's voice provider")] = "kokoro",
        narrator: Annotated[str | None, Field(description="the narrator's voice, left out of the cast's (kokoro default: bf_emma)")] = None,
        model: Annotated[str | None, Field(description="openrouter: the TTS model whose voices to use")] = None,
        force: Annotated[bool, Field(description="replace an existing file")] = False,
    ) -> Any:
        options = {
            "random": count, "seed": seed, "species": species, "out": str(where(out, "out")), "provider": provider,
            "narrator": narrator, "model": model, "force": force,
        }
        return answer(await call(ctx, args_of(["cast"], [], options)))

    # ----- checking --------------------------------------------------------------------------------

    @tool("Check the project's video.yaml and every variant: problems with their location, estimated length, "
          "narration audio status, generated pictures. Run it after every edit.", read_only)
    async def validate(ctx: Context, project: Project = ".") -> Any:
        return answer(await call(ctx, args_of(["validate"], [str(where(project))])))

    @tool("The actions auto_direct adds to the beats of the stage scenes (looks, reactions, gestures, close-ups), "
          "without rendering: per scene and beat, each in the form to paste into the beat's actions: list and "
          "edit (written actions win, so pasted ones replace the automatic ones).", read_only)
    async def direct(ctx: Context, project: Project = ".", variant: Variant = None, scene: Scenes = None) -> Any:
        return answer(await call(ctx, args_of(["direct"], [str(where(project))], {"variant": variant, "scene": scene})))

    @tool("The JSON Schema of one scene type's params (scene=TYPE, a few KB: what you normally want), or of the "
          "whole video.yaml (full=true) or of one scene item with every type (all_types=true): both are hundreds "
          "of KB. The resource vidgen://schema serves the whole one too.", read_only)
    async def schema(
        ctx: Context,
        project: OptionalProject = None,
        scene: Annotated[str | None, Field(description="only this scene type's params")] = None,
        all_types: Annotated[bool, Field(description="one scene item with every type's params (large)")] = False,
        full: Annotated[bool, Field(description="the whole video.yaml schema (large)")] = False,
    ) -> Any:
        if scene is None and not all_types and not full:
            raise ToolError(
                "give scene=TYPE for one scene type's params (list_scenes lists the types), or full=true for the "
                "whole video.yaml schema / all_types=true for one scene item (both hundreds of KB: ~100k tokens)"
            )
        positionals = [str(where(project))] if project else []
        return answer(await call(ctx, args_of(["schema"], positionals, {"scene": scene, "all": all_types})))

    @tool("Check the layout and timing of every beat-end still (renders what is needed, preview size): text off "
          "frame, overlaps, too small, low contrast, too many words, dead air, narration speed... "
          "readback=true also transcribes the narration (slow; cached) and flags unclear words and pauses "
          "(unclear_speech). ok=false when a finding is at least fail_on.", writes)
    async def lint(
        ctx: Context,
        project: Project = ".",
        variant: Variant = None,
        scene: Scenes = None,
        rule: Annotated[list[str] | None, Field(description="only these rules")] = None,
        final: Annotated[bool, Field(description="lint the final format instead of the preview (slower)")] = False,
        fail_on: Literal["error", "warning", "info", "never"] | None = None,
        jobs: Jobs = 1,
        force: Annotated[bool, Field(description="render again even if current")] = False,
        readback: Annotated[bool, Field(description="also run unclear_speech: speech to text of the narration (slow)")] = False,
        confirm_cost: Annotated[bool, Field(description="readback with a paid STT provider: the user accepted the cost")] = False,
        all_languages: AllLanguages = False,
    ) -> Any:
        path = where(project)
        if (readback or (rule and "unclear_speech" in rule)) and not confirm_cost and stt_provider(path, variant) in PAID_STT:
            raise ToolError(
                "lint with readback and this project's stt.provider calls a paid speech-to-text API; call again with "
                "confirm_cost=true once the user agreed (transcripts are cached: unchanged beats cost nothing)"
            )
        options = {
            "variant": variant, "scene": scene, "rule": rule, "final": final, "fail-on": fail_on, "jobs": jobs, "force": force,
            "readback": readback, "all-languages": all_languages,
        }
        return answer(await call(ctx, args_of(["lint"], [str(path)], options), heavy=True))

    @tool("Contact sheets of the video (one still per beat end, labelled with beat, time and narration): the way "
          "to SEE what you made. Returns the sheets as images (whole-video sheets first) and their paths; "
          "page with image_offset (stills are reused, so later calls are fast).", writes)
    async def storyboard(
        ctx: Context,
        project: Project = ".",
        variant: Variant = None,
        scene: Annotated[list[str] | None, Field(description="only these scenes' sheets (bigger stills)")] = None,
        per_beat: Annotated[int, Field(ge=1, le=6, description="stills per beat, the last at its end")] = 1,
        final: Annotated[bool, Field(description="final format instead of the preview (slower)")] = False,
        width: Annotated[int | None, Field(ge=640, le=2000, description="sheet width in pixels")] = None,
        jobs: Jobs = 1,
        force: Annotated[bool, Field(description="render again even if current")] = False,
        images: Images = DEFAULT_IMAGES,
        image_offset: Offset = 0,
    ) -> Any:
        options = {"scene": scene, "per-beat": per_beat, "variant": variant, "final": final, "width": width, "jobs": jobs, "force": force}
        doc = await call(ctx, args_of(["storyboard"], [str(where(project))], options), heavy=True)
        sheets = sorted(doc.get("sheets", []), key=lambda s: s.get("kind") != "video")
        return paged(doc, [Path(s["path"]) for s in sheets], image_offset, images)

    @tool("An animatic: the storyboard's stills (beat ends and half-way through actions) held in time with the "
          "narration, with the video's audio (narration, effects, music) and captions, as an MP4 "
          "(<output>_animatic.mp4) to check pacing before a full render. Joined by ffmpeg in seconds when the "
          "storyboard's stills are current; scenes without them are rendered first.", writes)
    async def animatic(
        ctx: Context,
        project: Project = ".",
        variant: Variant = None,
        no_audio: Annotated[bool, Field(description="a silent animatic")] = False,
        captions: Annotated[bool | None, Field(description="draw the subtitles (default: on unless a captions overlay burns them in)")] = None,
        jobs: Jobs = 1,
    ) -> Any:
        options = {
            "variant": variant, "no-audio": no_audio, "captions": captions is True, "no-captions": captions is False, "jobs": jobs,
        }
        return answer(await call(ctx, args_of(["animatic"], [str(where(project))], options), heavy=True))

    # ----- listing ---------------------------------------------------------------------------------

    @tool("Every scene type (built-in and the project's) with its params, beats, targets; beat actions and overlays.", read_only)
    async def list_scenes(ctx: Context, project: OptionalProject = None) -> Any:
        return answer(await call(ctx, args_of(["list-scenes"], [str(where(project))] if project else [])))

    @tool("Icons (built-in and the project's assets/icons) by search words or category; sheet=true also returns "
          "a picture of them, labelled.", read_only)
    async def list_icons(
        ctx: Context,
        search: Annotated[str | None, Field(description="words the name or tags must contain")] = None,
        category: str | None = None,
        project: OptionalProject = None,
        sheet: Annotated[bool, Field(description="also return a labelled sheet of the icons found")] = False,
        images: Images = DEFAULT_IMAGES,
    ) -> Any:
        out = policy.root / WORK_DIR / "icons.png"
        options = {"search": search, "category": category, "sheet": str(out) if sheet else None}
        doc = await call(ctx, args_of(["list-icons"], [str(where(project))] if project else [], options))
        return paged(doc, [Path(p) for p in doc.get("sheets", [])], 0, images if sheet else 0)

    @tool("Theme presets (built-in and the project's) with their colours, contrast checks and type scales; "
          "swatches=true also returns a swatch picture.", read_only)
    async def list_themes(
        ctx: Context,
        project: OptionalProject = None,
        swatches: Annotated[bool, Field(description="also return a swatch sheet of every preset")] = False,
    ) -> Any:
        out = policy.root / WORK_DIR / "themes.png"
        doc = await call(ctx, args_of(["list-themes"], [str(where(project))] if project else [], {"swatches": str(out) if swatches else None}))
        return answer(doc, [Path(doc["swatches"])] if swatches and doc.get("swatches") else [])

    @tool("Sound effects (built-in and the project's assets/sfx) with what they sound like and their params.", read_only)
    async def list_sfx(ctx: Context, project: OptionalProject = None) -> Any:
        return answer(await call(ctx, args_of(["list-sfx"], [str(where(project))] if project else [])))

    @tool("Background music: the built-in beds and the project's assets/music files, and composed music's moods "
          "(music: {compose: MOOD}; explainers: calm, focused, curious, upbeat; cartoons: playful, sleepy, tense, "
          "triumphant) and instrument names, each described in words, with whether the music extra is installed.", read_only)
    async def list_music(ctx: Context, project: OptionalProject = None) -> Any:
        return answer(await call(ctx, args_of(["list-music"], [str(where(project))] if project else [])))

    @tool("Compose a piece of music in a mood (the project's first compose: cue, changed by the options, or mood "
          "alone) and write it as a WAV and a MIDI file to listen to; returns its key, tempo, parts, chords per "
          "phrase and loudness. Needs the music extra (and downloads the SoundFont, 32 MB, on first use).", writes)
    async def music_preview(
        ctx: Context,
        project: OptionalProject = None,
        mood: Annotated[str | None, Field(description="the mood (list_music); default the project's compose: mood")] = None,
        seed: Annotated[int | None, Field(ge=0, description="another seed gives another piece in the mood")] = None,
        bars: Annotated[int | None, Field(ge=4, le=128, description="length in bars, a multiple of 4 (default: the mood's)")] = None,
        key: Annotated[str | None, Field(description="e.g. E, 'Eb major', 'F# minor' (default: the mood's)")] = None,
        tempo: Annotated[float | None, Field(ge=40, le=200, description="quarter notes per minute (default: the mood's)")] = None,
        out: Annotated[str, Field(description="folder for <mood>-seed<N>.wav and .mid, relative to the root")] = str(WORK_DIR / "music"),
    ) -> Any:
        options = {"mood": mood, "seed": seed, "bars": bars, "key": key, "tempo": tempo, "out": str(where(out, "out"))}
        positionals = ["preview", *([str(where(project))] if project else [])]
        return answer(await call(ctx, args_of(["music"], positionals, options), heavy=True))

    @tool("Score files (music written in YAML: key, tempo, sections, chords, tracks of step patterns; a project piece "
          "is assets/music/NAME.yaml, played with music: NAME): write a built-in bed as an editable template "
          "(bed=NAME; no bed: list the 17 templates with key, tempo, bars, sections). Start from momentum for "
          "documentaries; then change one thing at a time and run music_check after each change.", writes)
    async def music_template(
        ctx: Context,
        bed: Annotated[str | None, Field(description="the built-in bed to write as a score file (none: list them)")] = None,
        out: Annotated[str | None, Field(description="the .yaml to write, relative to the root (default assets/music/<bed>.yaml)")] = None,
        force: Annotated[bool, Field(description="overwrite the file if it exists")] = False,
    ) -> Any:
        if bed is None:
            return answer(await call(ctx, args_of(["music"], ["template"])))
        target = out or (Path("assets") / "music" / f"{bed}.yaml").as_posix()
        return answer(await call(ctx, args_of(["music"], ["template", bed], {"out": str(where(target, "out")), "force": force})))

    @tool("Every score-file instrument (drums, noises, basses, plucks and keys, leads, pads) with its settings, ranges "
          "and level, and every track effect (sweeps, ducking, gate, echo, reverb, width, volume curves), in words.", read_only)
    async def music_patches(ctx: Context) -> Any:
        return answer(await call(ctx, args_of(["music"], ["patches"])))

    @tool("Play a score file (YAML) to an MP3 or WAV for a human to listen to; returns its sections (start, bars, key, "
          "chords), tracks, length, loudness and warnings. Problems in the file come back all at once as "
          "'where: what' with did-you-mean.", writes)
    async def music_render(
        ctx: Context,
        score: Annotated[str, Field(description="the score file, relative to the root (e.g. assets/music/my_theme.yaml), or a project "
                                                "piece's name (my_theme) or a built-in bed's (tidewater)")],
        out: Annotated[str | None, Field(description="the .mp3 or .wav to write, relative to the root (default build/mcp/music/<score>.mp3)")] = None,
    ) -> Any:
        path = piece(score, "score")
        target = where(out, "out") if out else policy.root / WORK_DIR / "music" / f"{Path(path).stem}.mp3"
        return answer(await call(ctx, args_of(["music"], ["render", path], {"out": str(target)}), heavy=True))

    @tool("How a piece will sit under narration, for agents that cannot listen: a score file or an audio file checked "
          "for loudness and steadiness, peaks, tempo, loop seam, voice-range level (300 Hz-3 kHz), bass, harsh highs, "
          "key and whether its build / lift rise; a verdict, advice naming the score keys to change, a demo MP3 under a "
          "narration sample, and the spectrogram (returned as a picture: section marks, the voice band, a red lane "
          "where the voice range is too loud). compare=OTHER puts two versions side by side. A human makes the final choice.", writes)
    async def music_check(
        ctx: Context,
        source: Annotated[str, Field(description="a score file (.yaml) or an audio file, relative to the root, or a project piece's name "
                                                 "(my_theme) or a built-in bed's (momentum)")],
        compare: Annotated[str | None, Field(description="a second piece to compare with (e.g. the version before a change), given the same way")] = None,
        narration: Annotated[str | None, Field(description="an audio file of a voice for the demo (default: a 20 s sample shipped with vidgen)")] = None,
        out: Annotated[str, Field(description="folder for <name>-check.png and <name>-demo.mp3, relative to the root")] = str(WORK_DIR / "music"),
        images: Images = DEFAULT_IMAGES,
    ) -> Any:
        options = {
            "compare": piece(compare, "compare") if compare else None,
            "narration": str(where(narration, "narration")) if narration else None,
            "out": str(where(out, "out")),
        }
        doc = await call(ctx, args_of(["music"], ["check", piece(source, "source")], options), heavy=True)
        picture = (doc.get("files") or {}).get("spectrogram")
        return answer(doc, [Path(picture)] if picture and images else [])

    # ----- outputs ---------------------------------------------------------------------------------

    @tool("Render the video (MP4 + SRT + timings) and its thumbnail. preview=true (default) is fast and small; "
          "draft=true is faster still (about 8 fps, 240p, no idle, wind, shadows, particles or light grade; same "
          "timings) for checking timing and staging; the final render can take minutes. Scenes unchanged since "
          "their last render (e.g. by storyboard or lint) are reused. Reports progress.", writes)
    async def render(
        ctx: Context,
        project: Project = ".",
        preview: Annotated[bool, Field(description="fast low-resolution render (false: the final format)")] = True,
        draft: Annotated[bool, Field(description="a draft instead (wins over preview): ..._draft.mp4 from build/draft")] = False,
        variant: Variant = None,
        scene: Annotated[list[str] | None, Field(description="only re-render these scenes, then join")] = None,
        no_audio: Annotated[bool, Field(description="render without narration")] = False,
        keep_going: Annotated[bool, Field(description="continue after a scene fails")] = False,
        jobs: Jobs = 1,
        frames: Annotated[bool, Field(description="also save a still per beat end")] = False,
        force: Annotated[bool, Field(description="render every scene again, even unchanged ones")] = False,
        max_scenes: Annotated[int | None, Field(ge=1, description="render at most this many scenes, then stop without joining "
                                                "if more are left (call again to go on): a long final render in steps")] = None,
        all_languages: AllLanguages = False,
    ) -> Any:
        options = {
            "preview": preview and not draft, "draft": draft, "scene": scene, "variant": variant, "no-audio": no_audio,
            "keep-going": keep_going, "jobs": jobs, "frames": frames, "force": force, "max-scenes": max_scenes,
            "all-languages": all_languages,
        }
        return answer(await call(ctx, args_of(["render"], [str(where(project))], options), heavy=True))

    @tool("Narration audio (ElevenLabs, OpenRouter with voice.provider: openrouter, or Kokoro on this computer with "
          "voice.provider: kokoro) for the beats whose MP3 is missing or stale. dry_run=true (default, free, no key "
          "needed) lists the beats, provider, model, voice and the characters that would be billed (OpenRouter: the "
          "estimated cost with its basis; Kokoro: free (local)). A real run with ElevenLabs or OpenRouter COSTS MONEY: "
          "only with dry_run=false and confirm_cost=true, after the user agreed; Kokoro is free and needs no "
          "confirm_cost (its first run downloads the ~330 MB model).", paid)
    async def tts(
        ctx: Context,
        project: Project = ".",
        dry_run: Annotated[bool, Field(description="only list what would be generated (free)")] = True,
        confirm_cost: Annotated[bool, Field(description="required for dry_run=false: the user accepted the cost")] = False,
        beat: Annotated[list[str] | None, Field(description="only these beat ids")] = None,
        voice: Annotated[list[str] | None, Field(description="only the beats of these voices")] = None,
        variant: Variant = None,
        force: Annotated[bool, Field(description="regenerate even if up to date (costs money)")] = False,
    ) -> Any:
        if not dry_run and not confirm_cost and tts_provider(where(project), variant) not in FREE_TTS:
            raise ToolError(cost_refusal("tts", "calls the paid text-to-speech API"))
        options = {"dry-run": dry_run, "beat": beat, "voice": voice, "variant": variant, "force": force}
        return answer(await call(ctx, args_of(["tts"], [str(where(project))], options), heavy=True))

    @tool("Pictures for the generate: params of image scenes (OpenAI Images, or OpenRouter with imagegen.provider: "
          "openrouter). dry_run=true (default, free) lists prompts and the estimated cost with its basis. A real run "
          "COSTS MONEY: only with dry_run=false and confirm_cost=true.", paid)
    async def imagegen(
        ctx: Context,
        project: Project = ".",
        dry_run: Annotated[bool, Field(description="only list what would be generated, with the cost (free)")] = True,
        confirm_cost: Annotated[bool, Field(description="required for dry_run=false: the user accepted the cost")] = False,
        scene: Scenes = None,
        variant: Variant = None,
        force: Annotated[bool, Field(description="generate again even if the picture exists (costs money)")] = False,
    ) -> Any:
        if not dry_run and not confirm_cost:
            raise ToolError(cost_refusal("imagegen", "calls the paid image-generation API"))
        options = {"dry-run": dry_run, "scene": scene, "variant": variant, "force": force}
        return answer(await call(ctx, args_of(["imagegen"], [str(where(project))], options), heavy=True))

    @tool("Transcribe the narration MP3s (speech to text, cached) and compare them with the beat texts: word error "
          "rate, misheard words, words heard unclearly or after an odd pause (flags with beat and video times), "
          "suggested fixes. With a paid STT provider (stt.provider: elevenlabs) it needs "
          "confirm_cost=true.", paid)
    async def readback(
        ctx: Context,
        project: Project = ".",
        variant: Variant = None,
        beat: Annotated[list[str] | None, Field(description="only these beat ids")] = None,
        max_wer: Annotated[float | None, Field(ge=0, le=1, description="flag beats above this word error rate")] = None,
        force: Annotated[bool, Field(description="transcribe again even when cached")] = False,
        confirm_cost: Annotated[bool, Field(description="the user accepted the cost of a paid STT provider")] = False,
    ) -> Any:
        path = where(project)
        if not confirm_cost and stt_provider(path, variant) in PAID_STT:
            raise ToolError(
                "readback with this project's stt.provider calls a paid speech-to-text API; call again with "
                "confirm_cost=true once the user agreed (transcripts are cached: unchanged beats cost nothing)"
            )
        options = {"variant": variant, "beat": beat, "max-wer": max_wer, "force": force}
        return answer(await call(ctx, args_of(["readback"], [str(path)], options), heavy=True))

    @tool("A slide deck of the video's key frames with the narration as speaker notes: one self-contained HTML "
          "file (or a PDF, needs the extra schu-video-generator[pdf]).", writes)
    async def slides(
        ctx: Context,
        project: Project = ".",
        format: Literal["html", "pdf"] = "html",
        variant: Variant = None,
        final: Annotated[bool, Field(description="sharp slides from the final format (slower)")] = False,
        mode: Annotated[Literal["beat", "scene"], Field(description="a slide per beat or per scene")] = "beat",
        per_beat: Annotated[int, Field(ge=1, le=6)] = 1,
        overlays: Annotated[bool, Field(description="show captions, watermark... on the slides")] = True,
        notes: Annotated[bool, Field(description="PDF: notes pages")] = False,
        title_page: Annotated[bool, Field(description="PDF: a title page")] = False,
        audio: Annotated[bool, Field(description="HTML: embed the narration (Play narrates the deck)")] = False,
        output: Annotated[str | None, Field(description="file to write, relative to the root (default: exports/...)")] = None,
        jobs: Jobs = 1,
    ) -> Any:
        options = {
            "format": format, "variant": variant, "final": final, "mode": mode, "per-beat": per_beat,
            "no-overlays": not overlays, "notes": notes, "title-page": title_page, "audio": audio,
            "output": str(where(output, "output")) if output else None, "jobs": jobs,
        }
        return answer(await call(ctx, args_of(["slides"], [str(where(project))], options), heavy=True))

    @tool("The video's thumbnail (the config's thumbnail:, or a frame of a scene) with legibility checks; returns "
          "the picture and the small copy (as YouTube shows it).", writes)
    async def thumbnail(
        ctx: Context,
        project: Project = ".",
        variant: Variant = None,
        preview: Annotated[bool, Field(description="frames from the preview render (fast)")] = True,
        scene: Annotated[str | None, Field(description="a frame of this scene instead of the configured thumbnail")] = None,
        beat: Annotated[str | None, Field(description="with scene: the beat id or number (default: the last)")] = None,
        at: Annotated[float | None, Field(description="with scene: seconds into the beat")] = None,
        no_overlays: Annotated[bool, Field(description="with scene: the frame without overlays")] = False,
        jpeg: Annotated[bool, Field(description="also write a JPEG under 2 MB")] = False,
        jobs: Jobs = 1,
    ) -> Any:
        options = {"variant": variant, "preview": preview, "scene": scene, "beat": beat, "at": at, "no-overlays": no_overlays, "jpeg": jpeg, "jobs": jobs}
        doc = await call(ctx, args_of(["thumbnail"], [str(where(project))], options), heavy=True)
        return answer(doc, [Path(p) for p in (doc.get("path"), doc.get("small")) if p])

    @tool("Character sheets: every pose, expression and mouth shape of a declared character (characters: in "
          "video.yaml) on one labelled PNG, to check a character before acting with it; no name: one sheet per "
          "character. Returns the sheets as images and their paths (exports/character_sheet_<name>.png).", writes)
    async def character_sheet(
        ctx: Context,
        project: Project = ".",
        name: Annotated[str | None, Field(description="the character's name (default: every character)")] = None,
        variant: Variant = None,
        images: Images = DEFAULT_IMAGES,
        image_offset: Offset = 0,
    ) -> Any:
        positionals = [name, str(where(project))] if name else [str(where(project))]
        options = {"all": name is None, "variant": variant}
        doc = await call(ctx, args_of(["character-sheet"], positionals, options))
        return paged(doc, [Path(s["path"]) for s in doc.get("sheets", [])], image_offset, images)

    @tool("Export a scene or a time range of the rendered video as a GIF or an MP4 clip (render first).", writes)
    async def export(
        ctx: Context,
        kind: Literal["gif", "clip"],
        project: Project = ".",
        scene: Annotated[str | None, Field(description="this scene; start / end then count from its start")] = None,
        start: Annotated[float | None, Field(ge=0, description="start in seconds")] = None,
        end: Annotated[float | None, Field(ge=0, description="end in seconds")] = None,
        variant: Variant = None,
        preview: Annotated[bool, Field(description="from the preview render")] = True,
        width: Annotated[int | None, Field(ge=16)] = None,
        fps: Annotated[float | None, Field(gt=0)] = None,
        max_mb: Annotated[float | None, Field(gt=0, description="GIF: size budget")] = None,
        with_audio: Annotated[bool, Field(description="clip: keep the sound")] = False,
        output: Annotated[str | None, Field(description="file to write, relative to the root (default: exports/...)")] = None,
    ) -> Any:
        options = {
            "scene": scene, "from": start, "to": end, "variant": variant, "preview": preview, "width": width, "fps": fps,
            "max-mb": max_mb, "with-audio": with_audio, "output": str(where(output, "output")) if output else None,
        }
        return answer(await call(ctx, args_of(["export", kind], [str(where(project))], options), heavy=True))

    @tool("Render scene types' samples (from the guide's snippets) and return their stills: what each type looks "
          "like at 16:9 and 9:16. Give types (a full run renders all ~28 types: minutes).", writes)
    async def gallery(
        ctx: Context,
        types: Annotated[list[str] | None, Field(description="scene types to show (default: all)")] = None,
        formats: Annotated[list[Literal["16:9", "9:16"]] | None, Field(description="formats (default: both)")] = None,
        theme: Annotated[str | None, Field(description="theme preset")] = None,
        project: OptionalProject = None,
        output: Annotated[str, Field(description="gallery folder, relative to the root")] = str(WORK_DIR / "gallery"),
        jobs: Jobs = 1,
        images: Images = DEFAULT_IMAGES,
        image_offset: Offset = 0,
    ) -> Any:
        options = {
            "output": str(where(output, "output")), "types": [",".join(types)] if types else None,
            "formats": ",".join(formats) if formats else None, "theme": theme, "no-clips": True, "jobs": jobs,
        }
        doc = await call(ctx, args_of(["gallery"], [str(where(project))] if project else [], options), heavy=True)
        stills = [Path(p) for t in doc.get("types", []) for p in t.get("stills", {}).values()]
        return paged(doc, stills, image_offset, images)

    @tool("Write or update a variant's translation file: every text to translate with its source (merging what "
          "it already holds).", writes)
    async def translate_template(
        ctx: Context,
        project: Project = ".",
        variant: Variant = None,
        language: Annotated[str | None, Field(description="language of the translation, BCP-47 (e.g. pt-BR)")] = None,
        output: Annotated[str | None, Field(description="file to write, relative to the root")] = None,
    ) -> Any:
        options = {"variant": variant, "language": language, "output": str(where(output, "output")) if output else None}
        return answer(await call(ctx, args_of(["translate-template"], [str(where(project))], options)))

    # ----- the studio's hand-offs (Step 198, DESIGN.md §94.16) -------------------------------------
    # Through files on disk, in this process (small reads and one atomic write; no Manim).

    async def studio(command: str, work: Callable[[], dict[str, Any]]) -> Any:
        import anyio

        try:
            doc = await anyio.to_thread.run_sync(work)
        except VidgenError as exc:
            raise ToolError(str(exc)) from None
        return answer({"ok": True, "command": command, **doc})

    Session = Annotated[str | None, Field(description="the studio session id (studio_sessions lists them; default: the one a running studio has open)")]

    @tool("The vidgen studio sessions (music a person is shaping in `vidgen studio`) you can answer: the one open in a "
          "running studio first, each with its open listening notes and whether the person asked an agent (a hand-off).", read_only)
    async def studio_sessions(ctx: Context) -> Any:
        from vidgen.studio_app.agent import agent_sessions

        return await studio("studio_sessions", lambda: agent_sessions(policy.root))

    @tool("Read a studio hand-off: the score (YAML) of the version to change, the person's open listening notes (id, "
          "words, bar, beat, section), its last check report (text and findings), what changed from its parent "
          "version, and the instruction. Then change the score (one thing per note when you can), studio_check it, "
          "and studio_propose it with one line per note.", read_only)
    async def studio_read(
        ctx: Context,
        session: Session = None,
        version: Annotated[int | None, Field(ge=1, description="another version (default: the hand-off's, else the current one)")] = None,
    ) -> Any:
        from vidgen.studio_app.agent import agent_read

        return await studio("studio_read", lambda: agent_read(policy.root, session, version))

    @tool("Check a score as the studio will show it to the person (vidgen music check: how it sits under narration, a "
          "verdict and advice; the spectrogram as a picture): give the score you mean to propose; no score: the "
          "session's version handed off. compare=true puts it side by side with that version.", writes)
    async def studio_check(
        ctx: Context,
        session: Session = None,
        score: Annotated[str | None, Field(description="the whole score file's text to check (default: the version handed off)")] = None,
        compare: Annotated[bool, Field(description="also check the version handed off and compare the two")] = False,
        images: Images = DEFAULT_IMAGES,
    ) -> Any:
        import anyio

        from vidgen.studio_app.agent import agent_read

        try:
            read = await anyio.to_thread.run_sync(lambda: agent_read(policy.root, session))
        except VidgenError as exc:
            raise ToolError(str(exc)) from None
        folder = policy.root / WORK_DIR / "studio"
        folder.mkdir(parents=True, exist_ok=True)
        base = folder / f"{read['session']}-v{read['base']}.yaml"
        base.write_text(read["score"], encoding="utf-8")
        target = base
        if score is not None:
            target = folder / f"{read['session']}-proposal.yaml"
            target.write_text(score, encoding="utf-8")
        options = {"compare": str(base) if compare and target != base else None, "out": str(folder)}
        doc = await call(ctx, args_of(["music"], ["check", str(target)], options), heavy=True)
        picture = (doc.get("files") or {}).get("spectrogram")
        return answer({**doc, "session": read["session"], "base": read["base"]}, [Path(picture)] if picture and images else [])

    @tool("Four variations of a studio session's version (the studio's Variations button: another voicing or chord, an "
          "altered figure, a darker or brighter mix, another arrangement), each a whole score with a one-line label. Pure "
          "edits of the score (nothing rendered or written); shuffle=N gives four others. Start from one, change it "
          "further if the notes ask, then studio_propose it.", read_only)
    async def studio_variations(
        ctx: Context,
        session: Session = None,
        version: Annotated[int | None, Field(ge=1, description="the version to vary (default: the current one)")] = None,
        shuffle: Annotated[int, Field(ge=0, le=999, description="a counter: the same one always gives the same four")] = 0,
    ) -> Any:
        from vidgen.studio_app.variations import agent_variations

        return await studio("studio_variations", lambda: agent_variations(policy.root, session, version, shuffle))

    @tool("Propose a new version of a studio session's score, answering the person's notes: the WHOLE score text and "
          "one line per note id on what you changed and why. It is validated (a score with problems is refused with "
          "them; fix and call again) and appears in the studio as a new version 'agent: <summary>' that the person "
          "A/Bs against the one handed off and keeps or discards. It never replaces a version.", writes)
    async def studio_propose(
        ctx: Context,
        score: Annotated[str, Field(description="the whole new score file (YAML), comments kept")],
        explanations: Annotated[dict[str, str], Field(description="note id (n1, n2...) -> one line: what you changed for it and why")],
        summary: Annotated[str | None, Field(description="a few words naming the change (the version's name)")] = None,
        agent: Annotated[str | None, Field(description="your name, shown with the proposal")] = None,
        session: Session = None,
        base: Annotated[int | None, Field(ge=1, description="the version you changed (default: the hand-off's)")] = None,
    ) -> Any:
        from vidgen.studio_app.agent import agent_propose

        return await studio("studio_propose", lambda: agent_propose(policy.root, score, explanations, summary, agent, session, base))

    _add_resources(server, policy)
    return server


def _add_resources(server: Any, policy: RootPolicy) -> None:
    """The guide (whole and per topic), the JSON Schema of video.yaml and the gallery pages under
    the root (``docs/gallery``), if any, as MCP resources."""
    from vidgen.guide import guide_text, guide_topics

    def text_resource(uri: str, name: str, description: str, mime: str, read: Callable[[], Any]) -> None:
        server.resource(uri, name=name, description=description, mime_type=mime)(read)

    def guide_resource() -> str:
        return guide_text()

    text_resource("vidgen://guide", "guide", "The vidgen author guide (AGENTS.md): how to make a good video.", "text/markdown", guide_resource)
    for topic in guide_topics():
        text_resource(
            f"vidgen://guide/{topic.name}", f"guide-{topic.name}", f"Author guide: {topic.title}", "text/markdown", _constant(topic.text)
        )

    async def schema_resource() -> str:
        run = await run_vidgen(["schema", "--json"], policy.root)
        if run.doc is None or not run.doc.get("ok"):
            raise VidgenError(f"vidgen schema failed: {compact(run.doc) if run.doc else run.stderr_tail}")
        return json.dumps(run.doc["schema"], ensure_ascii=False)

    text_resource(
        "vidgen://schema", "schema", "JSON Schema of video.yaml (the root project's scene types, else the built-ins).",
        "application/json", schema_resource,
    )
    gallery = policy.root / "docs" / "gallery"
    if gallery.is_dir():
        for page in sorted(gallery.glob("*.md")):
            name = "index" if page.name == "README.md" else page.stem
            text_resource(
                f"vidgen://gallery/{name}", f"gallery-{name}", f"Scene gallery page: {name}", "text/markdown", _file_reader(page)
            )


def _constant(text: str) -> Callable[[], str]:
    def read() -> str:
        return text

    return read


def _file_reader(path: Path) -> Callable[[], str]:
    def read() -> str:
        return path.read_text(encoding="utf-8")

    return read


def serve(root: Path) -> None:
    """Run the server on stdin / stdout until the client closes the connection."""
    server = build_server(root)
    server.run("stdio")


def main(argv: Sequence[str] | None = None) -> int:
    """The ``vidgen-mcp`` console script: ``vidgen-mcp [--root DIR]``."""
    import argparse

    parser = argparse.ArgumentParser(prog="vidgen-mcp", description="MCP server (stdio) for vidgen")
    parser.add_argument("--root", metavar="DIR", default=".", help="the only folder the tools may read and write (default: .)")
    parser.add_argument("--version", action="version", version=f"vidgen {__version__}")
    args = parser.parse_args(argv)
    try:
        serve(Path(args.root))
    except VidgenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0

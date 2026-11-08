"""Generated video shots of a project (DESIGN.md §113.3): each beat's ``generated_shot:``
resolved into one or more :class:`~vidgen.videogen.VideoRequest` s with their inputs, and the
dry-run plan of ``vidgen generate plan``.

- **Timing**: a shot covers its beat's window on the planned timeline (:mod:`vidgen.videoplan`:
  the beat's start to the next beat's start, at the video's frame rate). The model is asked for
  the shortest length it allows that covers it (:func:`~vidgen.videogen.models.snap_duration`;
  the clip is trimmed later); a beat longer than the model's longest clip is split into equal
  parts (``<beat>_p2``...). A model without lengths (heygen/avatar-iv) follows its audio: the
  beat's length is sent as nothing and priced in whole seconds.
- **Inputs** (made by :mod:`vidgen.videogen.inputs` into ``build/videogen/<shot>/``): the
  beat's voice cut to the part (``audio.mp3``), a silent low-resolution render of the part
  (``guide.mp4``) or, on a ``3d`` scene with ``guide: depth | outline | mask``, that guide pass
  of the part (``guide.<pass>.mp4``, DESIGN.md §113.8), the render's first frame
  (``first_frame.png``); pictures of approved reference sheets
  (:mod:`vidgen.videogen.sheets`) and your own pictures. The first frame goes in as a frame image
  where the model lists ``first_frame``, else as a picture reference.
- **Prompt**: the kind's framing and the shot's ``prompt``, the setting, the characters' sheet
  words, the line said, what a guide pass is (:data:`GUIDE_PROMPTS`; a mask also lists the
  stand-ins' colours), the style sheet's words and "no on-screen text". A shot with a guide video
  (DESIGN.md §113.12) leaves the framing to the guide: a talking shot says
  :data:`GUIDED_TALKING_FRAMING`, and the framing instructions of the characters' sheet words are
  left out (:func:`without_framing`; the plan notes what was left out).
- **Blocked**: a shot whose sheets are not approved, whose inputs are not made yet or no longer
  match what they were cut from (:mod:`vidgen.videogen.freshness`; a shot already cached or with
  an earlier job is reused free and only gets a note), or whose audio / video needs a hosted URL
  (``videogen.host: none``) is planned and priced but not ready to pay for. With ``inline_media: all`` (and no host) the audio / video would go inline, which
  OpenRouter refuses: that is a problem (``run --pay`` refuses it before sending).
- **Shared** (``videogen.host: quick_tunnel``, DESIGN.md §115): a paid run shares the shot's audio
  / video inputs (:attr:`Shot.shared`) through a Cloudflare quick tunnel while its job runs; the
  plan lists exactly those files and the tunnel's maximum lifetime; without ``cloudflared`` the
  shot is blocked with the install hints.
- **Earlier wording**: a guided shot paid for under the earlier prompt wording is blocked, not
  paid again by itself (:data:`EARLIER_WORDING_BLOCKED`).
- **Sound** (:attr:`Shot.sound`, DESIGN.md §113.11): ``mix`` (no sound asked of the model) or
  ``model`` (``generate_audio: true``): ``generated_shot.sound``, else
  ``videogen.models.<model>.sound``, else ``videogen.sound``. A model the list says cannot make
  sound is blocked, one it says nothing about gets a note.
- **Size**: the plan of a ready shot gives the request's size with its inline pictures (sent as
  smaller copies, :mod:`vidgen.videogen.pictures`, made here into ``build/videogen/pictures/``);
  over :data:`~vidgen.videogen.openrouter.MAX_INLINE_BYTES` is a problem.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from pathlib import Path

from vidgen.config import BeatConfig, GeneratedShot, SceneConfig, SoundChoice, VideoConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videogen import MOCK_PROVIDER, MediaInput, VideoRequest, did_you_mean, request_hash
from vidgen.videogen.ledger import BudgetState, Ledger, SubmitIntent, intent_refusal, intent_text
from vidgen.videogen.models import TIER_SHORT_SIDE, Catalog, Estimate, RequestCheck, VideoModel, check_request, estimate, money, snap_duration
from vidgen.videogen.sheets import STYLE, Sheet, character_sheet, plan_sheets, style_sheet
from vidgen.videogen.takes import takes_of

#: Where the cut inputs of each shot are written, relative to the project (rebuilt any time).
INPUTS_DIR = Path("build") / "videogen"
#: Words that start each kind's prompt.
FRAMING: dict[str, str] = {
    "talking": "Talking close-up of {who}, facing the camera, speaking",
    "action": "Action shot",
    "establishing": "Establishing shot",
}
#: Replaces ``FRAMING["talking"]`` when the shot has a guide video: the guide decides where the
#: speaker is and which way they face, so the prompt must not ask for a close-up.
GUIDED_TALKING_FRAMING = "{who}, speaking"
NO_TEXT = "No on-screen text, captions, subtitles or logos"
#: Words that instruct how a picture is framed. Hyphenated forms ("self-centred") do not count.
_FRAMING_WORDS = re.compile(
    r"(?<![\w-])(?:cent(?:red|ered)|(?:centre|center|middle) of the (?:picture|frame|image|shot|screen)"
    r"|(?:whole|full)[- ]body|full[- ]length|close[- ]?up|head[- ]and[- ]shoulders|from head to (?:toe|foot)"
    r"|(?:front|side|back|rear|three[- ]quarter|profile)[- ]view|front[- ]facing|fac(?:es|ing) (?:the camera|forward)"
    r"|looking (?:at|into) the camera|in (?:the )?frame|waist[- ]up|(?:medium|wide)[- ]shot)(?![\w-])",
    re.IGNORECASE,
)
#: A clause naming any of these describes the character: it is kept even with framing words in it.
_APPEARANCE_WORDS = re.compile(
    r"\b(?:hair(?:ed)?|beard(?:ed)?|moustache|mustache|eyes?|eyebrows?|skin|freckles?|scars?|tattoos?|jackets?|coats?|raincoats?|"
    r"shirts?|blouses?|sweaters?|jumpers?|hoodies?|dress(?:es)?|skirts?|trousers|pants|jeans|shorts|suits?|uniforms?|"
    r"shoes|boots|sneakers|hats?|caps?|helmets?|scar(?:f|ves)|glasses|gloves)\b",
    re.IGNORECASE,
)
#: Clauses that only make a sheet picture clean ("exactly one character", "not a split image");
#: they are left out only next to a framing clause in the same sentence.
_SHEET_ONLY_CLAUSE = re.compile(
    r"^(?:(?:exactly|only|just)\s+)?(?:a\s+|one\s+)?(?:single\s+)?(?:character|person|figure|subject)(?:\s+only)?[,;.]?$"
    r"|^(?:alone|solo)[,;.]?$|^(?:not|no|never)\s",
    re.IGNORECASE,
)
#: What a guide pass is, said in the prompt when one is sent as the guide (DESIGN.md §113.8).
GUIDE_PROMPTS: dict[str, str] = {
    "depth": "The guide video is a depth map (near is white, far is dark): follow its layout and camera motion",
    "outline": "The guide video is an outline drawing (white edges on black): follow its shapes, layout and camera motion",
    "mask": "The guide video is a colour mask (each object one flat colour on black): follow its layout and motion",
}
#: A mask guide's prompt lists the stand-ins' colours when the scene has at most this many.
MASK_NAMES_MAX = 4
#: What the plan says each guide is.
GUIDE_WHAT: dict[str, str] = {
    "render": "silent draft render",
    "depth": "depth pass of the beat's 3D scene",
    "outline": "outline pass of the beat's 3D scene",
    "mask": "mask pass of the beat's 3D scene",
}
#: The problem of a shot whose voice or guide would go inline (OpenRouter answered HTTP 400
#: "Only HTTPS URLs are allowed" for an inline audio reference, Step 296).
INLINE_AUDIO_VIDEO_PROBLEM = (
    "audio/video references must be https URLs; OpenRouter refuses inline audio/video — "
    "remove `audio:`/`guide:` from the shot or host the files (videogen: {host: quick_tunnel})"
)
#: The blocked reason of a shot with audio / video inputs and no host.
NO_HOST_BLOCKED = (
    "audio / video inputs need a hosted URL (OpenRouter refuses inline audio / video): set videogen: {host: quick_tunnel} "
    "to share only this shot's files through a Cloudflare quick tunnel while its job runs (check it first, free: "
    "`vidgen generate host-test`)"
)
#: The blocked reason of a guided shot already paid for under the earlier prompt wording.
EARLIER_WORDING_BLOCKED = (
    "this guided shot was paid for already under vidgen's earlier prompt wording (close-up words and sheet framing words are no longer "
    "sent with a guide), so a run would pay for a new clip; not paid again by itself. The earlier take stays in the film. "
    "To pay for a new take with the new wording: set or change seed: on the shot, or change its prompt:"
)
#: What the plan says each sound setting is.
SOUND_WHAT: dict[str, str] = {
    "mix": "vidgen's voice and music; the model is asked for no sound",
    "model": "the model makes the clip's own sound and vidgen keeps it",
}
#: Picture files a shot may name in ``refs`` / ``first_frame``.
PICTURE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


@dataclass(frozen=True)
class ShotInput:
    """One input of a shot: its ``role`` (``first_frame``, ``reference``, ``audio``, ``guide``),
    kind, file, what it is (``what``) and whether it goes in as a frame image."""

    role: str
    kind: str
    path: Path
    what: str
    frame: bool = False

    @property
    def ready(self) -> bool:
        """Whether the file exists."""
        return self.path.is_file()

    def media(self) -> MediaInput:
        """The input as sent."""
        return MediaInput(self.kind, path=self.path, frame_type="first_frame" if self.frame else None)  # type: ignore[arg-type]


@dataclass
class Shot:
    """One clip of a beat's ``generated_shot`` (a part of it when the beat is split)."""

    id: str
    scene_id: str
    beat: BeatConfig
    spec: GeneratedShot
    location: str
    start: float
    offset: float
    length: float
    part: int = 1
    parts: int = 1
    speaker: str | None = None
    characters: list[str] = field(default_factory=list)
    model: VideoModel | None = None
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    inputs: list[ShotInput] = field(default_factory=list)
    prompt: str = ""
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    #: Where the shot's scene starts on the planned timeline (``start - scene_start``: the shot's
    #: time in its scene's render).
    scene_start: float = 0.0
    #: Where the shot's scene ends on the planned timeline (its fade-out and hold included).
    scene_end: float = 0.0
    #: With ``videogen.host: quick_tunnel``: the tunnel's maximum lifetime in minutes (``None``:
    #: nothing is shared, no host or no audio / video input).
    share_minutes: float | None = None
    #: The mock provider gives this shot's audio / video inputs fake addresses (nothing is shared).
    fake_addresses: bool = False
    #: The shot's resolved sound setting (``mix`` or ``model``).
    sound: SoundChoice = "mix"
    #: A guided shot's prompt under the earlier wording, when it differs from :attr:`prompt` (else
    #: empty): what a clip paid for before the wording changed was asked with.
    earlier_prompt: str = ""

    @property
    def shared(self) -> list[ShotInput]:
        """The inputs a paid run would share through the host (audio and video; pictures go inline)."""
        return [i for i in self.inputs if i.kind != "image"]

    @property
    def folder(self) -> str:
        """``build/videogen/<id>`` (as written in messages)."""
        return (INPUTS_DIR / self.id).as_posix()

    def request(self) -> VideoRequest | None:
        """The clip asked of the model (``None`` when the model is unknown)."""
        if self.model is None:
            return None
        return VideoRequest(
            model=self.model.id, prompt=self.prompt, duration=self.duration if self.duration is not None else max(1, math.ceil(self.length - 1e-9)),
            resolution=self.resolution, aspect_ratio=self.aspect_ratio,
            frame_images=tuple(i.media() for i in self.inputs if i.frame),
            references=tuple(i.media() for i in self.inputs if not i.frame), seed=self.spec.seed,
            generate_audio=self.sound == "model",
        )

    @property
    def priced_seconds(self) -> float | None:
        """Seconds a model without lengths is priced for (the part, rounded up), else ``None``."""
        return float(math.ceil(self.length - 1e-9)) if self.duration is None else None


def guide_name(source: str) -> str:
    """The guide file of a shot: ``guide.mp4`` for the draft render, ``guide.<pass>.mp4`` for a
    guide pass of a ``3d`` scene."""
    return "guide.mp4" if source == "render" else f"guide.{source}.mp4"


def inputs_command(project: Project, guide: bool) -> str:
    """The command that cuts ``project``'s inputs (the free re-cut a blocked shot asks for)."""
    variant = f" --variant {project.variant}" if project.variant else ""
    return f"vidgen generate inputs{' --guide' if guide else ''}{variant}"


def _ratio(text: str) -> float:
    a, _, b = text.partition(":")
    return float(a) / float(b)


def video_ratio(config: VideoConfig) -> str:
    """The format's aspect ratio as ``9:16`` (reduced)."""
    w, h = config.format.width, config.format.height
    g = math.gcd(w, h)
    return f"{w // g}:{h // g}"


def pick_aspect(config: VideoConfig, model: VideoModel) -> str:
    """The model's listed aspect ratio nearest the video's (the video's own when none is listed)."""
    own = video_ratio(config)
    if not model.aspect_ratios:
        return own
    target = config.format.width / config.format.height
    usable = [r for r in model.aspect_ratios if ":" in r]
    return min(usable, key=lambda r: abs(math.log(_ratio(r) / target))) if usable else own


def lowest_resolution(model: VideoModel) -> str | None:
    """The model's lowest listed resolution tier (``None``: it lists none)."""
    if not model.resolutions:
        return None
    return min(model.resolutions, key=lambda r: TIER_SHORT_SIDE.get(r.lower(), 10**6))


def _speaker(config: VideoConfig, scene: SceneConfig, beat: BeatConfig) -> str | None:
    """The character whose voice says ``beat`` (the first one; ``None``: the narrator)."""
    from vidgen.voices import DEFAULT_VOICE

    voice = beat.voice or scene.voice or DEFAULT_VOICE
    return next((e.name for e in config.characters if e.voice is not None and e.voice == voice), None)


def _clean(text: str) -> str:
    return " ".join(text.split()).rstrip(".")


def display_name(name: str) -> str:
    """A character's name as a prompt writes it: ``old_tom`` -> ``Old Tom``."""
    return " ".join(w.capitalize() for w in name.split("_"))


def _sentence(text: str) -> str:
    return text if text.endswith((".", "!", "?", '."', '!"', '?"')) else text + "."


def without_framing(words: str) -> tuple[str, list[str]]:
    """``words`` (a character's sheet text) without its picture-framing instructions, and the
    pieces left out. A sentence with a framing clause loses its framing clauses and the clauses
    that only make the sheet picture clean; a sentence with none is kept as it is, and so is a
    clause that also describes the character, even with framing words in it."""
    kept_sentences: list[str] = []
    removed: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", words):
        clauses = re.split(r"(?<=[,;])\s+", sentence)
        if not any(_is_framing_clause(c) for c in clauses):
            kept_sentences.append(sentence)
            continue
        kept = [c for c in clauses if not _is_left_out(c)]
        removed.append(" ".join(c for c in clauses if _is_left_out(c)).rstrip(",;. "))
        if kept:
            kept_sentences.append(" ".join(kept).rstrip(",;. ") + ".")
    if not removed:
        return words, []
    return " ".join(kept_sentences).rstrip("."), removed


def _is_framing_clause(clause: str) -> bool:
    return bool(_FRAMING_WORDS.search(clause)) and not _APPEARANCE_WORDS.search(clause)


def _is_left_out(clause: str) -> bool:
    """Whether ``clause``, of a sentence with a framing clause, leaves the shot prompt."""
    return _is_framing_clause(clause) or (bool(_SHEET_ONLY_CLAUSE.search(clause.strip())) and not _APPEARANCE_WORDS.search(clause))


def shot_prompt(project: Project, shot: Shot, sheets: dict[str, Sheet | None]) -> str:
    """The prompt of ``shot`` (see the module docstring)."""
    return _prompt_text(project, shot, sheets, guided=shot.spec.guide_source is not None)


def _prompt_text(project: Project, shot: Shot, sheets: dict[str, Sheet | None], *, guided: bool) -> str:
    """The prompt; ``guided`` leaves framing to the guide (with ``False``, also a guided shot's
    prompt under the earlier wording: the guide sentence depends on the shot, not on this flag)."""
    spec = shot.spec
    who = shot.speaker or (shot.characters[0] if shot.characters else None)
    framing = GUIDED_TALKING_FRAMING if guided and spec.kind == "talking" else FRAMING[spec.kind]
    head = framing.format(who=display_name(who) if who else "the speaker")
    parts = [f"{head}: {_clean(spec.prompt)}" if spec.prompt.strip() else head]
    if spec.setting:
        parts.append(f"Setting: {_clean(spec.setting)}")
    if shot.characters:
        described = []
        for name in shot.characters:
            sheet = sheets.get(name)
            words = (without_framing(sheet.notes)[0] if guided else sheet.notes) if sheet is not None else ""
            described.append(f"{display_name(name)} ({words})" if words else display_name(name))
        parts.append("Characters: " + "; ".join(described))
    if spec.line:
        text = " ".join(shot.beat.text.replace('"', "'").split())
        parts.append(f'{display_name(shot.speaker)} says: "{text}"' if shot.speaker else f'Spoken over the shot: "{text}"')
    guide = spec.guide_source
    if guide in GUIDE_PROMPTS:
        parts.append(GUIDE_PROMPTS[guide])
        if guide == "mask":
            parts += _mask_names(project, shot.scene_id)
    style = project.config.style_sheet
    if style is not None and style.words():
        parts.append(f"Style: {style.words()}")
    parts.append(NO_TEXT)
    return " ".join(_sentence(p) for p in parts)


def _left_out_notes(shot: Shot, sheets: dict[str, Sheet | None]) -> list[str]:
    """A plan note for each character of a guided shot whose sheet words lost framing instructions."""
    notes = []
    for name in shot.characters:
        sheet = sheets.get(name)
        removed = without_framing(sheet.notes)[1] if sheet is not None else []
        if removed:
            left_out = "; ".join(f'"{r}"' for r in removed)
            notes.append(f"{display_name(name)}'s sheet words left out of this prompt, because the guide decides where the character is and how the shot is framed (the sheet itself is unchanged): {left_out}")
    return notes


def _paid_under_earlier_wording(root: Path, ledger: Ledger, shot: Shot, request: VideoRequest) -> bool:
    """Whether a clip of ``shot`` under its earlier prompt wording was paid for (a clip, a take or a
    job of that request; ``request``'s inputs exist)."""
    from vidgen.videogen.run import clip_path

    if not shot.earlier_prompt:
        return False
    key = request_hash(replace(request, prompt=shot.earlier_prompt))
    if clip_path(root, key).is_file() or any(t.info.get("key") == key for t in takes_of(root, shot.id)):
        return True
    return any(j.request_hash == key and j.status in (None, "completed") for j in ledger.jobs())


def _mask_names(project: Project, scene_id: str) -> list[str]:
    """``["Mask colours: Ana #rrggbb, Ben #rrggbb"]`` for the stand-ins of ``scene_id`` (by
    name, else id) when there are 1 to :data:`MASK_NAMES_MAX`; else nothing. The colours are
    the mask pass's own (:func:`~vidgen.three_d.passes.mask_colors`: they depend only on the ids)."""
    from vidgen.three_d.passes import mask_colors
    from vidgen.three_d.spec import FLOOR_ID, Scene3DParams

    scene = project.scene(scene_id)
    try:
        params = Scene3DParams.model_validate(scene.params)
    except ValueError:   # the scene's own problem, reported by vidgen validate
        return []
    standins = [o for o in params.objects if o.shape == "standin"]
    if not standins or len(standins) > MASK_NAMES_MAX:
        return []
    objects = ([{"id": FLOOR_ID, "shape": "plane"}] if params.floor is not None else []) + [{"id": o.id, "shape": o.shape} for o in params.objects]
    colors = mask_colors({"objects": objects})
    return ["Mask colours: " + ", ".join(f"{o.name or display_name(o.id)} {colors[o.id]}" for o in standins)]


def _picture(project: Project, value: str, where: str, problems: list[str]) -> Path | None:
    path = project.root / value
    if path.suffix.lower() not in PICTURE_SUFFIXES:
        problems.append(f"{where}: {value!r} is not a character, style or a picture file ({', '.join(PICTURE_SUFFIXES)})")
        return None
    if not path.is_file():
        problems.append(f"{where}: no picture {value} in the project")
        return None
    return path


def _sheet_of(name: str, sheets: dict[str, Sheet | None]) -> Sheet | None:
    if name not in sheets:
        return None
    return sheets[name]


def _resolve_inputs(project: Project, shot: Shot, sheets: dict[str, Sheet | None]) -> None:
    """Fill ``shot.inputs`` and its problems / blocked reasons."""
    spec, folder, where = shot.spec, project.root / INPUTS_DIR / shot.id, shot.location
    frame_ok = shot.model is not None and shot.model.frame_types is not None and "first_frame" in shot.model.frame_types
    used: set[Path] = set()
    needs: set[str] = set()   # sheets the shot uses
    source = spec.first_frame_source
    first: Path | None = None
    what = ""
    if source == "sheet":
        owner = shot.speaker if spec.kind == "talking" and shot.speaker else (shot.characters[0] if shot.characters else None)
        sheet = _sheet_of(owner, sheets) if owner else None
        if owner is None:
            problems = "a talking shot needs a speaker: the beat's voice belongs to no character" if spec.kind == "talking" else "first_frame: sheet needs a character in the shot"
            shot.problems.append(f"{where}: {problems} (set characters:, or first_frame: a picture file)")
        elif sheet is None:
            shot.problems.append(f"{where}: first_frame: sheet, but character {owner!r} has no reference_sheet (add one, or first_frame: a picture file)")
        else:
            first, what = sheet.paths[0], f"{owner} sheet, {sheet.pictures[0].label}"
            needs.add(owner)
    elif source == "render":
        first, what = folder / "first_frame.png", "first frame of the beat's render"
    elif source != "none":
        first = _picture(project, source, f"{where}.first_frame", shot.problems)
        what = "your picture"
    if first is not None:
        role = "first_frame" if frame_ok else "portrait" if spec.kind == "talking" else "first_frame"
        shot.inputs.append(ShotInput(role, "image", first, what, frame=frame_ok))
        used.add(first)
        if not frame_ok and shot.model is not None:
            shot.notes.append(f"{shot.model.id} lists no first-frame images: the {role.replace('_', ' ')} goes in as a picture reference")
    # a talking model animates one portrait: no other pictures unless refs: names them
    default_refs = [] if spec.kind == "talking" else list(shot.characters) + ([STYLE] if project.config.style_sheet is not None else [])
    for value in spec.refs if spec.refs is not None else default_refs:
        if value == STYLE:
            sheet = sheets.get(STYLE)
            if sheet is None:
                shot.problems.append(f"{where}.refs: style, but the video has no style_sheet:")
                continue
            if sheet.pictures:
                needs.add(STYLE)
            for picture in sheet.pictures:
                if picture.request.path not in used:
                    shot.inputs.append(ShotInput("reference", "image", picture.request.path, f"style sheet, {picture.label}"))
                    used.add(picture.request.path)
            for ref in project.config.style_sheet.references if project.config.style_sheet else []:
                path = _picture(project, ref, "style_sheet.references", shot.problems)
                if path is not None and path not in used:
                    shot.inputs.append(ShotInput("reference", "image", path, "style reference"))
                    used.add(path)
        elif value in sheets:
            sheet = sheets[value]
            if sheet is None:
                shot.problems.append(f"{where}.refs: character {value!r} has no reference_sheet")
                continue
            needs.add(value)
            for picture in sheet.pictures:
                if picture.request.path not in used:
                    shot.inputs.append(ShotInput("reference", "image", picture.request.path, f"{value} sheet, {picture.label}"))
                    used.add(picture.request.path)
        elif "/" not in value and "." not in value:
            names = [n for n in sheets if n != STYLE]
            shot.problems.append(f"{where}.refs: unknown character {value!r}{did_you_mean(value, [*names, STYLE])}; characters: {', '.join(names) or 'none'}")
        else:
            path = _picture(project, value, f"{where}.refs", shot.problems)
            if path is not None and path not in used:
                shot.inputs.append(ShotInput("reference", "image", path, "your picture"))
                used.add(path)
    if spec.wants_audio:
        shot.inputs.append(ShotInput("audio", "audio", folder / "audio.mp3", f"the beat's voice, {shot.length:.2f} s"))
    guide = spec.guide_source
    if guide is not None:
        shot.inputs.append(ShotInput("guide", "video", folder / guide_name(guide), f"{GUIDE_WHAT[guide]}, {shot.length:.2f} s"))
    for owner in sorted(needs):
        sheet = sheets.get(owner)
        if sheet is not None and sheet.problem():
            shot.blocked.append(sheet.problem() or "")
    made_here = [i for i in shot.inputs if i.path.is_relative_to(project.root / INPUTS_DIR)]
    if any(not i.ready for i in made_here):
        shot.blocked.append(f"inputs not made yet: `{inputs_command(project, bool(guide) or source == 'render')}`")
    if shot.shared:
        settings = project.config.videogen
        if settings.inline_media == "all" and settings.host != "quick_tunnel":
            shot.problems.append(f"{where}: {INLINE_AUDIO_VIDEO_PROBLEM}")
        elif settings.provider == MOCK_PROVIDER:
            shot.fake_addresses = True
        elif settings.host == "quick_tunnel":
            from vidgen.videogen.host import HostSettings, find_cloudflared

            shot.share_minutes = settings.host_max_minutes
            try:
                find_cloudflared(settings.cloudflared)
            except VidgenError as exc:
                shot.blocked.append(str(exc))
            lifetime = HostSettings.from_config(settings).lifetime_problem(settings.poll_timeout)
            if lifetime:
                shot.blocked.append(lifetime)
        else:
            shot.blocked.append(NO_HOST_BLOCKED)


def _check_sound(shot: Shot) -> None:
    """Fill the blocked reason or notes of a ``sound: model`` shot (:attr:`Shot.sound`) from its model's capability."""
    if shot.sound != "model" or shot.model is None:
        return
    model = shot.model
    if model.generate_audio is False:
        shot.blocked.append(
            f"sound: model, but {model.id} cannot make sound (the model list says generate_audio false): "
            "set sound: mix, or pick a model that can (`vidgen generate models --json`)"
        )
    elif model.generate_audio is None:
        shot.notes.append(f"{model.id} does not say whether it can make sound: generate_audio true is sent; the take may have no sound of its own")
    if shot.spec.place:
        shot.notes.append("sound: model: a placed take plays vidgen's mix, not the clip's sound; to hear the clip's sound use place: false and a video_clip scene")


def _windows(project: Project, scene: SceneConfig, fps: int) -> list[float]:
    """Each beat's window (seconds from its start to the next beat's start, whole frames)."""
    from vidgen.overlap import beat_lines, beat_windows
    from vidgen.videoplan import beat_seconds

    lines = beat_lines(project, scene.beats, lambda b: beat_seconds(project, b.id, b.text))
    return [round(w.window * fps) / fps for w in beat_windows(lines, project.config.narration.pad, fps)]


def project_shots(project: Project, catalog: Catalog | None) -> list[Shot]:
    """Every generated shot of ``project`` in video order. ``catalog``: the video model list
    (``None``: models are not checked; no lengths, no prices)."""
    from vidgen import extensions, registry
    from vidgen.videoplan import VideoPlan

    config = project.config
    fps = config.format.fps
    names = [e.name for e in config.characters]
    sheets: dict[str, Sheet | None] = {name: character_sheet(project, name) for name in names}
    if config.style_sheet is not None:
        sheets[STYLE] = style_sheet(project)
    shots: list[Shot] = []
    # scene lengths need the scene types (their fade-out); inside a session they are registered
    registered = all(registry.find(spec.type) is not None for spec in config.scenes)
    with nullcontext() if registered else extensions.project_session(project):
        plan = VideoPlan(project, fps)
        for i, scene in enumerate(config.scenes):
            if not any(b.generated_shot is not None for b in scene.beats):
                continue
            slot = plan.scene(scene.id)
            windows = _windows(project, scene, fps)
            for j, (beat, beat_slot, window) in enumerate(zip(scene.beats, slot.beats, windows)):
                if beat.generated_shot is not None:
                    found = _beat_shots(project, scene, beat, f"scenes[{i}].beats[{j}].generated_shot", slot.start + beat_slot.start, window, catalog, sheets)
                    for shot in found:
                        shot.scene_start, shot.scene_end = slot.start, slot.start + slot.duration
                    shots += found
    return shots


def _beat_shots(
    project: Project, scene: SceneConfig, beat: BeatConfig, where: str, start: float, window: float,
    catalog: Catalog | None, sheets: dict[str, Sheet | None],
) -> list[Shot]:
    spec = beat.generated_shot
    assert spec is not None
    config = project.config
    problems: list[str] = []
    model = None
    if catalog is not None:
        try:
            model = catalog.find(spec.model)
        except VidgenError as exc:
            problems.append(f"{where}.model: {exc}")
    names = [e.name for e in config.characters]
    speaker = _speaker(config, scene, beat)
    for name in spec.characters or []:
        if name not in names:
            problems.append(f"{where}.characters: unknown character {name!r}{did_you_mean(name, names)}; characters: {', '.join(names) or 'none'}")
    chosen = [n for n in spec.characters if n in names] if spec.characters is not None else ([speaker] if speaker and spec.kind != "establishing" else [])
    if spec.kind == "talking" and spec.characters:
        speaker = chosen[0] if chosen else speaker
    parts = 1
    if model is not None and model.durations:
        parts = max(1, math.ceil(window / max(model.durations) - 1e-9))
    length = window / parts
    shots = []
    for k in range(parts):
        shot = Shot(
            id=beat.id if parts == 1 else f"{beat.id}_p{k + 1}", scene_id=scene.id, beat=beat, spec=spec, location=where,
            start=start + k * length, offset=k * length, length=length, part=k + 1, parts=parts, speaker=speaker,
            characters=chosen, model=model, problems=list(problems), sound=config.videogen.sound_for(spec.model, spec.sound),
        )
        if model is not None:
            shot.duration = snap_duration(length, model.durations) if model.durations else None
            shot.resolution = spec.resolution or lowest_resolution(model)
            shot.aspect_ratio = spec.aspect_ratio or pick_aspect(config, model)
            if parts > 1 and k == 0:
                shot.notes.append(f"the beat ({window:.2f} s) is longer than {model.id}'s longest clip ({max(model.durations or [0])} s): split into {parts} parts")
        _resolve_inputs(project, shot, sheets)
        _check_sound(shot)
        shot.prompt = shot_prompt(project, shot, sheets)
        if spec.guide_source is not None:
            earlier = _prompt_text(project, shot, sheets, guided=False)
            shot.earlier_prompt = earlier if earlier != shot.prompt else ""
            shot.notes += _left_out_notes(shot, sheets)
        shots.append(shot)
    return shots


def shot_problems(project: Project) -> list[tuple[str, str]]:
    """Config errors of the project's generated shots for ``vidgen validate`` (models are not
    looked up: ``vidgen generate plan`` checks them): unknown characters and pictures, a talking
    shot without a speaker or portrait. ``(location, message)`` pairs."""
    if not any(b.generated_shot is not None for s in project.config.scenes for b in s.beats):
        return []
    out = []
    seen = set()
    for shot in project_shots(project, None):
        for problem in shot.problems:
            if problem not in seen:
                seen.add(problem)
                location, _, message = problem.partition(": ")
                out.append((location, message))
    return out


# ----- the plan ------------------------------------------------------------------------------------


@dataclass
class ShotPlan:
    """A shot as ``vidgen generate plan`` shows it: the request, the model's checks, the estimate,
    the cache / earlier job, the request's size and what the budget has left after it (in plan
    order)."""

    shot: Shot
    request: VideoRequest | None = None
    check: RequestCheck = field(default_factory=RequestCheck)
    estimate: Estimate | None = None
    cached: bool = False
    previous_job: str | None = None
    left_after: float | None = None
    over_budget: bool = False
    #: Bytes of the request body with its inline pictures (``None``: inputs not all made yet).
    request_bytes: int | None = None
    #: The shot's cut inputs no longer match what they were cut from and a run would pay for it
    #: (the same text is in ``shot.blocked``); ``run --pay`` refuses (nothing sent or paid).
    changed_inputs: str | None = None
    #: The ledger's unresolved submit intent of this request (``shot.blocked`` says what to do):
    #: ``run --pay`` refuses, and the plan counts no new cost for the shot.
    unresolved_intent: SubmitIntent | None = None

    @property
    def cost(self) -> float:
        """What the shot would cost now (0 when cached or already paid; unknown counts 0)."""
        if self.cached or self.previous_job or self.unresolved_intent or self.estimate is None or self.estimate.cost is None:
            return 0.0
        return self.estimate.cost

    def lines(self, root: Path) -> list[str]:
        """The shot's lines of the plan."""
        shot, spec = self.shot, self.shot.spec
        end = shot.start + shot.length
        part = f", part {shot.part} of {shot.parts}" if shot.parts > 1 else ""
        r = self.request
        what = [spec.model, r.resolution if r else None, r.aspect_ratio if r else None]
        lines = [f"shot {shot.id} ({spec.kind}, scene {shot.scene_id}, beat {shot.beat.id}{part}, {_clock(shot.start)}-{_clock(end)}, {shot.length:.2f} s): {', '.join(w for w in what if w)}"]
        if shot.model is not None:
            if shot.duration is None:
                lines.append(f"  length: follows the audio ({shot.length:.2f} s; {shot.model.id} takes no duration), priced as {shot.priced_seconds:g} s")
            else:
                trim = shot.duration - shot.length
                lines.append(f"  length: asks for {shot.duration} s, trimmed to {shot.length:.2f} s later" if trim > 1e-6 else f"  length: {shot.duration} s")
        lines.append(f"  sound: {shot.sound} ({SOUND_WHAT[shot.sound]})")
        for item in shot.inputs:
            role = item.role + (" (frame image)" if item.frame else " (reference)" if item.role in ("portrait", "first_frame") else "")
            lines.append(f"  {role}: {_shown(item.path, root)} ({item.what}{'' if item.ready else '; not made yet'})")
        if shot.fake_addresses and not self.cached and not self.previous_job:
            lines.append("  mock provider: these inputs stay on this machine (fake addresses; nothing is shared)")
        if shot.share_minutes is not None and not self.cached and not self.previous_job:
            lines.append(
                f"  would share through a public Cloudflare quick tunnel, only while this shot's job runs (at most {shot.share_minutes:g} min; "
                "copies under random names behind a secret path; pictures are not shared, they go inline):"
            )
            lines += [f"    {_shown(i.path, root)} ({share_size(i)})" for i in shot.shared]
        if self.cached:
            lines.append("  cached: the clip is already made (nothing to pay)")
        if self.previous_job:
            lines.append(f"  job {self.previous_job} of this request was paid already: a run downloads it (not paid again)")
        if self.request_bytes is not None:
            from vidgen.videogen.openrouter import MAX_INLINE_BYTES

            lines.append(f"  request: {self.request_bytes / 1e6:.1f} MB with its inline pictures (vidgen sends at most {MAX_INLINE_BYTES / 1e6:.0f} MB)")
        if self.estimate is not None:
            cost = money(self.estimate.cost) if self.estimate.cost is not None else "unknown"
            lines.append(f"  estimate: {cost} ({self.estimate.basis})")
        if self.left_after is not None:
            lines.append(f"  budget left after this shot: {money(self.left_after)}" + (" (over the budget: refused)" if self.over_budget else ""))
        lines += [f"  note: {n}" for n in [*shot.notes, *self.check.notes]]
        lines += [f"  problem: {p}" for p in [*shot.problems, *self.check.problems]]
        lines += [f"  blocked: {b}" for b in shot.blocked]
        lines.append(f"  prompt: {shot.prompt}")
        return lines


def _shown(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def share_size(item: ShotInput) -> str:
    """The size of a shared input as the plan prints it (``not made yet`` while missing)."""
    if not item.ready:
        return "not made yet"
    size = item.path.stat().st_size
    return f"{size / 1e6:.2f} MB" if size >= 100_000 else f"{size:,} bytes"


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:05.2f}"


@dataclass
class VideoGenPlan:
    """The whole dry run: every shot, the sheets' pictures still to make, the budget."""

    shots: list[ShotPlan]
    budget: BudgetState
    sheets_cost: float = 0.0
    sheets_todo: int = 0
    sheets_unknown: int = 0
    sheet_lines: list[str] = field(default_factory=list)
    #: Ledger intents with no known outcome (of any request); they count in the budget at their estimate.
    unresolved_intents: list[SubmitIntent] = field(default_factory=list)
    #: Entries of the config that have no effect (a ``videogen.models`` id OpenRouter does not list).
    warnings: list[str] = field(default_factory=list)

    @property
    def clips_cost(self) -> float:
        """Estimated US dollars of the clips still to pay for."""
        return sum(s.cost for s in self.shots)

    @property
    def total(self) -> float:
        """Clips and sheet pictures."""
        return self.clips_cost + self.sheets_cost

    def lines(self, root: Path) -> list[str]:
        """The text of ``vidgen generate plan``."""
        out: list[str] = []
        for shot in self.shots:
            out += shot.lines(root)
        if not self.shots:
            out.append("no generated shots (add generated_shot: to a beat)")
        out += self.sheet_lines
        unknown = sum(1 for s in self.shots if s.estimate is None or s.estimate.cost is None)
        extra = f" (+ {unknown} of unknown price)" if unknown else ""
        sheets = f"; sheets: {self.sheets_todo} picture(s), estimated {money(self.sheets_cost)}" + (f" (+ {self.sheets_unknown} of unknown price)" if self.sheets_unknown else "")
        out.append(f"total: {len(self.shots)} shot(s), clips estimated {money(self.clips_cost)}{extra}{sheets}; together {money(self.total)}")
        left = self.budget.remaining_usd
        after = f", {money(max(0.0, left - self.total))} after this plan" if left is not None else ""
        out.append(f"{self.budget.text()}{after}" + (" - OVER THE BUDGET" if left is not None and self.total > left + 1e-9 else ""))
        out += [f"unresolved submit: {intent_text(i)}" for i in self.unresolved_intents]
        out += [f"warning: {w}" for w in self.warnings]
        blocked = sum(1 for s in self.shots if s.shot.blocked)
        problems = sum(1 for s in self.shots if s.shot.problems or s.check.problems)
        out.append(f"dry run: nothing was sent or paid; {blocked} shot(s) blocked, {problems} with problems")
        return out


def _unlisted_models(models: Iterable[str], catalog: Catalog) -> list[str]:
    """A warning for each ``videogen.models`` id the model list does not have (a typo has no effect)."""
    known = [m.id for m in catalog.models]
    return [f"videogen.models: OpenRouter lists no video model {m!r}{did_you_mean(m, known)}: its entry has no effect" for m in models if m not in known]


def plan_shots(
    project: Project, *, catalog: Catalog | None = None, budget_usd: float | None = None, shot_ids: Sequence[str] = (),
    lookup: object = None,
) -> VideoGenPlan:
    """The dry run of every generated shot (``shot_ids``: only those; an unknown one is an error
    with a did-you-mean) and of the sheet pictures still to make. Free: the public model lists
    may be fetched (``catalog`` / ``lookup`` replace them in tests); nothing is sent or paid. The
    only files written are the smaller copies of ready shots' pictures in ``build/videogen/pictures/``."""
    from vidgen.videogen.freshness import InputSources
    from vidgen.videogen.models import load_catalog
    from vidgen.videogen.openrouter import MAX_INLINE_BYTES, request_bytes
    from vidgen.videogen.run import _cap, ledger_path, plan_clip

    settings = project.config.videogen
    catalog = catalog if catalog is not None else load_catalog()
    shots = project_shots(project, catalog)
    if shot_ids:
        known = [s.id for s in shots]
        for wanted in shot_ids:
            if wanted not in known and not any(s.beat.id == wanted for s in shots):
                raise VidgenError(f"no generated shot {wanted!r}{did_you_mean(wanted, known)}; shots: {', '.join(known) or 'none'}")
        shots = [s for s in shots if s.id in shot_ids or s.beat.id in shot_ids]
    ledger = Ledger(ledger_path(project.root, settings.provider))
    budget = BudgetState(_cap(settings, budget_usd), ledger.spent())
    sheets = plan_sheets(project, lookup=lookup, ledger=ledger)  # type: ignore[arg-type]
    sheet_cost, sheet_unknown = sheets.cost
    from vidgen.videogen.sheets import sheet_lines

    plan = VideoGenPlan(
        [], budget, sheet_cost, len(sheets.plan.todo), sheet_unknown, sheet_lines(sheets, project.root, prompts=False)[:-1] if sheets.sheets else [],
        ledger.unresolved_intents(), _unlisted_models(settings.models, catalog),
    )
    left = budget.remaining_usd - sheet_cost if budget.remaining_usd is not None else None
    sources = InputSources(project)
    for shot in shots:
        item = ShotPlan(shot, shot.request())
        if item.request is not None and shot.model is not None:
            if all(i.ready for i in shot.inputs):
                clip = plan_clip(project.root, settings, item.request, catalog=catalog, budget_usd=budget_usd, duration=shot.priced_seconds)
                item.cached = clip.cached
                item.previous_job = clip.previous_job.job_id if clip.previous_job is not None else None
                item.unresolved_intent = clip.unresolved_intent
                if clip.unresolved_intent is not None:
                    shot.blocked.append(intent_refusal(clip.unresolved_intent))
                elif not clip.cached and clip.previous_job is None and _paid_under_earlier_wording(project.root, ledger, shot, item.request):
                    shot.blocked.append(EARLIER_WORDING_BLOCKED)
                item.check = clip.check
                item.estimate = clip.estimate or estimate(item.request, shot.model, duration=shot.priced_seconds)
                if not clip.cached:
                    item.request_bytes = request_bytes(item.request, project.root)
                    if item.request_bytes > MAX_INLINE_BYTES:
                        shot.problems.append(
                            f"{shot.location}: the request is {item.request_bytes / 1e6:.1f} MB with its inline pictures, more than vidgen "
                            f"sends ({MAX_INLINE_BYTES / 1e6:.0f} MB): use fewer or smaller pictures (refs:)"
                        )
            else:
                item.check = check_request(item.request, shot.model)
                item.estimate = estimate(item.request, shot.model, duration=shot.priced_seconds)
        stale = sources.stale(shot)
        if stale is not None and (item.cached or item.previous_job):
            shot.notes.append(stale.reuse_note)
        elif stale is not None:
            item.changed_inputs = stale.blocked
            shot.blocked.append(stale.blocked)
        if left is not None:
            left -= item.cost
            item.left_after = max(0.0, left)
            item.over_budget = left < -1e-9
        plan.shots.append(item)
    return plan


__all__ = [
    "EARLIER_WORDING_BLOCKED", "GUIDED_TALKING_FRAMING", "GUIDE_PROMPTS", "INPUTS_DIR", "NO_HOST_BLOCKED", "Shot", "ShotInput", "ShotPlan", "VideoGenPlan", "lowest_resolution", "guide_name", "inputs_command", "pick_aspect", "plan_shots", "project_shots",
    "shot_problems", "shot_prompt", "video_ratio", "without_framing",
]

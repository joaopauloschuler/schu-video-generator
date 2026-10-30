"""'Ask an agent' (DESIGN.md §94.16): a person's listening notes handed to an AI agent, whose
answer — a whole new score and one line per note on what it changed and why — comes back as a
**proposal**: a new version (``origin: agent``, never the current one until the person keeps
it) to A/B against the version it was made from.

schu-video-generator has no LLM of its own. A hand-off (``request.json`` in the session folder: the score,
the open notes, the last check, what changed since the parent version, the instruction) is
answered in one of three ways, all ending in :func:`make_proposal` (validated like every
version; an invalid one is shown with its problems and can never be kept):

- an agent connected through ``vidgen mcp`` reads the session (``studio_read``) and writes a
  proposal file into the session's ``inbox/`` (``studio_propose``); the running studio turns it
  into a proposal when the page polls (:func:`ingest_inbox`);
- the person copies the prompt into any chat assistant and pastes the reply
  (:func:`parse_reply`);
- optionally OpenRouter, the LLM provider schu-video-generator already uses, with ``OPENROUTER_API_KEY`` from
  the environment, as the image and TTS providers read it (:func:`ask_openrouter`).

The second half of the module is what the MCP tools call (:func:`agent_sessions`,
:func:`agent_read`, :func:`agent_propose`): through files on disk only, so no port or token
has to be discovered and a proposal made while the studio is closed is picked up when it opens.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import secrets
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError
from vidgen.fileio import remove_file, write_text_atomic
from vidgen.studio_app.notes import NOTE_ID, NoteBook
from vidgen.studio_app.session import OPEN_FILE, SESSION_ID, StudioSession, list_sessions, normal_text, studio_dir

#: ``request.json`` / ``proposals.json`` / inbox files' ``format``.
AGENT_FORMAT = 1
#: The hand-off of the last "Ask an agent", in the session folder.
REQUEST_FILE = "request.json"
#: Proposals made in the session (valid ones are versions too).
PROPOSALS_FILE = "proposals.json"
#: Where MCP agents put proposals for the studio to pick up.
INBOX = "inbox"
#: An inbox file's name (written by :func:`agent_propose`).
INBOX_NAME = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}\.json\Z")
#: The longest score text a proposal may carry (characters).
MAX_SCORE_CHARS = 200_000
#: The longest explanation of one note / summary (characters).
MAX_EXPLANATION_CHARS = 600
MAX_SUMMARY_CHARS = 80
#: Lines of the parent → base diff put in a hand-off.
MAX_DIFF_LINES = 80
#: The OpenRouter model used when none is named on the page (none: the person names one).
MODEL_ENV = "VIDGEN_STUDIO_MODEL"
#: Seconds an OpenRouter answer may take.
PROVIDER_TIMEOUT = 180.0

INSTRUCTION = (
    "A person is shaping a piece of music written as a vidgen score file (YAML). They listened to it and pinned "
    "notes at moments of the piece (bar, beat, section). For each open note, change the score to address it: "
    "one focused change per note when you can, in the section and bar the note names. Keep everything else as "
    "it is, comments included. Write one line per note explaining what you changed and why (or why you changed "
    "nothing). Return the FULL score, not a diff. The check report says how the piece sits under narration: do "
    "not make it worse. The instruments and effects are in `vidgen music patches` (MCP: music_patches)."
)
REPLY_FORMAT = (
    "Reply with: a first line `summary: <a few words naming the change>`; the full score in one ```yaml code "
    "block; then one line per note, `n1: what you changed and why`."
)
MCP_STEPS = (
    "Answer through vidgen's MCP tools: studio_read (this) -> change the score -> studio_check with the new score "
    "(the check, as the person will see it) -> studio_propose(session, score, explanations={note id: one line}, "
    "summary). The proposal appears in the studio as a new version the person A/Bs and keeps or discards."
)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        raise VidgenError(f"cannot read {path}: {exc}") from None


# ----- the hand-off -------------------------------------------------------------------------


def diff_summary(session: StudioSession, version: int) -> dict[str, Any] | None:
    """What changed from version ``version``'s parent to it: ``{parent, version, label,
    changed_lines, diff}`` (a unified diff, at most :data:`MAX_DIFF_LINES` lines), or ``None``
    for the first version."""
    entry = next(v for v in session.versions if v.number == version)
    if entry.parent is None:
        return None
    before, after = session.text(entry.parent), session.text(version)
    lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(), f"v{entry.parent}", f"v{version}", lineterm="", n=1))
    changed = sum(1 for line in lines if line[:1] in "+-" and not line.startswith(("+++", "---")))
    cut = len(lines) > MAX_DIFF_LINES
    text = "\n".join(lines[:MAX_DIFF_LINES]) + ("\n... (cut)" if cut else "")
    return {"parent": entry.parent, "version": version, "label": entry.label, "changed_lines": changed, "diff": text}


def check_summary(doc: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The parts of a kept check (``checks/<key>.json``) an agent needs: verdict, level, the
    headline numbers, the findings with their advice, and the report in words."""
    if doc is None:
        return None
    return {
        "verdict": doc.get("verdict"),
        "level": doc.get("level"),
        "headline": [{k: h.get(k) for k in ("name", "value", "level")} for h in doc.get("headline", [])],
        "findings": [{k: f.get(k) for k in ("topic", "level", "text", "fixes")} for f in doc.get("findings", [])],
        "text": doc.get("text"),
    }


def note_for_agent(note: Mapping[str, Any]) -> dict[str, Any]:
    """A note as an agent reads it: id, words, where it is in the version handed off."""
    at = note["at"]
    out = {"id": note["id"], "text": note["text"], "bar": at["bar"], "beat": at["beat"], "section": at["section"],
           "seconds": at["seconds"], "made_on": f"v{note['version']}"}
    if at.get("moved"):
        out["moved"] = at["moved"]
    return out


def handoff(session: StudioSession, version: int, notes: Sequence[Mapping[str, Any]], check: Mapping[str, Any] | None) -> dict[str, Any]:
    """The hand-off of version ``version`` with its open ``notes`` (placed in it, as
    :meth:`NoteBook.shown` gives them) and its kept ``check`` (or ``None``)."""
    open_notes = [note_for_agent(n) for n in notes if n["status"] == "open"]
    return {
        "format": AGENT_FORMAT,
        "id": f"r{time.strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2)}",
        "created": _now(),
        "session": session.id,
        "title": session.data.get("title"),
        "base": version,
        "score": session.text(version),
        "notes": open_notes,
        "check": check_summary(check),
        "diff": diff_summary(session, version),
        "instruction": INSTRUCTION,
        "reply_format": REPLY_FORMAT,
    }


def prompt_text(request: Mapping[str, Any]) -> str:
    """The hand-off as one text to paste into any chat assistant (or send to a provider)."""
    out = [f"# Music to change: {request.get('title') or 'a piece'} (version v{request['base']})", "", request["instruction"], "",
           request["reply_format"], "", "## Notes"]
    if request["notes"]:
        for n in request["notes"]:
            moved = f" ({n['moved']})" if n.get("moved") else ""
            out.append(f"- {n['id']}: bar {n['bar']}, beat {n['beat']}, in the {n['section']} ({n['seconds']:.1f} s){moved}: \"{n['text']}\"")
    else:
        out.append("(no open notes: improve what the check report asks for, one thing)")
    out += ["", "## The score", "", "```yaml", request["score"].rstrip("\n"), "```", ""]
    check = request.get("check")
    out.append("## The check report (vidgen music check: how it sits under narration)")
    out += ["", "```text", (check.get("text") or "").rstrip("\n"), "```", ""] if check else ["", "(not checked yet)", ""]
    diff = request.get("diff")
    if diff:
        out += [f"## What changed from v{diff['parent']} to v{diff['version']} ({diff['label']})", "", "```diff", diff["diff"], "```", ""]
    return "\n".join(out)


def write_request(session: StudioSession, request: Mapping[str, Any]) -> None:
    write_text_atomic(session.folder / REQUEST_FILE, json.dumps(request, indent=2, ensure_ascii=False) + "\n")


def read_request(folder: Path) -> dict[str, Any] | None:
    doc = _read_json(folder / REQUEST_FILE, None)
    return doc if isinstance(doc, dict) else None


# ----- replies ------------------------------------------------------------------------------

_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[^\n]*\n(.*?)```", re.S)
_EXPLAIN = re.compile(r"^[ \t]*(?:[-*•][ \t]*)?(?:\*\*|`)?(n\d{1,5})(?:\*\*|`)?[ \t]*(?:\*\*)?[ \t]*[:.)\-–—][ \t]*(.+?)[ \t]*$", re.M)
_SUMMARY = re.compile(r"^[ \t]*(?:\*\*)?summary(?:\*\*)?[ \t]*:[ \t]*(.+?)[ \t]*$", re.M | re.I)


def parse_reply(text: str) -> dict[str, Any]:
    """An agent's reply as text (pasted, or a provider's answer): ``{score, explanations,
    summary}`` — the score from its ```yaml block (else the largest code block, else the whole
    text when it reads as a score), the ``n1: ...`` lines and the ``summary:`` line outside it.
    ``score`` is ``None`` when no score is found."""
    import yaml

    blocks = [(m.group(1).lower(), m.group(2), m.span()) for m in _FENCE.finditer(text)]
    chosen = next((b for b in blocks if b[0] in ("yaml", "yml")), None) or max(blocks, key=lambda b: len(b[1]), default=None)
    if chosen is not None:
        score, (a, b) = chosen[1], chosen[2]
        rest = text[:a] + "\n" + text[b:]
    else:
        score, rest = None, text
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            data = None
        if isinstance(data, dict) and "tracks" in data:
            score, rest = text, ""
    explanations: dict[str, str] = {}
    for m in _EXPLAIN.finditer(rest):
        explanations.setdefault(m.group(1), m.group(2).strip().strip("*").strip())
    summary = _SUMMARY.search(rest)
    return {"score": score, "explanations": explanations, "summary": summary.group(1).strip("*` ") if summary else None}


def clean_explanations(explanations: Any) -> dict[str, str]:
    """``{note id: one line}`` checked: ids like ``n3``, lines of text (folded, cut)."""
    if explanations is None:
        return {}
    if not isinstance(explanations, Mapping):
        raise VidgenError("explanations: a mapping of note id (n1, n2...) to one line")
    out = {}
    for key, value in explanations.items():
        if not isinstance(key, str) or not NOTE_ID.match(key):
            raise VidgenError(f"explanations: {key!r} is not a note id (n1, n2...)")
        if not isinstance(value, str) or not value.strip():
            raise VidgenError(f"explanations.{key}: one line of text")
        line = " ".join(value.split())
        out[key] = line if len(line) <= MAX_EXPLANATION_CHARS else line[: MAX_EXPLANATION_CHARS - 1] + "…"
    return out


def clean_summary(summary: Any) -> str | None:
    if summary is None:
        return None
    if not isinstance(summary, str):
        raise VidgenError("summary: a few words")
    line = " ".join(summary.split())
    return (line if len(line) <= MAX_SUMMARY_CHARS else line[: MAX_SUMMARY_CHARS - 1] + "…") or None


# ----- proposals ----------------------------------------------------------------------------


class Proposals:
    """A session's ``proposals.json``: every proposal made, ``{id, status, source, agent,
    summary, base, version, explanations, unknown_notes, problems, created, request}`` —
    ``status`` ``pending`` (a version to listen to), ``kept``, ``discarded`` or ``invalid`` (its
    problems; no version, it can never be kept)."""

    def __init__(self, folder: Path) -> None:
        self.path = folder / PROPOSALS_FILE
        doc = _read_json(self.path, {})
        self.items: list[dict[str, Any]] = list(doc.get("proposals", []))
        self.next = int(doc.get("next", 1))

    def save(self) -> None:
        doc = {"format": AGENT_FORMAT, "next": self.next, "proposals": self.items}
        write_text_atomic(self.path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")

    def get(self, proposal_id: str) -> dict[str, Any]:
        found = next((p for p in self.items if p["id"] == proposal_id), None)
        if found is None:
            raise VidgenError(f"no proposal {proposal_id!r} in this session")
        return found

    def new_id(self) -> str:
        pid = f"p{self.next}"
        self.next += 1
        return pid


def make_proposal(session: StudioSession, notes: NoteBook, proposals: Proposals, text: Any, explanations: Any = None,
                  summary: Any = None, agent: str | None = None, source: str = "paste", base: int | None = None,
                  request: str | None = None) -> dict[str, Any]:
    """Turn an answer into a proposal. A valid score different from its base becomes a new
    version (``origin: agent``, parent ``base``, labelled ``agent: <summary>``) that is **not**
    the current one, and each explanation is attached to its note; anything else is kept as an
    ``invalid`` proposal with its problems (shown, never a version). Saves notes and proposals."""
    from vidgen.studio_app.app import check_text

    base = base if base is not None else session.current
    assert base is not None
    session.text(base)  # the base must exist
    explanations = clean_explanations(explanations)
    summary = clean_summary(summary)
    agent = " ".join(str(agent).split())[:40] if agent else None
    known = {n["id"] for n in notes.notes}
    proposal: dict[str, Any] = {
        "id": proposals.new_id(), "status": "pending", "source": source, "agent": agent, "summary": summary, "base": base,
        "version": None, "explanations": explanations, "unknown_notes": sorted(set(explanations) - known), "problems": [],
        "created": _now(), "request": request,
    }
    if not isinstance(text, str) or not text.strip():
        proposal.update(status="invalid", problems=[{"where": "", "message": "the answer holds no score (a ```yaml block with the whole score)", "line": None}])
    elif len(text) > MAX_SCORE_CHARS:
        proposal.update(status="invalid", problems=[{"where": "", "message": f"the score is longer than {MAX_SCORE_CHARS} characters", "line": None}])
    else:
        text = normal_text(text)
        text = text if text.endswith("\n") else text + "\n"
        _, score, problems = check_text(text)
        if score is None:
            proposal.update(status="invalid", problems=problems, text=text)
        elif text == session.text(base):
            proposal.update(status="invalid", problems=[{"where": "", "message": f"the score is the same as v{base}: nothing changed", "line": None}])
        else:
            who = summary or (f"{agent}'s changes" if agent else "changes for the notes")
            version = session.add_version(text, "agent", f"agent: {who}"[:120], base, current=False)
            proposal["version"] = version.number
            for note_id, line in explanations.items():
                if note_id in known:
                    notes.answer(note_id, {"proposal": proposal["id"], "version": version.number, "by": agent or source, "text": line, "status": "pending"})
    proposals.items.append(proposal)
    proposals.save()
    notes.save()
    session.touch()
    return proposal


def ingest_inbox(session: StudioSession, notes: NoteBook, proposals: Proposals) -> list[dict[str, Any]]:
    """Turn the proposal files MCP agents wrote into ``inbox/`` into proposals (oldest first);
    each file is removed once it is recorded. A file that cannot be read becomes an invalid
    proposal saying so."""
    folder = session.folder / INBOX
    if not folder.is_dir():
        return []
    made = []
    for path in sorted(p for p in folder.iterdir() if INBOX_NAME.match(p.name)):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(doc, dict):
                raise ValueError("not a JSON object")
            base = doc.get("base")
            if not isinstance(base, int) or isinstance(base, bool) or not any(v.number == base for v in session.versions):
                base = session.current
            made.append(make_proposal(session, notes, proposals, doc.get("score"), doc.get("explanations"), doc.get("summary"),
                                      doc.get("agent"), "mcp", base, doc.get("request") if isinstance(doc.get("request"), str) else None))
        except (OSError, ValueError, VidgenError) as exc:
            bad = {"id": proposals.new_id(), "status": "invalid", "source": "mcp", "agent": None, "summary": None, "base": session.current,
                   "version": None, "explanations": {}, "unknown_notes": [], "created": _now(), "request": None,
                   "problems": [{"where": "", "message": f"the proposal file {path.name} could not be read: {exc}", "line": None}]}
            proposals.items.append(bad)
            proposals.save()
            session.touch()
            made.append(bad)
        remove_file(path)
    return made


def decide(session: StudioSession, notes: NoteBook, proposals: Proposals, proposal_id: str, keep: bool) -> dict[str, Any]:
    """Keep a pending proposal (its version becomes the current one; the notes it explained are
    resolved) or discard it (its version stays in the history, named as discarded). An invalid
    proposal can only be discarded."""
    proposal = proposals.get(proposal_id)
    if proposal["status"] not in ("pending", "invalid"):
        raise VidgenError(f"proposal {proposal_id} was already {proposal['status']}")
    if keep and proposal["status"] == "invalid":
        raise VidgenError(f"proposal {proposal_id} has problems: it cannot be kept")
    proposal["status"] = "kept" if keep else "discarded"
    if proposal["version"] is not None:
        if keep:
            session.set_current(proposal["version"])
            for note_id in proposal["explanations"]:
                if any(n["id"] == note_id for n in notes.notes):
                    notes.get(note_id)["status"] = "resolved"
        else:
            entry = next(v for v in session.versions if v.number == proposal["version"])
            session.update_version(entry.number, label=f"discarded · {entry.label}"[:120])
        notes.set_answers(proposal_id, proposal["status"])
    proposals.save()
    notes.save()
    session.touch()
    return proposal


# ----- the optional provider: OpenRouter ----------------------------------------------------


def provider_info() -> dict[str, Any]:
    """Whether "Send to OpenRouter" can be offered: the key's presence (never its value) and the
    model from :data:`MODEL_ENV`."""
    from vidgen.imagegen.openrouter import API_KEY_ENV

    return {"name": "OpenRouter", "key_env": API_KEY_ENV, "key_set": bool(os.environ.get(API_KEY_ENV, "").strip()),
            "model": os.environ.get(MODEL_ENV, "").strip() or None, "model_env": MODEL_ENV}


def ask_openrouter(prompt: str, model: str) -> str:
    """Send ``prompt`` to OpenRouter's chat completions with ``model``; the answer's text. The
    key is read from the environment now (never stored, scrubbed from errors). Costs money."""
    from vidgen import httpapi
    from vidgen.imagegen.openrouter import API_BASE, APP_HEADERS, SERVICE, TRANSIENT_STATUS, read_api_key

    model = (model or "").strip()
    if not model or any(c.isspace() for c in model):
        raise VidgenError(f"name an OpenRouter model (e.g. vendor/model), or set {MODEL_ENV}")
    key = read_api_key("studio")
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json", **APP_HEADERS}
    raw = httpapi.post_with_retries(
        f"{API_BASE}/chat/completions", json.dumps(body).encode("utf-8"), headers=headers, service=SERVICE, secret=key,
        timeout=PROVIDER_TIMEOUT, retries=2, backoff=2.0, max_wait=30.0, sleep=time.sleep,
        transient=lambda status, _body: status in TRANSIENT_STATUS,
    )
    try:
        doc = json.loads(raw.decode("utf-8"))
        content = doc["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise VidgenError(f"{SERVICE} answered something that is not a chat reply") from None
    if isinstance(content, list):  # content parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not isinstance(content, str) or not content.strip():
        raise VidgenError(f"{SERVICE} sent an empty reply")
    return content


# ----- what the MCP tools call (through the disk) -------------------------------------------


def studio_folders(root: Path) -> list[Path]:
    """The studio folders an agent working in ``root`` may use: the root's ``build/studio``,
    each folder's directly under the root, and the studio folder of vidgen's cache (sessions
    of a studio started without a project) — those that exist."""
    found = [root / "build" / "studio"]
    try:
        found += [p / "build" / "studio" for p in sorted(root.iterdir()) if p.is_dir() and not p.name.startswith(".")]
    except OSError:
        pass
    inside = root.resolve()
    found = [f for f in found if f.resolve().is_relative_to(inside)]  # a link out of the root is not followed
    found.append(studio_dir(None))
    out: list[Path] = []
    for folder in found:
        if (folder / "sessions").is_dir() and folder.resolve() not in [f.resolve() for f in out]:
            out.append(folder)
    return out


def _open_marker(folder: Path) -> dict[str, Any] | None:
    doc = _read_json(folder / OPEN_FILE, None) if (folder / OPEN_FILE).is_file() else None
    return doc if isinstance(doc, dict) else None


def agent_sessions(root: Path) -> dict[str, Any]:
    """The studio sessions an agent can answer, newest first: id, title, folder, versions,
    current, open notes, a pending hand-off, pending proposals, ``open`` (the session a running
    studio has open, with its address)."""
    sessions = []
    for folder in studio_folders(root):
        marker = _open_marker(folder)
        for s in list_sessions(folder, limit=20):
            path = folder / "sessions" / s["id"]
            data = _read_json(path / "session.json", {})
            notes = NoteBook(path)
            request = read_request(path)
            proposals = Proposals(path)
            answered = request is not None and any(p.get("request") == request["id"] for p in proposals.items)
            waiting = [p for p in (path / INBOX).glob("*.json") if INBOX_NAME.match(p.name)] if (path / INBOX).is_dir() else []
            is_open = bool(marker and marker.get("session") == s["id"])
            sessions.append({
                **s, "folder": str(path), "current": data.get("current"),
                "open_notes": len(notes.open_notes()),
                "request": {"id": request["id"], "base": request["base"], "created": request["created"], "answered": answered} if request else None,
                "pending_proposals": sum(1 for p in proposals.items if p["status"] == "pending") + len(waiting),
                "open": is_open,
                **({"url": marker.get("url")} if marker and is_open else {}),
            })
    opened = [s for s in sessions if s["open"]]
    rest = sorted((s for s in sessions if not s["open"]), key=lambda s: s["id"], reverse=True)
    return {"sessions": opened + rest, "folders": [str(f) for f in studio_folders(root)]}


def find_session(root: Path, session_id: str | None) -> StudioSession:
    """Session ``session_id`` in one of :func:`studio_folders`, or (no id) the one a running
    studio has open; :class:`VidgenError` saying what to do otherwise."""
    folders = studio_folders(root)
    if session_id is None:
        markers = [(m.get("started", ""), f, m) for f in folders if (m := _open_marker(f)) and m.get("session")]
        if not markers:
            raise VidgenError("no studio has a session open; give session= (studio_sessions lists them)")
        _, folder, marker = max(markers, key=lambda x: x[0])
        return _contained(StudioSession.open(folder, str(marker["session"])), folder)
    if not SESSION_ID.match(session_id):
        raise VidgenError(f"not a studio session id: {session_id!r} (studio_sessions lists them)")
    for folder in folders:
        if (folder / "sessions" / session_id / "session.json").is_file():
            return _contained(StudioSession.open(folder, session_id), folder)
    raise VidgenError(f"no studio session {session_id} (studio_sessions lists them)")


def _contained(session: StudioSession, studio: Path) -> StudioSession:
    """``session`` if its folder really is in ``studio``'s ``sessions/`` (a link to elsewhere is
    refused: an agent writes its proposals there)."""
    if not session.folder.resolve().is_relative_to((studio / "sessions").resolve()):
        raise VidgenError(f"studio session {session.id} is a link out of {studio}; not using it")
    return session


def _outline(text: str) -> dict[str, Any] | None:
    from vidgen.studio_app.app import check_text
    from vidgen.studio_app.song import describe_score

    data, score, _ = check_text(text)
    return describe_score(score, data) if score is not None else None


def agent_read(root: Path, session_id: str | None = None, version: int | None = None) -> dict[str, Any]:
    """What an agent needs to answer a session: the hand-off of the version asked for (default:
    the pending request's base, else the current version) — its score, the open notes placed in
    it, its kept check, the change from its parent, the instruction — and how to answer."""
    from vidgen.studio_app.app import check_text, render_key
    from vidgen.studio_app.checks import kept_check

    session = find_session(root, session_id)
    request = read_request(session.folder)
    proposals = Proposals(session.folder)
    pending = request if request is not None and not any(p.get("request") == request["id"] for p in proposals.items) else None
    base = version if version is not None else (pending["base"] if pending else session.current)
    assert base is not None
    text = session.text(base)
    outline = _outline(text)
    notes = NoteBook(session.folder).shown(outline)
    data, score, _ = check_text(text)
    check = None
    if score is not None:
        check = kept_check(session.folder / "checks", render_key(data))
    doc = handoff(session, base, notes, check)
    doc.pop("format")
    doc["id"] = pending["id"] if pending and pending["base"] == base else None
    doc["current"] = session.current
    doc["versions"] = [{"number": v.number, "parent": v.parent, "origin": v.origin, "label": v.label} for v in session.versions][-30:]
    doc["resolved_notes"] = len([n for n in notes if n["status"] != "open"])
    doc["how_to_answer"] = MCP_STEPS
    if check is None:
        doc["check_note"] = "no check kept for this version: studio_check checks a score as the studio would"
    return doc


def agent_propose(root: Path, score: str, explanations: Any = None, summary: Any = None, agent: str | None = None,
                  session_id: str | None = None, base: int | None = None, request: str | None = None) -> dict[str, Any]:
    """Validate an agent's proposal and write it into the session's ``inbox/`` for the studio to
    pick up: ``{session, base, file, explanations, missing_notes, unknown_notes, studio_open}``.
    A score with problems is refused here with them (nothing written), so the agent can fix it."""
    from vidgen.studio_app.app import check_text

    session = find_session(root, session_id)
    explanations = clean_explanations(explanations)
    summary = clean_summary(summary)
    if not isinstance(score, str) or not score.strip():
        raise VidgenError("score: the whole score file's text")
    if len(score) > MAX_SCORE_CHARS:
        raise VidgenError(f"score: at most {MAX_SCORE_CHARS} characters")
    _, parsed, problems = check_text(score)
    if parsed is None:
        lines = "\n".join(f"  - {p['where'] or 'score'}: {p['message']}" + (f" (line {p['line']})" if p.get("line") else "") for p in problems)
        raise VidgenError(f"the score has problems; nothing was proposed:\n{lines}")
    pending = read_request(session.folder)
    if base is None:
        base = pending["base"] if pending and (request is None or request == pending["id"]) else session.current
    assert base is not None
    session.text(base)
    if normal_text(score).rstrip("\n") == session.text(base).rstrip("\n"):
        raise VidgenError(f"the score is the same as v{base}: change it to answer the notes")
    open_ids = [n["id"] for n in NoteBook(session.folder).open_notes()]
    doc = {"format": AGENT_FORMAT, "created": _now(), "base": base, "score": score, "explanations": explanations, "summary": summary,
           "agent": " ".join(str(agent).split())[:40] if agent else None,
           "request": request or (pending["id"] if pending and pending["base"] == base else None)}
    name = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}.json"
    write_text_atomic(session.folder / INBOX / name, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    marker = _open_marker(session.folder.parent.parent)
    return {
        "session": session.id, "base": base, "file": str(session.folder / INBOX / name), "explanations": sorted(explanations),
        "missing_notes": [n for n in open_ids if n not in explanations], "unknown_notes": sorted(set(explanations) - set(open_ids)),
        "studio_open": bool(marker and marker.get("session") == session.id),
        "next": "the studio shows it as a new version to A/B; the person keeps or discards it"
        if marker and marker.get("session") == session.id else "the studio picks it up when this session is opened",
    }

"""``vidgen tts``: generate the narration MP3s that are missing or stale (DESIGN.md §7).

The caller activates the project's extensions first (so ``pre_tts``/``post_tts`` hooks are
registered); :func:`run_tts` then plans, dispatches the hooks and generates.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from vidgen import hooks
from vidgen.config import BeatConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.tts import TTSProvider, get_provider
from vidgen.tts.cache import atomic_write, hash_path, is_up_to_date, mp3_path, orphaned_audio


@dataclass
class TTSPlan:
    """What ``vidgen tts`` will do.

    ``todo``: beats to generate, in video order. ``reuse``: beat id -> base ``audio/`` MP3 to copy
    instead of calling the API (a variant with its own audio folder whose beat and voice are
    unchanged). ``up_to_date``: ids skipped because their audio is current.
    """

    audio_dir: Path
    todo: list[BeatConfig] = field(default_factory=list)
    reuse: dict[str, Path] = field(default_factory=dict)
    up_to_date: list[str] = field(default_factory=list)

    @property
    def characters(self) -> int:
        """Characters that will be sent for synthesis (what ElevenLabs bills; context excluded)."""
        return sum(len(beat.text) for beat in self.todo if beat.id not in self.reuse)


def plan_tts(project: Project, provider: TTSProvider, beat_ids: Sequence[str] = (), force: bool = False) -> TTSPlan:
    """Decide which beats need audio. ``beat_ids`` restricts the selection (unknown id: error)."""
    known = [beat for _, beat in project.beats()]
    by_id = {beat.id: beat for beat in known}
    unknown = [b for b in beat_ids if b not in by_id]
    if unknown:
        raise VidgenError(f"unknown beat id(s): {', '.join(unknown)}; beats: {', '.join(by_id) or 'none'}")
    wanted = set(beat_ids) if beat_ids else set(by_id)
    plan = TTSPlan(project.audio_dir)
    base_dir = project.root / "audio"
    for beat in known:
        if beat.id not in wanted:
            continue
        if not force and is_up_to_date(provider, plan.audio_dir, beat.id, beat.text):
            plan.up_to_date.append(beat.id)
            continue
        plan.todo.append(beat)
        if not force and base_dir != plan.audio_dir and is_up_to_date(provider, base_dir, beat.id, beat.text):
            plan.reuse[beat.id] = mp3_path(base_dir, beat.id)
    return plan


def _apply_pre_tts(project: Project, plan: TTSPlan, force: bool, dry_run: bool) -> None:
    """Dispatch ``pre_tts``; hooks may remove ids from ``data["beats"]`` (or add known ones)."""
    ctx = hooks.dispatch(
        "pre_tts",
        project,
        beats=[beat.id for beat in plan.todo],
        audio_dir=plan.audio_dir,
        force=force,
        dry_run=dry_run,
    )
    chosen = ctx.data.get("beats")
    if not isinstance(chosen, list) or not all(isinstance(b, str) for b in chosen):
        raise VidgenError("a pre_tts hook set data['beats'] to something other than a list of beat ids")
    by_id = {beat.id: beat for _, beat in project.beats()}
    unknown = [b for b in chosen if b not in by_id]
    if unknown:
        raise VidgenError(f"a pre_tts hook added unknown beat id(s): {', '.join(unknown)}")
    selected = set(chosen)
    plan.todo = [beat for beat in by_id.values() if beat.id in selected]
    plan.reuse = {k: v for k, v in plan.reuse.items() if k in selected}
    plan.up_to_date = [b for b in plan.up_to_date if b not in selected]


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def run_tts(
    project: Project,
    *,
    beat_ids: Sequence[str] = (),
    force: bool = False,
    dry_run: bool = False,
    provider: TTSProvider | None = None,
    out: Callable[[str], None] = print,
) -> TTSPlan:
    """Generate missing/stale narration audio for ``project``; returns the executed plan.

    ``dry_run`` only prints what would be generated (no API key needed). The API key is needed
    only when at least one beat must be synthesised.
    """
    provider = provider if provider is not None else get_provider(project.config.voice)
    plan = plan_tts(project, provider, beat_ids, force)
    _apply_pre_tts(project, plan, force, dry_run)
    where = _relative(plan.audio_dir, project.root)

    orphans = orphaned_audio(project)
    if orphans:
        names = ", ".join(p.name for p in orphans)
        out(f"orphaned audio in {where}/ (no beat with that id; not deleted): {names}")

    if dry_run:
        for beat in plan.todo:
            source = plan.reuse.get(beat.id)
            note = f"copy from {_relative(source, project.root)}" if source else f"{len(beat.text)} chars"
            out(f"would generate {beat.id}.mp3 ({note})")
        out(
            f"dry run: {len(plan.todo)} beat(s) to generate, {plan.characters} characters; "
            f"{len(plan.up_to_date)} up to date"
        )
        return plan

    if plan.characters:
        provider.check_credentials()  # fail before the first request if the key is missing

    texts = [beat for _, beat in project.beats()]
    index = {beat.id: i for i, beat in enumerate(texts)}
    generated: list[str] = []
    total = len(plan.todo)
    for n, beat in enumerate(plan.todo, start=1):
        try:
            source = plan.reuse.get(beat.id)
            if source is not None:
                audio = source.read_bytes()
                action = f"copied {beat.id}.mp3 from {_relative(source, project.root)}"
            else:
                i = index[beat.id]
                previous = texts[i - 1].text if i > 0 else None
                following = texts[i + 1].text if i + 1 < len(texts) else None
                audio = provider.synthesize(beat.text, previous, following)
                action = f"generated {beat.id}.mp3 ({len(beat.text)} chars)"
            atomic_write(mp3_path(plan.audio_dir, beat.id), audio)
            atomic_write(hash_path(plan.audio_dir, beat.id), provider.cache_key(beat.text).encode("utf-8"))
        except (VidgenError, OSError) as exc:
            done = f"{len(generated)} of {total} done before the error; run again to continue"
            raise VidgenError(f"beat '{beat.id}': {exc}\n({done})") from None
        generated.append(beat.id)
        out(f"[{n}/{total}] {action}")

    hooks.dispatch("post_tts", project, generated=list(generated), audio_dir=plan.audio_dir)
    if generated:
        out(
            f"done: {len(generated)} beat(s) generated ({plan.characters} characters), "
            f"{len(plan.up_to_date)} up to date, audio in {where}/"
        )
    else:
        out(f"nothing to do: {len(plan.up_to_date)} beat(s) up to date in {where}/")
    return plan

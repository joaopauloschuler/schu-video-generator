"""``vidgen tts``: generate the narration MP3s that are missing or stale (DESIGN.md §7).

The caller activates the project's extensions first (so ``pre_tts``/``post_tts`` hooks are
registered); :func:`run_tts` then plans, dispatches the hooks and generates. Each beat is voiced
by its own voice (``voices:``, DESIGN.md §46).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vidgen import hooks
from vidgen.config import BeatConfig, VoiceConfig
from vidgen.errors import VidgenError
from vidgen.imagegen import PriceQuote
from vidgen.project import Project
from vidgen.speech import read_alignment, write_alignment
from vidgen.tts import TTSProvider, beat_providers
from vidgen.tts.cache import atomic_write, hash_path, is_up_to_date, mp3_path, orphaned_audio
from vidgen.voices import DEFAULT_VOICE, unknown_voice_message, voice_names


@dataclass
class TTSPlan:
    """What ``vidgen tts`` will do.

    ``todo``: beats to generate, in video order. ``reuse``: beat id -> base ``audio/`` MP3 to copy
    instead of calling the API (a variant with its own audio folder whose beat and voice are
    unchanged). ``up_to_date``: ids skipped because their audio is current. ``spoken``: beat id
    -> the text sent to the TTS (the beat's text with the project's pronunciation applied).
    ``voices``: beat id -> the name of the voice that says it (``None``: the base voice).
    """

    audio_dir: Path
    todo: list[BeatConfig] = field(default_factory=list)
    reuse: dict[str, Path] = field(default_factory=dict)
    up_to_date: list[str] = field(default_factory=list)
    spoken: dict[str, str] = field(default_factory=dict)
    voices: dict[str, str | None] = field(default_factory=dict)
    #: Beat id -> its effective voice (provider, model, voice...).
    beat_voices: dict[str, VoiceConfig] = field(default_factory=dict)
    #: OpenRouter model -> its price per character (:func:`price_tts`; DESIGN.md §66).
    rates: dict[str, PriceQuote] = field(default_factory=dict)
    #: What OpenRouter's live list says about the voices (``notes``) and what a real run refuses
    #: before paying (``problems``: a model it does not have).
    notes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    #: What the estimate is based on (shown with the total).
    price_notes: list[str] = field(default_factory=list)
    #: US dollars the provider reported charging in a real run (``None``: it did not say).
    charged: float | None = None

    def say(self, beat: BeatConfig) -> str:
        """What the TTS gets for ``beat``."""
        return self.spoken.get(beat.id, beat.text)

    def voice_of(self, beat: BeatConfig) -> str:
        """The name of ``beat``'s voice (``default`` for the base voice)."""
        return self.voices.get(beat.id) or DEFAULT_VOICE

    def engine(self, beat: BeatConfig) -> VoiceConfig:
        """``beat``'s effective voice (the default voice config when not planned)."""
        return self.beat_voices.get(beat.id) or VoiceConfig()

    def synthesised(self) -> list[BeatConfig]:
        """The beats a real run sends to the provider (copies excluded)."""
        return [beat for beat in self.todo if beat.id not in self.reuse]

    def beat_cost(self, beat: BeatConfig) -> float | None:
        """Estimated US dollars of ``beat``: 0 for a copy, OpenRouter's price per character x
        its characters, ``None`` when unknown (ElevenLabs bills a plan's quota)."""
        if beat.id in self.reuse:
            return 0.0
        voice = self.engine(beat)
        quote = self.rates.get(voice.model or "") if voice.provider == "openrouter" else None
        return None if quote is None or quote.cost is None else quote.cost * len(self.say(beat))

    @property
    def cost(self) -> tuple[float, int]:
        """Estimated US dollars of the beats to synthesise and how many have no known price."""
        prices = [self.beat_cost(beat) for beat in self.synthesised()]
        return sum(p for p in prices if p is not None), sum(1 for p in prices if p is None)

    @property
    def price_note(self) -> str | None:
        """What the estimate is based on (``None`` before :func:`price_tts`)."""
        return "; ".join(self.price_notes) if self.price_notes else None

    @property
    def characters(self) -> int:
        """Characters that will be sent for synthesis (what ElevenLabs bills; context excluded)."""
        return sum(len(self.say(beat)) for beat in self.todo if beat.id not in self.reuse)

    def characters_by_voice(self) -> dict[str, tuple[int, int]]:
        """Voice name -> (beats to synthesise, their characters), in order of first use."""
        out: dict[str, tuple[int, int]] = {}
        for beat in self.todo:
            if beat.id in self.reuse:
                continue
            beats, chars = out.get(self.voice_of(beat), (0, 0))
            out[self.voice_of(beat)] = (beats + 1, chars + len(self.say(beat)))
        return out


def _check_voices(project: Project, voices: Sequence[str]) -> None:
    known = voice_names(project.config)
    unknown = [name for name in voices if name not in known]
    if unknown:
        raise VidgenError("; ".join(unknown_voice_message(name, known) for name in unknown))


def plan_tts(
    project: Project,
    provider: TTSProvider | None = None,
    beat_ids: Sequence[str] = (),
    force: bool = False,
    voices: Sequence[str] = (),
) -> TTSPlan:
    """Decide which beats need audio. ``beat_ids`` and ``voices`` (voice names, ``default`` for
    the base voice) restrict the selection (unknown id or name: error). ``provider`` replaces
    every beat's own voice provider (tests)."""
    known = [beat for _, beat in project.beats()]
    by_id = {beat.id: beat for beat in known}
    unknown = [b for b in beat_ids if b not in by_id]
    if unknown:
        raise VidgenError(f"unknown beat id(s): {', '.join(unknown)}; beats: {', '.join(by_id) or 'none'}")
    _check_voices(project, voices)
    wanted = set(beat_ids) if beat_ids else set(by_id)
    plan = TTSPlan(project.audio_dir, spoken=project.spoken_texts(), voices=project.voice_names())
    plan.beat_voices = {beat.id: project.beat_voice(beat.id) for beat in known}
    providers = beat_providers(project) if provider is None else dict.fromkeys(by_id, provider)
    base_dir = project.root / "audio"
    for beat in known:
        if beat.id not in wanted or (voices and plan.voice_of(beat) not in voices):
            continue
        beat_provider = providers[beat.id]
        if not force and is_up_to_date(beat_provider, plan.audio_dir, beat.id, plan.say(beat)):
            plan.up_to_date.append(beat.id)
            continue
        plan.todo.append(beat)
        if not force and base_dir != plan.audio_dir and is_up_to_date(beat_provider, base_dir, beat.id, plan.say(beat)):
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


def context_texts(project: Project, spoken: dict[str, str]) -> dict[str, tuple[str | None, str | None]]:
    """Beat id -> (previous_text, next_text) sent for continuity: the neighbouring beats in video
    order (across scenes), but only when they have the same voice — another speaker's line would
    be taken as this voice's own surrounding speech (DESIGN.md §46)."""
    order = list(project.voice_names().items())
    out: dict[str, tuple[str | None, str | None]] = {}
    for i, (beat_id, name) in enumerate(order):
        previous = spoken[order[i - 1][0]] if i > 0 and order[i - 1][1] == name else None
        following = spoken[order[i + 1][0]] if i + 1 < len(order) and order[i + 1][1] == name else None
        out[beat_id] = (previous, following)
    return out


#: What an ElevenLabs estimate would need (its price depends on the account's plan).
ELEVENLABS_PRICE_NOTE = "ElevenLabs bills the characters against your plan's quota (no price estimate)"


def price_tts(plan: TTSPlan, *, lookup: Callable[[list[str]], dict[str, Any]] | None = None) -> TTSPlan:
    """Fill ``plan``'s OpenRouter prices, notes, problems and price notes from OpenRouter's live
    TTS model list (a free lookup with a short timeout; offline: "price unknown", nothing
    refused). ``lookup`` replaces :func:`vidgen.tts.openrouter.lookup_speech_models` (tests)."""
    from vidgen.tts import openrouter

    beats = plan.synthesised()
    routed = [plan.engine(b) for b in beats if plan.engine(b).provider == "openrouter"]
    notes: list[str] = []
    if any(plan.engine(b).provider == "elevenlabs" for b in beats):
        notes.append(ELEVENLABS_PRICE_NOTE)
    if routed:
        found = (lookup or openrouter.lookup_speech_models)(list(dict.fromkeys(str(v.model) for v in routed)))
        for model, result in found.items():
            plan.rates[model] = openrouter.character_rate(result)
            if isinstance(result, openrouter.LookupFailure) and result.missing:
                plan.problems.append(result.reason)
        for voice in {(v.model, v.voice, v.instructions, v.speed): v for v in routed}.values():
            for note in openrouter.voice_notes(voice, found[str(voice.model)]):
                if note not in plan.notes:
                    plan.notes.append(note)
        reached = any(not isinstance(v, openrouter.LookupFailure) or v.missing for v in found.values())
        today = datetime.now(timezone.utc).date().isoformat()
        notes.append(f"OpenRouter prices of {today}" if reached else "OpenRouter prices unknown (its model list could not be reached)")
    plan.price_notes = notes
    return plan


def describe_voice(voice: VoiceConfig) -> str:
    """``openrouter mistralai/voxtral-mini-tts-2603, voice en_paul_neutral`` / an ElevenLabs
    voice id (as the dry run names it)."""
    if voice.provider != "openrouter":
        return voice.voice_id
    parts = [f"openrouter {voice.model}", f"voice {voice.voice or '(model default)'}"]
    if voice.instructions:
        parts.append(f"instructions {voice.instructions!r}")
    if voice.speed is not None:
        parts.append(f"speed {voice.speed:g}")
    return ", ".join(parts)


def _money(value: float) -> str:
    from vidgen.tts.openrouter import money

    return money(value)


def estimate_text(plan: TTSPlan) -> str:
    """``estimated $0.0007 (OpenRouter prices of 2026-10-08)`` (+ beats of unknown price)."""
    total, unknown = plan.cost
    known = len(plan.synthesised()) - unknown
    text = f"estimated {_money(total)}" if known else "price unknown"
    if unknown and known:
        text += f" + {unknown} beat(s) of unknown price"
    return text + (f" ({plan.price_note})" if plan.price_note else "")


def _reported_cost(plan: TTSPlan, providers: Iterable[TTSProvider]) -> str:
    """Ask each provider that can tell (OpenRouter) what its requests cost; sets
    ``plan.charged`` and returns the ``, $X charged by openrouter`` part of the summary (``, cost
    not reported by openrouter`` when it could not be read; empty for other providers)."""
    asked = [p for p in {id(p): p for p in providers}.values() if callable(getattr(p, "reported_cost", None))]
    asked = [p for p in asked if getattr(p, "generations", None)]
    if not asked:
        return ""
    total, found = 0.0, 0
    for p in asked:
        cost, count = p.reported_cost()  # type: ignore[attr-defined]
        total, found = total + cost, found + count
    requests = sum(len(p.generations) for p in asked)  # type: ignore[attr-defined]
    if not found:
        return ", cost not reported by openrouter"
    plan.charged = total
    part = f" for {found} of {requests} requests" if found < requests else ""
    return f", {_money(total)} charged by openrouter{part}"


def _dry_run(project: Project, plan: TTSPlan, out: Callable[[str], None]) -> None:
    named = bool(project.config.voices)
    routed = any(plan.engine(b).provider == "openrouter" for b in plan.todo)
    for beat in plan.todo:
        source = plan.reuse.get(beat.id)
        note = f"copy from {_relative(source, project.root)}" if source else f"{len(plan.say(beat))} chars"
        cost = plan.beat_cost(beat)
        if routed and not source:
            note += f", ~{_money(cost)}" if cost is not None else ", price unknown"
        if named:
            note += f", voice {plan.voice_of(beat)}"
        out(f"would generate {beat.id}.mp3 ({note})")
        if plan.say(beat) != beat.text:
            out(f"    says: {plan.say(beat)}")
    out(
        f"dry run: {len(plan.todo)} beat(s) to generate, {plan.characters} characters; "
        f"{len(plan.up_to_date)} up to date"
    )
    if named or routed:
        for name, (beats, chars) in plan.characters_by_voice().items():
            out(f"  voice {name} ({describe_voice(project.voice(name))}): {beats} beat(s), {chars} characters")
    if routed:
        for model, quote in plan.rates.items():
            out(f"  price of {model}: {quote.basis}")
        for note in plan.notes:
            out(f"  note: {note}")
        for problem in plan.problems:
            out(f"  problem: {problem} (a real run refuses)")
        out(f"  cost: {estimate_text(plan)}")


def run_tts(
    project: Project,
    *,
    beat_ids: Sequence[str] = (),
    force: bool = False,
    dry_run: bool = False,
    provider: TTSProvider | None = None,
    voices: Sequence[str] = (),
    out: Callable[[str], None] = print,
    lookup: Callable[[list[str]], dict[str, Any]] | None = None,
) -> TTSPlan:
    """Generate missing/stale narration audio for ``project``; returns the executed plan.

    ``dry_run`` only prints what would be generated (no API key needed; OpenRouter prices are
    looked up online, see :func:`price_tts`). The API key is needed only when at least one beat
    must be synthesised. ``voices`` restricts it to the beats of those voices; ``provider``
    replaces every beat's own voice provider (tests); ``lookup`` the OpenRouter model lookup.
    """
    plan = plan_tts(project, provider, beat_ids, force, voices)
    _apply_pre_tts(project, plan, force, dry_run)
    where = _relative(plan.audio_dir, project.root)

    orphans = orphaned_audio(project)
    if orphans:
        names = ", ".join(p.name for p in orphans)
        out(f"orphaned audio in {where}/ (no beat with that id; not deleted): {names}")

    if dry_run:
        price_tts(plan, lookup=lookup)
        _dry_run(project, plan, out)
        return plan

    providers = beat_providers(project) if provider is None else {beat.id: provider for _, beat in project.beats()}
    if plan.characters:
        # fail before the first request if the key is missing
        providers[next(b.id for b in plan.todo if b.id not in plan.reuse)].check_credentials()
    if provider is None and any(plan.engine(b).provider == "openrouter" for b in plan.synthesised()):
        price_tts(plan, lookup=lookup)  # a model OpenRouter does not have: refused before paying
        if plan.problems:
            raise VidgenError("cannot generate with these settings:\n  " + "\n  ".join(plan.problems))
        for note in plan.notes:
            out(f"note: {note}")

    context = context_texts(project, {beat.id: plan.say(beat) for _, beat in project.beats()})
    generated: list[str] = []
    total = len(plan.todo)
    for n, beat in enumerate(plan.todo, start=1):
        text = plan.say(beat)
        try:
            source = plan.reuse.get(beat.id)
            alignment: dict[str, Any] | None = None
            if source is not None:
                audio = source.read_bytes()
                stored = read_alignment(source.parent, beat.id, text)
                if stored is not None:
                    keys = ("characters", "character_start_times_seconds", "character_end_times_seconds")
                    alignment = dict(zip(keys, (stored["characters"], stored["starts"], stored["ends"])))
                action = f"copied {beat.id}.mp3 from {_relative(source, project.root)}"
            else:
                previous, following = context[beat.id]
                beat_provider = providers[beat.id]
                timed = getattr(beat_provider, "synthesize_timed", None) if project.beat_voice(beat.id).timestamps else None
                if timed is not None:
                    audio, alignment = timed(text, previous, following)
                else:
                    audio = beat_provider.synthesize(text, previous, following)
                action = f"generated {beat.id}.mp3 ({len(text)} chars{', with timings' if alignment else ''})"
            atomic_write(mp3_path(plan.audio_dir, beat.id), audio)
            # The alignment's text and the hash are the spoken text (what the audio says).
            write_alignment(plan.audio_dir, beat.id, text, audio, alignment)
            atomic_write(hash_path(plan.audio_dir, beat.id), providers[beat.id].cache_key(text).encode("utf-8"))
        except (VidgenError, OSError) as exc:
            done = f"{len(generated)} of {total} done before the error; run again to continue"
            raise VidgenError(f"beat '{beat.id}': {exc}\n({done})") from None
        generated.append(beat.id)
        out(f"[{n}/{total}] {action}")

    hooks.dispatch("post_tts", project, generated=list(generated), audio_dir=plan.audio_dir)
    spent = _reported_cost(plan, providers.values())
    if generated:
        out(
            f"done: {len(generated)} beat(s) generated ({plan.characters} characters{spent}), "
            f"{len(plan.up_to_date)} up to date, audio in {where}/"
        )
    else:
        out(f"nothing to do: {len(plan.up_to_date)} beat(s) up to date in {where}/")
    return plan

"""The studio's check panel (DESIGN.md §94.15): ``vidgen music check`` of a version, made in the
background from the stems the studio already keeps (nothing is rendered again), giving way to
renders and dropped as soon as a newer version is asked for, so checking never slows editing.

A check is kept in the session as ``checks/<render key>.json`` (what the page shows) and
``checks/<render key>-check.png`` (the spectrogram with the section marks): the same notes are
never checked twice, and a reopened session shows its checks at once.
"""

from __future__ import annotations

import io
import json
import re
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.fileio import write_bytes_atomic, write_text_atomic

#: Bumped when what the studio keeps of a check changes (older ones are made again).
STUDIO_CHECK_FORMAT = 1
#: A check's picture: ``<render key>-check.png``.
CHECK_IMAGE = re.compile(r"^([0-9a-f]{20})-check\.png\Z")
#: A check starts once no render has been asked for or made for this long (s).
CHECK_AFTER_SECONDS = 0.4


class Superseded(Exception):
    """A newer version's check was asked for: this one stops."""


def check_path(folder: Path, key: str) -> Path:
    return folder / f"{key}.json"


def headline(report: Any) -> list[dict[str, Any]]:
    """The numbers the panel shows first, each ``{name, value, level, title}``: the voice range,
    the bass, the highs, the lift (or the build), the loudness."""
    f = report.facts
    level = {x.topic: x.level for x in report.findings if x.topic not in ("sections",)}
    out = [
        {"name": "voice", "value": f"{100 * f['voice_share']:.0f} %", "level": level.get("voice range", "ok"),
         "title": "share of the sound in the voice's range (300 Hz-3 kHz); the loudest bar there must stay under the limit"},
        {"name": "bass", "value": f"{100 * f['bass_share']:.0f} %", "level": level.get("bass", "ok"), "title": "share of the power under 150 Hz"},
        {"name": "highs", "value": f"{f['highs_db']:.0f} dB", "level": level.get("highs", "ok"), "title": "level above 5 kHz against the whole"},
    ]
    for row in report.sections:
        for fact, name in (("lift_db", "lift"), ("build_db", "build")):
            if fact in row:
                words = [x for x in report.findings if x.topic == "sections" and x.text.startswith(f"the {row['name']} ")]
                worst = "fix" if any(x.level == "fix" for x in words) else ("note" if any(x.level == "note" for x in words) else "ok")
                out.append({"name": name, "value": f"{row[fact]:+.1f} dB", "level": worst, "title": f"the {row['name']}: " + "; ".join(x.text for x in words)})
    out.append({"name": "loudness", "value": f"{f['lufs']:.1f} LUFS", "level": "ok",
                "title": f"integrated, as a video plays it at volume 0; true peak {f['true_peak']:.1f} dBTP"})
    return out


def report_doc(report: Any, key: str, image: Any) -> dict[str, Any]:
    """What the page shows of a check: the verdict, the headline numbers, each finding with its
    advice and the edits that do it (``id`` ``<finding>.<edit>``), the sections, the full
    report in words and where the picture's time axis is."""
    from vidgen.sfx import RATE
    from vidgen.studio import check as chk

    fixes = [x for x in report.findings if x.level == "fix"]
    notes = [x for x in report.findings if x.level == "note"]
    cols = len(report.frames.centres)
    hop = int(report.frames.centres[1] - report.frames.centres[0]) if cols > 1 else chk.frame_hop(report.seconds)
    return {
        "format": STUDIO_CHECK_FORMAT,
        "check_version": chk.CHECK_VERSION,
        "key": key,
        "name": report.name,
        "seconds": round(report.seconds, 3),
        "verdict": report.verdict,
        "level": "fix" if fixes else ("note" if notes else "ok"),
        "headline": headline(report),
        "findings": [
            {"topic": x.topic, "level": x.level, "text": x.text, "fixes": [str(fix) for fix in x.fixes],
             "edits": [{"id": f"{i}.{k}", **e} for k, e in enumerate(x.edits)]}
            for i, x in enumerate(report.findings)
        ],
        "sections": report.sections,
        "facts": {k: v for k, v in report.facts.items() if k not in ("bar_voice_db", "bar_lufs")},
        "text": chk.music_check_text(report),
        # the picture: columns per second from its left edge (the page draws the playhead on it)
        "image": {"url": f"/media/{key}-check.png", "width": image.width, "height": image.height, "left": chk._LEFT,
                  "px_per_second": RATE / hop},
        "timings": report.timings,
    }


def find_edit(doc: Mapping[str, Any], edit_id: str) -> tuple[str, list[dict[str, Any]]]:
    """The ``(label, ops)`` of advice ``edit_id`` (``<finding>.<edit>``) in a kept check."""
    for finding in doc.get("findings", []):
        for edit in finding.get("edits", []):
            if edit.get("id") == edit_id:
                return str(edit["label"]), list(edit["ops"])
    raise VidgenError(f"check: no advice {edit_id!r} to apply in this check")


def kept_check(folder: Path, key: str) -> dict[str, Any] | None:
    """The check of render ``key`` kept in ``folder``, when it is there and current."""
    from vidgen.studio.check import CHECK_VERSION

    path = check_path(folder, key)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if doc.get("format") != STUDIO_CHECK_FORMAT or doc.get("check_version") != CHECK_VERSION or not (folder / f"{key}-check.png").is_file():
        return None
    return doc


class Checker:
    """One background worker for the session's checks. ``idle`` says whether no render is under
    way or just asked for (the studio's); ``stems`` gives a version's kept stems and mix."""

    def __init__(self, idle: Callable[[], bool], stems: Callable[[Any, Any, str], tuple[list[Any], tuple[np.ndarray, float] | None]]) -> None:
        self._idle = idle
        self._stems = stems
        self._pool = ThreadPoolExecutor(1, thread_name_prefix="vidgen-studio-check")
        self._jobs: dict[str, Future[dict[str, Any] | None]] = {}
        self._wanted: str | None = None
        self._lock = threading.Lock()

    def close(self) -> None:
        self._wanted = None
        self._pool.shutdown(wait=False, cancel_futures=True)

    def kept(self, folder: Path, key: str) -> dict[str, Any] | None:
        """The check of render ``key`` kept in ``folder``, when it is there and current."""
        return kept_check(folder, key)

    def want(self, folder: Path, key: str, data: Any, score: Any) -> Future[dict[str, Any] | None]:
        """Ask for the check of ``score`` (render ``key``): the job doing it; jobs for other
        keys not started are dropped and the one under way stops at its next step."""
        with self._lock:
            self._wanted = key
            job = self._jobs.get(key)
            if job is not None and not job.cancelled() and (not job.done() or (job.exception() is None and job.result() is not None)):
                return job
            for other, queued in list(self._jobs.items()):
                if other != key and (queued.cancel() or queued.done()):
                    del self._jobs[other]
            job = self._pool.submit(self._run, folder, key, data, score)
            self._jobs[key] = job
            return job

    def wait(self, job: Future[dict[str, Any] | None], seconds: float) -> dict[str, Any] | None:
        try:
            return job.result(timeout=seconds)
        except FuturesTimeout:
            return None

    def is_wanted(self, key: str) -> bool:
        return self._wanted == key

    def _between(self, key: str) -> None:
        """Between a check's steps: stop if another check is wanted; wait while renders run."""
        while True:
            if self._wanted != key:
                raise Superseded(key)
            if self._idle():
                return
            time.sleep(0.05)

    def _run(self, folder: Path, key: str, data: Any, score: Any) -> dict[str, Any] | None:
        from vidgen.studio import check as chk

        try:
            self._between(key)
            tracks, mix = self._stems(data, score, key)
            began = time.perf_counter()
            report = chk.check_music_score(score, tracks=tracks, mix=mix, between=lambda: self._between(key))
            image = chk.spectrogram_image([report])
        except Superseded:
            return None
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        report.timings = {"check": round(time.perf_counter() - began, 2)}
        doc = report_doc(report, key, image)
        write_bytes_atomic(folder / f"{key}-check.png", buffer.getvalue())
        write_text_atomic(check_path(folder, key), json.dumps(doc, ensure_ascii=False) + "\n")
        return doc

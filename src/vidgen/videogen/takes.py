"""Takes of generated shots (DESIGN.md §113.4): every clip a shot got is kept as
``takes/<shot>/<n>.mp4`` (n = 1, 2, ...) with ``<n>.json`` (where it came from, its cost, its QA
report) and ``<n>.contact.png`` (its contact sheet); ``takes/picks.json`` records the take picked
per shot.

Which take a shot shows (:func:`chosen_take`): the picked one; ``none`` picked: no take (vidgen's
own picture of the beat); nothing picked: the newest take without QA errors. A clip already kept
as a take (same request, same cache key) is never added twice.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError
from vidgen.fileio import write_text_atomic
from vidgen.videogen import did_you_mean
from vidgen.videogen.ledger import utc_now

#: Where takes are kept, relative to the project (kept: they are paid for; commit or back them up).
TAKES_DIR = Path("takes")
#: The picks: ``{shot id: take number | "none"}``.
PICKS_NAME = "picks.json"
#: What ``pick`` takes besides a number: no take for the shot, or back to the default.
NONE, AUTO = "none", "auto"


@dataclass
class Take:
    """One take of a shot: its number, the clip and what its sidecar says."""

    shot: str
    number: int
    path: Path
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def contact(self) -> Path:
        """Its contact sheet ``<n>.contact.png``."""
        return self.path.with_name(f"{self.number}.contact.png")

    @property
    def qa(self) -> dict[str, Any]:
        """Its QA report (JSON; empty when not checked)."""
        return self.info.get("qa") or {}

    @property
    def qa_errors(self) -> int:
        """How many QA errors it has."""
        return sum(1 for c in self.qa.get("checks", []) if c.get("severity") == "error")

    @property
    def model(self) -> str:
        """The model that made it."""
        return str(self.info.get("model") or "?")

    def line(self, root: Path, picked: bool = False) -> str:
        """``take 2: takes/x/2.mp4 (model, $0.12, QA ok) [picked]``."""
        cost = self.info.get("cost_usd")
        money = f"${cost:.3f}" if isinstance(cost, (int, float)) else "cost not reported"
        mark = " [shown]" if picked else ""
        return f"take {self.number}: {self.path.relative_to(root).as_posix()} ({self.model}, {self.info.get('provider', '?')}, {money}, {self.qa.get('summary', 'not checked')}){mark}"


def takes_dir(root: Path, shot_id: str) -> Path:
    """``takes/<shot>`` of the project at ``root``."""
    return root / TAKES_DIR / shot_id


def takes_of(root: Path, shot_id: str) -> list[Take]:
    """The shot's takes, oldest first."""
    folder = takes_dir(root, shot_id)
    if not folder.is_dir():
        return []
    out = []
    for path in folder.glob("*.mp4"):
        if not path.stem.isdigit():
            continue
        sidecar = path.with_suffix(".json")
        info: dict[str, Any] = {}
        if sidecar.is_file():
            try:
                info = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise VidgenError(f"cannot read {sidecar}: {exc}") from None
        out.append(Take(shot_id, int(path.stem), path, info))
    return sorted(out, key=lambda t: t.number)


def load_picks(root: Path) -> dict[str, int | str]:
    """``takes/picks.json`` (empty when there is none)."""
    path = root / TAKES_DIR / PICKS_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VidgenError(f"cannot read {path}: {exc}") from None
    if not isinstance(data, dict):
        raise VidgenError(f"{path}: expected {{shot: take number}}")
    return data


def chosen_take(root: Path, shot_id: str) -> Take | None:
    """The take the shot shows (see the module docstring), ``None``: vidgen's own picture."""
    takes = takes_of(root, shot_id)
    pick = load_picks(root).get(shot_id)
    if pick == NONE:
        return None
    if isinstance(pick, int):
        found = next((t for t in takes if t.number == pick), None)
        if found is not None:
            return found
    good = [t for t in takes if not t.qa_errors]
    return good[-1] if good else None


def pick_take(root: Path, shot_id: str, take: str, known: list[str]) -> Take | None:
    """Record ``take`` (a number, ``none`` or ``auto``) for ``shot_id`` (one of ``known``) in
    ``takes/picks.json``; returns the take the shot now shows."""
    if shot_id not in known:
        raise VidgenError(f"no generated shot {shot_id!r}{did_you_mean(shot_id, known)}; shots: {', '.join(known) or 'none'}")
    picks = load_picks(root)
    value = take.strip().lower()
    if value == AUTO:
        picks.pop(shot_id, None)
    elif value == NONE:
        picks[shot_id] = NONE
    else:
        numbers = [t.number for t in takes_of(root, shot_id)]
        if not value.isdigit() or int(value) not in numbers:
            have = ", ".join(map(str, numbers)) or "none yet (`vidgen generate run --pay`)"
            raise VidgenError(f"shot {shot_id}: no take {take!r}; takes: {have}; or {NONE} (vidgen's own picture) / {AUTO} (the newest without QA errors)")
        picks[shot_id] = int(value)
    path = root / TAKES_DIR / PICKS_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(dict(sorted(picks.items())), indent=1) + "\n")
    return chosen_take(root, shot_id)


def add_take(
    root: Path, shot_id: str, clip: Path, *, key: str, model: str, provider: str, job_id: str | None, cost: float | None,
    length: float, width: int, height: int,
) -> tuple[Take, bool]:
    """Keep ``clip`` (the cached clip of request ``key``) as the shot's next take, with its QA
    report (for a ``length`` s shot in a ``width`` x ``height`` video) and contact sheet; the
    take that already holds ``key`` when there is one. Returns it and whether it is new."""
    from vidgen.videogen.qa import check_clip, contact_sheet

    takes = takes_of(root, shot_id)
    for take in takes:
        if take.info.get("key") == key:
            return take, False
    number = (takes[-1].number + 1) if takes else 1
    path = takes_dir(root, shot_id) / f"{number}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(clip, path)
    report = check_clip(path, length=length, width=width, height=height)
    info = {
        "shot": shot_id, "take": number, "key": key, "model": model, "provider": provider, "job_id": job_id, "cost_usd": cost,
        "source": clip.relative_to(root).as_posix() if clip.is_relative_to(root) else str(clip), "length": round(length, 3),
        "time": utc_now(), "qa": report.to_json(),
    }
    write_text_atomic(path.with_suffix(".json"), json.dumps(info, indent=1, ensure_ascii=True) + "\n")
    take = Take(shot_id, number, path, info)
    contact_sheet(path, take.contact, title=f"shot {shot_id}, take {number}: {model} ({provider})", report=report)
    return take, True


__all__ = ["AUTO", "NONE", "TAKES_DIR", "Take", "add_take", "chosen_take", "load_picks", "pick_take", "takes_of"]

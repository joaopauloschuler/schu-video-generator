"""For testing only: does Colab end an idle session? Sends one tiny ``colab exec`` per round.

    python tools/colab/keepalive.py SESSION [--every 7m] [--hours 8] [--log PATH]

Started only by hand (nothing in vidgen starts it). Each round (every ``--every``) it skips when
the session's lock is held (tried, never waited for) or when any call to the session happened
within the last ``--every`` (vidgen's "last call" stamp, or the colab CLI's history file, which
also sees direct ``colab`` calls); otherwise it holds the lock and runs one ``colab exec`` that
sends a random ``a`` and checks the VM's ``b`` and ``a+b``. One line per round goes to stdout and
the log. It stops after ``--hours``, when ``colab sessions`` no longer lists the session (``gone``)
or on Ctrl-C. It never creates or stops a session. See README.md here.
"""
from __future__ import annotations

import argparse
import random
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR.parents[1] / "src"))  # this checkout's vidgen.colab

from vidgen.colab import EXEC_SECONDS, Colab, parse_prefixed_json, parse_sessions, via_arg  # noqa: E402

VM_SCRIPT = TOOLS_DIR / "keepalive_vm.py"
PREFIX = "KEEPALIVE "
HISTORY_DIR = Path.home() / ".config" / "colab-cli" / "history"
#: A file time up to this many seconds after the keepalive's own call ended is that call's.
OWN_SLACK = 2.0


def parse_duration(text: str) -> float:
    """Seconds of ``30s``, ``7m``, ``1h`` or a bare number of minutes."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([smh]?)", text.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"not a duration: {text!r} (use e.g. 30s, 7m, 1h)")
    return float(match[1]) * {"s": 1, "m": 60, "h": 3600, "": 60}[match[2]]


def mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


@dataclass
class Keepalive:
    """One session's keepalive loop; ``colab.wall`` is the clock and ``colab.sleep`` the pause."""

    colab: Colab
    every: float
    hours: float
    log: Path
    history_dir: Path = HISTORY_DIR
    rand: Callable[[], int] = field(default=lambda: random.randint(1, 10**9))
    out: Callable[[str], None] = field(default=lambda line: print(line, flush=True))
    own_until: float = 0.0

    def say(self, result: str) -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.colab.wall()))
        line = f"{stamp} {self.colab.session} {result}"
        self.out(line)
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def last_call(self) -> float | None:
        """The newest call to the session by someone else (stamp or CLI history), as a wall time."""
        times = [t for t in (mtime(self.colab.stamp_path), mtime(self.history_dir / f"{self.colab.session}.jsonl"))
                 if t is not None and t > self.own_until]
        return max(times, default=None)

    def gone(self) -> bool:
        result = self.colab.run(["sessions"], 90)
        return result.returncode == 0 and self.colab.session not in parse_sessions(result.output)

    def ping(self) -> str:
        """Hold the lock and run one exec; ``ok rtt=Ns``, ``wrong-sum`` or ``no-answer``."""
        a = self.rand()
        start = self.colab.wall()
        args = [self.colab.cli, *self.colab.exec_args(VM_SCRIPT, {"KEEPALIVE_A": str(a)})]
        try:
            result = self.colab.runner(args, EXEC_SECONDS)
        finally:
            self.colab.touch_stamp()
            self.own_until = self.colab.wall() + OWN_SLACK
        reply = parse_prefixed_json(result.output, PREFIX)
        if reply is None:
            return "no-answer"
        try:
            right = int(reply["sum"]) == a + int(reply["b"])
        except (KeyError, TypeError, ValueError):
            right = False
        return f"ok rtt={self.colab.wall() - start:.1f}s" if right else "wrong-sum"

    def round(self) -> str:
        """One round's result (``gone`` ends the loop)."""
        if self.gone():
            return "gone"
        with self.colab.try_locked(EXEC_SECONDS) as got:
            if not got:
                return "skip-locked"
            last = self.last_call()
            ago = self.colab.wall() - last if last is not None else None
            if ago is not None and ago < self.every:
                return f"skip-recent ({max(ago, 0):.0f}s ago)"
            return self.ping()

    def run(self) -> int:
        """Rounds every ``every`` until ``hours`` passed or the session is gone; 0 either way."""
        start = self.colab.wall()
        end = start + self.hours * 3600
        rounds = 0
        while self.colab.wall() < end:
            result = self.round()
            self.say(result)
            if result == "gone":
                return 0
            rounds += 1
            pause = start + rounds * self.every - self.colab.wall()
            if self.colab.wall() + max(pause, 0) >= end:
                break
            self.colab.sleep(max(pause, 0))
        self.say(f"stop after {self.hours:g} h")
        return 0


def main(argv: list[str] | None = None, colab: Colab | None = None) -> int:
    parser = argparse.ArgumentParser(description="For testing only: one tiny colab exec per idle round.")
    parser.add_argument("session")
    parser.add_argument("--every", type=parse_duration, default=7 * 60.0, help="round length (default 7m)")
    parser.add_argument("--hours", type=float, default=8.0, help="stop after this many hours (default 8)")
    parser.add_argument("--log", type=Path, help="default ~/.config/colab-cli/keepalive-SESSION.log")
    via_arg(parser)
    args = parser.parse_args(argv)
    colab = colab or Colab(args.session, via=args.via)
    log = args.log or Path.home() / ".config" / "colab-cli" / f"keepalive-{args.session}.log"
    keepalive = Keepalive(colab, args.every, args.hours, log)
    try:
        return keepalive.run()
    except KeyboardInterrupt:
        keepalive.say("stop (Ctrl-C)")
        return 130


if __name__ == "__main__":
    sys.exit(main())

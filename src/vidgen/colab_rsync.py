"""``vidgen remote``'s project sync on the SSH route: ``rsync`` over the held master of
:class:`vidgen.colab_ssh.SshLink` (``-e`` is that link's own ssh command line).

- **Up** (:func:`up_args`): the project to the VM with ``--delete``, so a file deleted here goes
  there too. The left-out top folders (``build``, ``output``, ``exports``, ``media`` and the
  ``--exclude`` ones) and :data:`ALWAYS_SKIPPED` are rsync excludes: rsync neither sends them nor
  deletes or changes them on the VM (``build/`` stays there as a cache).
- **Down** (:func:`down_args`): after a run that succeeded, what the next step here needs: the
  files the command's JSON document names (``named``), and everything else outside the
  left-out folders, plus ``build/`` without its big caches (:data:`BUILD_CACHES`, rebuilt by a
  render: scene clips, web captures, frames, Manim's media, padded and mixed sound, music).
  ``--update`` keeps a file changed here during the run; nothing is deleted here.

Both use ``-rltz`` (times kept, so an unchanged file is not sent again) and ``--timeout``: rsync
stops when no data moves for :data:`IO_TIMEOUT` seconds. Standard library only.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from vidgen.colab import ColabError, CommandResult, last_line
from vidgen.colab_ssh import LOGIN, SSH_FAILED, SshLink

#: Folders skipped at any depth, both ways (``.vidgen-remote`` holds each side's own run files).
ALWAYS_SKIPPED: tuple[str, ...] = ("__pycache__", ".git", ".vidgen-remote")
#: Folders of each ``build/<render folder>/`` that do not come back (big, rebuilt by a render).
BUILD_CACHES: tuple[str, ...] = ("scenes", "web", "frames", "media", "padded", "three_d", "audio")
#: Folders right in ``build/`` that do not come back (the music cache: rendered sound).
BUILD_TOP_CACHES: tuple[str, ...] = ("music",)
#: ``build/`` folders that always come back whole (a shot named like a cache folder included).
BUILD_KEPT: tuple[str, ...] = ("videogen",)
#: rsync gives up when no data moves for this many seconds.
IO_TIMEOUT = 120
#: The whole call is cut after this long (``IO_TIMEOUT`` catches a stalled one much sooner).
CALL_SECONDS = 4 * 3600.0
#: rsync's exit codes when the connection broke (ssh's own 255, a stream error, a timeout).
CONNECTION_CODES = frozenset({SSH_FAILED, 12, 30, 35})
#: The line rsync prints per file it moves (``--out-format``): size and path.
OUT_FORMAT = ">> %l %n"
_MOVED = re.compile(r"^>> (\d+) (.+)$")
_WILDCARDS = re.compile(r"[*?\[]")


def available() -> bool:
    """Whether this computer can sync with rsync (an ``rsync`` on PATH; Windows uses the tar)."""
    return os.name != "nt" and shutil.which("rsync") is not None


def rsh_word(word: str) -> str:
    """``word`` quoted for rsync's ``-e`` (rsync splits it itself: single quotes, ``''`` inside)."""
    return "'" + word.replace("'", "''") + "'"


def rsh(link: SshLink) -> str:
    """The ``-e`` value: ``link``'s ssh command line through its master (never opening one)."""
    return " ".join(rsh_word(word) for word in link.ssh("-o", "ControlMaster=no"))


def literal(rel: str) -> str:
    """``rel`` as an rsync pattern that matches only itself."""
    return re.sub(r"([\\*?\[\]])", r"\\\1", rel) if _WILDCARDS.search(rel) else rel


def _common(link: SshLink) -> list[str]:
    return ["rsync", "-rltz", f"--timeout={IO_TIMEOUT}", f"--out-format={OUT_FORMAT}", "-e", rsh(link)]


def _skipped() -> list[str]:
    return [f"--exclude={name}" for name in ALWAYS_SKIPPED]


def up_filters(exclude: Iterable[str]) -> list[str]:
    """The excludes of a sync up: the top folders ``exclude`` and :data:`ALWAYS_SKIPPED`. An rsync
    exclude also protects the VM's copy from ``--delete``."""
    return [*(f"--exclude=/{literal(top)}" for top in dict.fromkeys(exclude)), *_skipped()]


def up_args(link: SshLink, local: str, remote: str, exclude: Iterable[str]) -> list[str]:
    """rsync from the project folder ``local`` to the VM folder ``remote`` (made when missing)."""
    return [*_common(link), "--delete", f"--rsync-path=mkdir -p {shlex.quote(remote)} && rsync", *up_filters(exclude),
            f"{local.rstrip('/')}/", f"{LOGIN}:{remote.rstrip('/')}/"]


def _parents(rel: str) -> list[str]:
    parts = rel.split("/")
    return ["/".join(parts[:end]) for end in range(1, len(parts))]


def down_filters(exclude: Iterable[str], named: Sequence[str]) -> list[str]:
    """The filter rules of a bring-back, first match wins: :data:`ALWAYS_SKIPPED`; the ``named``
    files (and their folders); ``build/`` without :data:`BUILD_CACHES` / :data:`BUILD_TOP_CACHES`;
    no other ``exclude`` top folder."""
    rules = _skipped()
    for rel in named:
        rules += [f"--include=/{literal(folder)}/" for folder in _parents(rel)] + [f"--include=/{literal(rel)}"]
    rules += [f"--include=/build/{name}/***" for name in BUILD_KEPT]
    rules += [f"--exclude=/build/*/{name}/" for name in BUILD_CACHES]
    rules += [f"--exclude=/build/{name}/" for name in BUILD_TOP_CACHES]
    rules += [f"--exclude=/{literal(top)}{tail}" for top in dict.fromkeys(exclude) if top != "build" for tail in ("", "/***")]
    return list(dict.fromkeys(rules))


def down_args(link: SshLink, remote: str, local: str, exclude: Iterable[str], named: Sequence[str]) -> list[str]:
    """rsync from the VM folder ``remote`` back into the project folder ``local``."""
    return [*_common(link), "--update", *down_filters(exclude, named), f"{LOGIN}:{remote.rstrip('/')}/", f"{local.rstrip('/')}/"]


@dataclass
class Moved:
    """What one rsync call moved: files (path -> bytes) and the paths it deleted."""

    files: dict[str, int] = field(default_factory=dict)
    deleted: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return sum(self.files.values())


def parse_moved(output: str) -> Moved:
    """The files (folders left out) and deletions in rsync's output (:data:`OUT_FORMAT` lines)."""
    moved = Moved()
    for line in output.splitlines():
        found = _MOVED.match(line)
        if found and not found.group(2).endswith("/"):
            moved.files[found.group(2)] = int(found.group(1))
        elif line.startswith("deleting "):
            moved.deleted.append(line[len("deleting "):])
    return moved


def run(link: SshLink, args: list[str], what: str) -> Moved:
    """Run rsync ``args`` over ``link``'s master (opened first); a broken connection reopens it and
    tries once more."""
    link.ensure()
    result: CommandResult = link.runner(args, CALL_SECONDS, None, None)
    if result.returncode in CONNECTION_CODES:
        link.reconnect(result)
        result = link.runner(args, CALL_SECONDS, None, None)
    if result.returncode != 0:
        raise ColabError(f"rsync could not {what} (exit code {result.returncode}): {last_line(result.output)}")
    return parse_moved(result.output)


__all__ = ["ALWAYS_SKIPPED", "BUILD_CACHES", "Moved", "available", "down_args", "down_filters", "parse_moved", "rsh",
           "run", "up_args", "up_filters"]

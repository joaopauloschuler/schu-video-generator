"""``vidgen studio``: a local music workstation in the browser (Phase T, DESIGN.md §94).

A small web app on 127.0.0.1 where people load the built-in beds as editable score files,
change them, listen and export. The sound is always vidgen's own renderer
(:mod:`vidgen.studio`, the score-file package — a different thing from this app, which is
named ``studio_app`` for that reason); the browser only plays the rendered audio.
"""

from __future__ import annotations

import threading
import webbrowser
from collections.abc import Callable
from pathlib import Path

from vidgen.studio_app.app import StudioApp
from vidgen.studio_app.cleanup import clean_studio
from vidgen.studio_app.server import StudioServer
from vidgen.studio_app.session import remove_open_marker, write_open_marker

__all__ = ["StudioApp", "StudioServer", "clean_studio_folder", "run_studio"]


def _say(text: str) -> None:
    print(text, flush=True)  # at once, also when the output is a pipe


def clean_studio_folder(project_root: Path | None, say: Callable[[str], None] = _say) -> dict[str, int]:
    """``vidgen studio --clean``: remove old renders of every session of the studio folder
    (those of each session's current, first and starred versions are kept) and exports older
    than an hour; versions, notes and checks are never removed (DESIGN.md §94.18)."""
    from vidgen.studio_app.cleanup import ASKED_EXPORT_AGE, disk_use
    from vidgen.studio_app.session import studio_dir

    studio = studio_dir(project_root)
    if not (studio / "sessions").is_dir():
        say(f"no studio sessions in {studio}")
        return {"files": 0, "bytes": 0, "busy": 0, "kept_bytes": 0, "sessions": 0}
    done = clean_studio(studio, None, ASKED_EXPORT_AGE)
    left = disk_use(studio, None)
    busy = f" ({done['busy']} in use, left for later)" if done["busy"] else ""
    say(f"studio {studio}: {done['sessions']} session(s); removed {done['files']} old render and export files, "
        f"{done['bytes'] / 1e6:.0f} MB{busy}; renders left {left['studio_renders'] / 1e6:.0f} MB (versions, notes and checks are kept)")
    return done


def run_studio(project_root: Path | None, port: int = 0, open_browser: bool = True, say: Callable[[str], None] = _say) -> None:
    """Serve the studio until Ctrl+C: on ``port`` (0: a free one), opening the page in the
    default browser unless ``open_browser`` is false. Writes ``open.json`` in the studio folder
    while it runs."""
    app = StudioApp(project_root)
    server = StudioServer(app, port)
    app.studio.mkdir(parents=True, exist_ok=True)
    write_open_marker(app.studio, server.url, None)
    say(f"vidgen studio: {server.url}")
    say(f"sessions: {app.studio / 'sessions'}")
    cleaned = clean_studio(app.studio, None)
    if cleaned["bytes"]:
        say(f"removed {cleaned['bytes'] / 1e6:.0f} MB of old renders and exports (versions are kept)")
    say("press Ctrl+C to stop it")
    if open_browser:
        threading.Timer(0.3, webbrowser.open, args=(server.url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        say("studio stopped")
    finally:
        server.server_close()
        app.close()
        remove_open_marker(app.studio)

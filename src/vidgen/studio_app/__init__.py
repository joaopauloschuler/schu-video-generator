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
from vidgen.studio_app.server import StudioServer
from vidgen.studio_app.session import remove_open_marker, write_open_marker

__all__ = ["StudioApp", "StudioServer", "run_studio"]


def _say(text: str) -> None:
    print(text, flush=True)  # at once, also when the output is a pipe


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
    say("press Ctrl+C to stop it")
    if open_browser:
        threading.Timer(0.3, webbrowser.open, args=(server.url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        say("studio stopped")
    finally:
        server.server_close()
        remove_open_marker(app.studio)

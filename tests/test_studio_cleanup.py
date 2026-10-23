"""Step 200 (DESIGN.md §94.18): the studio's disk rule for old renders and exports, ``vidgen studio
--clean``, the batch list and the last hand-off a reloaded page shows again. No rendering: render
files are stand-ins named as the studio names them."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from vidgen import cli
from vidgen.studio_app import clean_studio_folder
from vidgen.studio_app.app import StudioApp, render_key
from vidgen.studio_app.cleanup import clean_session, clean_studio, disk_use, kept_keys
from vidgen.studio_app.session import StudioSession, studio_dir

TINY = """\
title: Tiny
key: A minor
tempo: {tempo}
progression: "i VI"
sections: [{{name: a, bars: 1}}, {{name: b, bars: 1}}]
tracks:
  kick: {{instrument: kick, steps: "x... x... x... x..."}}
"""


def text(tempo: int) -> str:
    return TINY.format(tempo=tempo)


def key_of(tempo: int) -> str:
    import yaml

    return render_key(yaml.safe_load(text(tempo)))


def session_with(studio: Path, count: int, size: int = 1000) -> StudioSession:
    """A session of ``count`` versions (tempo 100, 101...), each with a render, its facts, a
    section and a listening mix under narration on disk."""
    session = StudioSession.create(studio, "tiny", "Tiny")
    for k in range(count):
        session.add_version(text(100 + k), "edit" if k else "text", f"v{k + 1}", k or None)
        key = key_of(100 + k)
        session.renders.mkdir(exist_ok=True)
        for name in (f"{key}.wav", f"{key}.json", f"{key}-a.wav", f"{key}.n.wav"):
            (session.renders / name).write_bytes(b"\0" * size)
    return session


def keys_on_disk(session: StudioSession) -> set[str]:
    return {p.name[:20] for p in session.renders.iterdir()}


def test_renders_of_old_versions_go_versions_never(tmp_path: Path) -> None:
    session = session_with(tmp_path, 12)
    session.update_version(2, starred=True)
    session.set_current(5)
    (session.renders / "stray.txt").write_text("not a render", encoding="utf-8")
    done = clean_session(session, keep_versions=3)
    kept = {key_of(100 + k) for k in (0, 1, 4, 9, 10, 11)}  # first, starred, current, last three
    assert keys_on_disk(session) - {"stray.txt"} == kept
    assert (session.renders / "stray.txt").is_file()  # not a render name: left alone
    assert done["files"] == 6 * 4 and done["bytes"] == 6 * 4 * 1000 and done["busy"] == 0
    assert all(session.version_path(n).is_file() for n in range(1, 13))  # versions are never removed
    assert (session.folder / "session.json").is_file()


def test_the_cap_drops_the_least_wanted_but_never_current_first_or_starred(tmp_path: Path) -> None:
    session = session_with(tmp_path, 6, size=1000)
    session.set_current(3)
    order, protected = kept_keys(session, keep_versions=8, extra=[key_of(105)])
    assert order[0] == key_of(105) and protected == {key_of(102), key_of(100), key_of(105)}
    clean_session(session, keep_versions=8, cap_bytes=12_000, extra=[key_of(105)])  # 3 versions' renders fit
    assert keys_on_disk(session) == {key_of(105), key_of(102), key_of(100)}
    clean_session(session, keep_versions=8, cap_bytes=0)
    assert keys_on_disk(session) == {key_of(102), key_of(100)}  # protected even over the cap


def test_exports_age_out_and_other_sessions_keep_current_and_starred(tmp_path: Path) -> None:
    mine = session_with(tmp_path, 4)
    other = session_with(tmp_path, 4)
    other.update_version(2, starred=True)
    exports = other.folder / "exports"
    exports.mkdir()
    (exports / "old.wav").write_bytes(b"\0" * 50)
    (exports / "new.wav").write_bytes(b"\0" * 50)
    old = time.time() - 2 * 3600
    os.utime(exports / "old.wav", (old, old))
    before = disk_use(tmp_path, mine)
    assert before["session_renders"] == 16_000 and before["studio_renders"] == 32_000 and before["studio_exports"] == 100
    done = clean_studio(tmp_path, mine.id, export_age=3600)
    assert done["sessions"] == 1
    assert keys_on_disk(other) == {key_of(100), key_of(101), key_of(103)}  # first, starred, current
    assert keys_on_disk(mine) == {key_of(100 + k) for k in range(4)}  # the open session is not touched
    assert not (exports / "old.wav").exists() and (exports / "new.wav").is_file()


def test_studio_clean_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "video.yaml").write_text("title: t\n", encoding="utf-8")
    studio = studio_dir(tmp_path)
    session = session_with(studio, 3)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vidgen.studio_app.run_studio", lambda *a, **k: pytest.fail("--clean must not start the studio"))
    assert cli.main(["studio", "--clean"]) == 0
    assert keys_on_disk(session) == {key_of(100), key_of(102)}  # first and current
    said: list[str] = []
    assert clean_studio_folder(tmp_path / "nowhere", said.append)["sessions"] == 0
    assert said and "no studio sessions" in said[0]


def test_batches_listed_newest_first_and_a_stopped_batch_says_so(tmp_path: Path) -> None:
    app = StudioApp(None, studio=tmp_path)
    app.load(text=text(100))
    assert app.variation_batches() == []
    for batch, state in (("b0001", "done"), ("b0002", "running")):
        folder = app.session.folder / "variations" / batch
        folder.mkdir(parents=True)
        doc = {"id": batch, "created": "2026-10-23T10:00:00", "root": 1, "base": {"version": 1}, "shuffle": 0, "chain": [], "state": state,
               "items": [{"letter": "a", "kind": "harmony", "label": "re-voiced", "kept": 2 if batch == "b0001" else None, "status": "done", "key": "0" * 20}]}
        (folder / "batch.json").write_text(json.dumps(doc), encoding="utf-8")
    listed = app.variation_batches()
    assert [b["id"] for b in listed] == ["b0002", "b0001"]
    assert listed[0]["state"] == "stopped"  # written as running by a studio that was closed
    assert listed[1]["items"] == [{"letter": "a", "kind": "harmony", "label": "re-voiced", "kept": 2, "status": "done"}]
    app.close()


def test_the_last_handoff_is_given_again(tmp_path: Path) -> None:
    app = StudioApp(None, studio=tmp_path)
    assert app.last_handoff() is None
    app.load(text=text(100))
    assert app.last_handoff() is None
    app.add_note(None, 0.5, "kick too plain")
    made = app.ask()
    again = app.last_handoff()
    assert again is not None and again["request"] == made["request"] and again["prompt"] == made["prompt"]
    app.load(text=text(101))  # another session: not its hand-off
    assert app.last_handoff() is None
    app.close()

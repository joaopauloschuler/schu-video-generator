"""The studio's inspector and the editable score file (Step 195, DESIGN.md §94.13): ``unset`` with
its pruning, the patch catalogue with units and scales, an instrument change that keeps what it
can and says what changes, the play mode, playing or resting in a section, typed text as a
version, and the tracks as written in the outline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from vidgen.errors import VidgenError
from vidgen.studio import patch_catalog
from vidgen.studio_app import inspector
from vidgen.studio_app.app import StudioApp, check_text
from vidgen.studio_app.edits import apply_edits, unset_value
from vidgen.studio_app.server import start_in_thread

TEXT = """\
# a score
key: A minor
tempo: 120
progression: "i VI"
sections: [{name: a, bars: 1}, {name: b, bars: 1}]
tracks:
  pad:
    instrument: pad
    play: chords
    settings: {tone: 2600, air: 0.3}
    sections:
      b: {settings: {tone: 1800}, lowpass: 900}
  arp:
    instrument: fm_pluck
    octave: 3
    steps: "1 5 8 5 3 5 8 5"   # broken chords
    settings:
      index: 1.2
      tone: 5800
    accent: "3+3+2"
  kick: {instrument: kick, steps: "x... x... x... x...", rest: [a]}
"""


@pytest.fixture
def app(tmp_path: Path) -> StudioApp:
    return StudioApp(None, studio=tmp_path / "studio")


def ops_result(text: str, ops: list[dict]) -> dict:
    out = apply_edits(text, ops)
    assert check_text(out)[2] == [], check_text(out)[2]
    return yaml.safe_load(out)


# ----- unset ------------------------------------------------------------------------------------------


def test_unset_removes_a_key_and_the_mappings_it_empties() -> None:
    out = unset_value(TEXT, "tracks.pad.settings.air")
    assert "settings: {tone: 2600}" in out and out.count("\n") == TEXT.count("\n")
    out = unset_value(TEXT, "tracks.pad.sections.b.settings.tone")  # settings left empty: gone, b and sections stay
    assert "b: {lowpass: 900}" in out
    out = unset_value(unset_value(TEXT, "tracks.pad.sections.b.settings.tone"), "tracks.pad.sections.b.lowpass")
    assert "sections:\n      b" not in out and yaml.safe_load(out)["tracks"]["pad"].get("sections") is None  # pruned to the track
    out = unset_value(TEXT, "tracks.arp.settings.index")  # a block mapping
    assert "    settings:\n      tone: 5800\n" in out
    out = unset_value(out, "tracks.arp.settings.tone")
    assert "settings" not in yaml.safe_load(out)["tracks"]["arp"] and "# broken chords" in out
    assert unset_value(TEXT, "tracks.arp.transpose") == TEXT  # nothing there: nothing changes
    # keep: a kept mapping left empty is written {} (an effect's field reset)
    out = unset_value("tracks:\n  p: {instrument: pad, echo: {delay: 0.5}}\n", "tracks.p.echo.delay", keep=3)
    assert "echo: {}" in out
    with pytest.raises(VidgenError, match="keep is a whole number"):
        apply_edits(TEXT, [{"op": "unset", "path": "tempo", "keep": 0}])


# ----- the catalogue ----------------------------------------------------------------------------------


def test_studio_catalog_adds_units_and_scales_and_leaves_the_patches_alone() -> None:
    before = json.dumps(patch_catalog(), sort_keys=True)
    cat = inspector.studio_catalog(patch_catalog())
    assert json.dumps(patch_catalog(), sort_keys=True) == before  # music patches --json unchanged
    kick = next(i for i in cat["instruments"] if i["name"] == "kick")["settings"]
    assert kick["high"]["unit"] == "Hz" and kick["high"]["scale"] == "linear"  # 60-160 Hz: under two octaves
    assert kick["decay"]["unit"] == "s" and kick["click"]["unit"] == ""
    pluck = next(i for i in cat["instruments"] if i["name"] == "fm_pluck")["settings"]
    assert pluck["tone"]["unit"] == "Hz" and pluck["tone"]["scale"] == "log"
    pad = next(i for i in cat["instruments"] if i["name"] == "pad")["settings"]
    assert pad["detune"]["unit"] == "cents" and pad["swell"]["unit"] == "bars"
    echo = next(e for e in cat["effects"] if e["name"] == "echo")["fields"]
    assert echo["delay"]["unit"] == "beats" and echo["repeats"]["integer"] is True and "unit" not in echo["pingpong"]
    lowpass = next(e for e in cat["effects"] if e["name"] == "lowpass")["fields"]["value"]
    assert lowpass["scale"] == "log" and lowpass["unit"] == "Hz"
    for i in cat["instruments"]:
        for s in i["settings"].values():
            assert {"unit", "scale", "integer"} <= set(s) and s["low"] <= s["default"] <= s["high"]


# ----- the instrument ---------------------------------------------------------------------------------


def test_change_instrument_keeps_what_it_can_and_says_what_changes() -> None:
    data, score, _ = check_text(TEXT)
    ops, label, notes = inspector.change_instrument(data, score, "arp", "bell")
    assert label == "arp: fm_pluck → bell"
    out = ops_result(TEXT, ops)["tracks"]["arp"]
    assert out["instrument"] == "bell" and out["settings"] == {"tone": 5800} and out["octave"] == 3
    assert notes[0] == "keeps tone" and any("drops index" in n for n in notes)
    # a setting outside the new range moves inside it, and the note says so
    ops, _, notes = inspector.change_instrument(data, score, "arp", "woodblock")
    assert ops_result(TEXT, ops)["tracks"]["arp"]["settings"] == {"tone": 5800}
    ops, _, notes = inspector.change_instrument(data, score, "arp", "music_box")
    assert ops_result(TEXT, ops)["tracks"]["arp"]["settings"] == {"tone": 5800}
    ops, _, notes = inspector.change_instrument(data, score, "arp", "sub")
    assert ops_result(TEXT, ops)["tracks"]["arp"]["settings"] == {"tone": 1500}
    assert any("tone 5800 → 1500" in n for n in notes)


def test_change_to_a_drum_drops_pitch_and_a_pad_s_chords() -> None:
    data, score, _ = check_text(TEXT)
    ops, _, notes = inspector.change_instrument(data, score, "arp", "hat")
    out = ops_result(TEXT, ops)["tracks"]["arp"]
    assert "octave" not in out and out["settings"] == {"tone": 5800} and "accent" not in out  # a hat has a tone too
    assert out["steps"] == "..x. ..x. ..x. ..x."
    assert any("has no pitch" in n for n in notes)
    # a pad holding chords becomes a pluck playing a first pattern; its section's changes follow
    ops, _, notes = inspector.change_instrument(data, score, "pad", "pluck")
    out = ops_result(TEXT, ops)["tracks"]["pad"]
    assert "play" not in out and out["steps"] and out["settings"] == {"tone": 2600}
    assert out["sections"]["b"] == {"settings": {"tone": 1800}, "lowpass": 900}
    assert any("cannot hold chords" in n for n in notes)
    with pytest.raises(VidgenError, match="did you mean 'bell'"):
        inspector.change_instrument(data, score, "arp", "bel")
    assert inspector.change_instrument(data, score, "arp", "fm_pluck") == ([], "", [])


# ----- play mode and sections -------------------------------------------------------------------------


def test_play_mode_switches_a_pad_between_chords_and_steps() -> None:
    data, score, _ = check_text(TEXT)
    ops, label, _ = inspector.set_play_mode(data, score, "pad", "steps")
    out = ops_result(TEXT, ops)
    assert out["tracks"]["pad"]["steps"] == "* - - -" and "play" not in out["tracks"]["pad"] and label == "pad: plays steps"
    text = apply_edits(TEXT, ops)
    data2, score2, _ = check_text(text)
    ops, _, notes = inspector.set_play_mode(data2, score2, "pad", "chords")
    assert ops_result(text, ops)["tracks"]["pad"]["play"] == "chords" and "steps" not in ops_result(text, ops)["tracks"]["pad"]
    with pytest.raises(VidgenError, match="cannot hold chords"):
        inspector.set_play_mode(data, score, "arp", "chords")


def test_section_plays_writes_rest_or_only_as_the_track_does() -> None:
    data, _, _ = check_text(TEXT)
    ops, label, _ = inspector.set_section_plays(data, "kick", "a", True)
    assert "rest" not in ops_result(TEXT, ops)["tracks"]["kick"] and label == "kick: plays in a"
    ops, _, _ = inspector.set_section_plays(data, "arp", "b", False)
    assert ops_result(TEXT, ops)["tracks"]["arp"]["rest"] == ["b"]
    # resting where the track has changes drops them (they would never play)
    ops, _, notes = inspector.set_section_plays(data, "pad", "b", False)
    out = ops_result(TEXT, ops)["tracks"]["pad"]
    assert out["rest"] == ["b"] and "sections" not in out and notes
    only = TEXT.replace("rest: [a]", "only: [b]")
    data, _, _ = check_text(only)
    ops, _, _ = inspector.set_section_plays(data, "kick", "a", True)
    assert "only" not in ops_result(only, ops)["tracks"]["kick"]
    with pytest.raises(VidgenError, match="play nowhere"):
        inspector.set_section_plays(data, "kick", "b", False)
    with pytest.raises(VidgenError, match="did you mean 'b'"):
        inspector.set_section_plays(data, "kick", "bb", True)


# ----- through the app and the server -----------------------------------------------------------------


def test_edit_ops_dry_run_notes_and_versions(app: StudioApp) -> None:
    app.load(text=TEXT)
    preview = app.edit(None, [{"op": "change_instrument", "track": "arp", "instrument": "bell"}], dry_run=True)
    assert preview["ok"] and "keeps tone" in preview["notes"] and len(app.session.versions) == 1
    done = app.edit(None, [{"op": "change_instrument", "track": "arp", "instrument": "bell"}])
    assert done["ok"] and app.session.versions[-1].label == "arp: fm_pluck → bell"
    arp = next(t for t in done["score"]["outline"]["tracks"] if t["name"] == "arp")
    assert arp["spec"]["instrument"] == "bell" and arp["spec"]["octave"] == 3  # the track as written
    pad = next(t for t in done["score"]["outline"]["tracks"] if t["name"] == "pad")
    assert pad["spec"]["sections"] == {"b": {"settings": {"tone": 1800}, "lowpass": 900}}
    # a setting outside its range is refused with the score's message; nothing written
    bad = app.edit(None, [{"op": "set", "path": "tracks.pad.settings.tone", "value": 90000}])
    assert not bad["ok"] and "out of range" in bad["problems"][0]["message"] and len(app.session.versions) == 2
    r = app.edit(None, [{"op": "section_plays", "track": "kick", "section": "a", "plays": True}])
    assert r["ok"] and app.session.versions[-1].label == "kick: plays in a"


def test_typed_text_becomes_a_version_and_a_bad_one_does_not(app: StudioApp) -> None:
    app.load(text=TEXT)
    typed = TEXT.replace("tempo: 120", "tempo: 100")
    r = app.text(1, typed)
    assert r["ok"] and app.session.current == 2 and app.session.text(2) == typed
    assert app.session.versions[-1].label == "typed in the score file" and app.session.versions[-1].origin == "edit"
    assert app.text(2, typed)["unchanged"] is True
    bad = app.text(2, typed.replace("instrument: kick", "instrument: kik"))
    assert not bad["ok"] and "did you mean 'kick'" in bad["problems"][0]["message"] and bad["problems"][0]["line"] == 21
    assert len(app.session.versions) == 2
    syntax = app.text(2, "tracks: [\n")
    assert not syntax["ok"] and syntax["problems"][0]["line"]


def test_routes_for_text_and_patches(app: StudioApp) -> None:
    import urllib.request

    app.load(text=TEXT)
    server, thread = start_in_thread(app)
    try:
        def post(path: str, body: dict) -> dict:
            req = urllib.request.Request(server.url + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())

        r = post("/api/text", {"version": 1, "text": TEXT.replace("tempo: 120", "tempo: 90")})
        assert r["ok"] and r["result"]["score"]["version"] == 2
        with urllib.request.urlopen(server.url + "/api/patches") as resp:
            cat = json.loads(resp.read())["result"]
        assert cat["instruments"][0]["settings"]["high"]["unit"] == "Hz"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)

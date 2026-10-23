"""The studio's song strip, timeline and track list (Step 194, DESIGN.md §94.12): value edits that
keep the score's comments, Roman numerals of the templates' chords, the song edits (tracks and
sections), versions from edits, the energy curve and listening mixes with tracks muted."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np
import pytest
import yaml

from vidgen.errors import VidgenError
from vidgen.studio import INSTRUMENTS, music_template_text
from vidgen.studio.templates import template_names
from vidgen.studio.theory import parse_chord, parse_key
from vidgen.studio_app import song
from vidgen.studio_app.app import AUDIO_NAME, StudioApp, check_text
from vidgen.studio_app.edits import apply_edits, delete_value, flow, insert_item, parse_path, rename_key, set_value
from vidgen.studio_app.server import start_in_thread

TEXT = """\
# a score
key: A minor   # the key
tempo: 120
progression: "i VI"
sections:
  - {name: a, bars: 1}   # first
  # the second
  - name: b
    bars: 1
tracks:
  # the kick
  kick: {instrument: kick, steps: "x... x... x... x..."}
  bass:
    instrument: synth_bass
    steps: '1.1. 1.1. 1.1. 1.1.'
    only: [b]
"""


@pytest.fixture
def app(tmp_path: Path) -> StudioApp:
    return StudioApp(None, studio=tmp_path / "studio")


def data(text: str) -> dict:
    return yaml.safe_load(text)


# ----- value edits -------------------------------------------------------------------------------


def test_parse_path_and_flow() -> None:
    assert parse_path("sections[2].bars") == ["sections", 2, "bars"]
    assert parse_path("tracks.bass.settings.tone") == ["tracks", "bass", "settings", "tone"]
    with pytest.raises(VidgenError, match="cannot read the path"):
        parse_path("tracks..x")
    assert flow({"instrument": "fm_pluck", "steps": "1.3. 5.8.", "volume": -6, "only": ["b"]}) == '{instrument: fm_pluck, steps: "1.3. 5.8.", volume: -6, only: [b]}'
    assert flow("G minor") == "G minor" and flow("true") == '"true"' and flow(120.0) == "120" and flow(0.25) == "0.25"


def test_set_replaces_one_value_and_keeps_everything_else() -> None:
    out = set_value(TEXT, "tempo", 126)
    assert out == TEXT.replace("tempo: 120", "tempo: 126")
    out = set_value(TEXT, "key", "G minor")
    assert "key: G minor   # the key" in out
    out = set_value(TEXT, "tracks.kick.steps", "x.x. x... x... x...")
    assert 'steps: "x.x. x... x... x..."}' in out  # a double-quoted string stays double-quoted
    out = set_value(TEXT, "tracks.bass.steps", "1... 1...")
    assert "steps: '1... 1...'" in out  # and a single-quoted one single-quoted
    out = set_value(TEXT, "sections[1].bars", 3)
    assert "    bars: 3\n" in out and data(out)["sections"][1]["bars"] == 3


def test_set_adds_a_missing_key_by_its_siblings() -> None:
    out = set_value(TEXT, "tracks.kick.volume", -3)
    assert 'kick: {instrument: kick, steps: "x... x... x... x...", volume: -3}' in out
    out = set_value(TEXT, "tracks.bass.pan", 0.25)
    assert "    only: [b]\n    pan: 0.25\n" in out
    out = set_value(TEXT, "tracks.bass.settings.tone", 900)
    assert "    settings: {tone: 900}\n" in out
    out = set_value(TEXT, "tracks.pad", {"instrument": "pad", "play": "chords"})
    assert out.endswith("  pad:\n    instrument: pad\n    play: chords\n")
    assert check_text(out)[1] is not None


def test_set_replaces_a_block_value_with_a_flow_one() -> None:
    text = music_template_text("momentum")
    out = set_value(text, "progression", "i VI III VII")
    assert 'progression: "i VI III VII"\nsections:' in out and "Gm(add9)" not in out.split("sections:")[0]
    assert check_text(out)[1] is not None


def test_delete_insert_rename() -> None:
    out = delete_value(TEXT, "tracks.kick")
    assert "kick" not in out and "# the kick" not in out and "bass:" in out
    out = delete_value(TEXT, "sections[1]")
    assert "# the second" not in out and "name: b" not in out and "{name: a, bars: 1}   # first" in out
    assert delete_value(TEXT, "tracks.bass.only") == TEXT.replace("    only: [b]\n", "")
    out = delete_value(TEXT, "tracks.kick.steps")
    assert "kick: {instrument: kick}" in out
    out = insert_item(TEXT, "sections", 1, {"name": "c", "bars": 2})
    assert "  - {name: a, bars: 1}   # first\n  - {name: c, bars: 2}\n  # the second\n" in out
    out = insert_item(TEXT, "sections", 2, {"name": "c", "bars": 2})
    assert [s["name"] for s in data(out)["sections"]] == ["a", "b", "c"]
    out = insert_item(TEXT, "tracks.bass.only", 0, "a")
    assert "only: [a, b]" in out
    out = rename_key(TEXT, "tracks.kick", "kick_2")
    assert "  kick_2: {instrument: kick" in out
    with pytest.raises(VidgenError, match="already there"):
        rename_key(TEXT, "tracks.kick", "bass")
    with pytest.raises(VidgenError, match="nothing there"):
        delete_value(TEXT, "tracks.nope")
    with pytest.raises(VidgenError, match="unknown op"):
        apply_edits(TEXT, [{"op": "explode", "path": "tempo"}])


# ----- chords ------------------------------------------------------------------------------------


def test_roman_numerals_read_back_as_the_same_chords_in_every_template() -> None:
    count = 0
    for name in template_names():
        _, score, _ = check_text(music_template_text(name))
        for section in score.sections:
            for slot in section.chords:
                numeral = song.roman_numeral(slot.chord, section.key)
                back = parse_chord(numeral, section.key)
                assert set(back.pitch_classes) == set(slot.chord.pitch_classes) and back.bass == slot.chord.bass, (name, slot.chord.name, numeral)
                count += 1
    assert count > 100


def test_roman_numeral_examples() -> None:
    g_minor = parse_key("G minor")
    assert [song.roman_numeral(parse_chord(c, g_minor), g_minor) for c in ("Gm(add9)", "Ebmaj7", "Cm9", "Dsus4(add9)", "F", "Ab", "D/F#")] == [
        "i(add9)", "VImaj7", "iv9", "Vsus4(add9)", "VII", "bII", "V/F#"]


def test_outline_shows_progressions_numerals_and_names(app: StudioApp) -> None:
    outline = app.load(preset="momentum")["score"]["outline"]
    top = outline["progression"]
    assert top["written"] == "voicings" and top["text"].startswith("i(add9) VImaj7 iv9")
    assert top["chords"][0] == {"symbol": "Gm(add9)", "numeral": "i(add9)", "name": "Gm(add9)"}
    drive, turn = outline["sections"]
    assert not drive["own_progression"] and drive["progression"]["text"] == top["text"]
    assert turn["own_progression"] and [c["numeral"] for c in turn["progression"]["chords"]] == ["V"]
    assert outline["sections_written"] and outline["steps_per_bar"] == 16 and outline["bar_seconds"] == pytest.approx(2.0, abs=0.01)
    tracks = {t["name"]: t for t in outline["tracks"]}
    assert tracks["kick"]["levels"]["drive"] == [[1.0, 0, 0, 0] * 4]
    assert tracks["ostinato"]["levels"]["drive"][0][:4] == [1.5, 1.0, 1.0, 1.5]  # accented 3+3+2
    assert tracks["pad"]["levels"] == {"drive": None, "turn": None} and tracks["riser"]["levels"].keys() == {"turn"}
    tide = app.load(preset="tidewater")["score"]["outline"]
    lift = next(s for s in tide["sections"] if s["name"] == "lift")
    assert lift["own_progression"] and lift["progression"]["text"] == "VI VII i i"
    assert [c["name"] for c in lift["progression"]["chords"]] == ["C", "D", "Em", "Em"]


# ----- song edits --------------------------------------------------------------------------------


@pytest.mark.parametrize("time", ["4/4", "3/4", "6/8"])
def test_every_instrument_gets_a_default_track_that_plays(time: str) -> None:
    text = TEXT.replace("tempo: 120", f"tempo: 120\ntime: {time}")
    for instrument in INSTRUMENTS:
        _, score, _ = check_text(text)
        ops, label = song.add_track(data(text), score, instrument)
        out = apply_edits(text, ops)
        _, new, problems = check_text(out)
        assert new is not None, (instrument, problems)
        added = next(t for t in new.tracks if t.instrument.name == instrument and t.name.startswith(instrument))
        assert label.startswith(f"+ track {added.name}")
    _, score, _ = check_text(text)
    assert song.add_track(data(text), score, "kick")[0][0]["path"] == "tracks.kick_2"
    with pytest.raises(VidgenError, match="did you mean 'pluck'"):
        song.add_track(data(text), score, "plunk")


def test_sections_add_remove_rename_keep_the_tracks_right(app: StudioApp) -> None:
    ops, _ = song.rename_section(data(TEXT), "b", "lift")
    out = apply_edits(TEXT, ops)
    assert "    only: [lift]" in out and check_text(out)[1] is not None
    ops, _ = song.add_section(data(out), 0, None, 2)
    out2 = apply_edits(out, ops)
    assert [s["name"] for s in data(out2)["sections"]] == ["a", "part", "lift"] and check_text(out2)[1] is not None
    ops, label = song.remove_section(data(out2), "lift")
    assert label == "− section lift (and track bass, which played only there)"
    assert list(data(apply_edits(out2, ops))["tracks"]) == ["kick"]
    with pytest.raises(VidgenError, match="at least one section"):
        song.remove_section(data(TEXT.replace("sections:\n  - {name: a, bars: 1}   # first\n", "sections:\n")), "b")
    ops, _ = song.remove_section(data(out2), "part")
    assert check_text(apply_edits(out2, ops))[1] is not None
    with pytest.raises(VidgenError, match="already a section"):
        song.rename_section(data(TEXT), "a", "b")
    with pytest.raises(VidgenError, match="not a name"):
        song.rename_section(data(TEXT), "a", "Lift!")
    # per-section steps only: the new section is a rest for that track
    cartoon = music_template_text("cartoon")
    ops, _ = song.add_section(data(cartoon), None)
    assert check_text(apply_edits(cartoon, ops))[1] is not None
    # a section's own changes go with it
    tide = music_template_text("tidewater")
    ops, _ = song.rename_section(data(tide), "lift", "peak")
    renamed = apply_edits(tide, ops)
    notes = {k: v for k, v in data(renamed).items() if k not in ("title", "description")}
    assert check_text(renamed)[1] is not None and "lift" not in json.dumps(notes) and "peak" in json.dumps(notes["tracks"])
    ops, _ = song.remove_section(data(tide), "lift")
    assert check_text(apply_edits(tide, ops))[1] is not None


# ----- versions from edits ---------------------------------------------------------------------


def test_edit_makes_a_version_and_a_bad_edit_none(app: StudioApp) -> None:
    app.load(text=TEXT)
    doc = app.edit(None, [{"op": "set", "path": "tempo", "value": 100}], "tempo 100")
    assert doc["ok"] and doc["score"]["version"] == 2 and doc["score"]["outline"]["tempo"] == 100
    version = doc["session"]["versions"][-1]
    assert version["origin"] == "edit" and version["parent"] == 1 and version["label"] == "tempo 100"
    assert "# a score" in doc["score"]["text"] and "key: A minor   # the key" in doc["score"]["text"]
    bad = app.edit(2, [{"op": "set", "path": "tracks.kick.steps", "value": "x..q"}])
    assert not bad["ok"] and bad["problems"][0]["where"] == "tracks.kick.steps" and "unknown symbol 'q'" in bad["problems"][0]["message"]
    assert len(app.session.versions) == 2  # nothing written
    dry = app.edit(2, [{"op": "set", "path": "progression", "value": "i iv"}], dry_run=True)
    assert dry["ok"] and [c["name"] for c in dry["outline"]["progression"]["chords"]] == ["Am", "Dm"] and len(app.session.versions) == 2
    doc = app.edit(2, [{"op": "add_track", "instrument": "fm_pluck"}, {"op": "delete_track", "name": "kick"}])
    assert doc["ok"] and [t["name"] for t in doc["score"]["outline"]["tracks"]] == ["bass", "fm_pluck"]
    assert app.session.versions[-1].label == "+ track fm_pluck (fm_pluck); − track kick"
    same = app.edit(3, [{"op": "set", "path": "tempo", "value": 100}])
    assert same["ok"] and same.get("unchanged") and len(app.session.versions) == 3
    with pytest.raises(VidgenError, match="at least one track"):
        app.edit(3, [{"op": "delete_track", "name": "bass"}, {"op": "delete_track", "name": "fm_pluck"}])


# ----- renders: energy and listening mixes -------------------------------------------------------


def wav_rms(path: Path) -> tuple[int, float]:
    with wave.open(str(path), "rb") as w:
        frames = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
        return w.getnframes(), float(np.sqrt(np.mean(frames**2)))


def test_render_has_energy_per_bar_and_mutes_make_a_mix(app: StudioApp) -> None:
    app.load(text=TEXT)
    full = app.render()
    assert len(full["energy"]) == 2 and all(-70 <= e < 0 for e in full["energy"]) and full["muted"] == []
    assert full["energy"][1] > full["energy"][0]  # the bass joins in section b
    mix = app.render(mute=["bass", "nope"])
    assert mix["muted"] == ["bass"] and AUDIO_NAME.match(mix["url"][len("/audio/"):])
    whole = app.audio_file(full["url"][len("/audio/"):])
    quiet = app.audio_file(mix["url"][len("/audio/"):])
    assert whole is not None and quiet is not None
    (n_full, rms_full), (n_mix, rms_mix) = wav_rms(whole), wav_rms(quiet)
    assert n_full == n_mix and 0 < rms_mix < rms_full
    # the kick alone plays at the full mix's gain: section a (kick only) is the same
    with wave.open(str(whole), "rb") as a, wave.open(str(quiet), "rb") as b:
        first = a.getnframes() // 2 - 4800
        x = np.frombuffer(a.readframes(first), dtype=np.int16).astype(float)
        y = np.frombuffer(b.readframes(first), dtype=np.int16).astype(float)
    assert np.sqrt(np.mean((x - y) ** 2)) < 0.05 * np.sqrt(np.mean(x**2))
    part = app.render(section="b", mute=["bass"])
    assert part["url"].endswith(f".m{mix['url'].split('.m')[1].split('.')[0]}-b.wav") and app.audio_file(part["url"][7:]) is not None
    assert json.loads((app.session.renders / f"{full['key']}.json").read_text(encoding="utf-8"))["energy"] == full["energy"]


def test_server_edit_route(app: StudioApp) -> None:
    import http.client

    app.load(text=TEXT)
    server, thread = start_in_thread(app)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=30)
        body = json.dumps({"version": 1, "ops": [{"op": "set", "path": "seed", "value": 7}], "label": "seed 7"})
        conn.request("POST", "/api/edit", body, {"Content-Type": "application/json", "Host": f"127.0.0.1:{server.port}"})
        doc = json.loads(conn.getresponse().read())
        assert doc["ok"] and doc["result"]["ok"] and doc["result"]["score"]["outline"]["seed"] == 7
        conn.request("POST", "/api/edit", json.dumps({"ops": "nope"}), {"Content-Type": "application/json", "Host": f"127.0.0.1:{server.port}"})
        response = conn.getresponse()
        assert response.status == 400 and "ops" in json.loads(response.read())["error"]
        conn.request("POST", "/api/render", json.dumps({"mute": "kick"}), {"Content-Type": "application/json", "Host": f"127.0.0.1:{server.port}"})
        response = conn.getresponse()
        assert response.status == 400 and "mute" in json.loads(response.read())["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)

"""``vidgen studio`` Step 199 (DESIGN.md §94.17): variations — the operators (pure, deterministic
edits of the score text), four of different kinds for every built-in template, the batches the
studio renders and checks in the background, keeping one, "more like this", the HTTP routes and
the MCP side (``agent_variations``)."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from vidgen.errors import VidgenError
from vidgen.studio import music_template_text
from vidgen.studio.templates import template_names
from vidgen.studio_app import variations as var
from vidgen.studio_app.app import StudioApp, check_text, render_key
from vidgen.studio_app.edits import apply_edits
from vidgen.studio_app.server import start_in_thread
from vidgen.studio_app.session import write_open_marker

#: Three bars at 120 BPM (6 s): chords in numerals, a pad, drums, a 3+3+2 arpeggio.
VARI = """\
# a small piece to vary
title: Vari
key: A minor
tempo: 120
seed: 2
progression: "i VI III VII"   # one chord a bar
sections: [{name: intro, bars: 1}, {name: lift, bars: 2}]
tracks:
  pad: {instrument: pad, play: chords, settings: {tone: 2000}}
  kick: {instrument: kick, steps: "x... x... x... x..."}
  hat: {instrument: hat, steps: "..x. ..x. ..x. ..x."}
  # the figure
  arp: {instrument: pluck, steps: "1358 5315 1358 5318", accent: "3+3+2", volume: -4}
"""


def piece(text: str = VARI) -> var.Piece:
    data, score, problems = check_text(text)
    assert score is not None, problems
    return var.Piece(text, data, score)


# ----- the operators ------------------------------------------------------------------------------


def test_step_helpers_keep_the_layout() -> None:
    assert var.step_cells("1 5 | v3+v4 .") == [[(0, 1), (2, 3)], [(6, 11), (12, 13)]]
    assert var.rotate_steps("1358 5315", 1) == "3585 3151"
    assert var.rotate_steps("x... | .x..", 1) == "...x | x..."  # each bar on its own
    assert var.map_tokens("1 3' 5! v2 v3, A4", {"3": "5", "5": "3", "v2": "v3", "v3": "v2"}) == "1 5' 3! v3 v2, A4"


@pytest.mark.parametrize("op", [op for ops in var.OPERATORS.values() for op in ops], ids=lambda op: op.__name__)
def test_each_operator_is_deterministic_and_valid(op: Any) -> None:
    text = music_template_text("momentum") if op in (var.revoice,) else VARI
    if op in (var.build_in, var.breathe):
        text = music_template_text("neon")  # one section (bars:) with drums and pads
    p = piece(text)
    found = op(p, 0)
    if found is None:  # not every operator applies to these pieces; those that do are checked
        assert op in (var.hat_touch,) or op(p, 1) is None
        return
    assert found == op(piece(text), 0)
    new = apply_edits(text, found.ops)
    data, score, problems = check_text(new)
    assert score is not None, (found.label, problems)
    assert render_key(data) != render_key(p.data) and found.kind in var.KINDS and found.label
    assert (score.tempo, score.key.name) == (p.score.tempo, p.score.key.name)  # never the tempo or the key


def test_operators_say_what_they_change() -> None:
    p = piece()
    sub = var.substitute(p, 0)
    assert sub is not None and sub.label == "a chord substituted: VII → v (G → Em) in the progression"
    assert sub.ops == ({"op": "set", "path": "progression", "value": "i VI III v"},)
    assert apply_edits(VARI, sub.ops).count("# one chord a bar") == 1  # the comments stay
    rot = var.rotate(p, 0)
    assert rot is not None and rot.label == "arp turned by 1 step: 1 3 5 8 5 3 1 5 … → 3 5 8 5 3 1 5 1 …"
    accent = var.reaccent(p, 0)
    assert accent is not None and accent.label == "arp re-accented: 3+3+2 → 4+4+2+3+3"
    dark = var.tone(p, 0)
    assert dark is not None and dark.label == "darker mix: master low-pass 4500 → 3250, pad tone 2000 → 1400, hat −2 dB"
    bright = var.tone(p, 1)
    assert bright is not None and bright.name == "brighter" and "pad tone 2000 → 2800" in bright.label
    intro = var.sparser_intro(p, 0)
    assert intro is not None and intro.label == "sparser intro: kick, hat rest there"
    lift = var.stronger_lift(p, 0)
    assert lift is not None and lift.label == "stronger lift: kick +2 dB there"
    seed = var.reseed(p, 1)
    assert seed is not None and seed.ops == ({"op": "set", "path": "seed", "value": 4},)
    voiced = var.revoice(piece(music_template_text("momentum")), 0)
    assert voiced is not None and "Gm(add9): G2 → G3" in voiced.label


def test_four_variations_of_different_kinds_and_shuffles() -> None:
    found = var.make_variations(VARI)
    assert [v.kind for v, _ in found] == ["harmony", "pattern", "mix", "energy"]
    assert [v.label for v, _ in found] == [v.label for v, _ in var.make_variations(VARI)]  # the same four again
    shuffled = var.make_variations(VARI, 1)
    assert {t for _, t in shuffled}.isdisjoint({t for _, t in found})
    first = var.make_variations(VARI, 0, first="mix")
    assert first[0][0].kind == "mix"
    with pytest.raises(VidgenError, match="shuffle"):
        var.make_variations(VARI, -1)
    with pytest.raises(VidgenError, match="problems to fix first"):
        var.make_variations(VARI.replace("pluck", "plunk"))


def test_every_template_gets_four_valid_variations() -> None:
    for name in template_names():
        text = music_template_text(name)
        base = yaml.safe_load(text)
        found = var.make_variations(text)
        assert len(found) == 4, name
        assert len({t for _, t in found}) == 4 and len({v.kind for v, _ in found}) >= 3, (name, [v.label for v, _ in found])
        for v, new in found:
            data, score, problems = check_text(new)
            assert score is not None, (name, v.label, problems)
            assert render_key(data) != render_key(base), (name, v.label)
            assert (data["tempo"], data["key"]) == (base["tempo"], base["key"]), (name, v.label)
            assert new.splitlines()[0] == text.splitlines()[0]  # the header comment kept


# ----- the studio: batches, keep, more like this ---------------------------------------------------


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("VIDGEN_CACHE_DIR", str(tmp_path / "cache"))
    root = tmp_path / "root"
    root.mkdir()
    studio = StudioApp(root, studio=root / "build" / "studio")
    yield studio
    studio.close()


def finished(app: StudioApp, batch: str) -> dict[str, Any]:
    app.variations.wait(240)
    doc = app.variation_batch(batch)
    assert doc["state"] == "done", doc
    return doc


def test_a_batch_is_rendered_checked_and_one_kept(app: StudioApp) -> None:
    app.load(text=VARI)
    app.render()  # as the page does before anyone asks for variations: v1's stems are kept
    doc = app.make_variations()
    assert doc["id"] == "b0001" and doc["root"] == 1 and [i["letter"] for i in doc["items"]] == ["a", "b", "c", "d"]
    doc = finished(app, "b0001")
    for item in doc["items"]:
        assert item["status"] == "done" and item["render"]["url"] == f"/audio/{item['key']}.wav"
        assert item["check"]["verdict"] and item["check"]["image"]["url"] == f"/media/{item['key']}-check.png"
        assert app.audio_file(f"{item['key']}.wav") is not None and app.media_file(f"{item['key']}-check.png") is not None
    pattern = next(i for i in doc["items"] if i["kind"] == "pattern")
    assert pattern["render"]["tracks"] == ["arp"]  # the other tracks' stems were kept
    assert {"render", "check", "total", "made"} <= set(doc["timing"])
    played = app.render(variation=("b0001", pattern["letter"]))
    assert played["version"] is None and played["variation"] == f"b0001/{pattern['letter']}" and played["cached"]
    assert [v.number for v in app.session.versions] == [1]  # nothing is a version until kept

    state = app.keep_variation("b0001", pattern["letter"])
    version = state["session"]["versions"][-1]
    assert (version["number"], version["parent"], version["origin"]) == (2, 1, "variation")
    assert version["label"] == f"variation: {pattern['label']}" and state["session"]["current"] == 2
    assert app.variation_batch("b0001")["items"][1]["kept"] == 2
    assert app.keep_variation("b0001", pattern["letter"])["session"]["current"] == 2  # again: no second version
    assert len(app.session.versions) == 2

    more = app.make_variations(batch="b0001", letter="c")
    assert more["id"] == "b0002" and more["base"] == {"batch": "b0001", "letter": "c"} and more["root"] == 1
    assert more["items"][0]["kind"] == doc["items"][2]["kind"] and more["chain"] == [doc["items"][2]["label"]]
    finished(app, "b0002")
    state = app.keep_variation("b0002", "a")
    assert state["session"]["versions"][-1]["parent"] == 1
    assert state["session"]["versions"][-1]["label"].startswith(f"variation: {doc['items'][2]['label']}; ")


def test_bad_batches_and_letters_are_refused(app: StudioApp) -> None:
    app.load(text=VARI)
    for batch, letter in (("../x", "a"), ("b0001", "e"), ("b0009", "a")):
        with pytest.raises(VidgenError, match="variations"):
            app.render(variation=(batch, letter))
    with pytest.raises(VidgenError, match="letter"):
        app.make_variations(batch="b0001")


def post(port: int, path: str, body: Any) -> tuple[int, dict[str, Any]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
    conn.request("POST", path, json.dumps(body), {"Content-Type": "application/json"})
    r = conn.getresponse()
    return r.status, json.loads(r.read())


def test_routes(app: StudioApp) -> None:
    app.load(text=VARI)
    server, thread = start_in_thread(app)
    try:
        port = server.server_address[1]
        status, doc = post(port, "/api/variations", {"version": 1, "shuffle": 1})
        assert status == 200 and doc["result"]["shuffle"] == 1
        app.variations.wait(240)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("GET", "/api/variations?batch=b0001")
        got = json.loads(conn.getresponse().read())["result"]
        assert got["state"] == "done"
        status, doc = post(port, "/api/render", {"variation": "b0001/a"})
        assert status == 200 and doc["result"]["variation"] == "b0001/a"
        assert post(port, "/api/render", {"variation": "b0001"})[0] == 400
        status, doc = post(port, "/api/variations/keep", {"batch": "b0001", "letter": "b"})
        assert status == 200 and doc["result"]["session"]["versions"][-1]["origin"] == "variation"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_agents_get_variations_through_mcp(app: StudioApp, tmp_path: Path) -> None:
    app.load(text=VARI)
    write_open_marker(app.studio, "http://127.0.0.1:1/", app.session.id)
    doc = var.agent_variations(tmp_path / "root")
    assert doc["session"] == app.session.id and doc["version"] == 1 and len(doc["variations"]) == 4
    assert doc["variations"][0]["score"] == var.make_variations(VARI)[0][1] and "studio_propose" in doc["next"]
    assert not (app.session.folder / "variations").exists()  # nothing written

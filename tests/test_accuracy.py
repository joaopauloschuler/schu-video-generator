"""Step 209 (DESIGN.md §95.14): the scientific-accuracy lint rules and references.

The text checks are run on wrong statements (each must be found) and on correct ones (none may
be); the scene checks on small projects. References are checked offline: every identifier
here is a clearly fake placeholder in a valid format (10.0000/…, PMID 12345678, an ISBN made
of zeros with its check digit), never a real source."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from vidgen.cellworld import accuracy as acc
from vidgen.chapter_export import write_youtube_list
from vidgen.config import LINT_RULES, LintRules, SceneConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.lint import RULES
from vidgen.lint.science_rule import SCIENCE_RULES, science_issues
from vidgen.project import Project
from vidgen.references import (beat_numbers, description_text, marker, normal_doi, normal_isbn, normal_pmid, normal_url, scene_numbers,
                               video_references)
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.videoplan import Chapter

FAKE_DOI = "10.0000/example.1"          # a placeholder in DOI format, not a real DOI
FAKE_ISBN = "978-0-00-000000-2"         # zeros with a valid ISBN-13 check digit, a placeholder
FAKE_PMID = "12345678"


# ----- text checks -----------------------------------------------------------------------------------

DIRECTION_WRONG = [
    "RNA polymerase synthesises the mRNA 3′ to 5′.",
    "DNA polymerase adds nucleotides to the new strand from 3' to 5'.",
    "The ribosome moves along the mRNA from 3' to 5'.",
    "The polypeptide grows from the C-terminus to the N-terminus during translation.",
    "Kinesin carries the vesicle towards the minus end.",
    "Dynein walks to the plus end of the microtubule.",
    "Complex I pumps protons into the matrix.",
    "In the light, protons are pumped into the stroma.",
    "The sodium-potassium pump moves sodium into the cell.",
]
DIRECTION_RIGHT = [
    "RNA polymerase reads the template 3′ to 5′ and makes RNA 5′ to 3′.",
    "The ribosome reads the mRNA 5′→3′, and the chain grows from N to C.",
    "Kinesin walks to the plus end and dynein to the minus end.",
    "Protons flow back into the matrix through ATP synthase.",
    "The pump moves three sodium ions out of the cell and two potassium ions into the cell.",
    "DNA polymerase proofreads 3' to 5'.",
    "The lagging strand grows 3' to 5' overall, in Okazaki fragments.",
    "The anticodon 3'-UAC-5' pairs with the codon AUG.",
    "Kinesin-14 walks towards the minus end.",
    "RNA is never made 3' to 5'.",
]


@pytest.mark.parametrize("text", DIRECTION_WRONG)
def test_wrong_directions_are_found(text: str) -> None:
    assert len(acc.direction_claims(text)) == 1, text


@pytest.mark.parametrize("text", DIRECTION_RIGHT)
def test_right_directions_are_left_alone(text: str) -> None:
    assert acc.direction_claims(text) == []


def test_places_of_processes() -> None:
    wrong = ["Glycolysis takes place in the mitochondria.", "Translation happens in the nucleus.", "The citric acid cycle runs in the cytosol.",
             "Transcription occurs in the cytoplasm.", "The Calvin cycle takes place in the thylakoid lumen."]
    for text in wrong:
        found = acc.location_claims(text)
        assert len(found) == 1, text
    assert "cytosol" in acc.location_claims(wrong[0])[0].message
    right = ["Glycolysis in the cytosol makes pyruvate.", "Transcription factors in the cytoplasm wait for a signal.",
             "The mRNA made by transcription travels in the cytoplasm.", "Glycolysis does not take place in the mitochondria.",
             "Reverse transcription happens in the cytoplasm.", "The citric acid cycle runs in the matrix."]
    assert [t for t in right if acc.location_claims(t)] == []
    assert acc.location_claims("The citric acid cycle runs in the cytosol.", prokaryote=True) == []   # right in bacteria
    assert acc.location_claims("In bacteria, transcription occurs in the cytoplasm.") == []


def test_counts() -> None:
    wrong = {
        "Glycolysis yields a net 4 ATP.": "net 2 ATP",
        "Each turn of the citric acid cycle makes two NADH.": "3 NADH",
        "The sodium-potassium pump moves two sodium ions out and three potassium ions in.": "3 Na⁺",
        "NADH feeds the chain: 12 protons are pumped per NADH.": "10 H⁺",
        "Mitosis produces four daughter cells.": "2 daughter cells",
        "There are four stop codons.": "3 stop codons",
        "Human cells have 48 chromosomes.": "46 chromosomes",
        "Complex II pumps two protons.": "no protons",
    }
    for text, says in wrong.items():
        found = acc.count_claims(text)
        assert found and says in found[0].message, (text, found)
    right = ["Glycolysis yields a net two ATP and two NADH.", "Each turn of the citric acid cycle makes three NADH and one FADH2.",
             "Per glucose, the citric acid cycle makes 6 NADH.", "The citric acid cycle makes 3 NADH per turn.",
             "Electrons from NADH pass through complexes one, three and four; ten protons are pumped.", "Meiosis produces four haploid cells.",
             "Meiosis I produces two cells.", "A nucleosome wraps 147 base pairs.", "In the payoff phase each triose yields NADH and two ATP.",
             "Two ATP are invested to phosphorylate and split glucose.", "A human gamete has 23 chromosomes."]
    assert [t for t in right if acc.count_claims(t)] == []


def test_pathway_claims() -> None:
    names = {"akt": "akt", "tsc2": "tsc2", "rheb": "rheb", "pka": "pka", "creb": "creb"}
    arcs = {("akt", "tsc2"): (-1, "phosphorylates"), ("tsc2", "rheb"): (-1, "inhibits"), ("pka", "creb"): (1, "phosphorylates")}
    for text in ["Akt activates TSC2.", "TSC2 is activated by Akt.", "PKA inhibits CREB.", "PKA dephosphorylates CREB."]:
        assert len(acc.pathway_claims(text, names, arcs)) == 1, text
    for text in ["Akt inhibits TSC2, which inhibits Rheb.", "PKA phosphorylates and activates CREB.", "Akt phosphorylates TSC2.",
                 "Rheb activates something else."]:
        assert acc.pathway_claims(text, names, arcs) == [], text


def test_naming_claims() -> None:
    mouse = [acc.GeneName("Trp53", "mouse", acc.protein_form("Trp53", "mouse"))]
    assert acc.protein_form("CDC28", "yeast") == "Cdc28" and acc.protein_form("lacZ", "e_coli") == "LacZ"
    assert "the gene is written Trp53" in acc.naming_claims("The TRP53 gene", mouse)[0].message
    assert "its protein is written TRP53" in acc.naming_claims("Trp53 protein", mouse)[0].message
    assert "written Trp53" in acc.naming_claims("the trp53 locus", mouse)[0].message
    assert "<i>Trp53</i>" in acc.naming_claims("Trp53 gene", mouse, markup=True)[0].message
    assert acc.naming_claims("<i>Trp53</i> gene and TRP53 protein", mouse, markup=True) == []
    human = [acc.GeneName("TP53", "human", "TP53")]
    assert acc.naming_claims("TP53 protein, the TP53 gene", human) == []           # roman text: case is all there is
    assert "roman" in acc.naming_claims("<i>TP53</i> protein", human, markup=True)[0].message


def test_transport_words() -> None:
    assert acc.says_active("Potassium leaves the cell by active transport.")
    assert acc.says_active("Glucose enters by secondary active transport with sodium.") is None
    assert acc.says_passive("Glucose moves by facilitated diffusion.")
    assert acc.transport_mode("carrier", None) == "passive" and acc.transport_mode("carrier", "symport") == "secondary"
    assert acc.transport_mode("na_k_atpase", None) == "primary" and acc.transport_mode("gpcr", None) is None


# ----- scene checks ----------------------------------------------------------------------------------


def _project(make_project, scenes: list[dict[str, Any]], **extra: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, **extra)))


def _found(project: Project, scene_id: str) -> list[tuple[str, str | None, str]]:
    import vidgen.scenes  # noqa: F401 - registers the built-in scene types

    return [(f.rule, f.beat, f.message) for f in science_issues(project, scene_id, LintRules())]


def test_rules_are_registered_in_config_order() -> None:
    k = LINT_RULES.index(SCIENCE_RULES[0])
    assert list(LINT_RULES[k:k + len(SCIENCE_RULES)]) == list(SCIENCE_RULES)
    for name in SCIENCE_RULES:
        assert RULES[name].scope == "scene" and RULES[name].default == "warning"


def test_cell_scale(make_project) -> None:
    cell = {"id": "c", "type": "cell", "params": {"contents": "none", "objects": [
        {"kind": "mitochondrion", "id": "big", "size": "7 um", "at": [0, 0]},
        *({"kind": "centrosome", "id": f"c{k}", "at": [-6 + 3 * k, -4]} for k in range(3))]},
            "beats": [{"text": "A cell."}]}
    found = _found(_project(make_project, [cell]), "c")
    rules = [f[0] for f in found]
    assert rules.count("science_scale") == 2, found
    assert any("objects[0] (mitochondrion 'big'): size 7 µm is far outside" in f[2] for f in found)
    assert any("3 of kind centrosome" in f[2] for f in found)
    cell["params"]["not_to_scale"] = True
    found = _found(_project(make_project, [cell]), "c")
    assert [f for f in found if "size 7" in f[2]] == []                   # the scene says so
    cell["params"].update({"not_to_scale": False, "scale_bar": False})
    assert [f for f in _found(_project(make_project, [cell]), "c") if "size 7" in f[2]] == []


def test_cell_placement_and_text(make_project) -> None:
    cell = {"id": "c", "type": "cell", "params": {},
            "beats": [{"text": "Ribosomes in the nucleus make proteins."}, {"text": "Ribosomes in the cytosol make proteins."},
                      {"text": "Glycolysis takes place in the mitochondria."}]}
    found = _found(_project(make_project, [cell]), "c")
    assert sorted((f[0], f[1]) for f in found) == [("science_location", "c_b1"), ("science_location", "c_b3")], found
    assert any("the scene shows them in the cytosol" in f[2] for f in found)


def test_molecule_energy(make_project) -> None:
    scene = {"id": "m", "type": "molecule", "params": {"membrane": "plasma", "molecules": [{"kind": "ion_channel", "id": "kv", "ion": "K+",
                                                                                           "state": "open"}], "solutes": ["K+"]},
             "beats": [{"text": "Potassium leaves the cell by active transport.", "actions": [{"transport": "kv", "count": 2}]}]}
    found = _found(_project(make_project, [scene]), "m")
    assert [f[0] for f in found] == ["science_energy"] and "passive" in found[0][2]
    scene["beats"][0]["text"] = "Potassium leaves the cell down its gradient."
    assert _found(_project(make_project, [scene]), "m") == []


def test_pathway_and_naming(make_project) -> None:
    scene = {"id": "p", "type": "pathway", "params": {"template": "pi3k_akt", "title": "Akt and the BCL2L11 protein"},
             "beats": [{"text": "Akt activates TSC2."}, {"text": "Akt inhibits TSC2."}]}
    found = _found(_project(make_project, [scene]), "p")
    assert [(f[0], f[1]) for f in found] == [("science_pathway", "p_b1")], found
    mouse = {"id": "q", "type": "molecule", "params": {"species": "mouse", "title": "The TRP53 gene",
                                                       "molecules": [{"kind": "protein", "gene": "Trp53", "protein": "TRP53",
                                                                      "label": "Trp53 gene"}]},
             "beats": [{"text": "The Trp53 protein is shown."}]}
    found = _found(_project(make_project, [mouse]), "q")
    assert sorted(f[0] for f in found) == ["science_naming"] * 3, found
    assert any(f[2].startswith("title 'The TRP53 gene'") for f in found)
    assert any("molecules[0].label" in f[2] and "<i>Trp53</i>" in f[2] for f in found)


def test_narration_rules_know_the_targets(make_project) -> None:
    from vidgen.lint.narration_rule import SHOWING_ACTIONS, target_texts

    assert {"zoom_to", "advance", "signal", "transcribe"} <= SHOWING_ACTIONS
    p = _project(make_project, [{"id": "p", "type": "pathway", "params": {"template": "pi3k_akt"}, "beats": [{"text": "x"}]},
                                {"id": "c", "type": "cell", "params": {}, "beats": [{"text": "x"}]},
                                {"id": "b", "type": "bullets", "params": {"items": ["x"]}, "beats": [{"text": "x"}]}])
    _found(p, "p")                                   # registers the scene types
    assert target_texts(p, "p")("akt") == "Akt" and target_texts(p, "p")("nope") is None
    assert target_texts(p, "c")("mitochondria") == "Mitochondria" and target_texts(p, "c")("cell") is None
    assert target_texts(p, "b")("item1") is None


def test_rules_off_and_other_scene_types(make_project) -> None:
    p = _project(make_project, [{"id": "b", "type": "bullets", "params": {"items": ["x"]}, "beats": [{"text": "Glycolysis yields a net 4 ATP."}]}],
                 lint={"rules": {"science_counts": {"severity": "off"}}})
    assert science_issues(p, "b", p.config.lint.rules) == []
    assert [f[0] for f in _found(p, "b")] == ["science_counts"]       # with the default rules


# ----- references ------------------------------------------------------------------------------------


def test_identifier_formats() -> None:
    assert normal_doi("https://doi.org/" + FAKE_DOI) == FAKE_DOI and normal_doi("doi:" + FAKE_DOI) == FAKE_DOI
    assert normal_pmid("PMID: 12345678") == FAKE_PMID and normal_pmid(12345678) == FAKE_PMID
    assert normal_isbn("ISBN " + FAKE_ISBN) == FAKE_ISBN and normal_isbn("0-000-00000-0") == "0-000-00000-0"
    assert normal_url("https://example.org/a?b=1") == "https://example.org/a?b=1"
    for bad, call in [("11.1000/x", normal_doi), ("10.12/x", normal_doi), ("0123", normal_pmid), ("123456789", normal_pmid),
                      ("978-0-00-000000-3", normal_isbn), ("12345", normal_isbn), ("example.org", normal_url), ("http://a b", normal_url)]:
        with pytest.raises(ValueError):
            call(bad)


def _config(scenes: list[dict[str, Any]], **extra: Any) -> Any:
    return parse_config(minimal_config(scenes=scenes, **extra))


def test_reference_config_and_cites() -> None:
    refs = [{"id": "ex", "label": "Example et al. (placeholder)", "doi": FAKE_DOI}, {"label": "Example book (placeholder)", "isbn": FAKE_ISBN}]
    cfg = _config([{"id": "a", "type": "bullets", "params": {"items": ["x"]}, "references": refs, "beats": [{"text": "x", "cite": ["ex"]},
                                                                                                         {"text": "y", "cite": [2]}]},
                   {"id": "b", "type": "bullets", "params": {"items": ["x"]}, "beats": [{"text": "z"}],
                    "references": [{"label": "Same DOI again", "doi": "doi:10.0000/EXAMPLE.1"}, {"label": "PubMed (placeholder)", "pmid": FAKE_PMID}],
                    "figure_credit": {"text": "Micrograph: Example Lab (placeholder)", "license": "CC BY 4.0", "url": "https://example.org/x"}}])
    assert [n.number for n in video_references(cfg.scenes)] == [1, 2, 3]
    assert scene_numbers(cfg.scenes, "b") == [1, 3]                  # the same DOI keeps its number
    assert beat_numbers(cfg.scenes, "a") == {"a_b1": (1,), "a_b2": (2,)}
    text = description_text(cfg.scenes)
    assert text.splitlines()[:4] == ["References", f"[1] Example et al. (placeholder) https://doi.org/{FAKE_DOI}",
                                     f"[2] Example book (placeholder) ISBN {FAKE_ISBN}", f"[3] PubMed (placeholder) PMID: {FAKE_PMID}"]
    assert "- Micrograph: Example Lab (placeholder) (CC BY 4.0) https://example.org/x" in text
    assert marker([3, 1, 2]) == "[1–3]" and marker([1, 3]) == "[1, 3]" and marker([]) == ""
    for scene, says in [({"references": [{"label": "No identifier"}]}, "give its doi, pmid, isbn or url"),
                        ({"references": [{"label": "x", "doi": "10.1/x"}]}, "is not a DOI"),
                        ({"references": [{"label": "x", "doi": FAKE_DOI}], "beats": [{"text": "x", "cite": [2]}]}, "cite 2"),
                        ({"references": [{"label": "x", "doi": FAKE_DOI, "id": "example"}], "beats": [{"text": "x", "cite": ["exampel"]}]},
                         "did you mean 'example'"),
                        ({"beats": [{"text": "x", "cite": [1]}]}, "has no references to cite")]:
        data = {"id": "s", "type": "bullets", "params": {"items": ["x"]}, "beats": [{"text": "x"}], **scene}
        with pytest.raises(VidgenError, match=says.replace("(", r"\(")):
            _config([data])
    assert SceneConfig.model_validate({"id": "s", "type": "t", "beats": [{"text": "x"}], "figure_credit": "Image: placeholder"}).figure_credit.text


def test_description_file_has_chapters_then_references(tmp_path: Path) -> None:
    cfg = _config([{"id": "a", "type": "bullets", "params": {"items": ["x"]}, "beats": [{"text": "x"}],
                    "references": [{"label": "Example (placeholder)", "doi": FAKE_DOI}]}])
    path = tmp_path / "out_chapters.txt"
    chapters = [Chapter("Intro", None, "a", 0.0, 12.0, 1, 1, False)]
    write_youtube_list(path, chapters, description_text(cfg.scenes))
    assert path.read_text(encoding="utf-8") == f"0:00 Intro\n\nReferences\n[1] Example (placeholder) https://doi.org/{FAKE_DOI}\n"
    write_youtube_list(path, [], description_text(cfg.scenes))
    assert path.read_text(encoding="utf-8").startswith("References\n")
    write_youtube_list(path, chapters)
    assert path.read_text(encoding="utf-8") == "0:00 Intro\n"


def test_render_writes_the_references_into_the_description_file(make_project) -> None:
    from vidgen.render.pipeline import write_chapter_list

    scene = {"id": "a", "type": "bullets", "params": {"items": ["x"]}, "beats": [{"text": "x"}],
             "references": [{"label": "Example (placeholder)", "pmid": FAKE_PMID}]}
    p = _project(make_project, [scene])
    p.output_dir.mkdir(parents=True, exist_ok=True)       # the render makes it before the join
    path = write_chapter_list(p, True, {"chapters": []})
    assert path is not None and path.read_text(encoding="utf-8") == f"References\n[1] Example (placeholder) PMID: {FAKE_PMID}\n"
    p = _project(make_project, [scene], citations={"description": False})
    assert write_chapter_list(p, True, {"chapters": []}) is None and not path.exists()


def test_fingerprints_change_only_where_citations_are(make_project) -> None:
    scenes = [{"id": s, "type": "bullets", "params": {"items": ["x"]}, "beats": [{"text": "x"}]} for s in ("a", "b", "c")]
    before = {s: scene_fingerprint(_project(make_project, scenes), s) for s in ("a", "b", "c")}
    scenes[2]["references"] = [{"label": "Example (placeholder)", "doi": FAKE_DOI}]
    after = {s: scene_fingerprint(_project(make_project, scenes), s) for s in ("a", "b", "c")}
    assert before["a"] == after["a"]                                 # no citations here or next
    assert before["b"] != after["b"] and before["c"] != after["c"]   # the next scene's / its own


@pytest.mark.render
def test_citations_are_drawn_as_a_footer_and_reserve_room(make_project, media: Path) -> None:
    from test_overlays import bullets, objects_of, project, render

    scene = bullets("s", beats=2, references=[{"label": "Example (placeholder)", "doi": FAKE_DOI}, {"label": "Other (placeholder)", "pmid": FAKE_PMID}])
    scene["beats"][1]["cite"] = [2]
    p = project(make_project, [scene], [])
    rendered = render(p, "s", media, per_beat=1)
    texts = [[o["text"] for o in objects_of(f, "citations") if o["kind"] == "text"] for f in rendered.layout]
    assert texts[0] == []                                          # beat 1 cites nothing (beat 2 does): hidden
    assert "[2] Other (placeholder)" in " ".join(texts[-1]) and "[1]" not in " ".join(texts[-1])
    assert rendered.safe_box.y0 > rendered.frame_safe.y0                           # the footer keeps the bullets clear


@pytest.mark.render
def test_not_to_scale_note(make_project, media: Path) -> None:
    from test_overlays import project, render

    cell = {"id": "c", "type": "cell", "params": {"contents": "none", "not_to_scale": True,
                                                  "objects": [{"kind": "mitochondrion", "size": "7 um", "at": [0, 0]}]},
            "beats": [{"text": "one two three four five six seven eight"}]}
    rendered = render(project(make_project, [cell], []), "c", media, per_beat=1)
    assert "not to scale" in {o.get("text") for o in rendered.layout[-1]["objects"] if o["kind"] == "text"}


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")

"""Step 217 (DESIGN.md §96.13–96.15): HGVS notation on real coding sequences (the variant's
consequence from the genetic code, generation and parsing, the textbook variants), CRISPR–Cas9
(PAM finding, guide checks, the cut, NHEJ and HDR outcomes) and the laboratory methods (PCR
counts and primer checks, gel migration, Sanger calls, NGS reads and the variant call); the
``mutation``, ``crispr`` and ``dna_lab`` scenes validated and rendered in 16:9 and 9:16."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_actions import project_with, render
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.genetics import crispr as cr
from vidgen.genetics import dna_lab as lab
from vidgen.genetics import hgvs
from vidgen.genetics import mutation as mu
from vidgen.genetics.reference_genes import REFERENCE_GENES
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}
#: A target with several PAMs on both strands (the start of HBB with some flank).
TARGET = "GACTGCATCAGCTGAAGGTCACCATGGTGCATCTGACTCCTGAGGAGAAGTCTGCC"


def consequence(symbol: str, text: str, **kw: Any) -> hgvs.Consequence:
    return hgvs.consequence(REFERENCE_GENES[symbol].coding(), text, "variant", **kw)


# ----- the reference windows -------------------------------------------------------------------------------


def test_reference_windows_translate_to_their_protein() -> None:
    """Every window is a real coding sequence in frame: the genetic code gives the protein."""
    for symbol, gene in REFERENCE_GENES.items():
        cds = gene.coding()
        assert hgvs.translation(cds.seq, cds.frame_start) == gene.protein, symbol
        assert cds.first + len(cds.seq) - 1 == cds.last
        assert cds.codon_number(cds.first + cds.frame_start) == (cds.first + 2) // 3


def test_the_textbook_variants_give_their_published_protein_change() -> None:
    for symbol, gene in REFERENCE_GENES.items():
        for v in gene.variants:
            c = consequence(symbol, v.c)
            assert c.protein.text() == v.p, (symbol, v.c)
            assert c.dna.text() == hgvs.normalize(gene.coding(), c.edit).text() if c.edit else True


def test_sickle_cell_and_the_legacy_numbering() -> None:
    c = consequence("HBB", "c.20A>T")
    assert c.kind == "missense" and c.protein.text() == "p.(Glu7Val)" and c.protein.text("one") == "p.(E7V)"
    assert "Glu (acidic) → Val (hydrophobic)" in c.notes[0]
    # HGVS counts the initiator Met; the legacy name of the same change is Glu6Val
    stated = hgvs.parse_p("p.(Glu6Val)")
    with pytest.raises(VidgenError, match="HGVS counts the initiator Met"):
        hgvs.check_stated(stated, c.protein, "p.(Glu6Val)", c.protein.text(), c.wt_protein, 1)
    hgvs.check_stated(hgvs.parse_p("p.(Glu7Val)"), c.protein, "p.(Glu7Val)", c.protein.text(), c.wt_protein, 1)
    hgvs.check_stated(hgvs.parse_p("p.(E7V)"), c.protein, "p.(E7V)", c.protein.text(), c.wt_protein, 1)


def test_cftr_phe508del_keeps_isoleucine_507() -> None:
    cds = REFERENCE_GENES["CFTR"].coding()
    c = hgvs.consequence(cds, "c.1521_1523delCTT")
    assert c.kind == "inframe_del" and c.protein.text() == "p.(Phe508del)" and c.dna.text() == "c.1521_1523del"
    assert c.dna.shown == "c.1521_1523delCTT"                       # the author's form is kept
    assert c.wt_protein[:3] == "IIF" and c.mut_protein[:3] == "IIG"  # Ile506 Ile507 stay, Phe508 goes
    assert any("multiple of 3" in n for n in c.notes)
    # the 3′ rule: the same deletion written one base earlier is refused with the canonical form
    with pytest.raises(VidgenError, match=r"write c.1521_1523del"):
        hgvs.consequence(cds, "c.1520_1522del")
    with pytest.raises(VidgenError, match="is CTT in this sequence"):
        hgvs.consequence(cds, "c.1521_1523delCTA")


def test_frameshift_and_nonsense_notation() -> None:
    gjb2 = consequence("GJB2", "c.35delG")
    assert gjb2.kind == "frameshift" and gjb2.protein.text() == "p.(Gly12Valfs*2)"
    assert gjb2.protein.text(stop="Ter") == "p.(Gly12ValfsTer2)" and gjb2.protein.fs == 2
    assert gjb2.mut_protein == "MDWGTLQTILGV*"                       # Gly12 becomes Val, then a stop
    cftr = consequence("CFTR", "c.1657C>T")
    assert cftr.kind == "nonsense" and cftr.protein.text() == "p.(Arg553*)" and cftr.protein.text(stop="Ter") == "p.(Arg553Ter)"
    hbb = consequence("HBB", "c.118C>T")
    assert hbb.protein.text() == "p.(Gln40*)"
    assert any("nonsense-mediated decay is expected" in n for n in hbb.notes)   # 195 nt before the last junction
    assert any("no nonsense-mediated decay" in n for n in gjb2.notes)            # the only coding exon


def test_silent_in_frame_and_other_classes() -> None:
    cds = REFERENCE_GENES["GJB2"].coding()
    assert hgvs.consequence(cds, "c.12C>T").kind == "synonymous"
    assert hgvs.consequence(cds, "c.12C>T").protein.text() == "p.(Gly4=)"
    assert hgvs.consequence(cds, "c.13_15del").protein.text() == "p.(Thr5del)"
    assert hgvs.consequence(cds, "c.3G>A").protein.text() == "p.(Met1?)"        # the start codon
    assert hgvs.consequence(cds, "c.10_11delinsTAA").kind == "nonsense"
    dup = hgvs.consequence(cds, "c.35dup")
    assert dup.kind == "frameshift" and dup.protein.fs is None and dup.protein.text().endswith("fs*?)")
    with pytest.raises(VidgenError, match="an insertion that copies the bases just before it is a duplication"):
        hgvs.consequence(cds, "c.35_36insG")


def test_splice_site_variants_are_predicted_not_translated() -> None:
    acceptor = consequence("CFTR", "c.1585-1G>A")
    assert acceptor.kind == "splice_acceptor" and acceptor.protein.text() == "p.?"
    assert acceptor.skipped_exon == 1 and acceptor.rna == "r.(1585_1679del)" and acceptor.frame_kept is False
    donor = consequence("HBB", "c.92+1G>A")
    assert donor.kind == "splice_donor" and donor.retained_intron == 0        # the first intron of the window
    with pytest.raises(VidgenError, match="is G, not T"):
        consequence("HBB", "c.92+1T>A")
    with pytest.raises(VidgenError, match="counts into an intron from an exon's last base"):
        consequence("HBB", "c.91+1G>A")


def test_hgvs_errors_name_the_fix() -> None:
    cds = REFERENCE_GENES["HBB"].coding()
    for text, message in [("p.(Glu7Val)", "give the DNA change"), ("20A>T", "starts with c."), ("c.A20T", "writes the position first"),
                          ("c.20A→T", "written with >"), ("c.20a>t", "capitals"), ("c.0A>T", "there is no c.0"),
                          ("c.20A>A", "no change"), ("c.20_19del", "lower position first"), ("c.20A>TT", "deletion–insertion"),
                          ("c.76insT", "names the two bases it lies between"), ("c.1000A>T", "outside the sequence given")]:
        with pytest.raises(VidgenError, match=message):
            hgvs.consequence(cds, text)
    for text, message in [("p.R553X", "X means an unknown amino acid"), ("p.ΔF508", "legacy name"), ("Glu7Val", "starts with p.")]:
        with pytest.raises(VidgenError, match=message):
            hgvs.parse_p(text)


def test_mutation_plan_checks_the_authors_protein_change() -> None:
    plan = mu.build_mutation_plan({"gene": "HBB", "variant": {"c": "c.20A>T", "p": "p.(Glu7Val)"}})
    assert plan.symbol == "HBB" and plan.transcript == "NM_000518.5" and plan.codon_range() == (1, 50)
    assert plan.variants[0].legacy.startswith("HbS")
    with pytest.raises(VidgenError, match="does not follow from the DNA change"):
        mu.build_mutation_plan({"gene": "HBB", "variant": {"c": "c.20A>T", "p": "p.(Glu7Lys)"}})
    with pytest.raises(VidgenError, match="not a reference sequence here"):
        mu.build_mutation_plan({"gene": "HBBB", "variant": "c.20A>T"})
    own = mu.build_mutation_plan({"sequence": "ATGGTGCATCTGACTCCT", "variant": "c.4G>T", "symbol": "TEST"})
    assert own.variants[0].consequence.protein.text() == "p.(Val2Leu)"
    gene = mu.build_mutation_plan({"gene": {"protein": "MVHLTPEEK", "introns": 1}, "variant": "c.1A>G"})
    assert gene.cds.exons and gene.variants[0].consequence.protein.kind == "start_loss"


# ----- CRISPR ----------------------------------------------------------------------------------------------


def test_pam_finding_and_the_cut_position() -> None:
    cas = cr.CAS["SpCas9"]
    guides = cr.find_guides(TARGET, cas)
    assert guides and all(len(g.spacer) == 20 for g in guides)
    for g in guides:
        pam = TARGET[g.pam_start:g.pam_end] if g.strand == "+" else None
        if g.strand == "+":
            assert pam[1:] == "GG" and g.pam_start == g.end          # the PAM follows the protospacer's 3′ end
            assert g.cut == g.end - 3                                 # blunt cut 3 bp upstream of the PAM
        else:
            assert g.pam_end == g.start and g.cut == g.start + 3
        assert 0.0 <= g.gc <= 1.0 and g.rna == g.spacer.replace("T", "U")
    assert cr.pam_matches("TGG", "NGG") and not cr.pam_matches("TGA", "NGG")
    assert cr.pam_matches("AAGAAT", "NNGRRT") and not cr.pam_matches("AAGAAC", "NNGRRT")


def test_guides_are_checked_against_the_pam() -> None:
    cas = cr.CAS["SpCas9"]
    good = cr.find_guides(TARGET, cas)[0]
    assert cr.check_guide(TARGET, cas, good.spacer).cut == good.cut
    assert cr.check_guide(TARGET, cas, good.rna).strand == good.strand          # an RNA spacer reads too
    with pytest.raises(VidgenError, match="needs the PAM NGG"):
        cr.check_guide(TARGET, cas, TARGET[2:22])
    with pytest.raises(VidgenError, match="the PAM is in the DNA, not in the sgRNA"):
        cr.check_guide(TARGET, cas, good.spacer + good.pam)
    with pytest.raises(VidgenError, match="uses a 21–23-nt spacer"):
        cr.check_guide(TARGET, cr.CAS["SaCas9"], good.spacer)
    with pytest.raises(VidgenError, match="SpCas9 uses a 20-nt spacer"):
        cr.check_guide(TARGET, cas, good.spacer[:18])
    with pytest.raises(VidgenError, match="written backwards"):
        cr.check_guide(TARGET, cas, good.spacer[::-1])
    with pytest.raises(VidgenError, match="no NGG PAM on either strand"):
        cr.build_crispr_plan({"target": "AAAAATTTTTAAAAATTTTTAAAAATTTTTAA"})


def test_nhej_and_hdr_outcomes() -> None:
    plan = cr.build_crispr_plan({"target": TARGET, "coding_first": None, "repair": "nhej"})
    rep = plan.repair
    assert rep.kind == "nhej" and len(rep.result) == len(TARGET) + 1
    assert any("blunt ends" in n for n in rep.notes)
    minus = cr.build_crispr_plan({"target": TARGET, "repair": "nhej", "indel": -4})
    assert len(minus.repair.result) == len(TARGET) - 4
    # on a coding sequence the outcome is written in HGVS with its protein change
    coding = "ATGGTGCATCTGACTCCTGAGGAGAAGTCTGCCGTTACTGCCCTGTGGGGCAAG"
    knock = cr.build_crispr_plan({"target": coding, "coding_first": 1, "repair": "nhej"})
    assert knock.repair.consequence.kind == "frameshift" and knock.repair.description.startswith("c.")
    assert any("knockout" in n for n in knock.repair.notes)
    hdr = cr.build_crispr_plan({"target": coding, "coding_first": 1, "repair": "hdr", "edit": "c.20A>T"})
    assert hdr.repair.description == "c.20A>T p.(Glu7Val)" and hdr.repair.result[19] == "T"
    assert any("no longer cut" in n or "cut it again" in n for n in hdr.repair.notes)
    with pytest.raises(VidgenError, match="c.20 is A in this sequence, not C"):
        cr.build_crispr_plan({"target": coding, "coding_first": 1, "repair": "hdr", "edit": "c.20C>T"})
    with pytest.raises(VidgenError, match=r"c\. numbers need coding_first"):
        cr.build_crispr_plan({"target": coding, "repair": "hdr", "edit": "c.20A>T"})
    with pytest.raises(VidgenError, match="it needs repair: hdr"):
        cr.build_crispr_plan({"target": coding, "repair": "nhej", "edit": "25A>T"})


# ----- the laboratory --------------------------------------------------------------------------------------


PCR_TEMPLATE = ("GCTTACCAGTCGATGCCATGACTGCATCAGCTGAAGGTCACCATGGTGCATCTGACTCCTGAGGAGAAGTCTGCCGTTACTGCCCTGTGGGGCAAGGTGAACGTGGATG"
                "AAGTTGGTGGTGAGGCCCTGGGCAGGCTGCTGGTGGTCTACCCTTGGACCCAGAGGTTCTTTGAGTCC")
PRIMERS = {"forward": "GACTGCATCAGCTGAAGGTC", "reverse": "CCAAGGGTAGACCACCAGCA"}


def test_pcr_primers_product_and_counts() -> None:
    p = lab.plan_pcr({"template": PCR_TEMPLATE, "primers": PRIMERS, "cycles": 30})
    assert p.product == p.r_end - p.f_at == 137
    assert 50 <= p.anneal <= 65 and p.anneal < min(p.tm_forward, p.tm_reverse) and p.denature == 95 and p.extend == 72
    # the strands simulated: the product of defined length first appears in cycle 3, then 2ⁿ − 2n
    for n in range(7):
        mols = lab.pcr_strands(p, n)[-1]
        exact = sum(1 for a, b in mols if (a.a, a.b) == (p.f_at, p.r_end) and (b.a, b.b) == (p.f_at, p.r_end))
        assert (len(mols), exact) == p.counts(n)
        assert exact == (2 ** n - 2 * n if n >= 1 else 0)
    assert p.counts(30) == (2 ** 30, 2 ** 30 - 60)
    assert lab.tm("GACTGCATCAGCTGAAGGTC") == pytest.approx(64.9 + 41 * (11 - 16.4) / 20)
    assert lab.tm("ACGTACGTACGT") == 2 * 6 + 4 * 6                       # Wallace rule below 14 nt


def test_pcr_primer_errors() -> None:
    swapped = {"forward": PRIMERS["reverse"], "reverse": PRIMERS["forward"]}
    with pytest.raises(VidgenError, match="it matches the bottom strand"):
        lab.plan_pcr({"template": PCR_TEMPLATE, "primers": swapped})
    with pytest.raises(VidgenError, match="a reverse primer is the reverse complement"):
        lab.plan_pcr({"template": PCR_TEMPLATE, "primers": {**PRIMERS, "reverse": "TGCTGGTGGTCTACCCTTGG"}})
    with pytest.raises(VidgenError, match="15–35 nt"):
        lab.plan_pcr({"template": PCR_TEMPLATE, "primers": {**PRIMERS, "forward": "GACTGCATCA"}})
    with pytest.raises(VidgenError, match="at or above a primer's Tm"):
        lab.plan_pcr({"template": PCR_TEMPLATE, "primers": PRIMERS, "temperatures": {"anneal": 70}})
    with pytest.raises(VidgenError, match="the strands separate at 94–98"):
        lab.plan_pcr({"template": PCR_TEMPLATE, "primers": PRIMERS, "temperatures": {"denature": 99.5}})


def test_gel_migration_is_monotonic_in_size() -> None:
    for agarose in (0.7, 1.0, 1.5, 2.0):
        lo, hi = lab.resolving_range(agarose)
        assert lo < hi
        sizes = [50, 100, 200, 500, 1000, 2000, 5000, 10000]
        distances = [lab.migration(s, agarose) for s in sizes]
        assert all(a > b for a, b in zip(distances, distances[1:]))      # smaller fragments run further
        assert all(0.0 < d < 1.0 for d in distances)
        # log-linear within the resolving range
        inside = [s for s in sizes if lo <= s <= hi]
        if len(inside) >= 3:
            import math

            slopes = [(lab.migration(a, agarose) - lab.migration(b, agarose)) / (math.log10(b) - math.log10(a))
                      for a, b in zip(inside, inside[1:])]
            assert max(slopes) - min(slopes) < 1e-6
    ladder = lab.LADDERS["100bp"]
    for size in (300, 450, 900):
        read = lab.size_from_distance(lab.migration(size, 1.5), ladder, 1.5)
        assert read == pytest.approx(size, rel=0.02)
    plan = lab.plan_gel({"agarose": 1.5, "ladder": "100bp", "lanes": {"PCR": [450], "digest": [300, 150]}})
    assert [lane.label for lane in plan.lanes] == ["100 bp", "PCR", "digest"] and plan.lanes[0].ladder
    assert any("outside a 1.5 % gel's range" in n for n in plan.notes)
    with pytest.raises(VidgenError, match="agarose gels are 0.5–3"):
        lab.plan_gel({"agarose": 4, "lanes": {"a": [100]}})
    with pytest.raises(VidgenError, match="did you mean"):
        lab.plan_gel({"ladder": "100bpp", "lanes": {"a": [100]}})


def test_sanger_calls_and_heterozygous_peaks() -> None:
    p = lab.plan_sanger({"sequence": "ATCATCTTTGGTGTTTCCTATG", "heterozygous": "8T>C"})
    assert p.calls == "ATCATCTYTGGTGTTTCCTATG" and p.het == {7: "C"}
    assert p.template == "TAGTAGAAACCACAAAGGATAC"[::-1] or len(p.template) == len(p.read)
    assert all(0.6 <= h <= 1.0 for h in p.heights)
    with pytest.raises(VidgenError, match="position 8 of the read is T, not A"):
        lab.plan_sanger({"sequence": "ATCATCTTTGGTGTTTCCTATG", "heterozygous": "8A>C"})
    with pytest.raises(VidgenError, match="write a position in the read"):
        lab.plan_sanger({"sequence": "ATCATCTTTGGT", "heterozygous": "T8C"})


def test_ngs_reads_and_the_variant_call() -> None:
    reference = "GACTGCATCAGCTGAAGGTCACCATGGTGCATCTGACTCCTGAGGAGAAGTCTG"
    het = lab.plan_ngs({"reference": reference, "variant": "26G>T", "depth": 20, "seed": 3})
    assert het.call == "heterozygous" and 0.15 <= het.vaf <= 0.85
    assert len(het.depth) == len(reference) and het.depth[het.position] >= 10
    assert all(lab.MIN_OVERLAP <= len(r.seq) <= het.read_length and 0 <= r.start <= len(reference) - len(r.seq) for r in het.reads)
    assert min(het.depth) >= 8                                             # clipped reads: even coverage up to the ends
    assert lab.plan_ngs({"reference": reference, "variant": "26G>T", "zygosity": "homozygous", "seed": 3}).call == "homozygous"
    assert lab.plan_ngs({"reference": reference, "variant": "26G>T", "zygosity": "absent", "seed": 3}).call == "none"
    assert lab.plan_ngs({"reference": reference, "variant": "26G>T", "depth": 4, "seed": 3}).call == "low coverage"
    rows = lab.pack_rows(het.reads)
    starts = {}
    for read, row in zip(het.reads, rows):                                # reads in a row do not touch
        assert starts.get(row, -1) < read.start
        starts[row] = read.start + len(read.seq)
    same = lab.plan_ngs({"reference": reference, "variant": "26G>T", "depth": 20, "seed": 3})
    assert [r.seq for r in same.reads] == [r.seq for r in het.reads]       # seeded: the same reads
    with pytest.raises(VidgenError, match="position 26 of the reference is G, not A"):
        lab.plan_ngs({"reference": reference, "variant": "26A>T"})


def test_ngs_deletion_near_the_window_edge() -> None:
    """Step 220: CFTR F508del (c.1521_1523del) read on the reference window c.1516–1575: the CTT is
    positions 6–8; alt reads carry gaps there and only reads spanning the stretch are counted."""
    from vidgen.genetics.reference_genes import REFERENCE_GENES

    reference = REFERENCE_GENES["CFTR"].seq[:60]
    plan = lab.plan_ngs({"reference": reference, "variant": "6_8delCTT", "depth": 24, "seed": 2})
    assert plan.kind == "deletion" and plan.ref == "CTT" and plan.site == "6_8delCTT" and (plan.position, plan.end) == (5, 8)
    assert plan.call == "heterozygous" and plan.site_depth >= 15
    gapped = [r for r in plan.reads if "-" in r.seq]
    assert gapped and all(r.alt for r in gapped)
    assert all(r.seq[5 - r.start:8 - r.start] == "---" for r in gapped if r.start <= 5 and r.start + len(r.seq) >= 8)
    assert plan.alt_reads == sum(1 for r in plan.reads if r.start <= 5 and r.start + len(r.seq) >= 8 and r.seq[5 - r.start] == "-")
    assert lab.plan_ngs({"reference": reference, "variant": "6_8del", "zygosity": "homozygous", "depth": 24, "seed": 2}).call == "homozygous"
    for bad, message in (("6_8delCAT", "are CTT, not CAT"), ("8_6del", "low to high"), ("1_3del", "both sides"),
                         ("6_30del", "1–12 bp"), ("6-8del", "write a position")):
        with pytest.raises(VidgenError, match=message):
            lab.plan_ngs({"reference": reference, "variant": bad})


def test_lab_params_belong_to_their_method() -> None:
    with pytest.raises(VidgenError, match="is a param of method: gel, not pcr"):
        lab.build_lab_plan({"method": "pcr", "template": PCR_TEMPLATE, "primers": PRIMERS, "agarose": 1.0})
    with pytest.raises(VidgenError, match="did you mean 'sanger'"):
        lab.build_lab_plan({"method": "sangr"})


# ----- in projects -------------------------------------------------------------------------------------------


def problems(make_project: Any, scene: dict[str, Any]) -> list[str]:
    return [p.message for p in project_problems(project_with(make_project, [scene], narration=NARRATION))]


def one(kind: str, params: dict[str, Any], actions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": "x", "type": kind, "params": params, "beats": [{"id": "b0", "text": "the sequence", "actions": actions or []}]}


def test_scenes_are_validated(make_project) -> None:
    assert problems(make_project, one("mutation", {"gene": "HBB", "variant": "c.20A>T"}, [{"mutate": "variant"}])) == []
    assert any("does not follow from the DNA change" in m
               for m in problems(make_project, one("mutation", {"gene": "HBB", "variant": {"c": "c.20A>T", "p": "p.(Glu7Lys)"}})))
    assert any("mutate acts on variant" in m
               for m in problems(make_project, one("mutation", {"gene": "HBB", "variant": "c.20A>T"}, [{"mutate": "variant:2"}])))
    assert problems(make_project, one("crispr", {"target": TARGET}, [{"scan": "dna"}, {"cleave": "cut"}, {"repair": "repair"}])) == []
    assert any("repair: none" in m
               for m in problems(make_project, one("crispr", {"target": TARGET, "repair": "none"}, [{"repair": "repair"}])))
    assert any("needs the PAM NGG" in m for m in problems(make_project, one("crispr", {"target": TARGET, "spacer": TARGET[2:22]})))
    assert problems(make_project, one("dna_lab", {"method": "gel", "lanes": {"PCR": [450]}}, [{"run": "sizes"}])) == []
    assert any("run plays a step of this method" in m
               for m in problems(make_project, one("dna_lab", {"method": "gel", "lanes": {"PCR": [450]}}, [{"run": "chromatogram"}])))
    assert any("is an action of mutation scenes" in m
               for m in problems(make_project, one("crispr", {"target": TARGET}, [{"mutate": "variant"}])))


# ----- renders -------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_molecular_scenes_render(size: tuple[int, int], make_project, media: Path) -> None:
    scenes = [
        {"id": "mut", "type": "mutation", "params": {"title": "HbS", "gene": "HBB", "variant": {"c": "c.20A>T", "p": "p.(Glu7Val)"}},
         "beats": [{"text": "the coding sequence"}, {"text": "one base changes", "actions": [{"mutate": "variant"}]}]},
        {"id": "few", "type": "mutation", "params": {"gene": "CFTR", "variant": "c.1521_1523del", "codons": 3},
         "beats": [{"text": "three codons"}, {"text": "three bases go", "actions": [{"mutate": "variant"}]}]},
        {"id": "splice", "type": "mutation", "params": {"gene": "CFTR", "variant": "c.1585-1G>A"},
         "beats": [{"text": "the acceptor site"}, {"text": "the exon is skipped"}]},
        {"id": "edit", "type": "crispr", "params": {"title": "Cas9", "target": TARGET, "repair": "nhej"},
         "beats": [{"text": "the target"}, {"text": "the guide binds", "actions": [{"scan": "dna"}]},
                   {"text": "the break", "actions": [{"cleave": "dna"}]}, {"text": "the repair", "actions": [{"repair": "dna"}]}]},
        {"id": "pcr", "type": "dna_lab", "params": {"method": "pcr", "template": PCR_TEMPLATE, "primers": PRIMERS},
         "beats": [{"text": "primers"}, {"text": "cycles"}, {"text": "copies"}]},
        {"id": "gel", "type": "dna_lab", "params": {"method": "gel", "agarose": 1.5, "lanes": {"patient": [450], "control": [450, 300]}},
         "beats": [{"text": "the gel"}, {"text": "the run"}, {"text": "the sizes"}]},
        {"id": "sanger", "type": "dna_lab", "params": {"method": "sanger", "sequence": "ATCATCTTTGGTGTTTCC", "heterozygous": "8T>C"},
         "beats": [{"text": "termination"}, {"text": "separation"}, {"text": "the trace"}]},
        {"id": "ngs", "type": "dna_lab", "params": {"method": "ngs", "reference": "GACTGCATCAGCTGAAGGTCACCATGGTGCATCTGACTCC",
                                                    "variant": "26G>T", "depth": 10},
         "beats": [{"text": "reads"}, {"text": "the call"}]},
    ]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 3.0})))
    mut = render(project, "mut", media, size)
    assert 0 in mut.made and mut.var_row is not None and mut.card is not None
    assert mut.plan.variants[0].p_text == "p.(Glu7Val)"
    few = render(project, "few", media, size)       # Step 221: few codons in 16:9 — the card beside larger rows
    assert few.side == (size[0] > size[1]) and few.card is not None
    if few.side:
        assert few.card.get_left()[0] >= max(t.get_right()[0] for t in few.ref_row.tiles.values())
    splice = render(project, "splice", media, size)
    assert splice.mrna is not None and splice.plan.variants[0].consequence.skipped_exon == 1
    edit = render(project, "edit", media, size)
    assert {"dna", "scan", "cleave", "repair"} <= edit.done and edit.card_mob is not None
    pcr = render(project, "pcr", media, size)
    assert {"setup", "cycle", "count"} <= pcr.done
    gel = render(project, "gel", media, size)
    assert {"setup", "run", "read"} <= gel.done and len(gel.gel_bands) == 3
    # Step 221: the ladder's sizes stand outside the plate, left of it; the lanes inside it
    assert all(t.get_right()[0] <= gel.gel_x0 for t in gel.ladder_labels)
    assert gel.gel_x0 < min(gel.lane_x) and max(gel.lane_x) < gel.gel_x0 + gel.gel_w
    sanger = render(project, "sanger", media, size)
    assert {"setup", "separate", "trace"} <= sanger.done and len(sanger.peak_groups) == 18
    ngs = render(project, "ngs", media, size)
    assert {"setup", "align", "call"} <= ngs.done and ngs.plan.ngs.call in ("heterozygous", "low coverage")

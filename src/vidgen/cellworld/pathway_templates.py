"""Built-in signalling pathways (DESIGN.md §95.12), usable as they are (``template:
gpcr_camp_pka``) or as a start that ``nodes``, ``edges`` and ``remove`` change. Each follows
the textbook account (Alberts, *Molecular Biology of the Cell*, ch. 15; Lodish, *Molecular Cell
Biology*, ch. 15–16), human nomenclature, and draws only what the textbooks agree on. No manim.

- ``gpcr_camp_pka`` — glucagon on a hepatocyte: the glucagon receptor (a Gs-coupled GPCR) acts
  as the GEF of Gαs (GDP → GTP); Gαs-GTP activates adenylyl cyclase, which makes cAMP from ATP;
  cAMP binds the regulatory subunits of PKA and frees the catalytic subunits, which enter the
  nucleus and phosphorylate CREB on Ser133; CREB with CBP drives *PCK1* (PEPCK) and
  gluconeogenesis. Phosphodiesterase 4 hydrolyses cAMP to AMP, and PKA phosphorylates and
  activates PDE4: negative feedback.
- ``rtk_ras_mapk`` — EGF on EGFR: the receptor dimerises and autophosphorylates; Grb2's SH2
  domain binds its phosphotyrosines and brings SOS (bound to Grb2's SH3 domains) to the
  membrane, where SOS, a GEF, loads Ras with GTP; Ras-GTP recruits and activates Raf (a
  MAPKKK), which phosphorylates MEK (a MAPKK), which phosphorylates ERK (a MAPK) on its
  Thr-Glu-Tyr motif; ERK enters the nucleus and phosphorylates Elk-1, which with SRF drives *FOS*
  (an immediate-early gene) towards proliferation. A Ras GAP (p120RasGAP, NF1) speeds GTP
  hydrolysis; ERK phosphorylates SOS, which leaves Grb2: negative feedback.
- ``pi3k_akt`` — a growth factor on an RTK recruits class I PI3K, which phosphorylates
  PI(4,5)P₂ to PI(3,4,5)P₃; PTEN removes that 3-phosphate (PIP₃ → PIP₂), opposing PI3K. PIP₃
  recruits PDK1 and Akt by their PH domains; PDK1 phosphorylates Akt on Thr308 and mTORC2 on
  Ser473. Akt phosphorylates and inhibits TSC2 (the GAP of Rheb), so Rheb-GTP activates mTORC1
  (protein synthesis, cell growth); it phosphorylates GSK3β on Ser9 (inhibiting it) and FOXO
  (14-3-3 binds it and it is kept out of the nucleus, so its pro-apoptotic target genes such
  as *BCL2L11*, encoding BIM, are not transcribed).
"""

from __future__ import annotations

from .pathway import EdgeSpec, NodeSpec, PathwaySpec


def _n(id: str, kind: str, label: str, compartment: str | None = None, gene: str | None = None) -> NodeSpec:
    return NodeSpec(id, kind, label, compartment, gene, where=f"template node '{id}'")


def _e(source: str, target: str, type: str = "activates", **kw: object) -> EdgeSpec:
    return EdgeSpec(source, target, type, where=f"template arc {source} -> {target}", **kw)  # type: ignore[arg-type]


GPCR_CAMP_PKA = PathwaySpec(
    nodes=(
        _n("glucagon", "ligand", "Glucagon"),
        _n("gcgr", "receptor", "GCGR", gene="GCGR"),
        _n("gas", "g_protein", "Gα_s", gene="GNAS"),
        _n("ac", "enzyme", "Adenylyl cyclase", "plasma_membrane"),
        _n("camp", "small_molecule", "cAMP"),
        _n("pde", "enzyme", "PDE4"),
        _n("pka", "kinase", "PKA"),
        _n("pka_n", "kinase", "PKA", "nucleus"),
        _n("creb", "transcription_factor", "CREB", gene="CREB1"),
        _n("pck1", "gene", "PCK1"),
        _n("gluconeogenesis", "phenotype", "Gluconeogenesis"),
    ),
    edges=(
        _e("glucagon", "gcgr"),
        _e("gcgr", "gas", label="GEF: GDP → GTP"),
        _e("gas", "ac"),
        _e("ac", "camp", "catalyses", label="ATP → cAMP"),
        _e("camp", "pka", "binds", label="frees C subunits"),
        _e("pde", "camp", "inhibits", label="cAMP → AMP"),
        _e("pka", "pde", "phosphorylates", feedback=True),
        _e("pka", "pka_n", "translocates"),
        _e("pka_n", "creb", "phosphorylates", site="Ser133"),
        _e("creb", "pck1", "transcribes"),
        _e("pck1", "gluconeogenesis", "expresses"),
    ),
)

RTK_RAS_MAPK = PathwaySpec(
    nodes=(
        _n("egf", "ligand", "EGF"),
        _n("egfr", "receptor", "EGFR", gene="EGFR"),
        _n("ras", "gtpase", "Ras", "plasma_membrane"),
        _n("grb2", "adaptor", "Grb2"),
        _n("sos", "gef", "SOS"),
        _n("rasgap", "gap", "RasGAP"),
        _n("raf", "kinase", "Raf"),
        _n("mek", "kinase", "MEK"),
        _n("erk", "kinase", "ERK"),
        _n("erk_n", "kinase", "ERK", "nucleus"),
        _n("elk1", "transcription_factor", "Elk-1", gene="ELK1"),
        _n("fos", "gene", "FOS"),
        _n("proliferation", "phenotype", "Proliferation"),
    ),
    edges=(
        _e("egf", "egfr"),
        _e("egfr", "grb2", "binds", label="SH2 on pTyr"),
        _e("grb2", "sos", "binds"),
        _e("sos", "ras", label="GEF: GDP → GTP"),
        _e("rasgap", "ras", "inhibits", label="GTP → GDP"),
        _e("ras", "raf"),
        _e("raf", "mek", "phosphorylates"),
        _e("mek", "erk", "phosphorylates"),
        _e("erk", "sos", "phosphorylates", effect="inhibits", feedback=True),
        _e("erk", "erk_n", "translocates"),
        _e("erk_n", "elk1", "phosphorylates"),
        _e("elk1", "fos", "transcribes"),
        _e("fos", "proliferation", "expresses"),
    ),
)

PI3K_AKT = PathwaySpec(
    nodes=(
        _n("gf", "ligand", "Growth factor"),
        _n("rtk", "receptor", "RTK"),
        _n("pip2", "small_molecule", "PIP2", "plasma_membrane"),
        _n("pip3", "small_molecule", "PIP3", "plasma_membrane"),
        _n("pi3k", "kinase", "PI3K"),
        _n("pten", "phosphatase", "PTEN", gene="PTEN"),
        _n("pdk1", "kinase", "PDK1", gene="PDPK1"),
        _n("mtorc2", "complex", "mTORC2"),
        _n("akt", "kinase", "Akt", gene="AKT1"),
        _n("tsc2", "gap", "TSC2", gene="TSC2"),
        _n("rheb", "gtpase", "Rheb"),
        _n("mtorc1", "complex", "mTORC1"),
        _n("gsk3b", "kinase", "GSK3β", gene="GSK3B"),
        _n("growth", "phenotype", "Cell growth"),
        _n("foxo", "transcription_factor", "FOXO"),
        _n("bcl2l11", "gene", "BCL2L11"),
        _n("apoptosis", "phenotype", "Apoptosis"),
    ),
    edges=(
        _e("gf", "rtk"),
        _e("rtk", "pi3k"),
        _e("pip2", "pip3", "converts"),
        _e("pi3k", "pip3", "catalyses"),
        _e("pten", "pip3", "dephosphorylates"),
        _e("pip3", "pdk1", "binds"),
        _e("pip3", "akt", "binds"),
        _e("pdk1", "akt", "phosphorylates", site="Thr308"),
        _e("mtorc2", "akt", "phosphorylates", site="Ser473"),
        _e("akt", "tsc2", "phosphorylates", effect="inhibits"),
        _e("tsc2", "rheb", "inhibits"),
        _e("rheb", "mtorc1"),
        _e("mtorc1", "growth"),
        _e("akt", "gsk3b", "phosphorylates", effect="inhibits", site="Ser9"),
        _e("akt", "foxo", "phosphorylates", effect="inhibits", label="nuclear exclusion"),
        _e("foxo", "bcl2l11", "transcribes"),
        _e("bcl2l11", "apoptosis", "expresses"),
    ),
)

#: The built-in pathways by name.
TEMPLATES: dict[str, PathwaySpec] = {
    "gpcr_camp_pka": GPCR_CAMP_PKA,
    "rtk_ras_mapk": RTK_RAS_MAPK,
    "pi3k_akt": PI3K_AKT,
}
#: One line per template, for the docs and the schema.
TEMPLATE_NOTES: dict[str, str] = {
    "gpcr_camp_pka": "glucagon → GCGR → Gαs → adenylyl cyclase → cAMP → PKA → CREB (Ser133) → PCK1; PDE4 hydrolyses cAMP (PKA → PDE4 feedback)",
    "rtk_ras_mapk": "EGF → EGFR → Grb2/SOS → Ras-GTP → Raf → MEK → ERK → Elk-1 → FOS; RasGAP and ERK ⊣ SOS feedback",
    "pi3k_akt": "growth factor → RTK → PI3K → PIP3 (PTEN opposes) → PDK1 / mTORC2 → Akt ⊣ TSC2 ⊣ Rheb → mTORC1; Akt ⊣ GSK3β, ⊣ FOXO",
}

__all__ = ["GPCR_CAMP_PKA", "PI3K_AKT", "RTK_RAS_MAPK", "TEMPLATES", "TEMPLATE_NOTES"]

"""The steps of gene expression as beat actions (DESIGN.md §95.11): ``transcribe``, ``cap``,
``splice``, ``polyadenylate``, ``export``, ``translate``, ``target_er``, ``glycosylate``,
``fold`` act on the gene of a ``molecule`` scene (a molecular close-up); ``transcribe``,
``export``, ``translate``, ``to_golgi`` and ``secrete`` on the gene of a ``cell`` scene (the
route through the cell, the camera following). Each is timed like any action (``at: "@word"``);
its default length follows what it shows (the nucleotides transcribed, the codons read) and
``run_time:`` overrides it. ``vidgen validate`` replays the steps in order and refuses one that
cannot come yet, with the reason (translation before export, glycosylation outside the ER…).
Written against ``vidgen.api``; the scenes do the drawing."""

from typing import Any, Literal

from vidgen.api import *

from .molecule_actions import _one_target, _process_problem


def _gene_step_problem(action: Action, scene_cls: type[NarratedScene], params: Any, name: str) -> list[tuple[str, str]]:
    """A molecule scene's checks, or a cell scene's, or the scene has no genes."""
    if name in getattr(scene_cls, "process_actions", ()):
        return _process_problem(action, scene_cls, params, name)
    if getattr(scene_cls, "cell_actions", False):
        problems = _one_target(action, name)
        if problems:
            return problems
        problem = scene_cls.expression_problem(params, name, action.config.targets()[0], action.options)  # type: ignore[attr-defined]
        return [("target", problem)] if problem else []
    return [("action", f"{name} is a step of gene expression: an action of molecule scenes with a gene (a close-up) and of cell "
                       f"scenes with a gene (the route through the cell)")]


class GeneStep(Action):
    """A step of gene expression on a scene's gene (base of the step actions)."""

    class Options(ActionOptions):
        notes: bool = True
        """Caption each step (what the molecules do)."""

    run_time = 8.0
    #: A molecule scene's close-up and a cell scene's route both move their view.
    moves_camera = True
    step = ""

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _gene_step_problem(self, scene_cls, params, self.step)

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        """As long as what it shows needs (its phases' weights, in seconds)."""
        self._clip = scene.expression_clip(self.step, self.options)  # type: ignore[attr-defined]
        return scene.expression_seconds(self._clip)  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Play the step."""
        clip = getattr(self, "_clip", None)
        self._clip = None
        return scene.run_expression(self.step, self.options, clip)  # type: ignore[attr-defined]


@action("transcribe")
class Transcribe(GeneStep):
    """Transcription of the gene (``transcribe: gene``). In a molecule scene: TFIID's TBP binds
    the TATA box, TFIIA, TFIIB, RNA polymerase II with TFIIF, TFIIE and TFIIH assemble the
    preinitiation complex, TFIIH opens a ~13 bp bubble at +1 and phosphorylates the CTD's Ser5;
    the polymerase reads the template strand 3′→5′ and makes RNA 5′→3′ (U pairs with A) with an
    8 bp RNA–DNA hybrid, caps the 5′ end at ~25 nt (unless the scene has its own cap step),
    transcribes introns and exons alike and runs past the poly(A) signal (a bacterium: σ⁷⁰ at
    the −35 and −10 boxes, termination at a terminator). In a cell scene: mRNAs are made at the
    gene in the nucleus (processing included)."""

    step = "transcribe"


@action("cap")
class Cap(GeneStep):
    """The 5′ cap as its own step (``cap: gene``, after transcribe): RNA triphosphatase,
    guanylyltransferase (G joined 5′–5′ by a triphosphate), guanine-N7 methyltransferase (m⁷G)."""

    step = "cap"


@action("splice")
class Splice(GeneStep):
    """Splicing (``splice: gene``): U1 snRNP on the 5′ splice site (GU), U2AF on the
    polypyrimidine tract and AG, U2 snRNP round the branch-point A, the tri-snRNP; the two
    transesterifications (the lariat; the exons joined); the lariat degraded and an EJC left
    ~24 nt upstream of each junction."""

    step = "splice"


@action("polyadenylate")
class Polyadenylate(GeneStep):
    """The 3′ end (``polyadenylate: gene``): CPSF on AAUAAA, CstF downstream, cleavage after a
    CA 10–30 nt on, Xrn2 and termination (torpedo), poly(A) polymerase and PABPN1."""

    step = "polyadenylate"


@action("export")
class Export(GeneStep):
    """Nuclear export (``export: gene``): a capped, spliced and polyadenylated mRNA (checked)
    with CBC, EJCs and PABPN1 and the export receptor NXF1–NXT1 goes through a nuclear pore 5′
    end first; Dbp5 remodels it in the cytosol, eIF4E and PABPC1 take over the ends. In a cell
    scene: mRNPs move to the nuclear pores and out."""

    step = "export"


@action("translate")
class Translate(GeneStep):
    """Translation (``translate: gene``; only in the cytoplasm — before export it is refused):
    initiation (eIF4F on the cap, the 43S complex scanning to the AUG, the 60S subunit joining;
    a bacterium's 30S at the Shine–Dalgarno sequence), elongation cycles (the aminoacyl-tRNA
    whose anticodon pairs with the codon, the peptide bond, translocation by one codon; the
    first two captioned, the rest fast), the stop codon read by a release factor, recycling.
    ``codons: n`` translates n codons and stops (target_er follows during translation). In a
    cell scene: ribosomes on the mRNA, on the rough ER for a protein with a signal peptide
    (then targeted, glycosylated and folded in the ER lumen)."""

    class Options(ActionOptions):
        codons: int | None = Field(None, ge=1, le=160)
        """How many codons to translate (default: to the stop codon)."""
        notes: bool = True
        """Caption each step."""

    step = "translate"


@action("target_er")
class TargetEr(GeneStep):
    """Co-translational targeting to the ER (``target_er: gene``, while the chain grows): the
    signal peptide leaves the exit tunnel, SRP binds it (elongation slows), docks on the SRP
    receptor, hands the ribosome to Sec61; the chain grows into the lumen with the signal in the
    lateral gate (N-terminus in the cytosol); signal peptidase cuts it off."""

    step = "target_er"


@action("glycosylate")
class Glycosylate(GeneStep):
    """N-linked glycosylation (``glycosylate: gene``, in the ER lumen): the
    oligosaccharyltransferase transfers Glc₃Man₉GlcNAc₂ (14 sugars, SNFG symbols) en bloc from
    dolichol-PP onto the Asn of each Asn-X-Ser/Thr sequon."""

    step = "glycosylate"


@action("fold")
class Fold(GeneStep):
    """Folding (``fold: gene``, once released): Hsp70 binds hydrophobic stretches and lets go, or
    the chaperonin TRiC folds the chain in its chamber (cytosol); BiP, or calnexin after two
    glucoses are trimmed (ER lumen); the chain packs its hydrophobic residues inside."""

    class Options(ActionOptions):
        chaperone: Literal["hsp70", "chaperonin", "bip", "calnexin"] | None = None
        """Which chaperone (checked against where the protein is); default hsp70 in the cytosol, calnexin (glycoproteins) or bip in the ER."""
        notes: bool = True
        """Caption each step."""

    step = "fold"


@action("to_golgi")
class ToGolgi(GeneStep):
    """ER to Golgi (``to_golgi: gene``, cell scenes): only a folded protein leaves the ER; COPII
    (Sar1, Sec23/24, Sec13/31) buds vesicles at an ER exit site, which fuse with the cis-Golgi;
    the protein passes cis → medial → trans by cisternal maturation while its N-glycan is
    trimmed and rebuilt."""

    step = "to_golgi"


@action("secrete")
class Secrete(GeneStep):
    """From the trans-Golgi network (``secrete: gene``, cell scenes): ``to: outside`` (a
    secretory vesicle fuses with the plasma membrane: exocytosis), ``lysosome`` (mannose
    6-phosphate receptors, clathrin-coated vesicles to the endosomes) or ``membrane`` (the
    protein stays in the vesicle's membrane and becomes part of the plasma membrane)."""

    class Options(ActionOptions):
        to: Literal["outside", "lysosome", "membrane"] = "outside"
        """Where the protein goes from the trans-Golgi network."""
        notes: bool = True
        """Caption each step."""

    step = "secrete"

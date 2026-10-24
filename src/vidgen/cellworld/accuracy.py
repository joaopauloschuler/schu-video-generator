"""The accuracy lint's knowledge (DESIGN.md §95.14): text checks of narration against textbook
facts — directions (5′→3′ synthesis, N→C, motors, pumps), where processes happen, numbers
(ATP, NADH, protons, ions per pump cycle, cells after division) — and the helpers the lint's
scene checks share (sentences, numbers, words for transport). Each check is narrow on purpose:
it reports a sentence only when the claim is clearly there (a negation, a question or a
comparison leaves the sentence alone), so correct material gives no findings. No manim."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass

# ----- text --------------------------------------------------------------------------------------

_PRIMES = str.maketrans({"’": "'", "‘": "'", "′": "'", "´": "'", "`": "'", "–": "-", "—": " - ", "−": "-"})
_SPELLED_PRIME = re.compile(r"\b(5|3|five|three)[- ]prime\b", re.IGNORECASE)
_ARROW = re.compile(r"\s*(?:→|⟶|->|-->)\s*")


def normal_text(text: str) -> str:
    """``text`` with Unicode folded (subscripts and superscripts to plain digits and signs:
    FADH₂ → FADH2, Na⁺ → Na+), primes and dashes as ASCII, "five prime" as 5', and arrows as
    " to "."""
    text = unicodedata.normalize("NFKC", text).translate(_PRIMES)
    text = _SPELLED_PRIME.sub(lambda m: ("5" if m.group(1).lower() in ("5", "five") else "3") + "'", text)
    return _ARROW.sub(" to ", text)


def sentences(text: str) -> list[str]:
    """The sentences (and ;-separated clauses) of ``text``, normalised (:func:`normal_text`)."""
    parts = re.split(r"(?<=[.!?;])\s+", normal_text(text).strip())
    return [p.strip() for p in parts if p.strip()]


#: Words that make a sentence a denial, a contrast or a question about the claim: left alone.
NEGATION = re.compile(
    r"\b(?:not|never|no|nor|neither|cannot|can't|isn't|aren't|doesn't|don't|won't|wasn't|weren't|without|rather than|instead|"
    r"unlike|except|outside|myth|misconception|wrong|incorrect|mistake|whereas|but)\b", re.IGNORECASE)


def plain(sentence: str) -> bool:
    """Whether ``sentence`` is a plain statement: no negation or contrast, not a question."""
    return not sentence.rstrip().endswith("?") and NEGATION.search(sentence) is None


_UNITS = {w: k for k, w in enumerate(("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                      "fifteen sixteen seventeen eighteen nineteen").split())}
_TENS = {w: 10 * k for k, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if k >= 2}
NUMBER = (r"(?:\d+(?:\.\d+)?|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five|six|seven|"
          r"eight|nine))?|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
          r"seventeen|eighteen|nineteen)")


def number_value(text: str) -> float | None:
    """The value of a number written in digits or English words (``ten``, ``thirty-two``)."""
    word = text.strip().lower()
    if re.fullmatch(r"\d+(?:\.\d+)?", word):
        return float(word)
    if word in _UNITS:
        return float(_UNITS[word])
    parts = re.split(r"[- ]", word)
    if parts[0] in _TENS:
        return float(_TENS[parts[0]] + (_UNITS.get(parts[1], 0) if len(parts) > 1 else 0))
    return None


@dataclass(frozen=True)
class Claim:
    """A wrong statement found in a text: the sentence (``quote``) and what to write instead."""

    quote: str
    message: str


def _quote(sentence: str, limit: int = 90) -> str:
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


# ----- directions ---------------------------------------------------------------------------------

_THREE_TO_FIVE = re.compile(r"\b3'\s*(?:end\s+)?(?:-|to(?:wards?)?(?:\s+the)?|towards?(?:\s+the)?)\s*5'", re.IGNORECASE)
_FIVE_TO_THREE = re.compile(r"\b5'\s*(?:end\s+)?(?:-|to(?:wards?)?(?:\s+the)?|towards?(?:\s+the)?)\s*3'", re.IGNORECASE)
_NUCLEIC = re.compile(r"\b(?:m?rna|transcripts?|dna|strands?|primers?|nucleotides?|chains?)\b", re.IGNORECASE)
_MAKE = re.compile(r"\b(?:synthes\w*|made|makes?|making|builds?|built|building|grows?|growing|grew|extend\w*|elongat\w*|polymeri\w*|adds?|added|"
                   r"adding|assembl\w*|transcrib\w*)\b", re.IGNORECASE)
_READ_CONTEXT = re.compile(r"\b(?:templates?|read\w*|exonuclease|proofread\w*|degrad\w*|digest\w*|lagging|overall|okazaki|antisense|"
                           r"anticodons?|scan\w*|decay)\b", re.IGNORECASE)
_RIBOSOME = re.compile(r"\b(?:ribosomes?|translat\w*|codons?)\b", re.IGNORECASE)
_PROTEIN = re.compile(r"\b(?:proteins?|polypeptides?|peptides?|chains?|amino acids?|translat\w*|ribosomes?|nascent)\b", re.IGNORECASE)
_PROTEIN_MAKE = re.compile(r"\b(?:synthes\w*|made|makes?|making|builds?|built|grows?|growing|grew|extend\w*|elongat\w*|adds?|added|adding|"
                           r"translat\w*|polymeri\w*|assembl\w*)\b", re.IGNORECASE)
_TERM = r"(?:[- ]?termin(?:us|al)(?:\s+end)?|[- ]?term|[- ]?end)?"
_C_TO_N = re.compile(rf"\b(?:C{_TERM}|(?i:carboxyl?){_TERM})\s+(?:to(?:wards?)?|toward)\s+(?:the\s+)?(?:N|(?i:amino)){_TERM}\b")
_C_TO_N_TERMINUS = re.compile(r"\bC-termin(?:us|al(?:\s+end)?)\s*-\s*(?:to\s+)?N-termin", re.IGNORECASE)
_MOTOR_END = r"(?:(?!\b(?:dyneins?|kinesins?|myosins?|plus|minus|end|ends)\b)[^.;:])*?"
_KINESIN_MINUS = re.compile(rf"\bkinesins?\b{_MOTOR_END}\b(?:to|towards?|toward)\s+(?:the\s+|its\s+|their\s+)?(?:microtubules?'?s?\s+)?minus\b",
                            re.IGNORECASE)
_DYNEIN_PLUS = re.compile(rf"\bdyneins?\b{_MOTOR_END}\b(?:to|towards?|toward)\s+(?:the\s+|its\s+|their\s+)?(?:microtubules?'?s?\s+)?plus\b",
                          re.IGNORECASE)
_KINESIN_14 = re.compile(r"\b(?:kinesin[- ]?14|ncd|kifc\w*|minus[- ]end[- ]directed)\b", re.IGNORECASE)
_PROTONS = r"(?:protons?|h\+|hydrogen ions?)"
_PUMP = re.compile(r"\bpump\w*\b", re.IGNORECASE)
_INTO_MATRIX = re.compile(rf"\b{_PROTONS}\b(?:(?!\b(?:back|flow\w*|return\w*|through|synthase)\b)[^.;])*?\binto\s+the\s+(?:mitochondrial\s+)?matrix\b",
                          re.IGNORECASE)
_INTO_STROMA = re.compile(rf"\b{_PROTONS}\b(?:(?!\b(?:back|flow\w*|return\w*|through|synthase)\b)[^.;])*?\binto\s+the\s+stroma\b", re.IGNORECASE)
_ION_MOVE = r"(?:(?!\b(?:sodium|potassium|na\+|k\+)(?![\w+]))[^.;])*?"
_NA_IN = re.compile(rf"(?:\bsodium\b|\bna\+){_ION_MOVE}\b(?:into|in to)\s+the\s+(?:cell|cytosol|cytoplasm)\b", re.IGNORECASE)
_K_OUT = re.compile(rf"(?:\bpotassium\b|\bk\+){_ION_MOVE}\bout\s+of\s+the\s+(?:cell|cytosol|cytoplasm)\b", re.IGNORECASE)
_NA_K_PUMP = re.compile(r"\b(?:na\+\s*/\s*k\+|sodium[- ]potassium|na,?\s*k-atpase|na\+/k\+-atpase|sodium pump)\b", re.IGNORECASE)


def direction_claims(text: str) -> list[Claim]:
    """Wrong directions in ``text``: a nucleic acid made 3′ to 5′ (it grows 5′→3′), a ribosome
    reading mRNA 3′ to 5′, a protein made C to N, kinesin walking to the minus end or dynein to
    the plus end, protons pumped into the matrix or the stroma, the Na⁺/K⁺ pump moving Na⁺ in or
    K⁺ out."""
    out: list[Claim] = []
    for s in sentences(text):
        if not plain(s):
            continue
        q = _quote(s)
        three_five = _THREE_TO_FIVE.search(s) is not None and _FIVE_TO_THREE.search(s) is None
        if three_five and _READ_CONTEXT.search(s) is None and _NUCLEIC.search(s) and _MAKE.search(s):
            out.append(Claim(q, "RNA and DNA are made 5′→3′ (nucleotides are added to the 3′ end; it is the template that is read "
                                "3′→5′): write 5′ to 3′"))
        elif three_five and _RIBOSOME.search(s) and re.search(r"\bm?rna\b", s, re.IGNORECASE) and \
                re.search(r"\b(?:templates?|dna|exonuclease|degrad\w*|decay|anticodons?)\b", s, re.IGNORECASE) is None:
            out.append(Claim(q, "a ribosome reads mRNA 5′→3′ (from the start codon near the 5′ cap to the stop codon): write 5′ to 3′"))
        if (_C_TO_N.search(s) or _C_TO_N_TERMINUS.search(s)) and _PROTEIN.search(s) and _PROTEIN_MAKE.search(s) and \
                re.search(r"\b(?:degrad\w*|cleav\w*|numbered|written)\b", s, re.IGNORECASE) is None:
            out.append(Claim(q, "a protein is made from its N-terminus to its C-terminus (each amino acid is added to the C-terminal "
                                "end): write N to C"))
        if _KINESIN_MINUS.search(s) and _KINESIN_14.search(s) is None:
            out.append(Claim(q, "kinesin-1 (and most kinesins) walks to a microtubule's plus end, out from the centrosome; dynein "
                                "walks to the minus end (name kinesin-14 if you mean a minus-end kinesin)"))
        if _DYNEIN_PLUS.search(s):
            out.append(Claim(q, "cytoplasmic dynein walks to a microtubule's minus end, in towards the centrosome; kinesin walks to "
                                "the plus end"))
        if _PUMP.search(s) and _INTO_MATRIX.search(s):
            out.append(Claim(q, "the respiratory chain pumps protons out of the matrix into the intermembrane space; they flow back "
                                "into the matrix through ATP synthase"))
        if _PUMP.search(s) and _INTO_STROMA.search(s):
            out.append(Claim(q, "in the light reactions protons are pumped from the stroma into the thylakoid lumen; they flow back "
                                "into the stroma through ATP synthase"))
        if (_NA_K_PUMP.search(s) or (_PUMP.search(s) and re.search(r"\batp\b", s, re.IGNORECASE))) and (_NA_IN.search(s) or _K_OUT.search(s)):
            out.append(Claim(q, "the Na⁺/K⁺ pump moves 3 Na⁺ out of the cell and 2 K⁺ into it per ATP"))
    return out


# ----- where processes happen ----------------------------------------------------------------------


@dataclass(frozen=True)
class Place:
    """A textbook fact: what (``subject``, a regex), the places it is never in (``wrong``), where
    it is (``right``) and whether it holds only in eukaryotes."""

    subject: str
    wrong: str
    right: str
    eukaryotes: bool = True


PLACES: tuple[Place, ...] = (
    Place(r"glycolysis", r"mitochondri\w*|(?:mitochondrial\s+)?matrix|nucleus|chloroplasts?", "the cytosol", eukaryotes=False),
    Place(r"(?:the\s+)?(?:citric acid|krebs|tca|tricarboxylic acid) cycle", r"cytosol|cytoplasm|nucleus", "the mitochondrial matrix"),
    Place(r"(?:pyruvate oxidation|the link reaction)", r"cytosol|cytoplasm|nucleus", "the mitochondrial matrix"),
    Place(r"(?:the\s+)?(?:electron transport chain|respiratory chain|oxidative phosphorylation)",
          r"cytosol|cytoplasm|nucleus|(?:mitochondrial\s+)?matrix|outer(?:\s+mitochondrial)?\s+membrane",
          "the inner mitochondrial membrane"),
    Place(r"(?<!reverse )transcription(?!\s+factors?)", r"cytosol|cytoplasm|ribosomes?", "the nucleus"),
    Place(r"(?:rna\s+)?splicing|(?:5'\s+)?capping|polyadenylation", r"cytosol|cytoplasm", "the nucleus"),
    Place(r"(?:translation(?!\s+factors?)|protein synthesis)", r"nucleus|nucleoplasm|nucleolus", "the cytosol (free ribosomes or the rough ER)"),
    Place(r"(?:the\s+)?(?:calvin cycle|calvin-benson cycle|carbon fixation)", r"thylakoids?(?:\s+(?:membranes?|lumen))?|lumen|cytosol|cytoplasm",
          "the chloroplast stroma"),
    Place(r"(?:the\s+)?light(?:-dependent)? reactions", r"stroma|cytosol|cytoplasm", "the thylakoid membranes"),
    Place(r"dna replication", r"cytosol|cytoplasm", "the nucleus"),
    Place(r"beta-oxidation|β-oxidation|fatty acid oxidation", r"cytosol|cytoplasm|nucleus", "the mitochondrial matrix (and peroxisomes)"),
)
_GAP = (r"(?:\s+(?:takes?|took|taking|place|occurs?|occurred|occurring|happens?|happened|happening|runs?|ran|running|is|are|was|were|"
        r"carried|out|proceeds?|starts?|begins?|continues?|also|mostly|only|all|entirely|then|first|itself|works?|located|found|done|"
        r"performed|always|still)){0,4}?")
_WHERE = r"\s+(?:in|inside|within)\s+(?:the\s+)?(?:cell'?s\s+)?"


def location_claims(text: str, prokaryote: bool = False) -> list[Claim]:
    """Narration placing a process where it never is (:data:`PLACES`; eukaryotic facts are left
    out for a prokaryote and in sentences about bacteria): ``glycolysis takes place in the
    mitochondria``, ``translation happens in the nucleus``."""
    out: list[Claim] = []
    for s in sentences(text):
        if not plain(s):
            continue
        bacterial = prokaryote or re.search(r"\b(?:bacteri\w*|prokaryot\w*|e\.?\s?coli|archae\w*)\b", s, re.IGNORECASE) is not None
        for fact in PLACES:
            if fact.eukaryotes and bacterial:
                continue
            m = re.search(rf"\b(?:{fact.subject}){_GAP}{_WHERE}({fact.wrong})\b", s, re.IGNORECASE)
            if m is None or "," in m.group(0):
                continue
            subject = re.match(rf"\b(?:{fact.subject})", m.group(0), re.IGNORECASE)
            name = subject.group(0) if subject else "it"
            out.append(Claim(_quote(s), f"{name} happens in {fact.right}, not in the {m.group(1).lower()}"))
    return out


#: Places narration names, as the compartments they mean (for things a cell scene shows).
PLACE_WORDS: dict[str, frozenset[str]] = {
    "nucleus": frozenset({"nucleoplasm"}), "nucleoplasm": frozenset({"nucleoplasm"}),
    "cytosol": frozenset({"cytosol"}), "cytoplasm": frozenset({"cytosol"}),
    "matrix": frozenset({"matrix"}), "mitochondrial matrix": frozenset({"matrix"}),
    "mitochondria": frozenset({"matrix", "intermembrane_space"}), "mitochondrion": frozenset({"matrix", "intermembrane_space"}),
    "stroma": frozenset({"stroma"}), "chloroplasts": frozenset({"stroma", "thylakoid_lumen", "chloroplast_intermembrane_space"}),
    "chloroplast": frozenset({"stroma", "thylakoid_lumen", "chloroplast_intermembrane_space"}),
    "vacuole": frozenset({"vacuole_lumen"}), "lysosomes": frozenset({"lysosome_lumen"}), "lysosome": frozenset({"lysosome_lumen"}),
    "extracellular space": frozenset({"extracellular"}), "periplasm": frozenset({"periplasm"}),
}


def placement_claims(text: str, shown: dict[str, tuple[str, frozenset[str]]]) -> list[Claim]:
    """Narration putting a thing a cell scene shows somewhere the scene does not have it:
    ``shown`` maps each word for a thing (its kind's name and plural, lower case) to its label
    and the compartments the scene has it in (``the ribosomes in the nucleus`` while the scene's
    ribosomes are all in the cytosol)."""
    from .catalog import COMPARTMENTS

    places = "|".join(re.escape(p) for p in sorted(PLACE_WORDS, key=len, reverse=True))
    out: list[Claim] = []
    for s in sentences(text):
        if not plain(s):
            continue
        for word, (label, comps) in shown.items():
            m = re.search(rf"\b{re.escape(word)}\b{_GAP}{_WHERE}({places})\b", s, re.IGNORECASE)
            if m is None or "," in m.group(0) or PLACE_WORDS[m.group(1).lower()] & comps:
                continue
            where = ", ".join(sorted(COMPARTMENTS[c].label.lower() if c in COMPARTMENTS else c for c in comps)) or "nowhere"
            out.append(Claim(_quote(s), f"the narration puts the {label.lower()} in the {m.group(1).lower()}, but the scene shows "
                                        f"them in the {where}: say where they are, or place them there (in:, on:)"))
    return out


# ----- numbers ---------------------------------------------------------------------------------------


def _numbers_before(s: str, noun: str) -> Iterator[tuple[str, float]]:
    """``(written, value)`` of each number written right before ``noun`` (``molecules of`` and
    ``a net`` between allowed)."""
    for m in re.finditer(rf"\b({NUMBER})\s+(?:(?:extra|more|new|molecules?\s+of)\s+)?(?:{noun})(?![\w+])", s, re.IGNORECASE):
        value = number_value(m.group(1))
        if value is not None:
            yield m.group(1), value


_ANY = re.compile(r"\b(?:about|approximately|around|roughly|up to|at most|at least|nearly|some|over|per\s+atp)\b", re.IGNORECASE)


def _glycolysis(s: str) -> list[str]:
    out: list[str] = []
    if not re.search(r"\bglycoly\w*", s, re.IGNORECASE) or re.search(r"\b(?:citric|krebs|tca|oxidative|electron transport|respiration)\b", s, re.IGNORECASE):
        return out
    per_triose = re.search(r"\b(?:each|per|every)\s+(?:triose|three-carbon|glyceraldehyde|g3p|gap|half)\b", s, re.IGNORECASE)
    m = re.search(rf"\bnet\s+(?:yield\s+|gain\s+|total\s+)?(?:of\s+)?({NUMBER})\s+(?:molecules?\s+of\s+)?atp\b", s, re.IGNORECASE) or \
        re.search(rf"\b({NUMBER})\s+(?:molecules?\s+of\s+)?atp\s+net\b", s, re.IGNORECASE)
    if m and not per_triose and number_value(m.group(1)) not in (None, 2.0):
        out.append(f"glycolysis yields a net 2 ATP per glucose (4 made, 2 invested), not {m.group(1)}")
    if not per_triose:
        for written, value in _numbers_before(s, r"nadh"):
            if value != 2:
                out.append(f"glycolysis makes 2 NADH per glucose (one per glyceraldehyde 3-phosphate), not {written}")
        for written, value in _numbers_before(s, r"pyruvates?"):
            if value != 2:
                out.append(f"glycolysis splits one glucose into 2 pyruvate, not {written}")
    return out


_PER_TURN = {"nadh": 3, "fadh2": 1, "co2": 2, "carbon dioxide": 2, "gtp": 1}


def _tca(s: str) -> list[str]:
    out: list[str] = []
    if not re.search(r"\b(?:citric acid cycle|krebs cycle|tca cycle|tricarboxylic|(?:each|per|every|one)\s+turn)\b", s, re.IGNORECASE):
        return out
    if re.search(r"\b(?:glycoly\w*|pyruvate dehydrogenase|link reaction|pyruvate oxidation|electron transport|oxidative)\b", s, re.IGNORECASE):
        return out                                    # several stages counted together
    per_glucose = re.search(r"\b(?:per|each|every|one)\s+glucose\b|\b(?:two|both|2)\s+turns\b", s, re.IGNORECASE) is not None
    per_turn = re.search(r"\b(?:per|each|every|one|a|single)\s+turn\b", s, re.IGNORECASE) is not None
    for noun, turn in _PER_TURN.items():
        for written, value in _numbers_before(s, noun):
            allowed = {turn * 2} if per_glucose and not per_turn else {turn} if per_turn and not per_glucose else {turn, turn * 2}
            if value not in allowed:
                name = {"fadh2": "FADH₂", "co2": "CO₂", "carbon dioxide": "CO₂", "nadh": "NADH", "gtp": "GTP (or ATP)"}[noun]
                out.append(f"one turn of the citric acid cycle makes {turn} {name} ({turn * 2} per glucose), not {written}")
    return out


def _pump(s: str) -> list[str]:
    out: list[str] = []
    if not (_NA_K_PUMP.search(s) or (_PUMP.search(s) and re.search(r"\b(?:sodium|na\+)", s, re.IGNORECASE) and
                                      re.search(r"\b(?:potassium|k\+)", s, re.IGNORECASE))):
        return out
    if re.search(r"\b(?:mm|millimolar|concentrations?|times|fold|gradients?)\b", s, re.IGNORECASE):
        return out
    for written, value in _numbers_before(s, r"sodium(?:\s+ions?)?|na\+(?:\s+ions?)?"):
        if value != 3:
            out.append(f"the Na⁺/K⁺ pump moves 3 Na⁺ out per ATP, not {written}")
    for written, value in _numbers_before(s, r"potassium(?:\s+ions?)?|k\+(?:\s+ions?)?"):
        if value != 2:
            out.append(f"the Na⁺/K⁺ pump moves 2 K⁺ in per ATP, not {written}")
    return out


_COMPLEX = {"i": 4, "one": 4, "1": 4, "iii": 4, "three": 4, "3": 4, "iv": 2, "four": 2, "4": 2}


def _protons(s: str) -> list[str]:
    out: list[str] = []
    if re.search(r"\b(?:photosystems?|thylakoids?|lumen|stroma|chloroplasts?|per\s+atp|each\s+atp|atp\s+synthase|c[- ]?ring|rotat\w*)\b", s, re.IGNORECASE):
        return out
    found = list(_numbers_before(s, r"protons?|h\+|hydrogen ions?"))
    if len(found) != 1 or _ANY.search(s):
        return out
    written, value = found[0]
    nadh = re.search(r"\bnadh\b", s, re.IGNORECASE) is not None
    fadh = re.search(r"\bfadh2\b", s, re.IGNORECASE) is not None
    complexes = re.findall(r"\bcomplex(?:es)?\s+(iv|iii|ii|i|one|two|three|four|[1-4])\b", s, re.IGNORECASE)
    if nadh and not fadh and not re.search(r"\bcomplex\s+(?:i|one|1)\b(?!\s*(?:,|and))", s, re.IGNORECASE) and value != 10:
        out.append(f"the respiratory chain pumps 10 H⁺ per NADH (4 at complex I, 4 at III, 2 at IV), not {written}")
    elif fadh and not nadh and value != 6:
        out.append(f"the respiratory chain pumps 6 H⁺ per FADH₂ (complex II pumps none; 4 at III, 2 at IV), not {written}")
    elif len(complexes) == 1 and not nadh and not fadh and _PUMP.search(s):
        key = complexes[0].lower()
        if key in ("ii", "two", "2"):
            out.append(f"complex II (succinate dehydrogenase) pumps no protons, not {written}")
        elif _COMPLEX.get(key) is not None and value != _COMPLEX[key]:
            out.append(f"complex {complexes[0].upper()} pumps {_COMPLEX[key]} H⁺ per two electrons, not {written}")
    return out


def _division(s: str) -> list[str]:
    out: list[str] = []
    m = re.search(rf"\bmitosis\b[^.;]*?\b(?:produces?|gives?|yields?|results?\s+in|makes?|forms?)\s+({NUMBER})\s+(?:\w+\s+){{0,2}}?(?:daughter\s+)?(?:cells|nuclei)\b",
                  s, re.IGNORECASE)
    if m and number_value(m.group(1)) != 2:
        out.append(f"mitosis (and cytokinesis) gives 2 daughter cells, not {m.group(1)}")
    if re.search(r"\bmeiosis\s+(?:i|ii|one|two|1|2)\b|\b(?:first|second)\s+(?:meiotic\s+)?division\b", s, re.IGNORECASE) is None:
        m = re.search(rf"\bmeiosis\b[^.;]*?\b(?:produces?|gives?|yields?|results?\s+in|makes?|forms?)\s+({NUMBER})\s+(?:\w+\s+){{0,2}}?(?:cells|gametes|nuclei)\b",
                      s, re.IGNORECASE)
        if m and number_value(m.group(1)) != 4:
            out.append(f"meiosis gives 4 haploid cells (or nuclei) from one diploid cell, not {m.group(1)}")
    return out


def _code(s: str) -> list[str]:
    out = [f"the standard genetic code has 3 stop codons (UAA, UAG, UGA), not {w}" for w, v in _numbers_before(s, r"stop\s+codons") if v != 3]
    if re.search(r"\bhuman", s, re.IGNORECASE) and not _ANY.search(s) and not re.search(
            r"\b(?:anaphase|telophase|metaphase|replicat\w*|duplicat\w*|chromatids?|tetraploid|polyploid|cancer\w*|tumou?r\w*|trisom\w*|"
            r"aneuploid\w*|syndrome)\b", s, re.IGNORECASE):
        haploid = re.search(r"\b(?:gametes?|haploid|sperm|eggs?|oocytes?|ova)\b", s, re.IGNORECASE) is not None
        for written, value in _numbers_before(s, r"chromosomes"):
            if value not in ((23.0,) if haploid else (46.0, 23.0)):
                out.append(f"human cells have 46 chromosomes (23 in a gamete), not {written}")
        for written, value in _numbers_before(s, r"pairs\s+of\s+chromosomes|chromosome\s+pairs"):
            if value != 23:
                out.append(f"human cells have 23 pairs of chromosomes, not {written}")
    for written, value in _numbers_before(s, r"(?:base\s+pairs|bp)\s+per\s+(?:helical\s+)?turn"):
        if not 10 <= value <= 10.5:
            out.append(f"B-DNA has about 10.5 base pairs per helical turn, not {written}")
    if re.search(r"\b(?:nucleosomes?|histone\s+octamers?|core\s+particles?)\b", s, re.IGNORECASE) and \
            not re.search(r"\b(?:linker|repeat|spacing|between)\b", s, re.IGNORECASE):
        for written, value in _numbers_before(s, r"base\s+pairs|bp"):
            if not 145 <= value <= 147:
                out.append(f"a nucleosome core wraps about 147 base pairs of DNA, not {written}")
    return out


_COUNTS: tuple[Callable[[str], list[str]], ...] = (_glycolysis, _tca, _pump, _protons, _division, _code)


def count_claims(text: str) -> list[Claim]:
    """Numbers in ``text`` that contradict the textbook: net ATP, NADH and pyruvate of
    glycolysis; NADH, FADH₂, CO₂ and GTP per turn (or per glucose) of the citric acid cycle; Na⁺
    and K⁺ per pump cycle; protons per NADH, FADH₂ or complex; cells after mitosis and meiosis;
    stop codons, human chromosomes, base pairs per turn and per nucleosome."""
    out: list[Claim] = []
    for s in sentences(text):
        if not plain(s):
            continue
        for check in _COUNTS:
            out += [Claim(_quote(s), message) for message in check(s)]
    return out


# ----- transport -----------------------------------------------------------------------------------

_ACTIVE = re.compile(r"\b(?:primary\s+)?active(?:ly)?\s+transport\w*\b|\bagainst\s+(?:its|their|the)\s+(?:concentration\s+|electrochemical\s+)?gradients?\b|"
                     r"\buphill\b|\b(?:transported|moved|pumped)\s+actively\b", re.IGNORECASE)
_SECONDARY = re.compile(r"\bsecondary(?:\s+active)?\b|\bco-?transport\w*|\bsymport\w*|\bantiport\w*|\bexchang\w*", re.IGNORECASE)
_PASSIVE = re.compile(r"\bpassive(?:ly)?\b|\bfacilitated\s+diffusion\b|\bdown\s+(?:its|their|the)\s+(?:concentration\s+|electrochemical\s+)?gradients?\b",
                      re.IGNORECASE)


def says_active(text: str) -> str | None:
    """The sentence of ``text`` that calls transport active or uphill (not secondary active or
    a symporter's own wording), or ``None``."""
    for s in sentences(text):
        if plain(s) and _ACTIVE.search(s) and _SECONDARY.search(s) is None:
            return _quote(s)
    return None


def says_passive(text: str) -> str | None:
    """The sentence of ``text`` that calls transport passive (or down its gradient), or ``None``."""
    for s in sentences(text):
        if plain(s) and _PASSIVE.search(s) and _SECONDARY.search(s) is None and _ACTIVE.search(s) is None:
            return _quote(s)
    return None


#: How each transporting molecule kind moves its solute: ``passive`` (a channel, an aquaporin,
#: a uniporter), ``secondary`` (a symporter or antiporter driven by an ion going down its
#: gradient) or ``primary`` (an ATP-driven pump).
PASSIVE_KINDS = frozenset({"ion_channel", "aquaporin"})
PRIMARY_KINDS = frozenset({"na_k_atpase", "h_atpase", "abc_transporter"})


def transport_mode(kind: str, carrier_mode: str | None) -> str | None:
    """``passive``, ``secondary`` or ``primary`` for a molecule kind (a carrier by its mode),
    ``None`` for one that does not transport."""
    if kind in PASSIVE_KINDS:
        return "passive"
    if kind in PRIMARY_KINDS:
        return "primary"
    if kind == "carrier":
        return "passive" if (carrier_mode or "uniport") == "uniport" else "secondary"
    return None


# ----- pathways -------------------------------------------------------------------------------------

_ACT_VERB = re.compile(r"\b(?:activat\w*|stimulat\w*|turns?\s+on|switch\w*\s+on|switched\s+on)\b", re.IGNORECASE)
_INH_VERB = re.compile(r"\b(?:inhibit\w*|block\w*|repress\w*|suppress\w*|turns?\s+off|switch\w*\s+off|inactivat\w*|deactivat\w*|"
                       r"antagoni\w*|shuts?\s+(?:down|off))\b", re.IGNORECASE)
_PHOS_VERB = re.compile(r"\b(?<!de)phosphorylat\w*", re.IGNORECASE)
_DEPHOS_VERB = re.compile(r"\bdephosphorylat\w*", re.IGNORECASE)
_PASSIVE_VOICE = re.compile(r"\b(?:is|are|was|were|gets?|got|becomes?|being)\b[^.;]*\bby\s*$", re.IGNORECASE)

#: An arc as the pathway check reads it: its sign (+1 activating, −1 inhibiting) and type name.
Arc = tuple[int, str]


def pathway_claims(text: str, names: dict[str, str], arcs: dict[tuple[str, str], Arc]) -> list[Claim]:
    """Narration contradicting a pathway's arcs: ``A activates B`` (or ``B is activated by A``)
    where the arc A → B inhibits, ``A inhibits B`` where it activates, ``A phosphorylates B``
    where it dephosphorylates and the other way round. ``names`` maps a node's name as said
    (lower case: its label, its gene) to its id; only arcs written between two named nodes with
    a few words between are read."""
    if not names:
        return []
    pattern = re.compile(r"(?<![\w])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?![\w])", re.IGNORECASE)
    out: list[Claim] = []
    for s in sentences(text):
        if not plain(s):
            continue
        mentions = [(m.start(), m.end(), names[m.group(1).lower()]) for m in pattern.finditer(s)]
        for (_, a_end, a), (b_start, _, b) in zip(mentions, mentions[1:]):
            between = s[a_end:b_start]
            if a == b or re.search(r"[,;:()]", between) or len(between.split()) > 6:
                continue
            passive = _PASSIVE_VOICE.search(between) is not None
            source, target = (b, a) if passive else (a, b)
            arc = arcs.get((source, target))
            if arc is None:
                continue
            sign, kind = arc
            act, inh = _ACT_VERB.search(between) is not None, _INH_VERB.search(between) is not None
            if act and not inh and sign < 0:
                out.append(Claim(_quote(s), f"the scene's arc {source} → {target} inhibits ({kind}), but the narration says it activates: "
                                            "say inhibits, or change the arc"))
            elif inh and not act and sign > 0:
                out.append(Claim(_quote(s), f"the scene's arc {source} → {target} activates ({kind}), but the narration says it inhibits: "
                                            "say activates, or change the arc"))
            if _DEPHOS_VERB.search(between) and kind == "phosphorylates":
                out.append(Claim(_quote(s), f"the scene's arc {source} → {target} phosphorylates, but the narration says dephosphorylates"))
            elif _PHOS_VERB.search(between) and not _DEPHOS_VERB.search(between) and kind == "dephosphorylates":
                out.append(Claim(_quote(s), f"the scene's arc {source} → {target} dephosphorylates, but the narration says phosphorylates"))
    return out


# ----- gene and protein names ------------------------------------------------------------------------


@dataclass(frozen=True)
class GeneName:
    """A gene a scene declares: its symbol, the species and how the species writes its protein
    (the same letters for human; TRP53 for mouse Trp53; Cdc28 for yeast CDC28)."""

    symbol: str
    species: str
    protein: str


def protein_form(symbol: str, species: str) -> str:
    """How ``species`` writes the protein of the gene ``symbol`` when it uses the symbol (HGNC:
    the same; MGI / RGD: all capitals; SGD, PomBase, ZFIN, E. coli: a capital first letter)."""
    if species in ("mouse", "rat"):
        return symbol.upper()
    if species in ("yeast", "fission_yeast", "zebrafish"):
        return symbol[:1].upper() + symbol[1:].lower()
    if species == "e_coli":
        return symbol[:1].upper() + symbol[1:]
    return symbol


_ITALIC = re.compile(r"<i>(.*?)</i>", re.IGNORECASE | re.DOTALL)


def naming_claims(text: str, genes: list[GeneName], markup: bool = False) -> list[Claim]:
    """A declared gene written as its protein (``TRP53 gene``) or its protein as the gene
    (``Trp53 protein``), a symbol in the wrong case for the species (``trp53``), and in Pango
    ``markup`` text a gene not in italics (``TP53 gene`` → ``<i>TP53</i> gene``) or a protein in
    italics."""
    out: list[Claim] = []
    flat = normal_text(text)
    italic_spans = [m.span(1) for m in _ITALIC.finditer(flat)] if markup else []
    plain_text = _ITALIC.sub(lambda m: m.group(1), flat)

    def in_italics(start: int) -> bool:
        return any(a <= start < b for a, b in italic_spans)

    for gene in genes:
        g, p = gene.symbol, gene.protein
        q = _quote(plain_text)
        if g != p:
            if re.search(rf"(?<![\w]){re.escape(g)}\s+protein\b", plain_text):
                out.append(Claim(q, f"'{g} protein': {g} is the {gene.species} gene; its protein is written {p} (roman)"))
            if re.search(rf"(?<![\w]){re.escape(p)}\s+gene\b", plain_text):
                out.append(Claim(q, f"'{p} gene': {p} is the {gene.species} protein; the gene is written {g} (italic)"))
        for m in re.finditer(rf"(?<![\w]){re.escape(g)}(?![\w])", plain_text, re.IGNORECASE):
            if m.group(0) not in (g, p):
                out.append(Claim(q, f"'{m.group(0)}': the {gene.species} gene is written {g} (italic) and its protein {p}"))
                break
        if markup:
            for m in re.finditer(rf"(?<![\w>]){re.escape(g)}(?![\w<])", flat):
                near = flat[max(0, m.start() - 6):m.end() + 7].lower()
                if "gene" in near and not in_italics(m.start()):
                    out.append(Claim(q, f"a gene symbol is italic: write <i>{g}</i>"))
                    break
            for m in re.finditer(rf"<i>\s*{re.escape(p)}\s*</i>\s*(?:protein|kinase|receptor|enzyme)\b", flat, re.IGNORECASE):
                out.append(Claim(q, f"a protein name is roman: write {p} without <i>"))
                break
    return out


__all__ = [
    "Arc", "Claim", "GeneName", "NEGATION", "PLACE_WORDS", "naming_claims", "pathway_claims", "placement_claims", "protein_form", "NUMBER", "PASSIVE_KINDS", "PLACES", "PRIMARY_KINDS", "Place", "count_claims", "direction_claims",
    "location_claims", "normal_text", "number_value", "plain", "says_active", "says_passive", "sentences", "transport_mode",
]

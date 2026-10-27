"""Sequence variants on a coding sequence in HGVS notation (DESIGN.md §96.13). No manim.

- **The coding sequence** (:class:`CodingSequence`): the coding strand's exonic DNA from ``c.first``
  (``c.1`` is the A of the ATG), its coding exons as ``c.`` ranges, the intron sequences when they
  are known (a gene built by ``cellworld.expression``), the length of the whole CDS (stop codon
  included) when it is known.
- **DNA variants** (``c.``): substitution ``c.20A>T``, deletion ``c.1521_1523del`` (the deleted
  bases may be written: ``c.1521_1523delCTT``, ``c.35delG``), duplication ``c.35dup``, insertion
  ``c.76_77insT``, deletion–insertion ``c.76_77delinsTT``, intronic substitutions ``c.92+1G>A`` /
  ``c.1585-1G>A``. :func:`parse_c` reads them (refusing the usual mistakes with the fix),
  :func:`normalize` writes what a change is in HGVS form: the shortest description, a deletion or
  duplication in a repeat at its 3′-most position (the 3′ rule; not across an exon border), an
  insertion that copies the bases before it as a duplication.
- **Protein consequences** (``p.``, predicted, so in parentheses): the mutant coding sequence is
  translated with the standard genetic code (``cellworld.sequences.CODONS``) and compared with the
  reference: synonymous ``p.(Leu10=)``, missense ``p.(Glu7Val)``, nonsense ``p.(Arg553*)`` (or
  ``Ter``), in-frame ``del`` / ``dup`` / ``ins`` / ``delins`` (3′-most in a run of one amino
  acid), frameshift ``p.(Gly12Valfs*2)`` (the new frame's length counting the first changed
  residue as 1 and the stop; ``fs*?`` when no stop is reached in the sequence given), start loss
  ``p.(Met1?)``, stop loss ``p.(*147Glnext*?)``; a splice-site change gives ``p.?`` (the protein
  is not predicted from DNA alone) with a predicted RNA consequence (exon skipping or intron
  retention). :func:`parse_p` reads an author's ``p.`` so it can be checked against the computed
  one (the legacy numbering without the initiator Met, ``X`` for a stop and ``ΔF508`` are refused
  with the reason).

HGVS: den Dunnen et al. (2016) *Hum. Mutat.* 37:564–569 and varnomen.hgvs.org. Nonsense-mediated
decay: a premature stop more than ~50–55 nt upstream of the last exon–exon junction (the rule of
``cellworld.expression.NMD_DISTANCE``)."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from vidgen.errors import VidgenError

from ..cellworld.expression import ACIDIC, BASIC, HYDROPHOBIC, NMD_DISTANCE, POLAR, SPECIAL
from ..cellworld.glyphs import BASE_HUES
from ..cellworld.model import did_you_mean
from ..cellworld.sequences import AMINO_ACIDS, CODONS

DNA = "ACGT"
STOP_CODONS = ("TAA", "TAG", "TGA")
#: Kinds of DNA change.
DNA_KINDS = ("sub", "del", "dup", "ins", "delins")
_THREE = {**AMINO_ACIDS, "*": "Ter"}
_ONE_OF = {v.lower(): k for k, v in _THREE.items()}
#: Consequence classes, as said in words.
CLASS_NAMES = {
    "synonymous": "silent (synonymous)", "missense": "missense", "nonsense": "nonsense", "frameshift": "frameshift",
    "inframe_del": "in-frame deletion", "inframe_dup": "in-frame duplication", "inframe_ins": "in-frame insertion",
    "inframe_delins": "in-frame deletion–insertion", "start_loss": "start loss", "stop_loss": "stop loss (extension)",
    "splice_donor": "splice donor site", "splice_acceptor": "splice acceptor site", "intronic": "intronic",
}


def translate(codon: str) -> str:
    """One-letter amino acid (``*`` for a stop) of a DNA codon."""
    return CODONS[codon.replace("T", "U")]


def aa3(code: str) -> str:
    return _THREE[code]


def aa_name(code: str, style: str = "three") -> str:
    """``Glu`` / ``E``; a stop ``Ter`` / ``*`` follows the stop style elsewhere."""
    return code if style == "one" else _THREE[code]


def side_chain_class(code: str) -> str:
    if code in ACIDIC:
        return "acidic"
    if code in BASIC:
        return "basic"
    if code in HYDROPHOBIC:
        return "hydrophobic"
    if code in POLAR:
        return "polar"
    if code in SPECIAL:
        return "special (Gly / Pro)"
    return "stop"


# ----- the coding sequence -----------------------------------------------------------------------------


@dataclass(frozen=True)
class CodingSequence:
    """Exonic coding-strand DNA from ``c.first``; ``exons`` the coding exons as inclusive ``c.``
    ranges (empty: not given); ``introns[k]`` the sequence of the intron after exon ``k`` (``None``
    when unknown); ``length`` the whole CDS with its stop codon, when known."""

    seq: str
    first: int = 1
    exons: tuple[tuple[int, int], ...] = ()
    introns: tuple[str | None, ...] = ()
    length: int | None = None
    name: str | None = None
    first_exon: int = 1

    @property
    def last(self) -> int:
        return self.first + len(self.seq) - 1

    def base(self, c: int) -> str:
        return self.seq[c - self.first]

    def index(self, c: int) -> int:
        return c - self.first

    @property
    def frame_start(self) -> int:
        """The window index of the first base of the first whole codon."""
        return (3 - (self.first - 1) % 3) % 3

    def codon_number(self, c: int) -> int:
        return (c + 2) // 3

    def exon_of(self, c: int) -> int | None:
        for k, (a, b) in enumerate(self.exons):
            if a <= c <= b:
                return k
        return None

    def complete_exons(self) -> bool:
        """Whether the exons cover the whole CDS (needed to judge nonsense-mediated decay)."""
        return bool(self.exons) and self.exons[0][0] == 1 and self.length is not None and self.exons[-1][1] >= self.length

    def intron_base(self, exon_end: int, offset: int) -> str | None:
        """The base at ``c.<exon_end>+offset`` (``offset`` > 0, after exon ``k``) or at
        ``c.<exon_start>-offset`` (``offset`` < 0, before an exon), when the intron is known."""
        for k, (a, b) in enumerate(self.exons):
            if offset > 0 and b == exon_end and k < len(self.introns) and self.introns[k] is not None:
                seq = self.introns[k] or ""
                return seq[offset - 1] if offset <= len(seq) else None
            if offset < 0 and a == exon_end and k > 0 and k - 1 < len(self.introns) and self.introns[k - 1] is not None:
                seq = self.introns[k - 1] or ""
                return seq[len(seq) + offset] if -offset <= len(seq) else None
        return None


def coding_sequence(seq: str, where: str, first: int = 1, exons: list[list[int]] | tuple[tuple[int, int], ...] | None = None,
                    length: int | None = None, name: str | None = None, introns: tuple[str | None, ...] = (),
                    first_exon: int = 1) -> CodingSequence:
    """A checked :class:`CodingSequence`: DNA (an mRNA's U read as T), ``first`` ≥ 1, exons in
    order, touching, covering the window."""
    text = re.sub(r"\s+", "", seq).upper()
    if not text:
        raise VidgenError(f"{where}: sequence is empty")
    if "U" in text and "T" not in text:
        text = text.replace("U", "T")         # an mRNA's coding sequence, written with U
    for k, b in enumerate(text):
        if b not in DNA:
            hint = " (write DNA with T, or an mRNA with U, not both)" if b == "U" else ""
            raise VidgenError(f"{where}: sequence: '{b}' at {k + 1} is not a base (A, C, G, T){hint}")
    if first < 1:
        raise VidgenError(f"{where}: first: {first}: c. numbering starts at 1 (the A of the ATG); UTRs are not part of the window")
    if first_exon < 1:
        raise VidgenError(f"{where}: first_exon: {first_exon}: exons are numbered from 1")
    cds = CodingSequence(text, first, (), (), length, name, first_exon)
    if length is not None and cds.last > length:
        raise VidgenError(f"{where}: the sequence runs to c.{cds.last}, past the CDS length {length}")
    ex: list[tuple[int, int]] = []
    for k, item in enumerate(exons or []):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise VidgenError(f"{where}: exons[{k}]: give [first, last] c. positions, e.g. [1, 92]")
        a, b = int(item[0]), int(item[1])
        if not 1 <= a <= b:
            raise VidgenError(f"{where}: exons[{k}] [{a}, {b}]: c. positions from 1, first ≤ last")
        if ex and a != ex[-1][1] + 1:
            raise VidgenError(f"{where}: exons[{k}] starts at c.{a}; the exon before ends at c.{ex[-1][1]}: coding exons follow each other "
                              f"in c. numbering (the next starts at c.{ex[-1][1] + 1}; introns have no c. number of their own)")
        ex.append((a, b))
    if ex and not (ex[0][0] <= cds.first and cds.last <= ex[-1][1]):
        raise VidgenError(f"{where}: the sequence (c.{cds.first}–c.{cds.last}) is not inside the exons given "
                          f"(c.{ex[0][0]}–c.{ex[-1][1]})")
    if ex and length is not None and ex[-1][1] > length:
        raise VidgenError(f"{where}: exons run to c.{ex[-1][1]}, past the CDS length {length}")
    return replace(cds, exons=tuple(ex), introns=tuple(introns) + (None,) * max(0, len(ex) - 1 - len(introns)))


# ----- positions and DNA variants -----------------------------------------------------------------------


@dataclass(frozen=True)
class Position:
    """``c.92+1`` → ``Position(92, 1)``."""

    c: int
    offset: int = 0

    def text(self) -> str:
        return f"{self.c}" + (f"+{self.offset}" if self.offset > 0 else f"{self.offset}" if self.offset < 0 else "")


@dataclass(frozen=True)
class DnaVariant:
    """A DNA change: ``kind`` (sub, del, dup, ins, delins); ``start`` / ``end`` the positions it
    covers (an insertion: the two bases it lies between); ``ref`` the reference bases it changes
    (empty for an insertion), ``alt`` the new bases (empty for a deletion; a duplication's copy);
    ``written`` as the author wrote it (when valid)."""

    kind: str
    start: Position
    end: Position
    ref: str
    alt: str
    written: str = ""

    @property
    def intronic(self) -> bool:
        return self.start.offset != 0 or self.end.offset != 0

    def text(self, prefix: str = "c.") -> str:
        """The HGVS form (deleted bases not written, as HGVS recommends)."""
        rng = self.start.text() if self.start == self.end else f"{self.start.text()}_{self.end.text()}"
        if self.kind == "sub":
            return f"{prefix}{self.start.text()}{self.ref}>{self.alt}"
        if self.kind == "del":
            return f"{prefix}{rng}del"
        if self.kind == "dup":
            return f"{prefix}{rng}dup"
        if self.kind == "ins":
            return f"{prefix}{self.start.text()}_{self.end.text()}ins{self.alt}"
        return f"{prefix}{rng}delins{self.alt}"

    @property
    def shown(self) -> str:
        return self.written or self.text()

    @property
    def length_change(self) -> int:
        if self.kind == "dup":
            return len(self.ref)
        return len(self.alt) - len(self.ref)


@dataclass(frozen=True)
class RawVariant:
    """What :func:`parse_c` read, before it is checked against a sequence."""

    kind: str
    start: Position
    end: Position
    stated: str | None       # bases written after del / dup, or the reference base of a substitution
    alt: str
    text: str


_POS = r"(\*?-?\d+)([+-]\d+)?"
_C_RE = re.compile(rf"^(?P<prefix>[a-z]\.)?{_POS}(?:_{_POS})?(?P<rest>.*)$")


def _position(c: str, off: str | None, where: str, text: str) -> Position:
    if c.startswith("*") or c.startswith("-"):
        raise VidgenError(f"{where}: '{text}': {c} is in the {'3′' if c.startswith('*') else '5′'} UTR; the window shown is the coding "
                          f"sequence (c.1 is the A of the ATG, the stop codon's last base ends it)")
    if int(c) < 1:
        raise VidgenError(f"{where}: '{text}': there is no c.0 (c.1 is the A of the ATG; the base before it is c.-1)")
    return Position(int(c), int(off) if off else 0)


def parse_c(text: str, where: str = "variant", prefix: str = "c.") -> RawVariant:
    """An HGVS DNA change (``c.20A>T``, ``c.1521_1523del``, ``c.1521_1523delCTT``, ``c.35dup``,
    ``c.76_77insT``, ``c.76_77delinsTT``, ``c.92+1G>A``) read, with the usual mistakes refused and
    the fix named. ``prefix``: ``c.`` (a coding sequence) or ``g.`` (a plain sequence, positions
    from 1; the prefix may then be left out)."""
    raw = str(text).strip()
    t = raw.replace("→", ">").replace("->", ">")
    if t != raw:
        raise VidgenError(f"{where}: '{raw}': a substitution is written with >: {t}")
    if t.startswith("p."):
        raise VidgenError(f"{where}: '{raw}' is a protein change; give the DNA change ({prefix}20A>T…): the p. change is computed from it")
    if t.startswith(("r.", "m.", "n.")) or (t[:2] in ("c.", "g.") and t[:2] != prefix and prefix == "c."):
        raise VidgenError(f"{where}: '{raw}': give the change on the coding DNA ({prefix}…)")
    if not t.startswith(prefix):
        if prefix == "g." and re.match(r"^\d", t):
            t = "g." + t
        else:
            raise VidgenError(f"{where}: '{raw}': an HGVS coding DNA change starts with {prefix} ({prefix}20A>T, {prefix}1521_1523del)")
    m_old = re.match(r"^[a-z]\.([ACGT])(\d+)([ACGT])$", t)
    if m_old:
        raise VidgenError(f"{where}: '{raw}': HGVS writes the position first: {t[:2]}{m_old.group(2)}{m_old.group(1)}>{m_old.group(3)}")
    m = _C_RE.match(t)
    if not m:
        raise VidgenError(f"{where}: '{raw}': not an HGVS change; write e.g. {prefix}20A>T, {prefix}1521_1523del, {prefix}35dup, "
                          f"{prefix}76_77insT, {prefix}76_77delinsTT")
    groups = m.groups()
    start = _position(groups[1], groups[2], where, raw)
    end = _position(groups[3], groups[4], where, raw) if groups[3] else start
    rest = m.group("rest")
    if rest != rest.upper() and re.search(r"[acgt]", rest):
        raise VidgenError(f"{where}: '{raw}': write the bases in capitals (lower case is RNA, r.)")
    if (end.c, end.offset) < (start.c, start.offset):
        raise VidgenError(f"{where}: '{raw}': a range is written 5′ to 3′ (lower position first)")
    if groups[3] and start == end:
        raise VidgenError(f"{where}: '{raw}': a single position is written once ({prefix}{start.text()}{rest})")
    sub = re.match(r"^([ACGT])>([ACGT])$", rest)
    if sub:
        if groups[3]:
            raise VidgenError(f"{where}: '{raw}': a substitution changes one base; several bases are a delins "
                              f"({prefix}{start.text()}_{end.text()}delins…)")
        if sub.group(1) == sub.group(2):
            raise VidgenError(f"{where}: '{raw}': the new base is the reference base: no change (HGVS writes {prefix}{start.text()}=)")
        return RawVariant("sub", start, end, sub.group(1), sub.group(2), raw)
    if re.match(r"^[ACGT]+>[ACGT]+$", rest):
        raise VidgenError(f"{where}: '{raw}': a change of several bases is a deletion–insertion: "
                          f"{prefix}{start.text()}_{end.text() if groups[3] else Position(start.c + len(rest.split('>')[0]) - 1).text()}"
                          f"delins{rest.split('>')[1]}")
    if rest.startswith("delins"):
        alt = rest[6:]
        if not re.fullmatch(r"[ACGT]+", alt):
            raise VidgenError(f"{where}: '{raw}': delins is followed by the new bases ({prefix}{start.text()}delinsTT)")
        return RawVariant("delins", start, end, None, alt, raw)
    if rest.startswith("del") and "ins" in rest:
        raise VidgenError(f"{where}: '{raw}': write a deletion–insertion as {prefix}{start.text()}{'_' + end.text() if groups[3] else ''}"
                          f"delins{rest.split('ins', 1)[1]} (the deleted bases are not written)")
    for kind in ("del", "dup"):
        if rest.startswith(kind):
            stated = rest[3:]
            if stated and not re.fullmatch(r"[ACGT]+", stated):
                raise VidgenError(f"{where}: '{raw}': after {kind} only the {kind}eted bases may follow ({prefix}35delG)"
                                  if kind == "del" else f"{where}: '{raw}': after dup only the duplicated bases may follow")
            if stated and len(stated) != end.c - start.c + 1:
                n = end.c - start.c + 1
                raise VidgenError(f"{where}: '{raw}': {len(stated)} bases written for {n} position{'s' if n != 1 else ''}")
            return RawVariant(kind, start, end, stated or None, "", raw)
    if rest.startswith("ins"):
        alt = rest[3:]
        if not groups[3]:
            raise VidgenError(f"{where}: '{raw}': an insertion names the two bases it lies between: {prefix}{start.text()}_"
                              f"{Position(start.c + 1, start.offset).text()}{rest}")
        if not re.fullmatch(r"[ACGT]+", alt):
            raise VidgenError(f"{where}: '{raw}': ins is followed by the inserted bases ({prefix}76_77insT)")
        if not (end.c == start.c + 1 and start.offset == end.offset == 0):
            raise VidgenError(f"{where}: '{raw}': the two positions of an insertion are neighbours ({start.c}_{start.c + 1})")
        return RawVariant("ins", start, end, None, alt, raw)
    if rest in ("=", ""):
        raise VidgenError(f"{where}: '{raw}': no change is given (write {prefix}20A>T, …del, …dup, …ins…)")
    raise VidgenError(f"{where}: '{raw}': '{rest}' is not a change HGVS writes{did_you_mean(rest[:3], ['del', 'dup', 'ins', 'delins'])} "
                      f"(substitution A>T, del, dup, ins, delins)")


# ----- applying and normalizing ------------------------------------------------------------------------


@dataclass(frozen=True)
class Edit:
    """An exonic change on the window: bases ``[start, end)`` (window indices) become ``alt``."""

    start: int
    end: int
    alt: str


def _px(text: str) -> str:
    """The prefix the author wrote (``c.``; none for a plain position in a target)."""
    return text.strip()[:2] if text.strip()[:2] in ("c.", "g.") else ""


def _check_in_window(cds: CodingSequence, pos: Position, where: str, text: str) -> None:
    if not cds.first <= pos.c <= cds.last:
        px = _px(text)
        raise VidgenError(f"{where}: '{text}': {px}{pos.c} is outside the sequence given ({px}{cds.first}–{px}{cds.last})")


def _intron_check(cds: CodingSequence, raw: RawVariant, where: str) -> str:
    """An intronic substitution's reference base: from the intron's sequence, or the splice-site
    consensus GT…AG at ±1 / ±2 when the intron is not known."""
    pos = raw.start
    if raw.kind != "sub" or raw.start != raw.end:
        raise VidgenError(f"{where}: '{raw.text}': intronic changes are modelled as substitutions (splice sites); write e.g. "
                          f"c.{pos.c}{'+1' if pos.offset > 0 else '-1'}G>A")
    if not cds.exons:
        raise VidgenError(f"{where}: '{raw.text}': an intronic position needs the exons (exons: [[1, 92], [93, 315], …]) to place "
                          f"the intron")
    k = cds.exon_of(pos.c)
    if k is None:
        raise VidgenError(f"{where}: '{raw.text}': c.{pos.c} is not in an exon given")
    a, b = cds.exons[k]
    if pos.offset > 0 and pos.c != b:
        raise VidgenError(f"{where}: '{raw.text}': c.{pos.c}+{pos.offset} counts into an intron from an exon's last base; exon {cds.first_exon + k} "
                          f"ends at c.{b} (write c.{b}+{pos.offset})")
    if pos.offset < 0 and pos.c != a:
        raise VidgenError(f"{where}: '{raw.text}': c.{pos.c}{pos.offset} counts back into an intron from an exon's first base; exon "
                          f"{cds.first_exon + k} starts at c.{a} (write c.{a}{pos.offset})")
    if pos.offset > 0 and k == len(cds.exons) - 1 or pos.offset < 0 and k == 0:
        raise VidgenError(f"{where}: '{raw.text}': there is no intron {'after the last' if pos.offset > 0 else 'before the first'} "
                          f"coding exon given")
    known = cds.intron_base(pos.c, pos.offset)
    if known is not None:
        return known
    consensus = {1: "G", 2: "T", -1: "G", -2: "A"}
    if pos.offset not in consensus:
        raise VidgenError(f"{where}: '{raw.text}': the intron's sequence is not given, so only the splice-site dinucleotides are known "
                          f"(GT at +1 +2, AG at −2 −1); give the gene with its introns (gene:) for deeper positions")
    return consensus[pos.offset]


def resolve(cds: CodingSequence, raw: RawVariant, where: str = "variant") -> tuple[DnaVariant, Edit | None]:
    """The variant checked against the sequence (the reference bases it states, the window),
    as written (``written`` kept) and its exonic :class:`Edit` (``None`` for an intronic one)."""
    text = raw.text
    if raw.start.offset or raw.end.offset:
        ref = _intron_check(cds, raw, where)
        if raw.stated != ref:
            raise VidgenError(f"{where}: '{text}': c.{raw.start.text()} is {ref}, not {raw.stated}"
                              + (" (the splice-site consensus: introns start GT and end AG)" if cds.intron_base(raw.start.c, raw.start.offset) is None else ""))
        return DnaVariant("sub", raw.start, raw.end, ref, raw.alt, text), None
    _check_in_window(cds, raw.start, where, text)
    _check_in_window(cds, raw.end, where, text)
    s, e = cds.index(raw.start.c), cds.index(raw.end.c) + 1
    ref = cds.seq[s:e]
    if raw.kind == "sub":
        if raw.stated != ref:
            raise VidgenError(f"{where}: '{text}': {_px(text)}{raw.start.c} is {ref} in this sequence, not {raw.stated}")
        return DnaVariant("sub", raw.start, raw.end, ref, raw.alt, text), Edit(s, e, raw.alt)
    if raw.kind in ("del", "dup"):
        if raw.stated is not None and raw.stated != ref:
            raise VidgenError(f"{where}: '{text}': {_px(text)}{raw.start.c}{'_' + str(raw.end.c) if e - s > 1 else ''} is {ref} in this sequence, "
                              f"not {raw.stated}")
        if raw.kind == "del":
            return DnaVariant("del", raw.start, raw.end, ref, "", text), Edit(s, e, "")
        return DnaVariant("dup", raw.start, raw.end, ref, ref, text), Edit(e, e, ref)
    if raw.kind == "ins":
        return DnaVariant("ins", raw.start, raw.end, "", raw.alt, text), Edit(e - 1, e - 1, raw.alt)
    return DnaVariant("delins", raw.start, raw.end, ref, raw.alt, text), Edit(s, e, raw.alt)


def _exon_limit(cds: CodingSequence, idx: int) -> int:
    """The window index after the last base of the exon holding ``idx`` (or the window's end)."""
    if cds.exons:
        k = cds.exon_of(cds.first + idx)
        if k is not None:
            return min(len(cds.seq), cds.exons[k][1] - cds.first + 1)
    return len(cds.seq)


def normalize(cds: CodingSequence, edit: Edit) -> DnaVariant:
    """The HGVS description of ``edit``: common bases trimmed, a single base change a
    substitution, deletions and insertions moved to their 3′-most position within the exon, an
    insertion copying the bases before it written as a duplication."""
    seq = cds.seq
    s, e, alt = edit.start, edit.end, edit.alt
    ref = seq[s:e]
    while ref and alt and ref[0] == alt[0]:
        ref, alt, s = ref[1:], alt[1:], s + 1
    while ref and alt and ref[-1] == alt[-1]:
        ref, alt, e = ref[:-1], alt[:-1], e - 1
    if not ref and not alt:
        raise VidgenError("the change leaves the sequence as it was")
    pos = lambda i: Position(cds.first + i)  # noqa: E731
    if len(ref) == 1 and len(alt) == 1:
        return DnaVariant("sub", pos(s), pos(s), ref, alt)
    limit = _exon_limit(cds, s)
    if not alt:
        while e < limit and seq[s] == seq[e]:
            s, e = s + 1, e + 1
        return DnaVariant("del", pos(s), pos(e - 1), seq[s:e], "")
    if not ref:
        ins = alt
        while s < limit and ins[0] == seq[s]:
            ins = ins[1:] + ins[0]
            s += 1
        n = len(ins)
        if s - n >= 0 and seq[s - n:s] == ins:
            return DnaVariant("dup", pos(s - n), pos(s - 1), ins, ins)
        return DnaVariant("ins", pos(s - 1), pos(s), "", ins)
    return DnaVariant("delins", pos(s), pos(e - 1), ref, alt)


def apply_edit(seq: str, edit: Edit) -> str:
    return seq[:edit.start] + edit.alt + seq[edit.end:]


def check_written(cds: CodingSequence, written: DnaVariant, edit: Edit | None, where: str = "variant", prefix: str = "c.") -> DnaVariant:
    """The canonical description, after checking the author's matches it (the 3′ rule, dup for
    a copied insertion, the shortest form); the written form kept when it only adds the deleted
    bases (``c.1521_1523delCTT``)."""
    if edit is None:
        return written
    canon = normalize(cds, edit)
    same = (canon.kind, canon.start, canon.end, canon.alt if canon.kind != "dup" else "") == (
        written.kind, written.start, written.end, written.alt if written.kind != "dup" else "")
    if same:
        return replace(canon, written=written.written)
    why = ""
    if canon.kind == written.kind and canon.kind in ("del", "dup", "ins"):
        why = (" — HGVS's 3′ rule: in a run of repeated bases the change is placed at its 3′-most position (the bases "
               f"{_run_text(cds, canon)})")
    elif canon.kind == "dup" and written.kind == "ins":
        why = " — an insertion that copies the bases just before it is a duplication"
    elif canon.kind == "sub" and written.kind != "sub":
        why = " — one base replaced by one is a substitution"
    elif canon.kind != written.kind:
        why = f" — the shortest description is a {canon.kind}"
    raise VidgenError(f"{where}: '{written.written}' describes the same change as {canon.text(prefix)}; write {canon.text(prefix)}{why}")


def _run_text(cds: CodingSequence, v: DnaVariant) -> str:
    unit = v.ref if v.kind in ("del", "dup") else v.alt
    i = cds.index(v.start.c)
    lo = i
    n = len(unit)
    while lo - n >= 0 and cds.seq[lo - n:lo] == unit:
        lo -= n
    hi = cds.index(v.end.c) + 1 if v.kind != "ins" else i + 1
    return f"c.{cds.first + lo}–c.{cds.first + hi - 1} {cds.seq[lo:hi]}"


# ----- the protein -------------------------------------------------------------------------------------


def translation(seq: str, start: int) -> str:
    """Amino acids (one-letter, ``*`` a stop, ending there) from window index ``start``."""
    out = []
    for i in range(start, len(seq) - 2, 3):
        aa = translate(seq[i:i + 3])
        out.append(aa)
        if aa == "*":
            break
    return "".join(out)


@dataclass(frozen=True)
class ProteinChange:
    """A predicted protein consequence: ``kind`` (a :data:`CLASS_NAMES` key, or ``unknown``);
    ``start`` / ``end`` residue numbers (``end`` = ``start`` for one residue); ``ref`` the
    reference residues there (one-letter); ``alt`` the new ones (``*`` a stop); ``fs`` the new
    frame's length counting the first changed residue as 1 (``None``: no stop in the sequence
    given); ``after`` / ``before`` the residues an insertion lies between."""

    kind: str
    start: int | None = None
    end: int | None = None
    ref: str = ""
    alt: str = ""
    fs: int | None = None
    flank: tuple[str, str] = ("", "")

    def text(self, style: str = "three", stop: str = "*") -> str:
        """``p.(Glu7Val)`` in ``style`` (three- or one-letter codes) with the stop written ``*`` or
        ``Ter`` (``*`` with one-letter codes)."""
        one = style == "one"

        def a(code: str) -> str:
            if not code:
                return ""
            if code == "*":
                return "*" if (one or stop == "*") else "Ter"
            return code if one else _THREE[code]

        def run(codes: str) -> str:
            return "".join(a(c) for c in codes)

        k, s, e = self.kind, self.start, self.end
        if k in ("splice_donor", "splice_acceptor", "intronic", "unknown"):
            return "p.?"
        if k == "start_loss":
            return f"p.({a('M')}1?)"
        if k == "synonymous":
            return f"p.({a(self.ref)}{s}=)"
        if k in ("missense", "nonsense"):
            return f"p.({a(self.ref)}{s}{a(self.alt)})"
        if k == "frameshift":
            tail = "?" if self.fs is None else str(self.fs)
            return f"p.({a(self.ref)}{s}{a(self.alt)}fs{a('*')}{tail})"
        if k == "stop_loss":
            tail = "?" if self.fs is None else str(self.fs)
            return f"p.({a('*')}{s}{a(self.alt)}ext{a('*')}{tail})"
        if k == "inframe_ins":
            return f"p.({a(self.flank[0])}{s}_{a(self.flank[1])}{e}ins{run(self.alt)})"
        rng = f"{a(self.ref[0])}{s}" + (f"_{a(self.ref[-1])}{e}" if e != s else "")
        if k == "inframe_del":
            return f"p.({rng}del)"
        if k == "inframe_dup":
            return f"p.({rng}dup)"
        if k == "inframe_delins":
            return f"p.({rng}delins{run(self.alt)})"
        return "p.?"


def _first_codon_number(cds: CodingSequence) -> int:
    return cds.codon_number(cds.first + cds.frame_start)


def protein_change(cds: CodingSequence, variant: DnaVariant, edit: Edit | None) -> tuple[ProteinChange, str, str]:
    """The consequence of an exonic edit (or of a splice-site substitution: ``p.?``), with the
    reference and mutant translations of the window (one-letter, from its first whole codon)."""
    f0 = cds.frame_start
    wt = translation(cds.seq, f0)
    if edit is None:
        off = variant.start.offset
        kind = ("splice_donor" if off > 0 else "splice_acceptor") if abs(off) <= 2 else "intronic"
        return ProteinChange(kind), wt, wt
    if edit.start < f0:
        raise VidgenError(f"the change at c.{cds.first + edit.start} lies before the first whole codon of the sequence given "
                          f"(start it at a codon: c.{cds.first + f0})")
    mseq = apply_edit(cds.seq, edit)
    mut = translation(mseq, f0)
    n0 = _first_codon_number(cds)
    i = 0
    while i < len(wt) and i < len(mut) and wt[i] == mut[i]:
        i += 1
    shift = variant.length_change
    if i == len(wt) == len(mut):
        # the protein is unchanged in the window: synonymous (the codon of the change)
        k = (edit.start - f0) // 3
        return ProteinChange("synonymous", n0 + k, n0 + k, wt[k] if k < len(wt) else ""), wt, mut
    if i >= len(wt) or i >= len(mut):
        # one translation ran out (the window's end) where the other goes on: an in-frame change at the end
        i = min(len(wt), len(mut))
    pos = n0 + i
    ref_aa = wt[i] if i < len(wt) else ""
    alt_aa = mut[i] if i < len(mut) else ""
    if pos == 1 and n0 == 1 and ref_aa == "M":
        return ProteinChange("start_loss", 1, 1, "M"), wt, mut
    if ref_aa == "*" and alt_aa and alt_aa != "*":
        j = mut.find("*", i)
        return ProteinChange("stop_loss", pos, pos, "*", alt_aa, fs=(j - i) if j >= 0 else None), wt, mut
    if alt_aa == "*":
        return ProteinChange("nonsense", pos, pos, ref_aa, "*"), wt, mut
    if shift % 3 != 0:
        j = mut.find("*", i)
        return ProteinChange("frameshift", pos, pos, ref_aa, alt_aa, fs=(j - i + 1) if j >= 0 else None), wt, mut
    ws, ms = wt[i:], mut[i:]
    k = 0
    while k < min(len(ws), len(ms)) and ws[len(ws) - 1 - k] == ms[len(ms) - 1 - k]:
        k += 1
    dele, ins = ws[:len(ws) - k], ms[:len(ms) - k]
    if not ins:
        return ProteinChange("inframe_del", pos, pos + len(dele) - 1, dele), wt, mut
    if not dele:
        n = len(ins)
        if i - n >= 0 and wt[i - n:i] == ins:
            return ProteinChange("inframe_dup", pos - n, pos - 1, ins, ins), wt, mut
        return ProteinChange("inframe_ins", pos - 1, pos, "", ins, flank=(wt[i - 1], wt[i] if i < len(wt) else "")), wt, mut
    if len(dele) == 1 and len(ins) == 1:
        return ProteinChange("missense", pos, pos, dele, ins), wt, mut
    return ProteinChange("inframe_delins", pos, pos + len(dele) - 1, dele, ins), wt, mut


# ----- the author's p. -------------------------------------------------------------------------------


_AA = r"(?:[A-Z][a-z]{2}|[A-Z*])"


def _codes(text: str, where: str, raw: str) -> str:
    """One-letter codes of a run of three-letter (``GlyLeu``) or one-letter (``GL``) codes."""
    out = []
    i = 0
    while i < len(text):
        three = text[i:i + 3]
        if three.lower() in _ONE_OF and three[0].isupper() and three[1:].islower():
            out.append(_ONE_OF[three.lower()])
            i += 3
        elif text[i] in AMINO_ACIDS or text[i] == "*":
            out.append(text[i])
            i += 1
        elif text[i] == "X":
            raise VidgenError(f"{where}: '{raw}': X means an unknown amino acid in HGVS; a stop is * or Ter (R553X is the legacy name: "
                              f"p.(Arg553*))")
        else:
            raise VidgenError(f"{where}: '{raw}': '{text[i:i + 3]}' is not an amino acid code (three-letter Glu, or one-letter E)")
    return "".join(out)


def parse_p(text: str, where: str = "protein") -> ProteinChange:
    """An author's predicted protein change read into a :class:`ProteinChange` (``fs`` is
    ``None`` for the short form ``p.(Gly12fs)`` and ``-1`` for ``fs*?``)."""
    raw = str(text).strip()
    t = raw.replace("Ter", "*")
    if raw.startswith(("Δ", "delta")) or "Δ" in raw:
        raise VidgenError(f"{where}: '{raw}': ΔF508 is the legacy name; HGVS writes p.(Phe508del)")
    if not t.startswith("p."):
        raise VidgenError(f"{where}: '{raw}': an HGVS protein change starts with p. (p.(Glu7Val))")
    body = t[2:]
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    if body in ("?", "0", "="):
        return ProteinChange({"?": "unknown", "0": "unknown", "=": "synonymous"}[body])
    if re.fullmatch(rf"({_AA})1\?", body):
        return ProteinChange("start_loss", 1, 1, "M")
    m = re.fullmatch(rf"({_AA})(\d+)=", body)
    if m:
        return ProteinChange("synonymous", int(m.group(2)), int(m.group(2)), _codes(m.group(1), where, raw))
    m = re.fullmatch(rf"({_AA})(\d+)({_AA})?fs(?:\*(\d+|\?))?", body)
    if m:
        alt = _codes(m.group(3), where, raw) if m.group(3) else ""
        fs = None if m.group(4) is None else (-1 if m.group(4) == "?" else int(m.group(4)))
        return ProteinChange("frameshift", int(m.group(2)), int(m.group(2)), _codes(m.group(1), where, raw), alt, fs=fs)
    m = re.fullmatch(rf"\*(\d+)({_AA})ext\*(\d+|\?)", body)
    if m:
        return ProteinChange("stop_loss", int(m.group(1)), int(m.group(1)), "*", _codes(m.group(2), where, raw),
                             fs=-1 if m.group(3) == "?" else int(m.group(3)))
    m = re.fullmatch(rf"({_AA})(\d+)(?:_({_AA})(\d+))?(del|dup|delins|ins)(.*)", body)
    if m:
        a1, p1, a2, p2, op, tail = m.groups()
        s = int(p1)
        e = int(p2) if p2 else s
        first = _codes(a1, where, raw)
        last = _codes(a2, where, raw) if a2 else first
        if op in ("del", "dup") and tail:
            raise VidgenError(f"{where}: '{raw}': nothing follows {op} in a protein change")
        if op == "ins":
            if not p2 or e != s + 1:
                raise VidgenError(f"{where}: '{raw}': an insertion names the two residues it lies between (p.(His7_Gln8insGly))")
            return ProteinChange("inframe_ins", s, e, "", _codes(tail, where, raw), flank=(first, last))
        if op == "delins":
            return ProteinChange("inframe_delins", s, e, first + ("" if e == s else "…" + last), _codes(tail, where, raw))
        return ProteinChange("inframe_del" if op == "del" else "inframe_dup", s, e, first + ("" if e == s else "…" + last))
    m = re.fullmatch(rf"({_AA})(\d+)({_AA})", body)
    if m:
        a, alt = _codes(m.group(1), where, raw), _codes(m.group(3), where, raw)
        return ProteinChange("nonsense" if alt == "*" else "missense", int(m.group(2)), int(m.group(2)), a, alt)
    raise VidgenError(f"{where}: '{raw}': not an HGVS protein change (p.(Glu7Val), p.(Arg553*), p.(Phe508del), p.(Gly12Valfs*2), "
                      f"p.(Leu10=), p.?)")


def check_stated(stated: ProteinChange, computed: ProteinChange, raw: str, computed_text: str, wt: str, first_codon: int,
                 where: str = "protein") -> None:
    """The author's ``p.`` agrees with the computed one; else a :class:`VidgenError` with the
    computed one (and the reason for the usual slips: legacy numbering without Met)."""
    def ends(pc: ProteinChange) -> str:
        return pc.ref[0] + pc.ref[-1] if pc.ref else ""

    ok = stated.kind == computed.kind or (stated.kind == "unknown" and computed.kind in ("splice_donor", "splice_acceptor", "intronic"))
    if ok and stated.kind not in ("unknown",) and computed.kind not in ("splice_donor", "splice_acceptor", "intronic"):
        if stated.kind == "synonymous" and stated.start is None:
            pass
        elif (stated.start, stated.end) != (computed.start, computed.end):
            ok = False
        elif stated.kind in ("inframe_del", "inframe_dup", "inframe_delins"):
            ok = ends(stated) == ends(computed) and (stated.kind != "inframe_delins" or stated.alt == computed.alt)
        elif stated.kind == "inframe_ins":
            ok = stated.flank == computed.flank and stated.alt == computed.alt
        elif stated.kind == "frameshift":
            ok = stated.ref == computed.ref and (not stated.alt or stated.alt == computed.alt) and (
                stated.fs is None or stated.fs == (computed.fs if computed.fs is not None else -1))
        elif stated.kind == "stop_loss":
            ok = stated.alt == computed.alt and stated.fs == (computed.fs if computed.fs is not None else -1)
        else:
            ok = stated.ref == computed.ref and stated.alt == computed.alt
    if ok:
        return
    hint = ""
    if (stated.start is not None and computed.start is not None and stated.start == computed.start - 1
            and stated.kind == computed.kind and stated.ref == computed.ref):
        hint = (f" — HGVS counts the initiator Met as residue 1; {stated.start} is the legacy numbering of the mature protein "
                f"(put it in legacy:)")
    elif stated.start is not None and computed.start is not None and stated.start != computed.start:
        idx = stated.start - first_codon
        if 0 <= idx < len(wt) and stated.ref[:1] and wt[idx] != stated.ref[:1]:
            hint = f" — residue {stated.start} is {_THREE[wt[idx]]} in this sequence, not {_THREE.get(stated.ref[0], stated.ref[0])}"
    raise VidgenError(f"{where}: '{raw}' does not follow from the DNA change: the genetic code gives {computed_text}{hint}")


# ----- consequences in words ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Consequence:
    """Everything said about a variant: the DNA change (canonical, as written), the protein change,
    its class, the window's reference and mutant translations, the mutant sequence, the edit,
    notes (amino acid properties, NMD, splicing), and a predicted RNA change for splice sites."""

    dna: DnaVariant
    protein: ProteinChange
    edit: Edit | None
    wt_protein: str
    mut_protein: str
    mut_seq: str
    notes: tuple[str, ...] = ()
    rna: str | None = None
    skipped_exon: int | None = None
    retained_intron: int | None = None
    frame_kept: bool | None = None

    @property
    def kind(self) -> str:
        return self.protein.kind

    @property
    def label(self) -> str:
        return CLASS_NAMES.get(self.protein.kind, self.protein.kind)


def consequence(cds: CodingSequence, text: str, where: str = "variant", splice: str = "auto", prefix: str = "c.") -> Consequence:
    """Parse ``text``, check it against ``cds`` (bases, window, HGVS form) and work out what it does."""
    raw = parse_c(text, where, prefix)
    written, edit = resolve(cds, raw, where)
    dna = check_written(cds, written, edit, where, prefix)
    return explain(cds, dna, edit, splice)


def edit_consequence(cds: CodingSequence, edit: Edit) -> Consequence:
    """What an exonic edit made by other means (a CRISPR repair) is, in HGVS form and its effect."""
    return explain(cds, normalize(cds, edit), edit, "auto")


def explain(cds: CodingSequence, dna: DnaVariant, edit: Edit | None, splice: str = "auto") -> Consequence:
    """The protein change, class and notes of a checked DNA change."""
    pc, wt, mut = protein_change(cds, dna, edit)
    mseq = apply_edit(cds.seq, edit) if edit is not None else cds.seq
    notes: list[str] = []
    rna = None
    skipped = retained = None
    kept = None
    if pc.kind == "missense":
        a, b = side_chain_class(pc.ref), side_chain_class(pc.alt)
        notes.append(f"{_THREE[pc.ref]} ({a}) → {_THREE[pc.alt]} ({b})" + ("" if a != b else ": a similar side chain (conservative)"))
    if pc.kind == "synonymous":
        k = (edit.start - cds.frame_start) // 3 if edit is not None else 0
        a0 = cds.frame_start + 3 * k
        notes.append(f"{cds.seq[a0:a0 + 3]} → {mseq[a0:a0 + 3]}: both code {_THREE[pc.ref]} (the code is degenerate)")
    if pc.kind in ("nonsense", "frameshift"):
        notes += _nmd_note(cds, pc, dna)
    if pc.kind in ("inframe_del", "inframe_dup", "inframe_ins", "inframe_delins"):
        # the class beside it says "in-frame"; the note says why
        notes.append(f"{abs(dna.length_change)} nt {'lost' if dna.length_change < 0 else 'added'}: a multiple of 3")
        if edit is not None:
            k = (edit.start - cds.frame_start) // 3
            a0 = cds.frame_start + 3 * k
            before, after = cds.seq[a0:a0 + 3], mseq[a0:a0 + 3]
            if len(after) == 3 and before != after and translate(before) == translate(after) and translate(before) != "*":
                notes.append(f"codon {cds.codon_number(cds.first + a0)} {before} → {after}: still {_THREE[translate(before)]}")
    if pc.kind == "frameshift":
        notes.append(f"{abs(dna.length_change)} nt {'lost' if dna.length_change < 0 else 'added'}: not a multiple of 3, the reading "
                     f"frame shifts")
    if pc.kind in ("splice_donor", "splice_acceptor"):
        rna, skipped, retained, kept, more = _splice(cds, dna, splice)
        notes += more
    if pc.kind == "intronic":
        notes.append("deeper in the intron: it may still change splicing (not predicted here)")
    return Consequence(dna, pc, edit, wt, mut, mseq, tuple(notes), rna, skipped, retained, kept)


def _nmd_note(cds: CodingSequence, pc: ProteinChange, dna: DnaVariant) -> list[str]:
    """Whether the premature stop lies more than ~50 nt upstream of the last exon–exon junction."""
    if pc.kind == "frameshift" and pc.fs is None:
        return ["the new frame's stop lies beyond the sequence given"]
    stop_res = (pc.start or 0) + ((pc.fs or 1) - 1 if pc.kind == "frameshift" else 0)
    stop_end = 3 * stop_res - (dna.length_change if pc.kind == "frameshift" else 0)   # c. of the stop's last base, reference numbering
    if not cds.complete_exons():
        return ["a premature stop codon: the mRNA may be degraded by nonsense-mediated decay (give every coding exon and length: to judge)"]
    if len(cds.exons) == 1:
        return ["the stop lies in the last (only) coding exon: no nonsense-mediated decay; a truncated protein may be made"]
    junction = cds.exons[-2][1]
    if junction - stop_end >= NMD_DISTANCE:
        return [f"premature stop {junction - stop_end} nt upstream of the last exon–exon junction (> ~{NMD_DISTANCE}): "
                f"nonsense-mediated decay is expected"]
    return ["the premature stop lies in the last exon or within ~50 nt of the last junction: the mRNA escapes "
            "nonsense-mediated decay; a truncated protein may be made"]


def _splice(cds: CodingSequence, dna: DnaVariant, splice: str) -> tuple[str, int | None, int | None, bool | None, list[str]]:
    """The predicted RNA consequence of a splice-site change: the exon skipped (in frame when its
    length is a multiple of 3) or the intron retained."""
    pos = dna.start
    k = cds.exon_of(pos.c)
    assert k is not None
    donor = pos.offset > 0
    n0 = cds.first_exon
    site = f"the {'donor (5′)' if donor else 'acceptor (3′)'} splice site of intron {n0 + k if donor else n0 + k - 1}"
    lost = "GT" if donor else "AG"
    changed = {1: dna.alt + "T", 2: "G" + dna.alt, -2: dna.alt + "G", -1: "A" + dna.alt}.get(pos.offset, "")
    notes = [f"{lost} → {changed}: {site} is lost (introns start GT and end AG)" if changed else f"{site} changed"]
    skip_exon = k
    first_coding = skip_exon == 0 and cds.exons[0][0] == 1
    last_coding = skip_exon == len(cds.exons) - 1 and cds.length is not None and cds.exons[-1][1] >= cds.length
    edge = first_coding or last_coding
    mode = splice
    if mode == "auto":
        mode = "retain" if edge else "skip"
    if mode == "skip" and edge:
        raise VidgenError(f"splice: skip: exon {n0 + skip_exon} is the {'first' if skip_exon == 0 else 'last'} coding exon given; exon "
                          f"skipping joins the exons on both sides of an internal exon (write splice: retain, or auto)")
    if mode == "skip":
        a, b = cds.exons[skip_exon]
        n = b - a + 1
        kept = n % 3 == 0
        rna = f"r.({a}_{b}del)"
        notes.append(f"predicted: exon {n0 + skip_exon} (c.{a}–{b}, {n} nt) is skipped → "
                     + ("in frame: its residues are lost" if kept else "not a multiple of 3: a frameshift"))
        notes.append("p.? — the protein effect needs RNA studies (exon skipping, intron retention or a cryptic site)")
        return rna, skip_exon, None, kept, notes
    intron = k if donor else k - 1
    seq = cds.introns[intron] if intron < len(cds.introns) else None
    if seq:
        kept = len(seq) % 3 == 0
        notes.append(f"predicted: intron {n0 + intron} ({len(seq)} nt) is retained in the mRNA and read as codons")
    else:
        kept = None
        notes.append(f"predicted: intron {n0 + intron} is retained in the mRNA and read as codons (usually a premature stop soon)")
    notes.append("p.? — the protein effect needs RNA studies (exon skipping, intron retention or a cryptic site)")
    b = cds.exons[intron][1]
    return f"r.({b}_{b + 1}ins{b}+1_{b + 1}-1)", None, intron, kept, notes


__all__ = ["BASE_HUES", "CLASS_NAMES","CodingSequence", "Consequence", "DnaVariant", "Edit", "Position", "ProteinChange", "RawVariant",
           "apply_edit", "check_stated", "check_written", "coding_sequence", "consequence", "edit_consequence", "explain", "normalize",
           "parse_c", "parse_p",
           "protein_change", "resolve", "side_chain_class", "translate", "translation"]

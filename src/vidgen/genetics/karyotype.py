"""Human karyotypes (DESIGN.md §96.10): the 24 chromosomes with their lengths and centromere
positions, schematic G-band ideograms, ISCN karyotype notation parsed and checked
(``46,XX``, ``47,XY,+21``, ``45,X``, ``47,XXY``, ``46,XY,del(5)(p15.2)``,
``46,XX,t(9;22)(q34;q11.2)``, ``45,XX,rob(14;21)(q10;q10)``…) and the chromosomes it describes,
derivatives included, as segments of the normal ones. No manim.

What is exact and what is schematic:

- **Lengths and centromeres** are the GRCh38 assembly's (Mb; the centromere at the middle of its
  ``acen`` bands), so relative sizes and arm ratios are right (21 is shorter than 22). The
  classes (metacentric, submetacentric, acrocentric with satellites on 13, 14, 15, 21 and 22) and
  the Denver groups A–G are the textbook ones.
- **Band names** follow ISCN syntax (arm, region, band, sub-band: ``7q31.2``); the last band of
  each arm (``1p36``, ``1q44``, ``Xq28``…) is checked, so a band past an arm's end is refused.
- **Band positions and patterns are schematic**: each arm is split into its regions and bands
  evenly (the terminal band pale, dark bands alternating), not the ISCN ideogram's measured
  positions. A named band is drawn where this scheme puts it — near, not exactly at, its real
  place. Heterochromatin (1q12, 9q12, 16q11.2, Yq12) and the satellites, stalks of the
  acrocentrics are drawn as such."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidgen.cellworld.model import did_you_mean
from vidgen.errors import VidgenError

AUTOSOMES = tuple(str(k) for k in range(1, 23))
NAMES = AUTOSOMES + ("X", "Y")
#: GRCh38: chromosome length and the centromere's middle (Mb).
LENGTH_MB: dict[str, float] = {
    "1": 248.96, "2": 242.19, "3": 198.30, "4": 190.21, "5": 181.54, "6": 170.81, "7": 159.35, "8": 145.14, "9": 138.39,
    "10": 133.80, "11": 135.09, "12": 133.28, "13": 114.36, "14": 107.04, "15": 101.99, "16": 90.34, "17": 83.26, "18": 80.37,
    "19": 58.62, "20": 64.44, "21": 46.71, "22": 50.82, "X": 156.04, "Y": 57.23,
}
CENTROMERE_MB: dict[str, float] = {
    "1": 123.4, "2": 93.9, "3": 90.9, "4": 50.0, "5": 48.8, "6": 59.8, "7": 60.1, "8": 45.2, "9": 43.0, "10": 39.8, "11": 53.4,
    "12": 35.5, "13": 17.7, "14": 17.2, "15": 19.0, "16": 36.8, "17": 25.1, "18": 18.5, "19": 26.2, "20": 28.1, "21": 12.0,
    "22": 15.0, "X": 60.6, "Y": 10.4,
}
#: The last band of each arm (ISCN): region and band of the terminal band.
TERMINAL: dict[str, tuple[str, str]] = {
    "1": ("36", "44"), "2": ("25", "37"), "3": ("26", "29"), "4": ("16", "35"), "5": ("15", "35"), "6": ("25", "27"),
    "7": ("22", "36"), "8": ("23", "24"), "9": ("24", "34"), "10": ("15", "26"), "11": ("15", "25"), "12": ("13", "24"),
    "13": ("13", "34"), "14": ("13", "32"), "15": ("13", "26"), "16": ("13", "24"), "17": ("13", "25"), "18": ("11", "23"),
    "19": ("13", "13"), "20": ("13", "13"), "21": ("13", "22"), "22": ("13", "13"), "X": ("22", "28"), "Y": ("11", "12"),
}
GROUPS: dict[str, tuple[str, ...]] = {
    "A": ("1", "2", "3"), "B": ("4", "5"), "C": ("6", "7", "8", "9", "10", "11", "12", "X"), "D": ("13", "14", "15"),
    "E": ("16", "17", "18"), "F": ("19", "20"), "G": ("21", "22", "Y"),
}
GROUP_OF = {c: g for g, cs in GROUPS.items() for c in cs}
METACENTRIC = ("1", "3", "16", "19", "20")
ACROCENTRIC = ("13", "14", "15", "21", "22", "Y")
#: Acrocentrics with satellites (nucleolus organizer regions on the stalks; not the Y).
SATELLITED = ("13", "14", "15", "21", "22")
#: Constitutive heterochromatin drawn as such.
HETEROCHROMATIN = {("1", "q12"), ("9", "q12"), ("16", "q11"), ("Y", "q12")}
#: Bands per region where the region is not the arm's last (schematic).
REGION_BANDS = 3


def chromosome_class(name: str) -> str:
    if name in ACROCENTRIC:
        return "acrocentric"
    return "metacentric" if name in METACENTRIC else "submetacentric"


def chromosome_name(value: Any, where: str) -> str:
    text = str(value).strip()
    key = text.upper() if text.upper() in ("X", "Y") else text
    if key not in NAMES:
        raise VidgenError(f"{where}: '{text}' is not a human chromosome (1–22, X, Y){did_you_mean(text, list(NAMES))}")
    return key


# ----- bands -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Band:
    """A drawn band: name (``q21``), from and to (Mb from pter), stain (``gneg``, ``gpos25`` …
    ``gpos100``, ``gvar`` heterochromatin, ``stalk``, ``satellite``)."""

    name: str
    start: float
    end: float
    stain: str


def _arm_bands(chrom: str, arm: str) -> list[tuple[str, int, int]]:
    """(name, region, band) from the centromere outwards."""
    term = TERMINAL[chrom][0 if arm == "p" else 1]
    regions, last = int(term[0]), int(term[1])
    out = []
    for r in range(1, regions + 1):
        for b in range(1, (last if r == regions else REGION_BANDS) + 1):
            out.append((f"{arm}{r}{b}", r, b))
    return out


def _stain_level(chrom: str, name: str) -> str:
    h = sum(ord(c) * (k + 7) for k, c in enumerate(chrom + name))
    return ("gpos50", "gpos75", "gpos100", "gpos75", "gpos25")[h % 5]


def bands(chrom: str) -> tuple[Band, ...]:
    """The schematic ideogram of ``chrom`` from pter to qter (see the module docstring)."""
    length, cen = LENGTH_MB[chrom], CENTROMERE_MB[chrom]
    out: list[Band] = []
    for arm in ("p", "q"):
        names = _arm_bands(chrom, arm)
        span = cen if arm == "p" else length - cen
        n = len(names)
        weights = [1.0 + 0.35 * (((sum(map(ord, chrom + nm)) * 37) % 11) / 10 - 0.5) for nm, _, _ in names]
        total = sum(weights)
        edge = 0.0
        made = []
        for i, ((nm, _r, _b), wgt) in enumerate(zip(names, weights)):
            a, b = edge, (edge + span * wgt / total if i < n - 1 else span)   # the last band ends exactly at the telomere
            edge = b
            dark = (n - 1 - i) % 2 == 1
            stain = _stain_level(chrom, nm) if dark else "gneg"
            if (chrom, nm) in HETEROCHROMATIN:
                stain = "gvar"
            if arm == "p" and chrom in SATELLITED:
                stain = {"p11": "gpos25", "p12": "stalk", "p13": "satellite"}.get(nm, stain)
            if arm == "p":
                made.append(Band(nm, cen - b, cen - a, stain))
            else:
                made.append(Band(nm, cen + a, cen + b, stain))
        out += sorted(made, key=lambda x: x.start)
    return tuple(out)


_BAND_RE = re.compile(r"^([pq])(\d)(\d)(?:\.(\d{1,3}))?$")


@dataclass(frozen=True)
class BandRef:
    """A band named in ISCN (``q31.2``) on a chromosome, with where the scheme puts it (Mb)."""

    chrom: str
    arm: str
    text: str
    start: float
    end: float

    @property
    def mid(self) -> float:
        return (self.start + self.end) / 2

    @property
    def label(self) -> str:
        return f"{self.chrom}{self.text}"


def band_ref(chrom: str, text: str, where: str) -> BandRef:
    """The band ``text`` (``p15.2``, ``q34``, ``q10`` = the centromere on the q side) of ``chrom``,
    checked against the arm's last band."""
    t = str(text).strip()
    if t in ("p10", "q10"):
        cen = CENTROMERE_MB[chrom]
        return BandRef(chrom, t[0], t, cen, cen)
    m = _BAND_RE.match(t)
    if not m:
        raise VidgenError(f"{where}: band '{t}' is not an ISCN band: write the arm (p or q), region and band, with an optional "
                          f"sub-band: p15.2, q34, q11.2 (q10 / p10 for the centromere)")
    arm, region, band, sub = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    term = TERMINAL[chrom][0 if arm == "p" else 1]
    last_r, last_b = int(term[0]), int(term[1])
    if region < 1 or band < 1 or region > last_r or (region == last_r and band > last_b):
        raise VidgenError(f"{where}: {chrom}{t} does not exist: {chrom}{arm} ends at band {chrom}{arm}{term}")
    in_region = [x for x in bands(chrom) if x.name[0] == arm and x.name[1] == str(region)]
    lo_mb, hi_mb = min(x.start for x in in_region), max(x.end for x in in_region)
    if band <= len(in_region):
        drawn = next(x for x in in_region if x.name == f"{arm}{region}{band}")
    else:   # a band the scheme does not draw (regions other than the last get a few): placed in proportion in its region
        parts = band
        if arm == "p":
            drawn = Band(t, hi_mb - (hi_mb - lo_mb) * band / parts, hi_mb - (hi_mb - lo_mb) * (band - 1) / parts, "gneg")
        else:
            drawn = Band(t, lo_mb + (hi_mb - lo_mb) * (band - 1) / parts, lo_mb + (hi_mb - lo_mb) * band / parts, "gneg")
    a, b = drawn.start, drawn.end
    if sub is not None:
        parts = max(3, int(sub[0]))
        k = int(sub[0])
        lo, hi = (k - 1) / parts, k / parts          # sub-bands from the centromere side
        if arm == "p":
            a, b = drawn.end - (drawn.end - drawn.start) * hi, drawn.end - (drawn.end - drawn.start) * lo
        else:
            a, b = drawn.start + (drawn.end - drawn.start) * lo, drawn.start + (drawn.end - drawn.start) * hi
    return BandRef(chrom, arm, t, a, b)


def parse_band_label(text: str, where: str) -> BandRef:
    """``7q31.2`` → the band q31.2 of chromosome 7."""
    m = re.match(r"^\s*(\d{1,2}|[XYxy])([pq].*)$", str(text))
    if not m:
        raise VidgenError(f"{where}: '{text}' is not a band: write the chromosome then the band, e.g. 7q31.2, Xq28, 21q22")
    return band_ref(chromosome_name(m.group(1), where), m.group(2), where)


# ----- chromosomes as segments --------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """A piece of a normal chromosome, from ``a`` to ``b`` Mb (``a > b``: inverted)."""

    chrom: str
    a: float
    b: float

    @property
    def length(self) -> float:
        return abs(self.b - self.a)


@dataclass(frozen=True)
class Copy:
    """One chromosome of the cell: its slot in the karyogram, its segments from pter, where its
    centromere is (Mb along it), its name (``21``, ``der(22)``), the abnormality that made it
    (index) and the stretches to highlight (Mb along it)."""

    slot: str
    segments: tuple[Segment, ...]
    centromere: float
    name: str
    change: int | None = None
    marks: tuple[tuple[float, float], ...] = ()

    @property
    def length(self) -> float:
        return sum(s.length for s in self.segments)

    @property
    def normal(self) -> bool:
        return self.change is None


def normal_copy(chrom: str, extra: int | None = None) -> Copy:
    """An intact chromosome (``extra``: the index of the numerical change that added it)."""
    return Copy(chrom, (Segment(chrom, 0.0, LENGTH_MB[chrom]),), CENTROMERE_MB[chrom], chrom, extra,
                ((0.0, LENGTH_MB[chrom]),) if extra is not None else ())


# ----- ISCN --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Abnormality:
    """One item after the sex chromosomes: ``kind`` (gain, loss, del, dup, inv, t, rob),
    chromosomes, bands, the ISCN text and its reading."""

    kind: str
    chroms: tuple[str, ...]
    bands: tuple[BandRef, ...]
    text: str
    reading: str
    origin: str = ""


@dataclass(frozen=True)
class Karyotype:
    """A parsed karyotype: the text, the count, the sex chromosomes, the abnormalities, the cell's
    chromosomes (by slot), the reading (sex, each change, a named condition) and notes."""

    text: str
    count: int
    sex: str
    abnormalities: tuple[Abnormality, ...]
    copies: Mapping[str, tuple[Copy, ...]]
    conditions: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_female(self) -> bool:
        return "Y" not in self.sex

    @property
    def balanced(self) -> bool:
        return all(a.kind in ("inv", "t") for a in self.abnormalities) and self.count == 46 and self.sex in ("XX", "XY")

    def summary(self) -> str:
        """``female, trisomy 21`` (the sex, the changes)."""
        sex = "female" if self.is_female else "male"
        if self.sex not in ("XX", "XY"):
            sex = f"{sex} with {len(self.sex)} sex chromosome{'s' if len(self.sex) != 1 else ''} ({self.sex})"
        return sex

    def changed_slots(self) -> list[str]:
        out: list[str] = []
        for a in self.abnormalities:
            out += [c for c in a.chroms if c not in out]
        if self.sex not in ("XX", "XY"):
            out += [c for c in ("X", "Y") if c not in out and (c in self.sex or c == "X")]
        return out


_STRUCT_RE = re.compile(r"^(del|dup|inv|t|rob|der)\(([^)]*)\)(?:\(([^)]*)\))?(mat|pat|dn)?$")
_SPLIT_BANDS = re.compile(r"[pq](?:\d\d(?:\.\d{1,3})?|10)")
ROB_FORM = "rob(14;21)(q10;q10)"


def _bands_in(text: str, count: int, where: str, what: str) -> list[str]:
    found = _SPLIT_BANDS.findall(text)
    if "".join(found) != text.replace(" ", "") or len(found) != count:
        raise VidgenError(f"{where}: {what}: write {count} band(s) without separators, e.g. "
                          f"{'(p15.2)' if count == 1 else '(q21q32)'}")
    return found


def _arm_of(ref: BandRef) -> str:
    return ref.arm


def parse_karyotype(text: Any, where: str = "karyotype") -> Karyotype:
    """Parse and check an ISCN karyotype (see the module docstring for what is supported)."""
    raw = str(text).strip()
    if not raw:
        raise VidgenError(f"{where}: empty karyotype: write e.g. 46,XX or 47,XY,+21")
    if "/" in raw:
        raise VidgenError(f"{where}: '{raw}' is a mosaic (cell lines separated by /): draw one cell line at a time, e.g. "
                          f"'{raw.split('/')[0]}'")
    parts = [p.strip() for p in raw.split(",")]
    if any(not p for p in parts):
        raise VidgenError(f"{where}: '{raw}': an empty item between commas (ISCN writes 47,XY,+21 without spaces)")
    if not parts[0].isdigit():
        raise VidgenError(f"{where}: '{raw}' starts with '{parts[0]}': an ISCN karyotype starts with the chromosome count, "
                          f"then the sex chromosomes: 46,XX")
    count = int(parts[0])
    if len(parts) < 2:
        raise VidgenError(f"{where}: '{raw}': after the count come the sex chromosomes (46,XX or 46,XY)")
    sex = parts[1]
    if not re.fullmatch(r"[XY]+", sex):
        hint = " (letters in capitals)" if re.fullmatch(r"[xyXY]+", sex) else ""
        raise VidgenError(f"{where}: '{sex}' is not a sex chromosome complement: write the X and Y chromosomes present, e.g. XX, XY, "
                          f"X, XXY{hint}")
    if "X" not in sex:
        raise VidgenError(f"{where}: {sex}: no X chromosome — a karyotype without an X is not viable (45,X is Turner syndrome)")
    if len(sex) > 5:
        raise VidgenError(f"{where}: {sex}: more than five sex chromosomes")
    sex = "".join(sorted(sex))           # X before Y
    copies: dict[str, list[Copy]] = {c: [normal_copy(c), normal_copy(c)] for c in AUTOSOMES}
    copies["X"] = [normal_copy("X") for _ in range(sex.count("X"))]
    copies["Y"] = [normal_copy("Y") for _ in range(sex.count("Y"))]
    abns: list[Abnormality] = []
    for k, item in enumerate(parts[2:]):
        here = f"{where} item '{item}'"
        abn = _parse_item(item, here)
        idx = len(abns)
        _apply(copies, abn, idx, here)
        abns.append(abn)
    total = sum(len(v) for v in copies.values())
    if total != count:
        gains = sum(1 for a in abns if a.kind == "gain")
        losses = sum(1 for a in abns if a.kind == "loss")
        robs = sum(1 for a in abns if a.kind == "rob")
        parts_txt = [f"44 autosomes + {sex} = {44 + len(sex)}"]
        if gains:
            parts_txt.append(f"+ {gains} gained")
        if losses:
            parts_txt.append(f"− {losses} lost")
        if robs:
            parts_txt.append(f"− {robs} (a Robertsonian translocation makes one chromosome of two)")
        raise VidgenError(f"{where}: '{raw}' says {count} chromosomes but lists {total} ({' '.join(parts_txt)}); write "
                          f"{total},{','.join(parts[1:])}")
    kt = Karyotype(raw, count, sex, tuple(abns), {c: tuple(v) for c, v in copies.items()})
    kt = Karyotype(kt.text, kt.count, kt.sex, kt.abnormalities, kt.copies, _conditions(kt))
    return Karyotype(kt.text, kt.count, kt.sex, kt.abnormalities, kt.copies, kt.conditions, _notes(kt))


def _parse_item(item: str, where: str) -> Abnormality:
    m = re.fullmatch(r"([+-])(\w+)", item)
    if m:
        sign, c = m.groups()
        if c.upper() in ("X", "Y"):
            raise VidgenError(f"{where}: sex chromosome gains and losses are written in the sex chromosomes, not as {sign}{c}: "
                              f"47,XXY, 45,X, 47,XYY")
        chrom = chromosome_name(c, where)
        if sign == "+":
            return Abnormality("gain", (chrom,), (), item, f"an extra chromosome {chrom} (trisomy {chrom})")
        return Abnormality("loss", (chrom,), (), item, f"one chromosome {chrom} missing (monosomy {chrom})")
    if re.fullmatch(r"\d{1,2}[pq][+-]", item):
        raise VidgenError(f"{where}: '{item}' is the old short notation: ISCN writes the change and its bands, e.g. del(5)(p15.2)")
    m = _STRUCT_RE.match(item)
    if not m:
        known = "+21, -13, del(5)(p15.2), del(1)(q21q32), dup(1)(q21q32), inv(9)(p12q13), t(9;22)(q34;q11.2), rob(14;21)(q10;q10)"
        head = item.split("(")[0]
        hint = did_you_mean(head, ["del", "dup", "inv", "t", "rob", "der"]) if "(" in item else ""
        raise VidgenError(f"{where}: not understood{hint} — supported: {known} (mosaics, rings, isochromosomes and markers are not)")
    kind, chroms_txt, bands_txt, origin = m.group(1), m.group(2), m.group(3), m.group(4) or ""
    chroms = tuple(chromosome_name(c, where) for c in chroms_txt.split(";"))
    if kind in ("del", "dup", "inv"):
        if len(chroms) != 1:
            raise VidgenError(f"{where}: {kind} names one chromosome: {kind}(5)(…)")
        if bands_txt is None:
            raise VidgenError(f"{where}: give the band(s) after the chromosome: {kind}({chroms[0]})(p15.2)")
        need = (1, 2) if kind == "del" else (2,)
        found = _SPLIT_BANDS.findall(bands_txt)
        if len(found) not in need:
            raise VidgenError(f"{where}: {kind} takes {' or '.join(map(str, need))} band(s): "
                              + ("del(5)(p15.2) (terminal) or del(1)(q21q32) (interstitial)" if kind == "del" else f"{kind}(1)(q21q32)"))
        names = _bands_in(bands_txt, len(found), where, kind)
        c = chroms[0]
        refs = tuple(sorted((band_ref(c, b, where) for b in names), key=lambda r: r.mid))
        if any(r.text in ("p10", "q10") for r in refs):
            raise VidgenError(f"{where}: p10 / q10 (the centromere) belong to Robertsonian translocations and isochromosomes")
        return _structural(kind, c, refs, item, where, origin)
    if kind == "t":
        if len(chroms) != 2 or chroms[0] == chroms[1]:
            raise VidgenError(f"{where}: a reciprocal translocation names two different chromosomes: t(9;22)(q34;q11.2)")
        order = list(NAMES[22:]) + list(AUTOSOMES)
        if order.index(chroms[0]) > order.index(chroms[1]):
            raise VidgenError(f"{where}: ISCN lists the sex chromosome or the lower-numbered chromosome first: "
                              f"t({chroms[1]};{chroms[0]})(…;…) with the bands in the same order")
        if bands_txt is None or bands_txt.count(";") != 1:
            raise VidgenError(f"{where}: give one band per chromosome, separated by ';': t({chroms[0]};{chroms[1]})(q34;q11.2)")
        b1, b2 = (x.strip() for x in bands_txt.split(";"))
        r1, r2 = band_ref(chroms[0], b1, where), band_ref(chroms[1], b2, where)
        if "10" in (b1[1:], b2[1:]):
            raise VidgenError(f"{where}: a break at the centromere (q10) between acrocentrics is a Robertsonian translocation: "
                              f"rob({chroms[0]};{chroms[1]})(q10;q10)")
        reading = (f"reciprocal translocation: {chroms[0]}{r1.text}→{r1.arm}ter and {chroms[1]}{r2.text}→{r2.arm}ter swapped "
                   f"(balanced)")
        return Abnormality("t", chroms, (r1, r2), item, reading, origin)
    # rob / der(a;b)
    if len(chroms) != 2:
        raise VidgenError(f"{where}: a Robertsonian translocation names two acrocentric chromosomes: {ROB_FORM}")
    for c in chroms:
        if c not in SATELLITED:
            raise VidgenError(f"{where}: {c} is not an acrocentric autosome: Robertsonian translocations join two of 13, 14, 15, "
                              f"21, 22 at their centromeres")
    if bands_txt is not None and bands_txt.replace(" ", "") != "q10;q10":
        raise VidgenError(f"{where}: a Robertsonian translocation joins the long arms at the centromere: "
                          f"{kind}({chroms[0]};{chroms[1]})(q10;q10)")
    if kind == "der" and bands_txt is None:
        raise VidgenError(f"{where}: der({chroms[0]};{chroms[1]}) needs its bands: der({chroms[0]};{chroms[1]})(q10;q10)")
    if NAMES.index(chroms[0]) > NAMES.index(chroms[1]):
        raise VidgenError(f"{where}: ISCN lists the lower-numbered chromosome first: {kind}({chroms[1]};{chroms[0]})(q10;q10)")
    refs = (band_ref(chroms[0], "q10", where), band_ref(chroms[1], "q10", where))
    reading = f"Robertsonian translocation: the long arms of {chroms[0]} and {chroms[1]} joined at the centromere (short arms lost)"
    return Abnormality("rob", chroms, refs, item, reading, origin)


def _structural(kind: str, c: str, refs: tuple[BandRef, ...], item: str, where: str, origin: str) -> Abnormality:
    if kind == "del" and len(refs) == 1:
        r = refs[0]
        reading = f"terminal deletion: {c}{r.text}→{r.arm}ter lost (the end of {c}{r.arm})"
        return Abnormality("del", (c,), refs, item, reading, origin)
    a, b = refs
    if kind in ("del", "dup") and a.arm != b.arm:
        raise VidgenError(f"{where}: {c}{a.text} and {c}{b.text} are on different arms: an interstitial {kind} between them would "
                          f"take in the centromere (write both bands on one arm)")
    if kind == "del":
        return Abnormality("del", (c,), refs, item, f"interstitial deletion of {c}{a.text}→{c}{b.text}", origin)
    if kind == "dup":
        return Abnormality("dup", (c,), refs, item, f"duplication of {c}{a.text}→{c}{b.text} (direct, in tandem)", origin)
    if a.arm == b.arm:
        reading = f"paracentric inversion: {c}{a.text}→{c}{b.text} turned round within {c}{a.arm} (centromere outside it)"
    else:
        reading = f"pericentric inversion: {c}{a.text}→{c}{b.text} turned round across the centromere"
    return Abnormality("inv", (c,), refs, item, reading, origin)


def _take(copies: dict[str, list[Copy]], chrom: str, where: str, what: str) -> Copy:
    normal = [x for x in copies[chrom] if x.normal]
    if not copies[chrom]:
        raise VidgenError(f"{where}: this karyotype has no chromosome {chrom} for {what} (the sex chromosomes listed have none)")
    if not normal:
        raise VidgenError(f"{where}: no normal chromosome {chrom} left for {what} (the sex chromosomes listed: check them)")
    copies[chrom].remove(normal[-1])
    return normal[-1]


def _distal(chrom: str, ref: BandRef, outward: bool = True) -> Segment:
    """The segment from the breakpoint to the end of its arm (written outwards)."""
    bp = ref.mid
    end = 0.0 if ref.arm == "p" else LENGTH_MB[chrom]
    return Segment(chrom, bp, end) if outward else Segment(chrom, end, bp)


def _apply(copies: dict[str, list[Copy]], abn: Abnormality, idx: int, where: str) -> None:
    kind = abn.kind
    if kind == "gain":
        copies[abn.chroms[0]].append(normal_copy(abn.chroms[0], idx))
        return
    if kind == "loss":
        _take(copies, abn.chroms[0], where, "the loss")
        return
    if kind in ("del", "dup", "inv"):
        c = abn.chroms[0]
        _take(copies, c, where, kind)
        L, cen = LENGTH_MB[c], CENTROMERE_MB[c]
        refs = abn.bands
        if kind == "del" and len(refs) == 1:
            r = refs[0]
            if r.arm == "p":
                segs = (Segment(c, r.mid, L),)
                new_cen = cen - r.mid
                marks = ((0.0, 0.0),)
            else:
                segs = (Segment(c, 0.0, r.mid),)
                new_cen = cen
                marks = ((r.mid, r.mid),)
        else:
            a, b = refs[0].mid, refs[1].mid
            if kind == "del":
                segs = (Segment(c, 0.0, a), Segment(c, b, L))
                new_cen = cen if cen < a else cen - (b - a)
                marks = ((a, a),)
            elif kind == "dup":
                segs = (Segment(c, 0.0, b), Segment(c, a, L))
                new_cen = cen if cen < a else cen + (b - a)
                marks = ((a, b + (b - a)),)
            else:
                segs = (Segment(c, 0.0, a), Segment(c, b, a), Segment(c, b, L))
                new_cen = a + (b - cen) if a < cen < b else cen
                marks = ((a, b),)
        copies[c].append(Copy(c, tuple(s for s in segs if s.length > 0), new_cen, f"del({c})" if kind == "del" else f"{kind}({c})", idx,
                              marks))
        return
    if kind == "t":
        (c1, c2), (r1, r2) = abn.chroms, abn.bands
        _take(copies, c1, where, "the translocation")
        _take(copies, c2, where, "the translocation")
        for own, ref, other, oref in ((c1, r1, c2, r2), (c2, r2, c1, r1)):
            L, cen = LENGTH_MB[own], CENTROMERE_MB[own]
            if ref.arm == "q":
                keep = Segment(own, 0.0, ref.mid)
                gained = _distal(other, oref, outward=True)
                segs = (keep, gained)
                new_cen = cen
                marks = ((ref.mid, ref.mid + gained.length),)
            else:
                keep = Segment(own, ref.mid, L)
                gained = _distal(other, oref, outward=False) if oref.arm == "p" else Segment(other, LENGTH_MB[other], oref.mid)
                segs = (gained, keep)
                new_cen = gained.length + (cen - ref.mid)
                marks = ((0.0, gained.length),)
            copies[own].append(Copy(own, segs, new_cen, f"der({own})", idx, marks))
        return
    # Robertsonian: c1's q arm (pointing up) + c2's q arm, the centromere between
    c1, c2 = abn.chroms
    _take(copies, c1, where, "the Robertsonian translocation")
    _take(copies, c2, where, "the Robertsonian translocation")
    q1 = Segment(c1, LENGTH_MB[c1], CENTROMERE_MB[c1])
    q2 = Segment(c2, CENTROMERE_MB[c2], LENGTH_MB[c2])
    copies[c1].append(Copy(c1, (q1, q2), q1.length, f"der({c1};{c2})", idx, ((0.0, q1.length + q2.length),)))


SYNDROMES = {"21": "Down syndrome", "18": "Edwards syndrome", "13": "Patau syndrome"}


def _conditions(kt: Karyotype) -> tuple[str, ...]:
    """Conditions the karyotype names with certainty (the classic ones only)."""
    out: list[str] = []
    gains = [a.chroms[0] for a in kt.abnormalities if a.kind == "gain"]
    robs = [a for a in kt.abnormalities if a.kind == "rob"]
    n21 = len(kt.copies["21"]) + sum(1 for a in robs if "21" in a.chroms)
    rob21 = any("21" in a.chroms for a in robs)
    for c, name in SYNDROMES.items():
        if gains.count(c) == 1 and not (c == "21" and rob21):
            out.append(f"{name} (trisomy {c})")
    if rob21:
        out.append("translocation Down syndrome (three copies of 21q)" if n21 >= 3
                   else "balanced carrier: usually unaffected; risk of translocation Down syndrome in children")
    elif robs:
        out.append("balanced carrier: usually unaffected; risk of unbalanced conceptions")
    sex = {"X": "Turner syndrome (monosomy X)", "XXY": "Klinefelter syndrome", "XXX": "trisomy X (triple X)",
           "XYY": "47,XYY syndrome"}.get(kt.sex)
    if sex:
        out.append(sex)
    for a in kt.abnormalities:
        if a.kind == "del" and a.chroms == ("5",) and a.bands and a.bands[0].arm == "p" and len(a.bands) == 1:
            out.append("cri-du-chat syndrome (5p deletion)")
        if a.kind == "t" and a.chroms == ("9", "22") and a.bands[0].text.startswith("q34") and a.bands[1].text.startswith("q11"):
            out.append("der(22) is the Philadelphia chromosome: BCR::ABL1 fusion, chronic myeloid leukaemia (acquired)")
    return tuple(out)


def _notes(kt: Karyotype) -> tuple[str, ...]:
    out = []
    kinds = {a.kind for a in kt.abnormalities}
    if kinds & {"del", "dup", "inv", "t", "rob"}:
        out.append("bands schematic (placed by their ISCN names)")
    acquired = any("Philadelphia" in c for c in kt.conditions)        # a leukaemia's change, not an inherited one
    if ("t" in kinds or "inv" in kinds) and not kinds & {"gain", "loss", "del", "dup"} and not acquired:
        out.append("balanced: carriers are usually unaffected but can have unbalanced gametes")
    return tuple(out)


def band_labels(value: Any, where: str = "bands") -> list[tuple[BandRef, str]]:
    """Landmark labels: ``{7q31.2: CFTR, Xq28: ""}`` or a list of band names."""
    items: list[tuple[str, str]] = []
    if isinstance(value, Mapping):
        items = [(str(k), "" if v is None else str(v)) for k, v in value.items()]
    elif isinstance(value, (list, tuple)):
        items = [(str(k), "") for k in value]
    else:
        raise VidgenError(f"{where}: give bands to label, e.g. {{7q31.2: CFTR, 21q22: ''}} or [Xq28]")
    return [(parse_band_label(k, f"{where}['{k}']"), v) for k, v in items]

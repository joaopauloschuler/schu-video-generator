"""References and figure credits of a video (DESIGN.md §95.14): the formats of a reference's
identifiers (DOI, PubMed ID, ISBN, URL) checked offline, one number per distinct reference across
the whole video (in order of first appearance), the on-screen citation texts and the numbered
reference list of the video's description. No network, no manim."""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

#: A DOI: the directory indicator ``10.``, a registrant code of 4–9 digits (dots between
#: sub-codes allowed), ``/`` and a suffix without spaces (Crossref's recommended pattern).
DOI_RE = re.compile(r"^10\.\d{4,9}(?:\.\d+)*/\S+$")
_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi.org/", "doi:", "doi ")
_URL_RE = re.compile(r"^https?://[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+(?::\d+)?(?:[/?#]\S*)?$")
#: Identifier keys of a reference, in the order the description prefers them.
IDENTIFIERS: tuple[str, ...] = ("doi", "pmid", "isbn", "url")


def normal_doi(text: str) -> str:
    """``text`` as a bare DOI (``doi:`` and ``https://doi.org/`` prefixes taken off), or a
    ``ValueError`` saying what a DOI looks like."""
    value = str(text).strip()
    for prefix in _DOI_PREFIXES:
        if value.lower().startswith(prefix):
            value = value[len(prefix):].strip()
            break
    if not DOI_RE.match(value):
        raise ValueError(f"doi {text!r} is not a DOI: write it as 10.<registrant>/<suffix>, e.g. 10.1000/xyz123 (a doi: or "
                         f"https://doi.org/ prefix is taken off)")
    return value


def normal_pmid(text: str | int) -> str:
    """``text`` as a PubMed ID (1–8 digits, no leading zero; a ``PMID:`` prefix is taken off)."""
    value = str(text).strip()
    if value.upper().startswith("PMID"):
        value = value[4:].lstrip(" :").strip()
    if not re.fullmatch(r"[1-9]\d{0,7}", value):
        raise ValueError(f"pmid {text!r} is not a PubMed ID: 1 to 8 digits (e.g. 12345678; a PMID: prefix is taken off)")
    return value


def _isbn10_ok(digits: str) -> bool:
    total = sum((10 - k) * (10 if c in "Xx" else int(c)) for k, c in enumerate(digits))
    return total % 11 == 0


def _isbn13_ok(digits: str) -> bool:
    total = sum((1 if k % 2 == 0 else 3) * int(c) for k, c in enumerate(digits))
    return total % 10 == 0


def normal_isbn(text: str | int) -> str:
    """``text`` as an ISBN with its hyphens kept as written (an ``ISBN`` prefix taken off),
    after checking its length and check digit (ISBN-10 or ISBN-13)."""
    value = str(text).strip()
    if value.upper().startswith("ISBN"):
        value = value[4:].lstrip(" :-").strip()
        if value[:3] in ("-10", "-13"):
            value = value[3:].lstrip(" :").strip()
    digits = re.sub(r"[\s-]", "", value)
    if re.fullmatch(r"\d{9}[\dXx]", digits):
        ok = _isbn10_ok(digits)
    elif re.fullmatch(r"97[89]\d{10}", digits):
        ok = _isbn13_ok(digits)
    else:
        raise ValueError(f"isbn {text!r} is not an ISBN: 10 characters (the last may be X) or 13 digits starting 978 or 979, "
                         f"hyphens allowed")
    if not ok:
        raise ValueError(f"isbn {text!r}: its check digit is wrong (copy it again from the book's copyright page)")
    return value


def normal_url(text: str) -> str:
    """``text`` when it is an http(s) URL with a host name (no spaces)."""
    value = str(text).strip()
    if not _URL_RE.match(value):
        raise ValueError(f"url {text!r} is not a web address: write http:// or https://, a host name and a path, without spaces")
    return value


def identifier_text(kind: str, value: str) -> str:
    """How an identifier is written in the description: ``https://doi.org/<doi>``,
    ``PMID: <id>``, ``ISBN <isbn>`` or the URL."""
    return {"doi": f"https://doi.org/{value}", "pmid": f"PMID: {value}", "isbn": f"ISBN {value}"}.get(kind, value)


def reference_key(ref: Any) -> tuple[str, str]:
    """What makes two references the same: their first identifier (DOIs compared in lower
    case, ISBNs without hyphens), else the label."""
    for kind in IDENTIFIERS:
        value = getattr(ref, kind, None)
        if value:
            value = str(value)
            if kind == "doi":
                return kind, value.lower()
            if kind == "isbn":
                return kind, re.sub(r"[\s-]", "", value).upper()
            return kind, value
    return "label", str(ref.label)


def reference_line(ref: Any) -> str:
    """A reference in the description: its label and each identifier it has."""
    ids = [identifier_text(kind, str(getattr(ref, kind))) for kind in IDENTIFIERS if getattr(ref, kind, None)]
    return " ".join([str(ref.label).rstrip(), *ids]).strip()


# ----- numbering ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Numbered:
    """A distinct reference of the video: its number (1-based), the reference as first written
    and the scenes that cite it (in order)."""

    number: int
    ref: Any
    scenes: tuple[str, ...]


def video_references(scenes: Sequence[Any]) -> list[Numbered]:
    """The video's references, numbered in order of first appearance (scene by scene, each
    scene's list in order); the same reference in several scenes keeps its first number."""
    order: dict[tuple[str, str], int] = {}
    refs: list[Any] = []
    where: list[list[str]] = []
    for spec in scenes:
        for ref in getattr(spec, "references", None) or []:
            key = reference_key(ref)
            if key not in order:
                order[key] = len(refs)
                refs.append(ref)
                where.append([])
            if spec.id not in where[order[key]]:
                where[order[key]].append(spec.id)
    return [Numbered(k + 1, ref, tuple(w)) for k, (ref, w) in enumerate(zip(refs, where))]


def scene_numbers(scenes: Sequence[Any], scene_id: str) -> list[int]:
    """The video-wide numbers of scene ``scene_id``'s references, in the scene's order."""
    numbers = {reference_key(n.ref): n.number for n in video_references(scenes)}
    spec = next(s for s in scenes if s.id == scene_id)
    return [numbers[reference_key(ref)] for ref in spec.references or []]


def cite_index(spec: Any, cite: str | int) -> int:
    """The 0-based place in ``spec.references`` a beat's ``cite`` entry names: a 1-based number
    or a reference's ``id`` (``ValueError`` when it names none)."""
    refs = list(spec.references or [])
    if isinstance(cite, int) and not isinstance(cite, bool):
        if 1 <= cite <= len(refs):
            return cite - 1
        raise ValueError(f"cite {cite}: the scene has {len(refs)} reference(s); cite 1 to {len(refs)} or a reference's id")
    ids = [r.id for r in refs if r.id]
    for k, ref in enumerate(refs):
        if ref.id == cite:
            return k
    close = difflib.get_close_matches(str(cite), ids, n=1, cutoff=0.6)
    hint = f"; did you mean '{close[0]}'?" if close else ""
    raise ValueError(f"cite '{cite}': no reference of this scene has that id{hint} (ids: {', '.join(ids) or 'none'})")


def beat_numbers(scenes: Sequence[Any], scene_id: str) -> dict[str, tuple[int, ...]]:
    """Beat id -> the video-wide numbers the beat cites (only beats with a ``cite``)."""
    spec = next(s for s in scenes if s.id == scene_id)
    numbers = scene_numbers(scenes, scene_id)
    out: dict[str, tuple[int, ...]] = {}
    for beat in spec.beats:
        cites = getattr(beat, "cite", None) or []
        if cites:
            out[beat.id] = tuple(sorted({numbers[cite_index(spec, c)] for c in cites}))
    return out


def marker(numbers: Iterable[int]) -> str:
    """``[1]``, ``[1, 2]``, ``[1–3]`` (runs of three or more joined with an en dash)."""
    values = sorted(set(numbers))
    parts: list[str] = []
    k = 0
    while k < len(values):
        j = k
        while j + 1 < len(values) and values[j + 1] == values[j] + 1:
            j += 1
        parts += [f"{values[k]}–{values[j]}"] if j - k >= 2 else [str(v) for v in values[k:j + 1]]
        k = j + 1
    return "[" + ", ".join(parts) + "]" if parts else ""


def credit_text(credit: Any) -> str:
    """A figure credit as shown on screen: its text and licence (``Image: … (CC BY 4.0)``)."""
    text = str(credit.text).strip()
    return f"{text} ({credit.license})" if getattr(credit, "license", None) else text


def credit_line(credit: Any) -> str:
    """A figure credit in the description: its text, licence and source."""
    ids = [identifier_text(kind, str(getattr(credit, kind))) for kind in IDENTIFIERS if getattr(credit, kind, None)]
    return " ".join([credit_text(credit), *ids])


def description_text(scenes: Sequence[Any]) -> str:
    """The description's reference section: ``References`` with one ``[n] label identifiers``
    line each, then ``Figure credits`` with one line per credited scene (empty when the video
    has neither)."""
    lines: list[str] = []
    numbered = video_references(scenes)
    if numbered:
        lines += ["References", *(f"[{n.number}] {reference_line(n.ref)}" for n in numbered)]
    credits = [s.figure_credit for s in scenes if getattr(s, "figure_credit", None) is not None]
    if credits:
        if lines:
            lines.append("")
        seen: list[str] = []
        for credit in credits:
            line = credit_line(credit)
            if line not in seen:
                seen.append(line)
        lines += ["Figure credits", *(f"- {line}" for line in seen)]
    return "\n".join(lines) + "\n" if lines else ""


def has_citations(scenes: Sequence[Any]) -> bool:
    """Whether any scene has references or a figure credit."""
    return any(getattr(s, "references", None) or getattr(s, "figure_credit", None) is not None for s in scenes)


__all__ = [
    "DOI_RE", "IDENTIFIERS", "Numbered", "beat_numbers", "cite_index", "credit_line", "credit_text", "description_text", "has_citations",
    "identifier_text", "marker", "normal_doi", "normal_isbn", "normal_pmid", "normal_url", "reference_key", "reference_line",
    "scene_numbers", "video_references",
]

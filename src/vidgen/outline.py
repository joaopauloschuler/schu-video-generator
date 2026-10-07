"""Markdown outlines and plain-text scripts as a list of blocks, for ``vidgen plan`` (DESIGN.md §61).

A deliberately small Markdown reader (no dependency): ATX and setext headings, paragraphs,
bullet and numbered lists (nested items become an item's ``children``), pipe tables, fenced code
blocks, ``$$...$$`` display maths, images on a line of their own, blockquotes (a last line
``— Author, Source`` is the attribution), horizontal rules (ignored), HTML comments and YAML
front matter (skipped). Inline Markdown (emphasis, code spans, links, inline images, HTML tags)
is removed by :func:`plain`, which also collects link targets. A plain-text script (``plain=True``)
is read the same way, with short lines standing alone (no final punctuation) taken as headings.
No manim import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Headings that stand alone in a plain-text script have at most this many words.
PLAIN_HEADING_WORDS = 8


@dataclass(frozen=True)
class Heading:
    """A heading of ``level`` 1-6."""

    level: int
    text: str


@dataclass(frozen=True)
class Paragraph:
    """Consecutive lines of prose, stripped, joined by newlines (inline Markdown kept; see
    :func:`plain`, which also joins the lines)."""

    text: str


@dataclass(frozen=True)
class ListItem:
    """One list item: its text and the texts of its nested items."""

    text: str
    children: tuple[str, ...] = ()


@dataclass(frozen=True)
class ListBlock:
    """A bullet list or (``ordered``) a numbered list."""

    items: tuple[ListItem, ...]
    ordered: bool = False


@dataclass(frozen=True)
class Table:
    """A pipe table: the ``header`` cells and the body ``rows`` (cells as written)."""

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Code:
    """A fenced code block and its info-string language (``""`` when none)."""

    code: str
    language: str = ""


@dataclass(frozen=True)
class Math:
    """Display maths: one or more formulas (LaTeX without ``$``), in order."""

    formulas: tuple[str, ...]


@dataclass(frozen=True)
class Image:
    """An image on a line of its own: ``![alt](path "title")``."""

    alt: str
    path: str
    title: str = ""


@dataclass(frozen=True)
class Quote:
    """A blockquote: the quoted text and its attribution, if any."""

    text: str
    author: str = ""
    source: str = ""


Block = Heading | Paragraph | ListBlock | Table | Code | Math | Image | Quote


@dataclass
class Inline:
    """Plain text of an inline Markdown string and the link targets found in it."""

    text: str
    links: list[str] = field(default_factory=list)


_ATX = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)\s*$")
_RULE = re.compile(r"^ {0,3}([-*_])(\s*\1){2,}\s*$")
_FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([^`\s]*)")
_LIST = re.compile(r"^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_IMAGE = re.compile(r'^\s*!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+"([^"]*)")?\s*\)\s*$')
_QUOTE = re.compile(r"^ {0,3}>\s?(.*)$")
_ATTRIBUTION = re.compile(r"^(?:—|–|--|-|~)\s*(.+)$")
_COMMENT_START = "<!--"


def _is_table_row(line: str) -> bool:
    return "|" in line and line.strip() != "|"


def _cells(line: str) -> tuple[str, ...]:
    """The cells of a pipe-table row (an escaped ``\\|`` stays in its cell)."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    parts = re.split(r"(?<!\\)\|", body)
    return tuple(p.strip().replace("\\|", "|") for p in parts)


def _starts_block(lines: list[str], i: int) -> bool:
    """Whether ``lines[i]`` starts a block other than a paragraph (ends a paragraph)."""
    line = lines[i]
    if _ATX.match(line) or _FENCE.match(line) or _LIST.match(line) or _QUOTE.match(line) or _IMAGE.match(line):
        return True
    if line.strip().startswith("$$") or line.strip().startswith(_COMMENT_START) or _RULE.match(line):
        return True
    return _is_table_row(line) and i + 1 < len(lines) and bool(_TABLE_SEP.match(lines[i + 1]))


def _math_formulas(body: str) -> tuple[str, ...]:
    """Formulas of a display-maths block: an ``aligned`` / ``align`` environment or ``\\\\`` line
    breaks give one formula per line (alignment marks ``&`` removed)."""
    body = re.sub(r"\\(?:begin|end)\{(?:aligned|align\*?|gathered|split|eqnarray\*?)\}", "", body)
    parts = [p.replace("&", "").strip() for p in re.split(r"\\\\", body)]
    return tuple(" ".join(p.split()) for p in parts if p.strip())


def _read_list(lines: list[str], i: int) -> tuple[ListBlock, int]:
    """The list starting at ``lines[i]``; returns it and the index after it."""
    first = _LIST.match(lines[i])
    assert first is not None
    base = len(first[1].expandtabs(4))
    ordered = first[2][0].isdigit()
    items: list[tuple[list[str], list[str]]] = []
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines):
                break
            nxt = _LIST.match(lines[j])
            indent = len(lines[j].expandtabs(4)) - len(lines[j].expandtabs(4).lstrip())
            if indent <= base and (nxt is None or nxt[2][0].isdigit() != ordered):
                break  # the list ends: a paragraph, or a list of the other kind
            i = j
            continue
        match = _LIST.match(line)
        indent = len(line) - len(line.lstrip()) if match is None else len(match[1].expandtabs(4))
        if match is not None and indent <= base:
            if match[2][0].isdigit() != ordered:
                break
            items.append(([match[3].strip()], []))
        elif match is not None and items:
            items[-1][1].append(match[3].strip())
        elif items and indent > base:
            target = items[-1][1] if items[-1][1] else items[-1][0]
            target[-1] = f"{target[-1]} {line.strip()}"
        elif items and not _starts_block(lines, i):
            items[-1][0][-1] = f"{items[-1][0][-1]} {line.strip()}"  # lazy continuation line
        else:
            break
        i += 1
    block = ListBlock(tuple(ListItem(" ".join(text), tuple(children)) for text, children in items), ordered)
    return block, i


def _read_quote(lines: list[str], i: int) -> tuple[Quote, int]:
    """The blockquote starting at ``lines[i]``; returns it and the index after it."""
    parts: list[str] = []
    while i < len(lines):
        match = _QUOTE.match(lines[i])
        if match is None:
            break
        parts.append(match[1].strip())
        i += 1
    author = source = ""
    while parts and not parts[-1]:
        parts.pop()
    if parts:
        attribution = _ATTRIBUTION.match(parts[-1])
        if attribution is not None and len(parts) > 1:
            parts.pop()
            who = attribution[1].strip()
            author, _, source = (s.strip() for s in who.partition(","))
    text = " ".join(p for p in parts if p)
    return Quote(text, author, source), i


def parse_outline(text: str, plain: bool = False) -> list[Block]:
    """The blocks of a Markdown outline (or, with ``plain``, a plain-text script) in order."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[Block] = []
    i = 0
    if lines and lines[0].strip() == "---" and not plain:  # YAML front matter
        end = next((j for j in range(1, len(lines)) if lines[j].strip() in ("---", "...")), None)
        if end is not None:
            i = end + 1
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith(_COMMENT_START):
            while i < len(lines) and "-->" not in lines[i]:
                i += 1
            i += 1
            continue
        fence = _FENCE.match(line)
        if fence is not None and not plain:
            marker, body = fence[2], []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(marker[0] * len(marker)):
                body.append(lines[i])
                i += 1
            indent = len(fence[1])
            code = "\n".join(b[indent:] if b[:indent].isspace() else b for b in body).strip("\n")
            blocks.append(Code(code, fence[3].lower()))
            i += 1
            continue
        if stripped.startswith("$$") and not plain:
            body_text = stripped[2:]
            if body_text.rstrip().endswith("$$"):
                body_text = body_text.rstrip()[:-2]
                i += 1
            else:
                parts = [body_text]
                i += 1
                while i < len(lines) and not lines[i].rstrip().endswith("$$"):
                    parts.append(lines[i])
                    i += 1
                if i < len(lines):
                    parts.append(lines[i].rstrip()[:-2])
                    i += 1
                body_text = "\n".join(parts)
            formulas = _math_formulas(body_text)
            if formulas:
                blocks.append(Math(formulas))
            continue
        atx = _ATX.match(line)
        if atx is not None and not plain:
            blocks.append(Heading(len(atx[1]), atx[2].strip()))
            i += 1
            continue
        if _RULE.match(line):
            i += 1
            continue
        if _is_table_row(line) and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]) and not plain:
            header = _cells(line)
            rows: list[tuple[str, ...]] = []
            i += 2
            while i < len(lines) and _is_table_row(lines[i]) and lines[i].strip():
                rows.append(_cells(lines[i]))
                i += 1
            blocks.append(Table(header, tuple(rows)))
            continue
        image = _IMAGE.match(line)
        if image is not None:
            blocks.append(Image(image[1].strip(), image[2].strip(), (image[3] or "").strip()))
            i += 1
            continue
        if _QUOTE.match(line):
            quote, i = _read_quote(lines, i)
            if quote.text:
                blocks.append(quote)
            continue
        if _LIST.match(line):
            block, i = _read_list(lines, i)
            blocks.append(block)
            continue
        parts = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not _starts_block(lines, i):
            if not plain and _SETEXT.match(lines[i]) and len(parts) == 1:
                break
            parts.append(lines[i].strip())
            i += 1
        if not plain and i < len(lines) and len(parts) == 1 and _SETEXT.match(lines[i]):
            blocks.append(Heading(1 if lines[i].strip()[0] == "=" else 2, parts[0]))
            i += 1
            continue
        paragraph = "\n".join(parts)
        if plain and _plain_heading(parts, lines, i):
            level = 1 if not blocks else 2
            blocks.append(Heading(level, paragraph))
        else:
            blocks.append(Paragraph(paragraph))
    return blocks


def _plain_heading(parts: list[str], lines: list[str], after: int) -> bool:
    """In a plain-text script: a single short line without final punctuation, followed by a blank
    line (or the end), stands for a heading."""
    if len(parts) != 1:
        return False
    words = parts[0].split()
    ends_blank = after >= len(lines) or not lines[after].strip()
    return 0 < len(words) <= PLAIN_HEADING_WORDS and not re.search(r"[.!?,;:…]$", parts[0]) and ends_blank


_INLINE_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_AUTOLINK = re.compile(r"<((?:https?://|mailto:)[^>\s]+)>")
_URL = re.compile(r"\bhttps?://[^\s)>\]]+")
#: A bare web address without a scheme ("batteryuniversity.com", "www.example.org/docs").
_DOMAIN = re.compile(
    r"(?<![\w@./-])(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|dev|ai|edu|gov|app|co)\b(?:/[^\s)>\]]*)?",
    re.IGNORECASE,
)
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_EMPHASIS = (
    re.compile(r"\*\*(.+?)\*\*"),
    re.compile(r"__(.+?)__"),
    re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"),
    re.compile(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])"),
    re.compile(r"~~(.+?)~~"),
)


def plain(text: str) -> Inline:
    """``text`` without inline Markdown: link texts kept (targets collected in ``links``), code
    spans and emphasis unwrapped, inline images replaced by their alt text, HTML tags removed,
    whitespace collapsed. Bare URLs stay in the text and are collected too."""
    links: list[str] = []

    def link(match: re.Match[str]) -> str:
        links.append(match[2])
        return match[1]

    def autolink(match: re.Match[str]) -> str:
        links.append(match[1])
        return match[1]

    out = _CODE_SPAN.sub(lambda m: m[2].strip(), text)
    out = _INLINE_IMAGE.sub(lambda m: m[1], out)
    out = _LINK.sub(link, out)
    out = _AUTOLINK.sub(autolink, out)
    bare = [u.rstrip(".,;:!?") for u in _URL.findall(out)]
    bare += [d.rstrip(".,;:!?") for d in _DOMAIN.findall(_URL.sub(" ", out))]
    links.extend(u for u in bare if u not in links)
    out = _HTML_TAG.sub("", out)
    for pattern in _EMPHASIS:
        out = pattern.sub(lambda m: m[1], out)
    out = out.replace("\\*", "*").replace("\\_", "_").replace("\\#", "#")
    return Inline(" ".join(out.split()), links)

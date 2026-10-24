"""Physical lengths of the cell world (DESIGN.md §95.3): everything is measured in micrometres
(µm) inside the model; YAML may write a number (µm) or a string with a unit (``"25 nm"``,
``"1.5 um"``, ``"20 µm"``, ``"0.1 mm"``). No manim."""

from __future__ import annotations

import math
import re

#: Unit names (as written, lower case) and their size in µm.
UNITS: dict[str, float] = {"nm": 1e-3, "um": 1.0, "µm": 1.0, "μm": 1.0, "micron": 1.0, "microns": 1.0, "mm": 1e3}
_LENGTH = re.compile(r"^\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*([a-zA-Zµμ]+)?\s*$")
#: Nice scale-bar lengths per decade.
NICE_STEPS = (1.0, 2.0, 5.0)


def parse_length(value: float | int | str, what: str = "length") -> float:
    """A length in µm from a number (µm) or a string with a unit; ``ValueError`` saying how to
    write it otherwise (also for zero or negative lengths)."""
    if isinstance(value, bool):
        raise ValueError(f"{what}: write a length such as 2 (µm), '1.5 um' or '25 nm'")
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        match = _LENGTH.match(str(value))
        if not match:
            raise ValueError(f"{what} {value!r}: write a length such as 2 (µm), '1.5 um' or '25 nm'")
        number = float(match.group(1))
        unit = (match.group(2) or "um").lower()
        if unit not in UNITS:
            raise ValueError(f"{what} {value!r}: unknown unit '{match.group(2)}'; use nm, um (µm) or mm")
        number *= UNITS[unit]
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{what} {value!r}: a length must be greater than 0")
    return number


def parse_coordinate(value: float | int | str, what: str = "coordinate") -> float:
    """A signed position in µm (``-3``, ``"-250 nm"``, ``0``): like :func:`parse_length` but
    zero and negative values are fine."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            raise ValueError(f"{what}: write a finite number of µm")
        return float(value)
    text = str(value).strip().replace("−", "-")
    sign = -1.0 if text.startswith("-") else 1.0
    text = text.lstrip("+-").strip()
    if _LENGTH.match(text) and float(_LENGTH.match(text).group(1)) == 0.0:  # type: ignore[union-attr]
        return 0.0
    return sign * parse_length(text, what)


def format_length(um: float) -> str:
    """``25 nm``, ``1.5 µm``, ``2 mm``: a length in µm written in the unit that reads best."""
    if um < 1.0:
        value, unit = um * 1e3, "nm"
    elif um < 1e3:
        value, unit = um, "µm"
    else:
        value, unit = um / 1e3, "mm"
    text = f"{value:.0f}" if abs(value - round(value)) < 1e-6 * max(1.0, value) else f"{value:.3g}"
    return f"{text} {unit}"


def nice_length(target_um: float) -> float:
    """The largest 1-2-5 length (…, 0.1, 0.2, 0.5, 1, 2, 5, 10, … µm) not above ``target_um``."""
    if target_um <= 0 or not math.isfinite(target_um):
        raise ValueError("nice_length needs a positive length")
    decade = 10.0 ** math.floor(math.log10(target_um) + 1e-12)
    best = decade
    for step in NICE_STEPS:
        if step * decade <= target_um * (1 + 1e-9):
            best = step * decade
    return best

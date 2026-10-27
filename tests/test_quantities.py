"""The quantities engine (Phase W Step 225): unit parsing, conversion and dimension algebra,
temperature offsets, constants, significant figures, exact fractions, expressions with units and
worked calculations — the textbook examples of the ``calculation`` scene. No manim."""

from __future__ import annotations

import math
import re
import subprocess
import sys
from fractions import Fraction

import pytest

from vidgen.errors import VidgenError
from vidgen.quantities import (
    CONSTANTS,
    CalcInput,
    Quantity,
    QuantityError,
    SymbolInput,
    constant,
    count_sig,
    decimal_text,
    describe_dim,
    dim,
    exact_root,
    in_unit,
    name_tex,
    parse,
    parse_unit,
    round_sig,
    si_unit,
    to_tex,
    work,
    written,
)
from vidgen.quantities.quantity import add, mul


def S(name: str, **kw) -> SymbolInput:  # noqa: N802
    return SymbolInput(name, **kw)


def C(name: str, expr: str, **kw) -> CalcInput:  # noqa: N802
    return CalcInput(name, expr, **kw)


def result(symbols, calcs, name=None):
    worked = work(symbols, calcs)
    return worked.results[-1] if name is None else next(r for r in worked.results if r.name == name)


def test_core_imports_without_manim() -> None:
    code = "import sys, vidgen.quantities; sys.exit(1 if 'manim' in sys.modules else 0)"
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0


# ----- units ------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "factor", "d", "shown"),
    [
        ("m/s^2", 1, dim(m=1, s=-2), "m/s²"),
        ("km h^-1", Fraction(1000, 3600), dim(m=1, s=-1), "km/h"),
        ("km/h", Fraction(1000, 3600), dim(m=1, s=-1), "km/h"),
        ("kg·m²·s⁻²", 1, dim(kg=1, m=2, s=-2), "kg·m²/s²"),
        ("kg*m**2/s**2", 1, dim(kg=1, m=2, s=-2), "kg·m²/s²"),
        ("J/(mol·K)", 1, dim(kg=1, m=2, s=-2, mol=-1, K=-1), "J·mol⁻¹·K⁻¹"),
        ("m/s/s", 1, dim(m=1, s=-2), "m/s²"),
        ("N m", 1, dim(kg=1, m=2, s=-2), "N·m"),
        ("1/s", 1, dim(s=-1), "s⁻¹"),
        ("µM", Fraction(1, 1000), dim(mol=1, m=-3), "µM"),
        ("uM", Fraction(1, 1000), dim(mol=1, m=-3), "µM"),
        ("mL", Fraction(1, 10**6), dim(m=3), "mL"),
        ("kWh", 3600000, dim(kg=1, m=2, s=-2), "kWh"),
        ("kcal", 4184, dim(kg=1, m=2, s=-2), "kcal"),
        ("MeV", Fraction("1.602176634e-13"), dim(kg=1, m=2, s=-2), "MeV"),
        ("GeV/c^2", Fraction("1.602176634e-10") / 299792458**2, dim(kg=1), "GeV/c²"),
        ("Da", Fraction("1.66053906892e-27"), dim(kg=1), "Da"),
        ("atm", 101325, dim(kg=1, m=-1, s=-2), "atm"),
        ("mbar", 100, dim(kg=1, m=-1, s=-2), "mbar"),
        ("AU", 149597870700, dim(m=1), "AU"),
        ("ly", 9460730472580800, dim(m=1), "ly"),
        ("Gyr", 31557600 * 10**9, dim(s=1), "Gyr"),
        ("%", Fraction(1, 100), dim(), "%"),
        ("m^(1/2)", 1, dim(m=Fraction(1, 2)), "m¹ᐟ²"),
        ("Pa", 1, dim(kg=1, m=-1, s=-2), "Pa"),
        ("min", 60, dim(s=1), "min"),
        ("cd", 1, dim(cd=1), "cd"),
    ],
)
def test_parse_units(text: str, factor, d, shown: str) -> None:
    u = parse_unit(text)
    assert u.dim == d and u.text == shown
    assert float(u.factor) == pytest.approx(float(factor), rel=1e-12)
    if isinstance(factor, (int, Fraction)) and text not in ("pc",):
        assert u.factor == factor          # exact definitions stay exact


def test_parsec_and_degree_are_floats() -> None:
    assert float(parse_unit("pc").factor) == pytest.approx(3.0856775814913673e16, rel=1e-12)
    assert parse_unit("deg").factor == pytest.approx(math.pi / 180)
    assert parse_unit("kpc").factor == pytest.approx(3.0856775814913673e19, rel=1e-12)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("kgg", "unknown unit 'kgg'"),
        ("mtr", "did you mean"),
        ("kmin", "'min' (minute) does not take a prefix"),
        ("°C/s", "°C is a scale with an offset and must stand alone; a change of 1 °C is 1 K"),
        ("m^", "expected an exponent"),
        ("(m/s", "is not closed"),
        ("ft", "'t' (tonne) does not take a prefix"),
    ],
)
def test_unit_errors(text: str, message: str) -> None:
    with pytest.raises(VidgenError, match=re.escape(message)):
        parse_unit(text)


def test_dimension_names_and_si_display() -> None:
    assert describe_dim(dim(kg=1, m=2, s=-2)) == "energy (kg·m²·s⁻², J)"
    assert describe_dim(dim(m=1, s=-1)) == "speed (m·s⁻¹)"
    assert describe_dim(dim(m=3, kg=-1, s=-2)) == "m³·kg⁻¹·s⁻²"
    assert si_unit(dim(kg=1, m=2, s=-2)).text == "J"
    assert si_unit(dim(kg=1, m=1, s=-2)).text == "N"
    assert si_unit(dim(kg=1, m=2, s=-1)).text == "J·s"
    assert si_unit(dim(m=1, s=-1)).text == "m/s"
    assert si_unit(dim(s=-1)).text == "s⁻¹"          # Hz or Bq: not guessed
    assert si_unit(dim(m=3, kg=-1, s=-2)).text == "m³·kg⁻¹·s⁻²"
    assert parse_unit("km/s").tex == r"\mathrm{km}/\mathrm{s}"
    assert parse_unit("µm").tex == r"\mu\mathrm{m}"


# ----- values, conversions, temperatures --------------------------------------------------------

def test_conversions() -> None:
    v = written("29.8 km/s").quantity
    assert v.value == 29800 and v.sig == 3
    assert in_unit(v, parse_unit("m/s")) == (29800, 3)
    assert float(in_unit(v, parse_unit("km/h"))[0]) == pytest.approx(107280)
    with pytest.raises(QuantityError, match=r"cannot express speed \(m·s⁻¹\) in kg \(mass \(kg\)\)"):
        in_unit(v, parse_unit("kg"))


def test_temperature_offsets() -> None:
    t = written("25.0 °C").quantity
    assert t.value == Fraction("298.15") and t.sig == 4            # 0.1 °C resolution: 298.2 K
    assert decimal_text(*in_unit(t, parse_unit("K"))).plain == "298.2"
    assert in_unit(Quantity(Fraction(27315, 100), dim(K=1), None), parse_unit("°C"))[0] == 0
    f = written("98.6 °F").quantity
    assert float(f.value) == pytest.approx(310.15)
    assert float(in_unit(f, parse_unit("°C"))[0]) == pytest.approx(37.0)
    # a difference: 30 °C − 20 °C = 10 K
    diff = result([S("a", value="30.0 °C"), S("b", value="20.0 °C")], [C("d", "a - b")])
    assert diff.value.value_text() == "10.0 K"


def test_written_values_and_exactness() -> None:
    assert written("1/25").quantity == Quantity(Fraction(1, 25), dim(), None)        # a fraction: exact
    assert written(3).quantity.sig is None                                            # a count: exact
    assert written("532 nm").quantity.sig == 3                                        # a whole number with a unit: measured
    assert written("1500 m").quantity.sig == 2                                        # trailing zeros of a whole number do not count
    assert written("1500 m", sig=4).quantity.sig == 4
    assert written("2.5 × 10^3 m").quantity.value == 2500
    assert written("6.674e-11").quantity.sig == 4
    assert written(9.80665, "m/s^2", sig=3).quantity.value == Fraction("9.81")        # rounded to its sig
    assert written("2 m", exact=True).quantity.sig is None
    with pytest.raises(QuantityError, match="carries a unit and unit"):
        written("2 m", "s")
    with pytest.raises(QuantityError, match="sig: 0 is impossible"):
        written("2.0", sig=0)
    with pytest.raises(QuantityError, match="not both"):
        written("2.0", sig=2, exact=True)


# ----- significant figures ----------------------------------------------------------------------

@pytest.mark.parametrize(("text", "n"), [("0.0250", 3), ("2.50e3", 3), ("1500", 2), ("1500.", 4), ("6.674e-11", 4), ("0.0", 1), ("100", 1),
                                         ("3", 1), ("29.8", 3), ("1.0", 2), ("2.5 × 10^3", 2)])
def test_count_sig(text: str, n: int) -> None:
    assert count_sig(text) == n


def test_sig_rules() -> None:
    a = written("12.3 m").quantity      # 3 figures, 0.1 m
    b = written("4.567 m").quantity     # 4 figures, 0.001 m
    assert add(a, b).sig == 3 and decimal_text(add(a, b).value, add(a, b).sig).plain == "16.9"     # sums: decimal places
    assert mul(a, b).sig == 3                                                                     # products: fewest figures
    c = written("100.0 m").quantity
    d = written("99.9 m").quantity
    diff = add(c, d, -1)
    assert diff.sig == 1 and decimal_text(diff.value, diff.sig).plain == "0.1"                    # cancellation loses figures
    assert mul(a, written("2").quantity).sig == 3                                                  # exact factors never limit
    assert str(round_sig(Fraction(2675, 1000), 3)) == "2.68"                                       # halves away from zero
    assert decimal_text(29784.7, 3).plain == "2.98 × 10⁴"                                          # no ambiguous trailing zeros
    assert decimal_text(240.4, 3).plain == "2.40 × 10²"
    assert decimal_text(0.0066667, 3).plain == "0.00667"
    assert decimal_text(-0.5, 2).plain == "−0.50"
    assert decimal_text(123456, 6).plain == "1.23456 × 10⁵"


def test_exact_roots_and_fractions() -> None:
    assert exact_root(Fraction(1, 2500), 2) == Fraction(1, 50)
    assert exact_root(Fraction(8, 27), 3) == Fraction(2, 3)
    assert exact_root(Fraction(2), 2) is None
    r = result([S("q2", value="1/2500")], [C("q", "sqrt(q2)")])
    assert r.value.quantity.value == Fraction(1, 50) and r.value.quantity.sig is None
    assert r.steps[-1].plain == "1/50 = 0.02"


# ----- constants --------------------------------------------------------------------------------

def test_constants() -> None:
    assert constant("c").number() == 299792458 and constant("c").exact
    assert constant("h").number() == Fraction("6.62607015e-34")
    assert constant("e").number() == Fraction("1.602176634e-19")
    assert constant("k_B").number() == Fraction("1.380649e-23")
    assert constant("N_A").number() == Fraction("6.02214076e23")
    assert constant("R").number() == Fraction("6.02214076e23") * Fraction("1.380649e-23")       # R = N_A k_B exactly
    assert constant("hbar").number() == pytest.approx(6.62607015e-34 / (2 * math.pi), rel=1e-15)
    assert constant("G").number() == Fraction("6.67430e-11") and not constant("G").exact
    assert constant("m_e").number() == Fraction("9.1093837139e-31")
    assert constant("m_p").number() == Fraction("1.67262192595e-27")
    assert constant("epsilon_0").number() == Fraction("8.8541878188e-12")
    assert constant("mu_0").number() == Fraction("1.25663706127e-6")
    assert constant("g").number() == Fraction("9.80665")
    assert constant("AU").number() == 149597870700
    # M = GM/G with the IAU 2015 nominal parameters
    assert float(constant("M_sun").number()) == pytest.approx(1.3271244e20 / 6.67430e-11, rel=1e-5)
    assert float(constant("M_earth").number()) == pytest.approx(3.986004e14 / 6.67430e-11, rel=1e-5)
    assert float(constant("sigma_SB").number()) == pytest.approx(5.670374419e-8, rel=1e-9)
    assert float(constant("epsilon_0").number()) * float(constant("mu_0").number()) * 299792458**2 == pytest.approx(1, rel=1e-9)
    for c in CONSTANTS.values():
        assert written(c.value, c.unit).quantity.dim == parse_unit(c.unit).dim and c.source
    assert constant("kB").key == "k_B" and constant("Msun").key == "M_sun"
    with pytest.raises(VidgenError, match="did you mean 'M_sun'"):
        constant("M_sunn")


# ----- expressions and TeX ----------------------------------------------------------------------

def test_expression_tex() -> None:
    def symbols(node):
        return (name_tex(node.value), 5)

    def tex(text: str) -> str:
        return to_tex(parse(text), symbols)[0]

    assert tex("sqrt(G*M_sun/r)") == r"\sqrt{\frac{G\,M_{\odot}}{r}}"
    assert tex("2*p*q") == "2 p q"
    assert tex("ln(2)/k") == r"\frac{\ln 2}{k}"
    assert tex("m*v^2/2") == r"\frac{m {v}^{2}}{2}"
    assert tex("(a + b)^2") == r"{\left(a + b\right)}^{2}"
    assert tex("a - (b - c)") == r"a - \left(b - c\right)"
    assert tex("exp(-k*t)") == r"e^{-k t}"
    assert tex("x^(1/2)") == r"{x}^{1/2}"
    assert tex("2/3 * 1/4") == r"\frac{\frac{2}{3} \times 1}{4}"
    assert name_tex("t_half") == "t_{1/2}" and name_tex("lambda") == r"\lambda" and name_tex("k_B") == r"k_{\mathrm{B}}"
    assert name_tex("p1") == "p_{1}" and name_tex("v_esc") == r"v_{\mathrm{esc}}" and name_tex("M_earth") == r"M_{\oplus}"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("sqr(x)", "unknown function 'sqr' \\(did you mean sqrt\\?\\)"),
        ("2 +", "expected a number"),
        ("(a", "is not closed"),
        ("sin x", "needs its argument in brackets"),
        ("a $ b", "unexpected '\\$'"),
        ("2 [parsecs]", "unknown unit"),
    ],
)
def test_expression_errors(text: str, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        parse(text)


# ----- worked calculations: the textbook examples ------------------------------------------------

def test_orbital_speed_of_the_earth() -> None:
    r = result([S("G", constant="G"), S("M_sun", constant="M_sun"), S("r", constant="AU")],
               [C("v", "sqrt(G*M_sun/r)", sig=3, convert=["km/s"])])
    assert float(r.value.quantity.value) == pytest.approx(29784.7, rel=1e-4)
    assert r.value.value_text() == "2.98 × 10⁴ m/s" and r.conversions[0].value_text() == "29.8 km/s"
    assert [s.kind for s in r.steps] == ["formula", "substitute", "intermediate", "result", "convert"]
    assert r.steps[0].tex == r"\sqrt{\frac{{G}\,{M_{\odot}}}{{r}}}"           # r named by the author, not 'au'
    assert r"6.674 \times 10^{-11}" in r.steps[1].tex and r"\mathrm{kg}" in r.steps[1].tex
    assert r"\mathrm{m}" not in r.steps[1].alt                                 # the SI variant has no units


def test_escape_velocity_from_the_earth() -> None:
    r = result([S("G", constant="G"), S("M", constant="M_earth"), S("R", constant="R_earth")],
               [C("v_esc", "sqrt(2*G*M/R)", sig=3, convert="km/s".split())])
    assert r.conversions[0].value_text() == "11.2 km/s"
    full = result([S("G", constant="G"), S("M", constant="M_earth"), S("R", constant="R_earth")], [C("v_esc", "sqrt(2*G*M/R)")])
    assert full.value.quantity.sig == 5                                       # R_earth has 5 figures


def test_hardy_weinberg_carrier_frequency() -> None:
    w = work([S("q2", value="1/2500")], [C("q", "sqrt(q2)"), C("p", "1 - q"), C("H", "2*p*q")])
    q, p, h = w.results
    assert (q.value.quantity.value, p.value.quantity.value, h.value.quantity.value) == (Fraction(1, 50), Fraction(49, 50), Fraction(49, 1250))
    assert h.steps[-1].plain == "49/1250 = 0.0392"
    assert h.steps[1].tex.count(r"\frac") == 2                                 # 2 × 49/50 × 1/50


def test_pedigree_risk_one_in_150() -> None:
    r = result([S("a", value="2/3"), S("b", value="1/25"), S("c", value="1/4")], [C("P", "a*b*c")])
    assert r.value.quantity.value == Fraction(1, 150) and r.value.quantity.exact
    assert r.steps[-1].tex.startswith(r"\frac{1}{150} \approx 0.00667")
    assert r.steps[1].tex == r"{\frac{2}{3}} \times {\frac{1}{25}} \times {\frac{1}{4}}"
    assert result([S("a", value="2/3")], [C("P", "a", format="percent")]).value.value_text() == "66.67 %"


def test_drug_half_life_from_k() -> None:
    r = result([S("k", value="0.173 h^-1")], [C("t_half", "ln(2)/k", unit="h", convert=["min"])])
    assert r.value.value_text() == "4.01 h" and r.conversions[0].value_text() == "2.40 × 10² min"
    assert float(r.value.quantity.value) == pytest.approx(math.log(2) / (0.173 / 3600))


def test_photon_energy_in_ev() -> None:
    r = result([S("h", constant="h"), S("c", constant="c"), S("lambda", value="532 nm")], [C("E", "h*c/lambda", convert=["eV"])])
    assert r.value.value_text() == "3.73 × 10⁻¹⁹ J" and r.conversions[0].value_text() == "2.33 eV"
    assert r.steps[0].tex == r"\frac{{h} {c}}{{\lambda}}"


def test_higgs_mass_in_kilograms() -> None:
    r = result([S("m_H", value="125.25 GeV/c^2")], [C("m", "m_H")])
    assert float(r.value.quantity.value) == pytest.approx(2.2328e-25, rel=1e-4)
    assert r.value.value_text() == "2.2328 × 10⁻²⁵ kg"
    assert r.value.quantity.value == Fraction("125.25") * Fraction("1.602176634e-10") / 299792458**2     # exact through c²


def test_chains_and_sig_override() -> None:
    w = work([S("r", constant="AU"), S("GM", constant="GM_sun")],
             [C("v", "sqrt(GM/r)", sig=3), C("T", "2*pi*r/v", unit="d", sig=3)])
    assert w.results[1].value.value_text() == "365 d"
    assert w.results[1].used == ["r", "v"]
    over = result([S("x", value="1.2 m")], [C("y", "2*x", sig=4)])
    assert over.warnings and "claims more" in over.warnings[0]


@pytest.mark.parametrize(
    ("symbols", "calcs", "message"),
    [
        ([S("a", value="3 m"), S("b", value="2 s")], [C("x", "a + b")], r"cannot add 'a' and 'b': length \(m\) vs time \(s\)"),
        ([S("a", value="3 m"), S("b", value="2 s")], [C("x", "a - b")], r"cannot subtract 'b' from 'a': time \(s\) vs length \(m\)"),
        ([S("speed", value="3 m/s")], [C("x", "sped * 2")], "unknown symbol 'sped'; did you mean 'speed'"),
        ([S("a", value="3 m"), S("b", value="0 m")], [C("x", "a/b")], "division by zero: 'b' is 0"),
        ([S("a", value="1")], [C("x", "a*G")], r"'G': it is a constant; add it to the symbols: \{name: G, constant: G\}"),
        ([S("a", value="3 m")], [C("x", "a", unit="kg")], r"the result is length \(m\), but unit 'kg' is mass"),
        ([S("a", value="3 m")], [C("x", "a", sig=0)], "sig: 0 is impossible"),
        ([S("a", value="3 m")], [C("x", "a", sig=16)], "sig: 16 is impossible"),
        ([S("a", value="3 m")], [C("x", "a", convert=["s"])], r"convert: 's' is time \(s\), but the result is length"),
        ([S("a", value="3 m")], [C("x", "exp(a)")], r"exp\('a'\): 'a' has a unit \(length \(m\)\)"),
        ([S("a", value="3 m"), S("n", value="2.5")], [C("x", "a^n")], "its exponent must be a fixed number"),
        ([S("a", value="-4 m")], [C("x", "sqrt(a)")], "square root of a negative number"),
        ([S("a", value="3 m")], [C("x", "y + a"), C("y", "a")], r"'y' is computed by calculations\[2\], after this one"),
        ([S("a", value="3 m"), S("a", value="4 m")], [C("x", "a")], r"symbols\[2\]: 'a' is already symbols\[1\]"),
        ([S("a", value="3 m")], [C("a", "2*a")], "the result name 'a' is already"),
        ([S("sqrt", value="3")], [C("x", "2")], "is a function name"),
        ([S("a")], [C("x", "2")], "give its value"),
        ([S("a", value="3", constant="G")], [C("x", "2")], "exactly one of value, constant or from_scene"),
        ([S("a", value="3 m")], [C("x", "a", format="fraction")], "format: fraction needs an exact result"),
        ([S("a", value="3 m")], [C("x", "a", format="percent")], "format: percent needs a pure number"),
        ([S("G", constant="G", unit="kg")], [C("x", "G")], "unit 'kg' is mass"),
    ],
)
def test_calculation_errors(symbols, calcs, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        work(symbols, calcs)


def test_lenient_skips_unresolved_imports() -> None:
    w = work([S("v", value=None), S("r", value="1.0 m")], [C("T", "2*pi*r/v"), C("A", "r^2")], lenient=True)
    assert [r.name for r in w.results] == ["A"]

"""Make the star file of ``vidgen/space-sky`` (DESIGN.md §122.6):
``src/vidgen/data/web/modules/space-sky-stars.js``, the bright stars the real sky draws.

Two sources, one output format:

* ``python tools/make_star_catalogue.py --fixture`` writes the stars of :data:`FIXTURE` below:
  well-known bright stars written down from memory, **approximate** (not checked against a
  catalogue). This is the file the repository ships until a catalogue is approved.
* ``python tools/make_star_catalogue.py PATH/TO/bsc5.dat`` converts the Yale Bright Star
  Catalogue, 5th revised edition (Hoffleit and Warren 1991; CDS catalogue V/50, file ``catalog``,
  also distributed as ``bsc5.dat``; a ``.gz`` of either is read too): fixed-width lines, J2000
  positions in bytes 76-90, V in 103-107, B-V in 110-114 (:data:`BSC5_COLUMNS`). Entries without
  a position (novae and other objects that are not stars) are left out. The names of
  :data:`FIXTURE` are carried over to the catalogue's star nearest each (within 0.5 degrees and
  1.2 magnitudes).

The output is an ES module whose default export is one JSON object, so JavaScript imports it and
Python reads it (``read_star_file``): ``{"catalog", "approximate", "epoch", "complete_to",
"columns", "stars"}`` (``complete_to``: the magnitude down to which the file has every star; the
sky draws seeded stars only fainter than that) with ``stars`` rows ``[ra_deg, dec_deg, v_mag, b_minus_v]`` or ``[..., "Name"]``; right ascension
and declination in degrees to 0.001 (3.6 arc seconds), magnitudes to 0.01. Nothing is fetched:
the catalogue file is given by path.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "src" / "vidgen" / "data" / "web" / "modules" / "space-sky-stars.js"
COLUMNS = ["ra_deg", "dec_deg", "v_mag", "b_minus_v", "name"]
#: 1-based inclusive byte ranges of the Bright Star Catalogue's fixed-width line (its ReadMe).
BSC5_COLUMNS = {"ra_h": (76, 77), "ra_m": (78, 79), "ra_s": (80, 83), "dec_sign": (84, 84), "dec_d": (85, 86),
                "dec_m": (87, 88), "dec_s": (89, 90), "v_mag": (103, 107), "b_minus_v": (110, 114)}
BSC5_NAME = "Yale Bright Star Catalogue, 5th revised edition (Hoffleit and Warren 1991), CDS V/50"
FIXTURE_NAME = "fixture: well-known bright stars written down from memory (approximate, not checked against a catalogue)"
#: The magnitude down to which each source has (about) every star of the sky.
FIXTURE_COMPLETE_TO = 2.5
BSC5_COMPLETE_TO = 6.5
#: B-V used for a catalogue star that has none (a white star).
DEFAULT_B_MINUS_V = 0.3
#: The fewest stars a converted catalogue must have (the Bright Star Catalogue has about 9,100).
MIN_CATALOGUE_STARS = 8000

#: name; right ascension h m; declination d m; V; B-V. J2000, from memory: approximate.
FIXTURE = """
Sirius            06 45.2  -16 43  -1.46  0.00
Canopus           06 24.0  -52 42  -0.74  0.15
Rigil Kentaurus   14 39.6  -60 50  -0.27  0.71
Arcturus          14 15.7  +19 11  -0.05  1.23
Vega              18 36.9  +38 47   0.03  0.00
Capella           05 16.7  +46 00   0.08  0.80
Rigel             05 14.5  -08 12   0.13 -0.03
Procyon           07 39.3  +05 13   0.34  0.42
Achernar          01 37.7  -57 14   0.46 -0.16
Betelgeuse        05 55.2  +07 24   0.50  1.85
Hadar             14 03.8  -60 22   0.61 -0.23
Altair            19 50.8  +08 52   0.77  0.22
Acrux             12 26.6  -63 06   0.76 -0.24
Aldebaran         04 35.9  +16 31   0.85  1.54
Antares           16 29.4  -26 26   0.96  1.83
Spica             13 25.2  -11 10   0.97 -0.23
Pollux            07 45.3  +28 02   1.14  1.00
Fomalhaut         22 57.7  -29 37   1.16  0.09
Deneb             20 41.4  +45 17   1.25  0.09
Mimosa            12 47.7  -59 41   1.25 -0.23
Regulus           10 08.4  +11 58   1.35 -0.11
Adhara            06 58.6  -28 58   1.50 -0.21
Castor            07 34.6  +31 53   1.58  0.03
Shaula            17 33.6  -37 06   1.63 -0.22
Gacrux            12 31.2  -57 07   1.63  1.59
Bellatrix         05 25.1  +06 21   1.64 -0.22
Elnath            05 26.3  +28 36   1.65 -0.13
Miaplacidus       09 13.2  -69 43   1.68  0.00
Alnilam           05 36.2  -01 12   1.70 -0.19
Alnair            22 08.2  -46 58   1.74 -0.13
Alnitak           05 40.8  -01 57   1.77 -0.21
Alioth            12 54.0  +55 58   1.77 -0.02
Regor             08 09.5  -47 20   1.78 -0.22
Dubhe             11 03.7  +61 45   1.79  1.07
Mirfak            03 24.3  +49 52   1.79  0.48
Wezen             07 08.4  -26 24   1.84  0.68
Kaus Australis    18 24.2  -34 23   1.85 -0.03
Avior             08 22.5  -59 31   1.86  1.28
Alkaid            13 47.5  +49 19   1.86 -0.19
Sargas            17 37.3  -43 00   1.87  0.40
Menkalinan        05 59.5  +44 57   1.90  0.03
Atria             16 48.7  -69 02   1.92  1.44
Alhena            06 37.7  +16 24   1.93  0.00
Peacock           20 25.6  -56 44   1.94 -0.20
Delta Velorum     08 44.7  -54 43   1.96  0.04
Polaris           02 31.8  +89 16   1.98  0.60
Mirzam            06 22.7  -17 57   1.98 -0.23
Alphard           09 27.6  -08 40   1.98  1.44
Hamal             02 07.2  +23 28   2.00  1.15
Nunki             18 55.3  -26 18   2.02 -0.22
Diphda            00 43.6  -17 59   2.04  1.02
Menkent           14 06.7  -36 22   2.06  1.01
Alpheratz         00 08.4  +29 05   2.06 -0.11
Mirach            01 09.7  +35 37   2.06  1.58
Saiph             05 47.8  -09 40   2.06 -0.18
Kochab            14 50.7  +74 09   2.08  1.47
Rasalhague        17 34.9  +12 34   2.08  0.15
Algieba           10 20.0  +19 50   2.08  1.15
Beta Gruis        22 42.7  -46 53   2.10  1.60
Algol             03 08.2  +40 57   2.12 -0.05
Denebola          11 49.1  +14 34   2.14  0.09
Muhlifain         12 41.5  -48 58   2.17 -0.01
Sadr              20 22.2  +40 15   2.20  0.68
Suhail            09 08.0  -43 26   2.21  1.66
Schedar           00 40.5  +56 32   2.23  1.17
Mintaka           05 32.0  -00 18   2.23 -0.22
Eltanin           17 56.6  +51 29   2.23  1.52
Alphecca          15 34.7  +26 43   2.23 -0.02
Naos              08 03.6  -40 00   2.25 -0.26
Aspidiske         09 17.1  -59 17   2.25  0.18
Almach            02 03.9  +42 20   2.26  1.37
Mizar             13 23.9  +54 56   2.27  0.02
Caph              00 09.2  +59 09   2.27  0.34
Larawag           16 50.2  -34 18   2.29  1.15
Epsilon Centauri  13 39.9  -53 28   2.30 -0.22
Alpha Lupi        14 41.9  -47 23   2.30 -0.20
Eta Centauri      14 35.5  -42 09   2.31 -0.19
Dschubba          16 00.3  -22 37   2.32 -0.12
Merak             11 01.8  +56 23   2.37 -0.02
Izar              14 45.0  +27 04   2.37  0.97
Enif              21 44.2  +09 52   2.39  1.53
Ankaa             00 26.3  -42 18   2.39  1.09
Girtab            17 42.5  -39 02   2.41 -0.22
Scheat            23 03.8  +28 05   2.42  1.67
Sabik             17 10.4  -15 43   2.43  0.06
Phecda            11 53.8  +53 42   2.44  0.00
Alderamin         21 18.6  +62 35   2.44  0.22
Aludra            07 24.1  -29 18   2.45 -0.08
Gienah Cygni      20 46.2  +33 58   2.46  1.03
Navi              00 56.7  +60 43   2.47 -0.15
Markab            23 04.8  +15 12   2.49 -0.04
Markeb            09 22.1  -55 01   2.50 -0.18
Menkar            03 02.3  +04 05   2.53  1.64
Zeta Centauri     13 55.5  -47 17   2.55 -0.22
Zosma             11 14.1  +20 31   2.56  0.12
Zeta Ophiuchi     16 37.2  -10 34   2.56  0.02
Arneb             05 32.7  -17 49   2.58  0.21
Gienah            12 15.8  -17 33   2.59 -0.11
Delta Centauri    12 08.4  -50 43   2.60 -0.12
Ascella           19 02.6  -29 53   2.60  0.08
Zubeneschamali    15 17.0  -09 23   2.61 -0.11
Theta Aurigae     05 59.7  +37 13   2.62 -0.08
Acrab             16 05.4  -19 48   2.62 -0.07
Sheratan          01 54.6  +20 48   2.64  0.13
Phact             05 39.6  -34 04   2.64 -0.12
Kraz              12 34.4  -23 24   2.65  0.89
Unukalhai         15 44.3  +06 26   2.65  1.17
Ruchbah           01 25.8  +60 14   2.68  0.13
Muphrid           13 54.7  +18 24   2.68  0.58
Beta Lupi         14 58.5  -43 08   2.68 -0.22
Lesath            17 30.8  -37 18   2.69 -0.22
Hassaleh          04 57.0  +33 10   2.69  1.53
Alpha Muscae      12 37.2  -69 08   2.69 -0.20
Mu Velorum        10 46.8  -49 25   2.69  0.90
Kaus Media        18 21.0  -29 50   2.70  1.38
Pi Puppis         07 17.1  -37 06   2.70  1.62
Tarazed           19 46.3  +10 37   2.72  1.52
Porrima           12 41.7  -01 27   2.74  0.36
Yed Prior         16 14.3  -03 42   2.74  1.58
Eta Draconis      16 24.0  +61 31   2.74  0.91
Zubenelgenubi     14 50.9  -16 03   2.75  0.15
Iota Centauri     13 20.6  -36 43   2.75  0.04
Theta Carinae     10 43.0  -64 24   2.76 -0.22
Hatysa            05 35.4  -05 55   2.77 -0.24
Kornephoros       16 30.2  +21 29   2.77  0.94
Cebalrai          17 43.5  +04 34   2.77  1.16
Gamma Lupi        15 35.1  -41 10   2.78 -0.20
Cursa             05 07.9  -05 05   2.79  0.13
Rastaban          17 30.4  +52 18   2.79  0.98
Imai              12 15.1  -58 45   2.80 -0.23
Beta Hydri        00 25.8  -77 15   2.80  0.62
Kaus Borealis     18 28.0  -25 25   2.81  1.04
Zeta Herculis     16 41.3  +31 36   2.81  0.65
Rho Puppis        08 07.5  -24 18   2.81  0.43
Paikauhale        16 35.9  -28 13   2.82 -0.25
Algenib           00 13.2  +15 11   2.83 -0.23
Vindemiatrix      13 02.2  +10 58   2.83  0.94
Nihal             05 28.3  -20 46   2.84  0.82
Beta Trianguli Australis  15 55.1  -63 26  2.85  0.29
Beta Arae         17 25.3  -55 32   2.85  1.46
Zeta Persei       03 54.1  +31 53   2.85  0.12
Alpha Hydri       01 58.8  -61 34   2.86  0.28
Alpha Tucanae     22 18.5  -60 16   2.86  1.39
Alcyone           03 47.5  +24 06   2.87 -0.09
Deneb Algedi      21 47.0  -16 08   2.87  0.29
Delta Cygni       19 45.0  +45 08   2.87 -0.03
Tejat             06 23.0  +22 31   2.88  1.64
Epsilon Persei    03 57.9  +40 01   2.89 -0.18
Pi Scorpii        15 58.9  -26 07   2.89 -0.19
Alniyat           16 21.2  -25 36   2.89  0.13
Albaldah          19 09.8  -21 01   2.89  0.35
Gamma Trianguli Australis  15 18.9  -68 41  2.89  0.00
Cor Caroli        12 56.0  +38 19   2.90 -0.12
Gomeisa           07 27.2  +08 17   2.90 -0.09
Acamar            02 58.3  -40 18   2.90  0.14
Sadalsuud         21 31.6  -05 34   2.91  0.83
Gamma Persei      03 04.8  +53 30   2.93  0.70
Tau Puppis        06 49.9  -50 37   2.93  1.20
Eta Pegasi        22 43.0  +30 13   2.94  0.86
Zaurak            03 58.0  -13 30   2.95  1.59
Delta Corvi       12 29.9  -16 31   2.95 -0.05
Alpha Arae        17 31.8  -49 53   2.95 -0.17
Sadalmelik        22 05.8  -00 19   2.96  0.98
Upsilon Carinae   09 47.1  -65 04   2.97  0.27
Mebsuta           06 43.9  +25 08   2.98  1.40
Epsilon Leonis    09 45.9  +23 46   2.98  0.80
Alnasl            18 05.8  -30 25   2.99  1.00
Zeta Aquilae      19 05.4  +13 52   2.99  0.01
Zeta Tauri        05 37.7  +21 09   3.00 -0.19
Beta Trianguli    02 09.5  +34 59   3.00  0.14
Epsilon Corvi     12 10.1  -22 37   3.00  1.33
Delta Persei      03 42.9  +47 47   3.01 -0.13
Gamma Gruis       21 53.9  -37 22   3.01 -0.12
Omicron2 Canis Majoris  07 03.0  -23 50  3.02 -0.08
Furud             06 20.3  -30 04   3.02 -0.19
Iota1 Scorpii     17 47.6  -40 08   3.03  0.51
Mu1 Scorpii       16 51.9  -38 03   3.04 -0.20
Pherkad           15 20.7  +71 50   3.05  0.05
Beta Muscae       12 46.3  -68 06   3.05 -0.18
Albireo           19 30.7  +27 58   3.08  1.13
Dabih             20 21.0  -14 47   3.08  0.79
Alpha Indi        20 37.6  -47 17   3.11  1.00
Eta Sagittarii    18 17.6  -36 46   3.11  1.56
Wazn              05 51.0  -35 46   3.12  1.16
Phi Sagittarii    18 45.7  -26 59   3.17 -0.11
Tabit             04 49.8  +06 58   3.19  0.45
Alpha Circini     14 42.5  -64 58   3.19  0.24
Kappa Ophiuchi    16 57.7  +09 23   3.20  1.15
Zeta Cygni        21 12.9  +30 14   3.20  0.99
Errai             23 39.4  +77 38   3.21  1.03
Alfirk            21 28.7  +70 34   3.23 -0.22
Theta Aquilae     20 11.3  -00 49   3.23 -0.07
Yed Posterior     16 18.3  -04 42   3.24  0.96
Sulafat           18 58.9  +32 41   3.24 -0.05
Eta Serpentis     18 21.3  -02 54   3.26  0.94
Theta Ophiuchi    17 22.0  -25 00   3.27 -0.22
Delta Andromedae  00 39.3  +30 52   3.27  1.28
Alpha Doradus     04 34.0  -55 03   3.27 -0.10
Alpha Pictoris    06 48.2  -61 56   3.27  0.21
Sigma Librae      15 04.1  -25 17   3.29  1.70
Megrez            12 15.4  +57 02   3.31  0.08
Tau Sagittarii    19 06.9  -27 40   3.32  1.19
Eta Scorpii       17 12.2  -43 14   3.33  0.41
Nu Ophiuchi       17 59.0  -09 46   3.34  0.99
Alpha Reticuli    04 14.4  -62 28   3.35  0.91
Eta Orionis       05 24.5  -02 24   3.36 -0.17
Delta Aquilae     19 25.5  +03 07   3.36  0.32
Segin             01 54.4  +63 40   3.38 -0.15
Meissa            05 35.1  +09 56   3.39 -0.18
Mothallah         01 53.1  +29 35   3.41  0.49
Lambda Aquilae    19 06.3  -04 53   3.44 -0.09
Sheliak           18 50.1  +33 22   3.45  0.00
Xi2 Sagittarii    18 57.7  -21 06   3.51  1.18
Alpha Telescopii  18 27.0  -45 58   3.51 -0.17
Algedi            20 18.1  -12 33   3.57  0.94
Zeta Scorpii      16 54.6  -42 22   3.62  1.37
Alshain           19 55.3  +06 24   3.71  0.86
Omicron Sagittarii  19 04.7  -21 44  3.77  1.01
Mu Sagittarii     18 13.8  -21 04   3.86  0.23
Meridiana         19 09.5  -37 54   4.11  0.04
Beta Coronae Australis  19 10.0  -39 20  4.11  1.20
"""


def fixture_stars() -> list[list]:
    """The rows of :data:`FIXTURE`: ``[ra_deg, dec_deg, v_mag, b_minus_v, name]``."""
    rows = []
    for line in FIXTURE.strip().splitlines():
        parts = line.split()
        name, (ra_h, ra_m, dec_d, dec_m, v_mag, b_v) = " ".join(parts[:-6]), parts[-6:]
        sign = -1.0 if dec_d.startswith("-") else 1.0
        ra = (float(ra_h) + float(ra_m) / 60.0) * 15.0
        dec = sign * (abs(float(dec_d)) + float(dec_m) / 60.0)
        rows.append([round(ra, 3), round(dec, 3), float(v_mag), float(b_v), name])
    return rows


def _field(line: str, key: str) -> str:
    first, last = BSC5_COLUMNS[key]
    return line[first - 1:last].strip()


def parse_bsc5(text: str) -> list[list]:
    """The stars of the Bright Star Catalogue's fixed-width ``text``: ``[ra_deg, dec_deg, v_mag,
    b_minus_v]`` rows, brightest first. Lines without a position or a magnitude are left out; a line
    whose numbers do not fit the layout stops the conversion with its line number."""
    rows = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not _field(line, "ra_h") or not _field(line, "v_mag"):
            continue
        try:
            ra = (float(_field(line, "ra_h")) + float(_field(line, "ra_m")) / 60.0 + float(_field(line, "ra_s")) / 3600.0) * 15.0
            sign = -1.0 if _field(line, "dec_sign") == "-" else 1.0
            dec = sign * (float(_field(line, "dec_d")) + float(_field(line, "dec_m")) / 60.0 + float(_field(line, "dec_s")) / 3600.0)
            v_mag = float(_field(line, "v_mag"))
            b_v = float(_field(line, "b_minus_v")) if _field(line, "b_minus_v") else DEFAULT_B_MINUS_V
        except ValueError as error:
            raise SystemExit(f"line {number} does not fit the Bright Star Catalogue's layout ({error}): {line[:60]!r}") from None
        if not (0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0 and -2.0 <= v_mag <= 9.0 and -0.6 <= b_v <= 3.5):
            raise SystemExit(f"line {number}: a value out of range (ra {ra}, dec {dec}, V {v_mag}, B-V {b_v}): wrong file or layout?")
        rows.append([round(ra, 3), round(dec, 3), round(v_mag, 2), round(b_v, 2)])
    rows.sort(key=lambda r: (r[2], r[0], r[1]))
    return rows


def separation_deg(a: list, b: list) -> float:
    """The angle in degrees between two rows' positions."""
    ra1, dec1, ra2, dec2 = (math.radians(x) for x in (a[0], a[1], b[0], b[1]))
    cos = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def carry_names(rows: list[list], named: list[list], within_deg: float = 0.5, within_mag: float = 1.2) -> int:
    """Give each star of ``named`` its name on the brightest row of ``rows`` close to it; the number carried."""
    carried = 0
    for star in named:
        near = [r for r in rows if len(r) == 4 and abs(r[1] - star[1]) <= within_deg and abs(r[2] - star[2]) <= within_mag
                and separation_deg(r, star) <= within_deg]
        if near:
            min(near, key=lambda r: r[2]).append(star[4])
            carried += 1
    return carried


def star_file_text(catalog: str, approximate: bool, complete_to: float, rows: list[list]) -> str:
    """The module's text: a comment, then ``export default`` one JSON object (a row per line)."""
    head = {"catalog": catalog, "approximate": approximate, "epoch": "J2000.0", "complete_to": complete_to, "columns": COLUMNS}
    lines = ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows)
    body = json.dumps(head, ensure_ascii=False)[:-1] + ', "stars": [\n' + lines + "\n]}"
    return ("// The bright stars of vidgen/space-sky's real sky (DESIGN.md §122.6). Written by\n"
            "// tools/make_star_catalogue.py; do not edit by hand. Right ascension and declination in\n"
            "// degrees (J2000), V magnitude, B-V colour index, a name where the star has one.\n"
            f"export default {body};\n")


def read_star_file(path: Path = OUTPUT) -> dict:
    """The JSON object of a star file written by :func:`star_file_text`."""
    text = path.read_text(encoding="utf-8")
    return json.loads(text[text.index("export default ") + len("export default "):].rstrip().rstrip(";"))


def read_catalogue_text(path: Path) -> str:
    """The catalogue file's text (``.gz`` is unpacked); the catalogue is plain ASCII."""
    data = path.read_bytes()
    if path.suffix == ".gz" or data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data.decode("latin-1")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write vidgen/space-sky's star file from the fixture or from the Bright Star Catalogue.")
    parser.add_argument("catalogue", nargs="?", type=Path, help="bsc5.dat (or CDS V/50 'catalog'), plain or .gz")
    parser.add_argument("--fixture", action="store_true", help="write the hand-written approximate stars instead")
    parser.add_argument("--out", type=Path, default=OUTPUT, help=f"the file to write (default: {OUTPUT})")
    args = parser.parse_args(argv)
    if args.fixture == (args.catalogue is not None):
        parser.error("give either --fixture or the catalogue file")
    if args.fixture:
        rows = sorted(fixture_stars(), key=lambda r: (r[2], r[0]))
        text = star_file_text(FIXTURE_NAME, True, FIXTURE_COMPLETE_TO, rows)
    else:
        if not args.catalogue.is_file():
            parser.error(f"no file {args.catalogue}")
        rows = parse_bsc5(read_catalogue_text(args.catalogue))
        if len(rows) < MIN_CATALOGUE_STARS:
            raise SystemExit(f"only {len(rows)} stars read from {args.catalogue}; the Bright Star Catalogue has about 9,100: wrong file or layout?")
        carried = carry_names(rows, fixture_stars())
        print(f"{len(rows)} stars, {carried} names carried over from the fixture")
        text = star_file_text(BSC5_NAME, False, BSC5_COMPLETE_TO, rows)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({len(text.encode('utf-8'))} bytes, {len(rows)} stars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Human pedigrees in standard nomenclature (DESIGN.md §96.8; NSGC recommendations, Bennett et al.
2008): the individuals and their relations as an author writes them in YAML (a mapping per person,
or a compact line such as ``"II-3: female affected of I-1 + I-2"``), checked with clear errors
(two fathers, a cycle, twins who are not siblings, generations that do not fit…), the couples
(from shared children, ``spouse:`` and ``couples:``; consanguinity found from shared ancestors),
the generations and who married into the family. The layout is ``pedigree_layout``, the analysis
of the modes of inheritance ``pedigree_analysis``. No manim."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from vidgen.cellworld.model import did_you_mean
from vidgen.errors import VidgenError

#: Sexes as written (NSGC: male square, female circle, unknown or not stated a diamond).
SEXES = {"female": "female", "f": "female", "woman": "female", "girl": "female", "male": "male", "m": "male", "man": "male",
         "boy": "male", "unknown": "unknown", "u": "unknown", "diamond": "unknown"}
ZYGOSITY = {"mz": "MZ", "monozygotic": "MZ", "identical": "MZ", "dz": "DZ", "dizygotic": "DZ", "fraternal": "DZ",
            "unknown": "unknown", "?": "unknown"}
LOSSES = ("miscarriage", "stillbirth")
PERSON_KEYS = ("id", "sex", "affected", "carrier", "deceased", "proband", "consultand", "adopted", "loss", "proposed", "parents",
               "spouse", "twin", "age", "label")
COUPLE_KEYS = ("partners", "consanguineous", "separated")
#: An id in NSGC form: generation in Roman numerals, then the individual's number (``II-3``).
NSGC_ID = re.compile(r"^(?P<gen>[IVXL]+)-(?P<num>[1-9][0-9]*)$")
_ID = re.compile(r"^[A-Za-z0-9_.\-]+$")
_ROMAN = [(50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def roman(n: int) -> str:
    """``n`` (1, 2, …) in Roman numerals: the generation's name (I, II, III, IV…)."""
    out = ""
    for value, letters in _ROMAN:
        while n >= value:
            out += letters
            n -= value
    return out


def roman_value(text: str) -> int:
    """The number a Roman numeral stands for (``IV`` → 4)."""
    values = {"I": 1, "V": 5, "X": 10, "L": 50}
    total = 0
    for i, ch in enumerate(text):
        v = values[ch]
        total += -v if i + 1 < len(text) and values[text[i + 1]] > v else v
    return total


@dataclass(frozen=True)
class Person:
    """One individual: sex, phenotype (affected, carrier), status and the NSGC marks."""

    id: str
    sex: str
    affected: bool = False
    carrier: bool = False
    deceased: bool = False
    proband: bool = False
    consultand: bool = False
    adopted: str | None = None          # "in" (into this family) or "out" (born here, raised elsewhere)
    loss: str | None = None             # miscarriage (small triangle) or stillbirth (SB)
    proposed: bool = False              # a child not yet born: the risk is for it
    parents: tuple[str, str] | None = None
    twin: str | None = None
    zygosity: str | None = None
    age: str = ""
    label: str = ""

    @property
    def phenotyped(self) -> bool:
        """Whether the person's phenotype is data for the analysis (a proposed child's is not)."""
        return not self.proposed


@dataclass(frozen=True)
class Couple:
    """Two partners (the male first when there is one), their children in birth order, and the
    marks on the mating line."""

    a: str
    b: str
    children: tuple[str, ...] = ()
    consanguineous: bool = False
    separated: bool = False

    @property
    def partners(self) -> tuple[str, str]:
        return (self.a, self.b)


@dataclass
class Pedigree:
    """A checked family chart: the people in YAML order, the couples, each person's generation
    (0 = the top row, I), who married into the family, the twins and the NSGC numbering when
    the author gave NSGC ids."""

    people: dict[str, Person]
    couples: tuple[Couple, ...]
    generation: dict[str, int]
    married_in: frozenset[str]
    nsgc_ids: bool
    labels: dict[str, str] = field(default_factory=dict)

    def person(self, pid: str) -> Person:
        return self.people[pid]

    def couple_of_parents(self, pid: str) -> Couple | None:
        """The couple whose child ``pid`` is (adoptive parents for an adopted-in child)."""
        p = self.people[pid]
        if p.parents is None:
            return None
        key = frozenset(p.parents)
        return next(c for c in self.couples if frozenset(c.partners) == key)

    def couples_of(self, pid: str) -> list[Couple]:
        return [c for c in self.couples if pid in c.partners]

    def partner(self, couple: Couple, pid: str) -> str:
        return couple.b if couple.a == pid else couple.a

    def bio_parents(self, pid: str) -> tuple[str, str] | None:
        """The biological parents on the chart: none for an adopted-in child."""
        p = self.people[pid]
        return None if p.adopted == "in" else p.parents

    def mother_father(self, pid: str) -> tuple[str, str] | None:
        """(mother, father) of ``pid`` (biological), or ``None``."""
        par = self.bio_parents(pid)
        if par is None:
            return None
        a, b = par
        return (a, b) if self.people[a].sex == "female" else (b, a)

    def label(self, pid: str) -> str:
        """The NSGC label (``II-3``) once the layout has numbered the chart, else the id."""
        return self.labels.get(pid, pid)

    @property
    def rows(self) -> int:
        return max(self.generation.values()) + 1

    @property
    def proposed(self) -> str | None:
        return next((p.id for p in self.people.values() if p.proposed), None)

    def ancestors(self, pid: str) -> set[str]:
        """Every biological ancestor of ``pid`` on the chart."""
        out: set[str] = set()
        todo = list(self.bio_parents(pid) or ())
        while todo:
            x = todo.pop()
            if x not in out:
                out.add(x)
                todo += list(self.bio_parents(x) or ())
        return out


# ----- parsing --------------------------------------------------------------------------------------


def _flag(value: Any, where: str, what: str) -> bool:
    if isinstance(value, bool):
        return value
    raise VidgenError(f"{where}: {what} is true or false, not '{value}'")


def _ids(value: Any, where: str, what: str) -> list[str]:
    if isinstance(value, str):
        parts = [x for x in re.split(r"[\s,+&]+", value.strip()) if x]
    elif isinstance(value, (list, tuple)):
        parts = [str(x).strip() for x in value]
    else:
        raise VidgenError(f"{where}: {what} lists ids ([I-1, I-2] or \"I-1 + I-2\")")
    return parts


def _compact(text: str, where: str) -> dict[str, Any]:
    """A person written on one line: ``"II-3: female affected deceased of I-1 + I-2 twin II-4 MZ
    age 45 y"`` (the id, a colon, then words: a sex, flags, ``of`` the parents, ``twin`` an id
    with MZ / DZ, ``spouse`` an id, ``adopted in`` / ``out``, ``age`` and the rest of the line)."""
    if ":" not in text:
        raise VidgenError(f"{where}: '{text}': write \"<id>: <sex> [affected] [carrier] [deceased] [of <parent> + <parent>]\"")
    pid, rest = text.split(":", 1)
    data: dict[str, Any] = {"id": pid.strip()}
    words = rest.replace(",", " ").split()
    flags = {"affected", "carrier", "deceased", "proband", "consultand", "proposed"}
    i = 0
    while i < len(words):
        w = words[i]
        low = w.lower()
        if low in SEXES:
            data["sex"] = low
        elif low in flags:
            data[low] = True
        elif low in LOSSES:
            data["loss"] = low
        elif low == "adopted":
            if i + 1 < len(words) and words[i + 1].lower() in ("in", "out"):
                data["adopted"] = words[i + 1].lower()
                i += 1
            else:
                data["adopted"] = "in"
        elif low == "of":
            got = []
            while i + 1 < len(words) and len(got) < 2:
                nxt = words[i + 1]
                i += 1
                got += [x for x in nxt.split("+") if x]
            data["parents"] = got
        elif low == "twin":
            if i + 1 >= len(words):
                raise VidgenError(f"{where}: 'twin' needs the co-twin's id (twin II-4 MZ)")
            twin: dict[str, Any] = {"with": words[i + 1]}
            i += 1
            if i + 1 < len(words) and words[i + 1].lower() in ZYGOSITY:
                twin["kind"] = words[i + 1]
                i += 1
            data["twin"] = twin
        elif low == "spouse":
            if i + 1 >= len(words):
                raise VidgenError(f"{where}: 'spouse' needs the partner's id")
            data.setdefault("spouse", []).append(words[i + 1])
            i += 1
        elif low == "age":
            data["age"] = " ".join(words[i + 1:])
            break
        else:
            known = [*SEXES, *flags, *LOSSES, "adopted", "of", "twin", "spouse", "age"]
            raise VidgenError(f"{where}: '{w}' in '{text}' is not a word of the compact form ({', '.join(known)}){did_you_mean(low, known)}")
        i += 1
    return data


def _person(data: Any, where: str) -> tuple[Person, list[str]]:
    if isinstance(data, str):
        data = _compact(data, where)
    if not isinstance(data, Mapping):
        raise VidgenError(f"{where}: an individual is a mapping ({{id: II-3, sex: female, affected: true, parents: [I-1, I-2]}}) "
                          f"or a line (\"II-3: female affected of I-1 + I-2\")")
    for key in data:
        if key not in PERSON_KEYS:
            raise VidgenError(f"{where}: unknown key '{key}': use {', '.join(PERSON_KEYS)}{did_you_mean(str(key), list(PERSON_KEYS))}")
    if "id" not in data:
        raise VidgenError(f"{where}: give the individual an id (II-3, or a name)")
    pid = str(data["id"]).strip()
    if not _ID.match(pid):
        raise VidgenError(f"{where}: id '{pid}': letters, digits, '-', '_' and '.' only (II-3, grandma)")
    where = f"{where} ({pid})"
    sex_text = str(data.get("sex", "unknown")).strip().lower()
    if sex_text not in SEXES:
        raise VidgenError(f"{where}: sex '{data.get('sex')}': use female, male or unknown{did_you_mean(sex_text, list(SEXES))}")
    flags = {k: _flag(data[k], where, k) for k in ("affected", "carrier", "deceased", "proband", "consultand", "proposed") if k in data}
    adopted = data.get("adopted")
    if adopted is True:
        adopted = "in"
    elif adopted is False or adopted is None:
        adopted = None
    elif str(adopted).lower() in ("in", "out"):
        adopted = str(adopted).lower()
    else:
        raise VidgenError(f"{where}: adopted: in (adopted into this family) or out (born here, adopted out), not '{adopted}'")
    loss = data.get("loss")
    if loss is not None and str(loss).lower() not in LOSSES:
        raise VidgenError(f"{where}: loss: {' or '.join(LOSSES)}, not '{loss}'{did_you_mean(str(loss), list(LOSSES))}")
    parents = None
    if data.get("parents") is not None:
        ids = _ids(data["parents"], where, "parents")
        if len(ids) != 2:
            raise VidgenError(f"{where}: parents: give both parents ({len(ids)} given); add a parent who is not shown "
                              f"otherwise as an individual (sex unknown is not enough: give the sex)")
        if ids[0] == ids[1]:
            raise VidgenError(f"{where}: parents: {ids[0]} twice")
        if pid in ids:
            raise VidgenError(f"{where}: parents: an individual cannot be its own parent")
        parents = (ids[0], ids[1])
    twin, zyg = None, None
    if data.get("twin") is not None:
        t = data["twin"]
        if isinstance(t, str):
            twin, zyg = t.strip(), "unknown"
        elif isinstance(t, Mapping):
            bad = [k for k in t if k not in ("with", "kind")]
            if bad or "with" not in t:
                raise VidgenError(f"{where}: twin: {{with: II-4, kind: MZ}} (kind MZ, DZ or unknown)")
            twin = str(t["with"]).strip()
            kind = str(t.get("kind", "unknown")).strip().lower()
            if kind not in ZYGOSITY:
                raise VidgenError(f"{where}: twin kind '{t.get('kind')}': MZ (monozygotic), DZ (dizygotic) or unknown")
            zyg = ZYGOSITY[kind]
        else:
            raise VidgenError(f"{where}: twin: the co-twin's id, or {{with: II-4, kind: MZ}}")
    spouses = _ids(data["spouse"], where, "spouse") if data.get("spouse") is not None else []
    person = Person(pid, SEXES[sex_text], adopted=adopted, loss=str(loss).lower() if loss else None, parents=parents, twin=twin,
                    zygosity=zyg, age=str(data.get("age", "") or ""), label=str(data.get("label", "") or ""), **flags)
    if person.affected and person.carrier:
        raise VidgenError(f"{where}: affected and carrier: a carrier is unaffected (mark one)")
    if person.proposed:
        if parents is None:
            raise VidgenError(f"{where}: a proposed child needs its parents (parents: [III-1, III-2])")
        if person.affected or person.carrier or person.deceased or person.loss:
            raise VidgenError(f"{where}: a proposed child has no phenotype yet: leave out affected / carrier / deceased / loss")
    if person.proband and person.consultand:
        raise VidgenError(f"{where}: proband or consultand: the proband is the affected person who brought the family to attention, "
                          f"the consultand the person seeking advice — mark one")
    return person, spouses


def _couple_entry(data: Any, where: str) -> tuple[list[str], bool, bool]:
    if isinstance(data, str):
        return _ids(data, where, "partners"), False, False
    if not isinstance(data, Mapping):
        raise VidgenError(f"{where}: a couple is {{partners: [II-1, II-2], consanguineous: true, separated: true}} or \"II-1 + II-2\"")
    for key in data:
        if key not in COUPLE_KEYS:
            raise VidgenError(f"{where}: unknown key '{key}': use {', '.join(COUPLE_KEYS)}{did_you_mean(str(key), list(COUPLE_KEYS))}")
    if "partners" not in data:
        raise VidgenError(f"{where}: give the partners: [II-1, II-2]")
    return (_ids(data["partners"], where, "partners"), _flag(data.get("consanguineous", False), where, "consanguineous"),
            _flag(data.get("separated", False), where, "separated"))


def _generations(people: dict[str, Person], couples: list[tuple[str, str]], where: str) -> dict[str, int]:
    """Each person's row: partners share a row, children are one row below their parents (or
    adoptive parents); each connected family starts at 0."""
    links: dict[str, list[tuple[str, int]]] = {p: [] for p in people}
    for a, b in couples:
        links[a].append((b, 0))
        links[b].append((a, 0))
    for p in people.values():
        for par in p.parents or ():
            links[p.id].append((par, -1))
            links[par].append((p.id, 1))
    gen: dict[str, int] = {}
    for start in people:
        if start in gen:
            continue
        comp = {start: 0}
        todo = [start]
        while todo:
            x = todo.pop()
            for y, d in links[x]:
                want = comp[x] + d
                if y not in comp:
                    comp[y] = want
                    todo.append(y)
                elif comp[y] != want:
                    raise VidgenError(f"{where}: the generations do not fit: {y} would be in two rows (partners share a "
                                      f"generation and children are one below their parents; a partner from another "
                                      f"generation, such as an uncle and his niece, is not supported)")
        low = min(comp.values())
        gen.update({k: v - low for k, v in comp.items()})
    return gen


def parse_pedigree(individuals: Any, couples: Any = None, where: str = "params") -> Pedigree:
    """The checked chart from the ``individuals`` (mappings or compact lines) and the optional
    ``couples`` (childless couples, consanguinity without the shared ancestors shown, separation)."""
    if not isinstance(individuals, (list, tuple)) or not individuals:
        raise VidgenError(f"{where}.individuals: list the individuals ({{id: I-1, sex: male, affected: true}}, …)")
    people: dict[str, Person] = {}
    spouse_of: list[tuple[str, str, str]] = []
    for i, item in enumerate(individuals):
        w = f"{where}.individuals[{i}]"
        p, spouses = _person(item, w)
        if p.id in people:
            raise VidgenError(f"{w}: id '{p.id}' is used twice")
        people[p.id] = p
        spouse_of += [(p.id, s, w) for s in spouses]
    ids = list(people)

    def known(pid: str, w: str, what: str) -> None:
        if pid not in people:
            raise VidgenError(f"{w}: {what} '{pid}' is not an individual{did_you_mean(pid, ids)}")

    pairs: dict[frozenset[str], dict[str, Any]] = {}

    def add(a: str, b: str, w: str) -> dict[str, Any]:
        if a == b:
            raise VidgenError(f"{w}: {a} cannot be their own partner")
        key = frozenset((a, b))
        if key not in pairs:
            pairs[key] = {"order": (a, b), "children": [], "consanguineous": False, "separated": False}
        return pairs[key]

    for i, p in enumerate(people.values()):
        w = f"{where}.individuals[{i}] ({p.id})"
        if p.parents is not None:
            for par in p.parents:
                known(par, w, "parent")
            a, b = (people[x] for x in p.parents)
            if a.sex == b.sex and a.sex != "unknown":
                kind = "fathers" if a.sex == "male" else "mothers"
                raise VidgenError(f"{w}: has two {kind} ({a.id} and {b.id} are both {a.sex}): parents are a female and a male")
            for x in (a, b):
                if x.sex == "unknown":
                    raise VidgenError(f"{w}: parent {x.id} has no sex: give it (what a parent passes on depends on it)")
                if x.proposed or x.loss:
                    raise VidgenError(f"{w}: {x.id} {'is a proposed child' if x.proposed else 'is a ' + str(x.loss)} and cannot be a parent")
            add(p.parents[0], p.parents[1], w)["children"].append(p.id)
        if p.twin is not None:
            known(p.twin, w, "twin")
    for pid, s, w in spouse_of:
        known(s, w, "spouse")
        add(pid, s, w)
    for i, entry in enumerate(couples or []):
        w = f"{where}.couples[{i}]"
        partners, cons, sep = _couple_entry(entry, w)
        if len(partners) != 2:
            raise VidgenError(f"{w}: a couple is two partners ({len(partners)} given)")
        for x in partners:
            known(x, w, "partner")
        c = add(partners[0], partners[1], w)
        c["consanguineous"] |= cons
        c["separated"] |= sep
    # cycles: nobody is their own ancestor
    state: dict[str, int] = {}

    def visit(pid: str, path: list[str]) -> None:
        state[pid] = 1
        for par in people[pid].parents or ():
            if state.get(par) == 1:
                cycle = path[path.index(par):] + [par] if par in path else [pid, par]
                raise VidgenError(f"{where}.individuals: a cycle in the parents: {' → '.join(cycle)} (someone would be their own ancestor)")
            if state.get(par) is None:
                visit(par, path + [par])
        state[pid] = 2

    for pid in people:
        if pid not in state:
            visit(pid, [pid])
    for key, c in pairs.items():
        a, b = (people[x] for x in c["order"])
        if a.loss or b.loss or a.proposed or b.proposed:
            raise VidgenError(f"{where}: {a.id} and {b.id}: a pregnancy loss or a proposed child has no partner")
    # twins: siblings of the same parents, same sex when monozygotic, and agreeing with each other
    for p in people.values():
        if p.twin is None:
            continue
        w = f"{where}.individuals ({p.id})"
        t = people[p.twin]
        if t.id == p.id:
            raise VidgenError(f"{w}: a twin of itself")
        if p.parents is None or t.parents is None or frozenset(p.parents) != frozenset(t.parents):
            raise VidgenError(f"{w}: twins {p.id} and {t.id} must have the same parents")
        if t.twin is not None and (t.twin != p.id or (t.zygosity != p.zygosity and "unknown" not in (t.zygosity, p.zygosity))):
            raise VidgenError(f"{w}: {p.id} and {t.id} disagree about their twin (each may name the other, with the same kind)")
        if p.zygosity == "MZ" and p.sex != t.sex and "unknown" not in (p.sex, t.sex):
            raise VidgenError(f"{w}: monozygotic (MZ) twins have the same sex ({p.id} is {p.sex}, {t.id} {t.sex}): DZ?")
    for flag in ("proband", "consultand", "proposed"):
        marked = [p.id for p in people.values() if getattr(p, flag)]
        if len(marked) > 1:
            raise VidgenError(f"{where}.individuals: {len(marked)} marked {flag} ({', '.join(marked)}): one only")
    for p in people.values():
        if p.twin is not None and sum(1 for q in people.values() if q.twin == p.id or p.twin == q.id) > 1:
            raise VidgenError(f"{where}.individuals ({p.id}): twins are pairs (triplets are not supported)")
    for pid in people:
        n = sum(1 for key in pairs if pid in key)
        if n > 2:
            raise VidgenError(f"{where}.individuals ({pid}): {n} partners; at most two per person in a chart")
    gen = _generations(people, [tuple(c["order"]) for c in pairs.values()], where)
    # who married in: a founder whose partner has parents on the chart (or an adopted-in child: unrelated)
    married_in = set()
    for p in people.values():
        if p.parents is None and any(people[x].parents is not None for key in pairs if p.id in key for x in key if x != p.id):
            married_in.add(p.id)
        if p.adopted == "in":
            married_in.add(p.id)
    # consanguinity: partners sharing an ancestor (or declared)
    out_couples: list[Couple] = []
    tmp = Pedigree(people, (), gen, frozenset(married_in), False)
    for key, c in pairs.items():
        a, b = c["order"]
        if people[a].sex == "female" and people[b].sex == "male":
            a, b = b, a
        shared = bool((tmp.ancestors(a) | {a}) & (tmp.ancestors(b) | {b}))
        children = tuple(x for x in people if x in c["children"])
        out_couples.append(Couple(a, b, children, c["consanguineous"] or shared, c["separated"]))
    nsgc = [NSGC_ID.match(pid) for pid in people]
    use_nsgc = all(nsgc)
    if any(nsgc) and not use_nsgc:
        odd = [pid for pid, m in zip(people, nsgc) if not m]
        raise VidgenError(f"{where}.individuals: some ids are in NSGC form (II-3) and some are not ({', '.join(odd[:4])}): "
                          f"use NSGC ids for everyone (vidgen then keeps your numbering) or for no one (vidgen numbers the chart)")
    ped = Pedigree(people, tuple(out_couples), gen, frozenset(married_in), use_nsgc)
    if use_nsgc:
        _check_nsgc(ped, where)
    return ped


def _check_nsgc(ped: Pedigree, where: str) -> None:
    """NSGC ids: the Roman numeral is the generation (partners share one, children are one
    below), the numbers are unique within a generation."""
    seen: dict[tuple[int, int], str] = {}
    gen: dict[str, int] = {}
    for pid in ped.people:
        m = NSGC_ID.match(pid)
        assert m is not None
        g, n = roman_value(m.group("gen")), int(m.group("num"))
        if roman(g) != m.group("gen"):
            raise VidgenError(f"{where}.individuals ({pid}): '{m.group('gen')}' is not a Roman numeral as written in pedigrees ({roman(g)})")
        if (g, n) in seen:
            raise VidgenError(f"{where}.individuals ({pid}): the same number as {seen[(g, n)]}")
        seen[(g, n)] = pid
        gen[pid] = g - 1
    for c in ped.couples:
        if gen[c.a] != gen[c.b]:
            raise VidgenError(f"{where}.individuals: partners {c.a} and {c.b} are in different generations: partners share one")
    for p in ped.people.values():
        for par in p.parents or ():
            if gen[p.id] != gen[par] + 1:
                raise VidgenError(f"{where}.individuals ({p.id}): the generation in its id does not fit its parent {par}: "
                                  f"children are one generation below their parents ({roman(gen[par] + 2)}-…)")
    if min(gen.values()) != 0:
        raise VidgenError(f"{where}.individuals: the top generation is {roman(min(gen.values()) + 1)}: number generations from I")
    ped.generation = gen
    ped.labels = {pid: pid for pid in ped.people}


__all__ = ["Couple", "LOSSES", "NSGC_ID", "Pedigree", "Person", "SEXES", "ZYGOSITY", "parse_pedigree", "roman", "roman_value"]

# Cookbook: genetics at university level

Craft notes for lectures, medical and biology students and science channels explaining heredity
with vidgen's genetics scene types (DESIGN §96): what to choose, how to write the notation, how to
keep every number exact, how to read a pedigree aloud, and how to speak about families. The
reference for every key is `docs/CONFIG.md` ([`cross`](CONFIG.md#cross),
[`pedigree`](CONFIG.md#pedigree), [`linkage_map`](CONFIG.md#linkage_map),
[`karyotype`](CONFIG.md#karyotype), [`mutation`](CONFIG.md#mutation), [`crispr`](CONFIG.md#crispr),
[`dna_lab`](CONFIG.md#dna_lab), [`population`](CONFIG.md#population), [`gwas`](CONFIG.md#gwas));
the author guide has the short version (`vidgen guide genetics`). The worked example is
[`examples/cystic-fibrosis`](../examples/cystic-fibrosis/README.md): one inherited disease from a
family's pedigree to the variant, a carrier test and the population, in about four minutes. The
[scene gallery](gallery/README.md#genetics) shows each type.

## 1. Choose the scene by the question

| the viewer should understand | scene | what it computes |
|---|---|---|
| what the offspring of a cross look like, and in what ratio | `cross` | gametes, the Punnett square or branch diagram, exact classes, χ² |
| how a trait runs in a family, who carries it, the risk for a child | `pedigree` | which modes fit (and why the others do not), forced genotypes, Bayesian carrier probabilities, the risk |
| how far apart two or three genes are | `linkage_map` | recombinant classes, gene order, cM, coincidence, interference |
| where a gene lies, what is wrong with the chromosome set | `karyotype` | ISCN read and checked, the change highlighted or played as an edit |
| how meiosis goes wrong | `cell_cycle` with `nondisjunction` | the gametes n + 1 / n − 1 and the zygotes |
| what a variant does to the protein | `mutation` | the codons, the protein change, HGVS, nonsense-mediated decay |
| how a gene is edited | `crispr` | the PAM, the cut, the repair outcome in HGVS |
| how a variant is detected | `dna_lab` (`pcr`, `gel`, `sanger`, `ngs`) | primers, cycles, migration, peaks, reads and a call |
| how common an allele is, how it changes | `population` | Hardy–Weinberg exactly; seeded drift, selection, migration |
| which loci go with a trait | `gwas` | a Manhattan plot with 5 × 10⁻⁸, QQ with λ_GC |

A clinical story moves through the levels in this order — family, chromosome, sequence, test,
population — and says when it moves ("Back in the family", "On the sequence"). Show the same
family twice rather than crowding one scene: the example draws the chart with its mode analysis,
then a Punnett square that explains the 2/3, then the chart again with the genotypes and the risk.

## 2. Notation: standard, and checked

- **Pedigrees: NSGC.** Squares male, circles female, diamonds unknown; affected filled; a carrier a
  dot (`carrier_style: half` for the half-shaded textbook symbol); the proband's arrow with P;
  generations in Roman numerals, people numbered left to right (`II-3`). Write NSGC ids and vidgen
  checks they read left to right as drawn; a partner from outside stands beside the relative.
- **Karyotypes: ISCN.** Count, sex chromosomes, then the changes in chromosome order:
  `47,XY,+21`, `46,XX,del(5)(p15.2)`, `46,XY,t(9;22)(q34;q11.2)`. Never `5p-`, never `47,+21,XY`.
- **Variants: HGVS** on the coding DNA of a named transcript: `c.20A>T`, `c.1521_1523del`,
  `c.35del`; the protein in parentheses (predicted): `p.(Glu7Val)`, `p.(Phe508del)`,
  `p.(Gly12Valfs*2)`. HGVS counts the initiator Met as residue 1, so the legacy names are one lower
  (Glu6Val, ΔF508 is the same residue). Use an old name only as "legacy" or "traditionally called".
  Deletions take the 3′-most position (`c.1521_1523del`, not `c.1520_1522del`): vidgen refuses the
  other with the reason.
- **Genes: HGNC**, italic (*CFTR*, *HBB*); proteins roman (CFTR, β-globin); mouse genes `Trp53`.
- **Alleles**: dominant capital, recessive lower case (`A` / `a`), superscripts (`I^A`, `X^H X^h`,
  `w^+`), linked loci with their phase (`AB/ab` coupling, `Ab/aB` repulsion).
- **Say it** through `pronunciation:` — the captions keep the notation, the voice says it:
  `"c.1521_1523del": c dot fifteen twenty-one to fifteen twenty-three del`,
  `"p.(Phe508del)": p dot phe five oh eight del`, `CFTR: C F T R`, `q31.2: q thirty-one point two`.

## 3. Exact numbers

Every number on screen comes from the model; say the same number.

- **Fractions as the scene writes them**: 3/4, 2/3, 1/150. A product of risks is said as its
  factors once ("two thirds, times one in twenty-five, times one quarter"), then the result.
- **Population numbers with "about"** and their population: "in people of European ancestry,
  about one baby in two thousand five hundred". 1/2500 gives q = 1/50 exactly and carriers
  2pq = 49/1250 ≈ 1 in 25.5 (≈ 2q = 1/25 for a rare allele): "about one in twenty-five".
- **Name the assumption** when it decides the number: random mating (q² = incidence), a rare
  allele in people marrying in (`rare: true`, the default) or the population's carrier frequency
  (`carrier_frequency: 1/25`), full penetrance (`penetrance: 0.8` otherwise).
- **Hard impossibilities are errors** in `vidgen validate` (RF over 0.5, a female with a Y, a
  stated `p.` that does not follow from the `c.`); **narration slips** are found by `vidgen lint`
  (table below).
- **Models are labelled.** NGS reads and GWAS peaks are seeded models ("simulated data" is written
  on a synthetic GWAS): never present them as a patient's or a study's result.
- **The karyotype's bands are schematic**: name the band, do not read a position off the picture.

## 4. Reading a pedigree aloud

Read it the way a geneticist does, one beat per step, the action on the word:

1. **The symbols** for this chart only (squares, circles, the filled symbol, the proband):
   `{highlight: "person:II-1", at: "@filled"}`.
2. **The modes, tested** — `{analyse: modes}` — and the reason for each exclusion in one sentence
   ("a dominant condition would have to show in a parent"). Keep the list to the modes worth
   discussing (`analyse: [AD, AR, XR]`): the card stays short.
3. **What the chart forces**: obligate carriers (`deduce: carriers`).
4. **What it makes likely**: carrier probabilities (`deduce: genotypes`), explained once (a Punnett
   square of two carriers: the affected square ruled out, two of the three left).
5. **The risk** for the proposed child (`risk: risk`), its factors, and what can change it
   (testing).

## 5. Tone: genetic counselling, not a verdict

- People "have" a condition, are "affected" or "unaffected", are "carriers"; avoid "suffers
  from", "defective gene", "normal children", "bad allele".
- Give a risk with what it means ("one in a hundred and fifty: under one percent") and the
  choices it opens (testing the partner, options before and during pregnancy), not with advice.
- Families without a history are the rule for recessive conditions: say so — it removes blame.
- Say "is expected to" for ratios: a family of four children need not show 3 : 1.

## 6. Pacing

- One step of reasoning per beat, 15–35 words, one number per sentence.
- Kokoro `speed: 0.85` for dense notation (0.9 made two beats too fast for `narration_speed`).
- Cards with full tables exceed `max_words`: reveal them step by step (`reveal: carriers`,
  `count: genotypes`) and let the narration carry the detail.
- Leave a scene title out when the drawing needs the height (the `mutation` scene's gene strip,
  two rows and the card), and use `codons: 5`–`8` so the tiles stay large (with about 5 or fewer
  in 16:9 the card stands beside the rows, which then use the whole height).
- A recap (`process`) at the end: the steps of the story, one stage per beat.

## 7. References

`references:` on the scene with an identifier copied from the source (DOI, PMID, ISBN) and `cite:`
on the beat; with karaoke captions `citations: {show: marker}`. Never invent a reference or an
identifier: leave it out instead. The example cites the 1989 papers identifying *CFTR* and
F508del (Riordan et al.; Kerem et al., *Science* 245) by their PMIDs.

## 8. Common mistakes (and the lint rule that catches them)

| mistake | rule | the fix |
|---|---|---|
| "a 3 : 1 ratio" for a dihybrid; "half the daughters are affected" for a carrier mother | `genetics_ratio` | the scene's ratio (9 : 3 : 3 : 1); "half the sons" |
| a chart that does not fit its stated `mode` | `genetics_pedigree` (error) | fix the chart or the mode |
| "a dominant trait skips a generation" | `genetics_pedigree` | say reduced penetrance and set `penetrance:` |
| father-to-son transmission of an X-linked trait | `genetics_pedigree` | a son's X comes from his mother |
| "II-2 is a carrier with probability 1/2" (it is 2/3) | `genetics_pedigree` | the chart's probability |
| an RF over 50 %, cM confused with RF | `genetics_linkage` | RF ≤ 0.5; distance = 100 × RF (or a map function) |
| "carriers are q²", "the incidence is 2pq" | `genetics_hwe` | carriers 2pq, affected q², q = √incidence |
| an NGG PAM for SaCas9, a cut "after the PAM", sticky ends from Cas9 | `genetics_crispr` | SpCas9: NGG, a blunt cut 3 bp upstream |
| `47,+21,XY`, "45,X is male" | `genetics_karyotype` | ISCN order; the right sex |
| `c.A1521del`, `p.Glu6Val` for HbS, an HGVS that is not the scene's variant | `genetics_hgvs` | `c.20A>T p.(Glu7Val)`; "legacy Glu6Val" |
| `ΔF508`, `R553X` unannounced | `genetics_hgvs` (info) | `p.(Phe508del)`, `p.(Arg553*)`; "traditionally called ΔF508" |
| *CFTR* written as a protein, a mouse gene in human form | `science_naming` | HGNC / MGI forms; italics |
| a deletion drawn at the 5′ end of a run | `vidgen validate` (`mutation`) | the 3′-most position |

## 9. The pattern of the example, in short

```yaml
- id: family
  type: pedigree
  params:
    title: "The family"
    condition: cystic fibrosis
    mode: AR
    carrier_frequency: 1/25             # a partner from the population
    analyse: [AD, AR, XR]
    individuals:
      - "I-1: male"
      - "I-2: female"
      - "II-1: female affected proband of I-1 + I-2"
      - "II-2: male consultand of I-1 + I-2"
      - "II-3: female"
      - "III-1: unknown proposed of II-2 + II-3"
  beats:
    - text: "Which modes of inheritance fit? We test each one against the chart."
      actions: [{analyse: modes, at: "@test"}]
    - text: "Her unaffected brother is a carrier with probability two thirds."
      actions: [{deduce: genotypes, at: "@carrier"}]
    - text: "For their child, the risk is one in a hundred and fifty."
      actions: [{risk: risk, at: "@risk"}]
- id: variant
  type: mutation
  params:
    gene: CFTR
    variant: {c: "c.1521_1523del", p: "p.(Phe508del)"}
  beats:
    - text: "Three bases, C T T, are deleted: c.1521_1523del."
      actions: [{mutate: variant, at: "@deleted"}]
- id: test
  type: dna_lab
  params:
    method: ngs
    reference: "ATCATCTTTGGTGTTTCCTATGATGAATATAGATACAGAA"   # CFTR c.1516–1555
    variant: "6_8delCTT"
  beats:
    - text: "About half the reads over the variant lack the three bases: he is a carrier."
      actions: [{run: call, at: "@half"}]
- id: carriers
  type: population
  params: {incidence: 1/2500, condition: cystic fibrosis}
  beats:
    - text: "Carriers are 2pq: about one person in twenty-five."
      actions: [{reveal: carriers}]
```

<!-- topic: genetics (also: heredity, inheritance, medical-genetics, punnett, hgvs) -->
## Genetics: crosses, families, variants and populations

Nine scene types draw genetics at university level, and **compute** what they show — ratios,
probabilities, gametes, map distances, protein changes, frequencies — so the picture cannot
disagree with the science (`vidgen guide scenes` has a snippet of each; every param:
`docs/CONFIG.md`). The craft in full: `docs/COOKBOOK-GENETICS.md` in the schu-video-generator
repository; a whole example: `examples/cystic-fibrosis` (one inherited disease from a pedigree to
a carrier test, 16:9 and 9:16).

**Choosing.** A question decides the type:
- What do the offspring of this cross look like? → `cross` (Punnett square or branch diagram,
  ratios, a chi-square of observed counts).
- How is it inherited in this family, who carries it, what is the risk? → `pedigree` (NSGC
  symbols, the modes tried one by one, carrier probabilities, the risk for a proposed child).
- How far apart are two genes? → `linkage_map` (crossing over, a test cross worked into cM).
- Which chromosome, which band, what is wrong with the set? → `karyotype` (ISCN; a karyogram or
  ideograms with `bands: {7q31.2: CFTR}`); non-disjunction → `cell_cycle` with `nondisjunction`.
- What does this variant do to the protein? → `mutation` (a real coding sequence, HGVS c. / p.).
- How do we edit it? → `crispr`. How do we detect it? → `dna_lab` (`pcr`, `gel`, `sanger`, `ngs`:
  a substitution or a short deletion, heterozygous or homozygous).
- How common is it, how does it change? → `population` (Hardy–Weinberg from counts or an
  incidence; drift, selection, migration, bottleneck, founder). Which loci go with a trait? →
  `gwas` (synthetic data is always labelled "simulated data").
A story across levels (family → gene → variant → test → population) uses one scene per level and
says when it moves ("Back in the family", "At the level of the sequence").

**Notation** (schu-video-generator checks it): pedigrees in NSGC symbols with generations in Roman numerals and
people numbered left to right (`II-3`); karyotypes in ISCN (`47,XY,+21`, `46,XX,t(9;22)(q34;q11.2)`;
sex chromosomes first, changes in order); variants in HGVS on the coding DNA (`c.1521_1523del`,
`p.(Phe508del)` — HGVS counts the initiator Met, so HbS is `p.(Glu7Val)`; say "legacy Glu6Val" or
"traditionally called ΔF508" when you use an old name); gene symbols in HGNC form, italic (*CFTR*),
proteins roman (CFTR); alleles in textbook form (`A` / `a`, `I^A`, `X^H X^h`, phased `AB/ab`).
Let the voice say them through `pronunciation:` (`"c.1521_1523del": c dot fifteen twenty-one to
fifteen twenty-three del`, `CFTR: C F T R`) and check with `vidgen readback`.

**Exactness.**
- Say what the scene computes: fractions as the scene writes them (2/3, 1/150) or "about" for a
  rounded population number ("about one in twenty-five" for 49/1250). The `genetics_*` lint rules
  read the narration and the on-screen text against each scene: `genetics_ratio`,
  `genetics_pedigree` (a chart that does not fit its stated `mode` is an error), `genetics_linkage`,
  `genetics_hwe`, `genetics_crispr`, `genetics_karyotype`, `genetics_hgvs`.
- State the assumptions where they matter: random mating for q² = incidence, a rare allele for
  people marrying in (`carrier_frequency: 1/25` when the population's number is the point), full
  penetrance unless `penetrance:` says otherwise.
- Real numbers need real sources: an incidence or carrier frequency "in people of European
  ancestry, approximately …", a reference with an identifier copied from the source (`references:`,
  `cite:`), never invented. Synthetic data (NGS reads, GWAS peaks) is a model: do not present it as
  a patient's or a study's result.
- The karyotype's band pattern is schematic: name the band ("band q31.2"), do not read positions
  off it.

**Tone.** Medical genetics is about families: say "affected", "has the condition", "a carrier"
(not "suffers from", "defective gene", "normal child"); give risks as chances with what they mean
("one in a hundred and fifty, under one percent") and end with what the family can do (testing,
counselling), not with a verdict.

**Pacing.** One step of reasoning per beat (the chart, the modes, the carriers, the risk), 15–35
words; actions on the word (`{analyse: modes, at: "@test"}`, `{mutate: variant, at:
"@deleted"}`); Kokoro `speed: 0.85` for dense notation; one number per sentence; a recap
(`process`) at the end. Long tables and cards exceed `max_words`: let the narration carry them
and reveal them step by step.

```yaml
- id: variant
  type: mutation
  params:
    gene: CFTR                         # a real coding window (NM_000492.4)
    variant: {c: "c.1521_1523del", p: "p.(Phe508del)"}   # p. is checked against the genetic code
  beats:
    - text: "Three bases, C T T, are deleted: c.1521_1523del."
      actions: [{mutate: variant, at: "@deleted"}]
    - text: "The frame is kept, and one phenylalanine is missing: p.(Phe508del), traditionally called ΔF508."
```


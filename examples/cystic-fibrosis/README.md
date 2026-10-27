# Cystic fibrosis: from a family to a diagnosis

A university-level medical-genetics explainer (nine scenes, about 4 min 12 s with Kokoro
narration) that follows one inherited disease, **cystic fibrosis**, from a family's pedigree to the
variant on the sequence, a carrier test and the population. It uses six of the genetics scene
types (DESIGN §96) the way the [genetics cookbook](../../docs/COOKBOOK-GENETICS.md) recommends;
every number on screen is computed by the scenes, and the narration says the same numbers
(`vidgen lint`'s `genetics_*` rules check it).

```
vidgen validate examples/cystic-fibrosis          # the short (9:16) variant too
vidgen lint examples/cystic-fibrosis               # incl. the science_* and genetics_* rules
vidgen storyboard examples/cystic-fibrosis --per-beat 2
vidgen tts examples/cystic-fibrosis                # Kokoro (the kokoro extra): local and free
vidgen render examples/cystic-fibrosis [--variant short]
```

| scene | type | what it shows |
|---|---|---|
| `intro` | `title` | the question: unaffected parents, an affected daughter, a brother planning a family |
| `family` | `pedigree` | the chart in NSGC symbols; AD, AR and XR tested one by one (only autosomal recessive fits); the parents as obligate carriers |
| `punnett` | `cross` | two carriers: 1/4 *AA*, 1/2 *Aa*, 1/4 *aa*; the affected square ruled out for the brother, two of the three left are carriers |
| `risk` | `pedigree` | the genotypes by Bayes' rule on the chart (2/3 *Aa* for the brother), his partner at the population's 1/25, the risk 2/3 × 1/25 × 1/4 = 1/150 |
| `gene` | `karyotype` (ideogram) | *CFTR* at 7q31.2 on both chromosomes 7 |
| `variant` | `mutation` | the real *CFTR* coding sequence (NM_000492.4): c.1521_1523del removes CTT across codons 507–508, the frame is kept, p.(Phe508del) (legacy ΔF508) |
| `test` | `dna_lab` (`ngs`) | the brother's reads over c.1516–1555: about half with a three-base gap — heterozygous, a carrier |
| `population` | `population` (Hardy–Weinberg) | incidence ≈ 1/2500 → q = 1/50 → carriers 2pq = 49/1250 ≈ 1 in 25 |
| `recap` | `process` | pedigree, risk, gene, variant, test |

**Choices.** Cystic fibrosis because every level of the story is textbook-solid: autosomal
recessive inheritance, the classic 2/3 for an unaffected sibling, one common variant that is an
in-frame deletion (a good contrast to the substitutions and frameshifts students usually see), and a
carrier frequency that follows from the incidence. The family is shown twice — the mode analysis,
then (after the Punnett square explains the 2/3) the genotypes and the risk — so each scene stays
readable. The diagnosis is a carrier test of the brother by sequencing: a 3-bp difference is too
small to see on an agarose gel, and NGS shows the heterozygous deletion directly. The incidence
(about 1 in 2,500 in people of European ancestry; commonly cited as 1 in 2,500–3,500, lower in
other populations) is said with "about" and its population; q counts every disease allele of
*CFTR*, not only F508del. The NGS reads are the scene's seeded model, not a patient's data. The
narration speaks of "the condition", "affected" and "carriers" and ends with what the family can
do (testing, counselling).

**References** (shown as markers, listed in the description file): Riordan et al., *Science* 1989
(the *CFTR* cDNA), PMID 2475911; Kerem et al., *Science* 1989 (the genetic analysis that found
F508del), PMID 2570460. Owner: please confirm both identifiers once.

**Checks.** `vidgen validate` and `vidgen lint` clean in 16:9 (with the real narration; 0
findings, three intended `covered_text` findings ignored with a reason — the struck-through
deleted residue); in 9:16 two warnings remain (`min_font` 2.42 % against the 2.5 % warning size
for "1/25 Aa" under the narrow pedigree, `max_words` 43 for the variant card with its notes).
`vidgen readback` word error rate 5.3 %; the beats it flags are the notation (Whisper writes
"fifteen twenty-one" as "one thousand five hundred twenty one", "five oh eight" as "five hundred
eight"). The rendered video (1920×1080, 30 fps, 251.8 s, video and audio the same length):
−16.1 LUFS integrated, true peak −1.8 dBTP, loudness range 3.1 LU; music: the `discovery` bed at
−6 dB, ducked under the voice. No audio is committed.

<!-- topic: biology (also: cell-biology, lecture, research) -->
## Cell biology: lectures and research explainers

Five scene types draw cell biology at university level, stylised but checked (`vidgen guide
scenes` has a snippet of each): `cell` (a cell in µm, zooming tissue → cell → organelle →
complex; with a `gene`, its products' route), `molecule` (molecules in nm, processes as actions;
with a `gene`, each step of expression up close), `pathway` (signalling in compartment bands),
`cell_cycle` (the cycle, mitosis, meiosis) and `metabolism` (glycolysis, the citric acid cycle,
the respiratory chain, the light reactions). The craft in full: `docs/COOKBOOK-CELL-BIOLOGY.md`
in the schu-video-generator repository; a whole example: `examples/gene-to-secreted-protein`.

**Choosing.** Where and how big → `cell`; how one molecule works → `molecule`; how a gene
becomes a protein, step by step → `molecule` with a `gene`, then the same route at the scale of
the cell → `cell` with the `gene`; who activates whom → `pathway`; the cycle and divisions →
`cell_cycle`; energy → `metabolism`. Move between levels on purpose and say so ("Up close",
"At the scale of the cell").

**Accuracy rules.**
- Pick an example that is true at every step you show (a glycoprotein secreted constitutively
  for ER glycosylation and secretion without a trigger; insulin is neither glycosylated nor
  constitutive). Say what is a model: a generated gene is "a short model gene"; a drawing larger
  than real gets `not_to_scale: true`.
- Directions: template read 3′→5′, RNA made 5′→3′, chains N→C, kinesin to +, dynein to −,
  protons out of the matrix, 3 Na⁺ out and 2 K⁺ in per ATP. Places: translation starts in the
  cytosol, N-glycans are added in the ER and remodelled in the Golgi, glycolysis in the cytosol.
- On-screen step captions are claims too: choose the context (`exocytosis` `snares: constitutive`
  in a liver cell, `neuronal` at a synapse; the default names generic v-/t-SNAREs), or
  `notes: false`. Step captions are full in 16:9 and their first clause in 9:16 (`notes:
  auto`; `full`, `short`). Gene symbols the video declares (a gene's `name`, a pathway's gene
  nodes) are italic in the captions overlay, protein names roman.
- An arc you cannot vouch for as direct is `indirect: true`.
- `vidgen validate` refuses the impossible; `vidgen lint`'s `science_*` rules read the narration.

**Naming.** Genes italic, proteins roman, by `species` (human *TP53* / p53, mouse *Trp53* /
TRP53); `<i>…</i>` for a gene in a markup label; `Ca2+`, `Pi`, `F_o` are typeset. Let the voice
say symbols through `pronunciation:` (`SERPINA1: serpin A one`, `STAT3: stat three`, `COPII: cop
two`) and check with `vidgen readback`. `terms:` for three or four concepts.

**References.** `references:` on the scene with an identifier copied from the source (DOI, PMID,
ISBN), `cite:` on the beat; never invent one, leave it out instead. With karaoke captions use
`citations: {show: marker}`.

**Pacing dense content.** One process per beat with 20–35 words for a long step (a gene step lasts
3–15 s and a short beat squeezes it); actions on the word (`at: "@scans"`); Kokoro
`speed: 0.85`; label only what is said (`labels: [granum, stroma]`, or `labels: false` where
processes move things); a long pathway in two scenes; a recap (`process`) at the end.

```yaml
- id: er
  type: molecule
  params:
    title: "Into the endoplasmic reticulum"
    gene: {id: gene, signal_peptide: true, glycosylation: true, start: mrna}
  references:
    - {id: blobel, label: "Blobel & Dobberstein, J. Cell Biol. 1975", doi: "10.1083/jcb.67.3.835"}
  beats:
    - text: "In the cytosol a ribosome scans to the start codon and begins the chain at its N terminus."
      actions: [{translate: gene, codons: 3, at: "@scans"}]
    - text: "Its first residues are a signal peptide. SRP binds it and docks the ribosome on the Sec61 translocon."
      cite: [blobel]
      actions: [{target_er: gene, at: "@SRP"}]
```


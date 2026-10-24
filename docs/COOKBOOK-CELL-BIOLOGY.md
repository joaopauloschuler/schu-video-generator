# Cookbook: cell biology at university and research level

Craft notes for lectures, science channels and researchers explaining their work with vidgen's
cell-biology scene types (DESIGN §95): what to choose, how much to show, how to keep it correct,
and how to pace a script full of terms. The reference for every key is `docs/CONFIG.md`
([`cell`](CONFIG.md#cell), [`molecule`](CONFIG.md#molecule), [`pathway`](CONFIG.md#pathway),
[`cell_cycle`](CONFIG.md#cell_cycle), [`metabolism`](CONFIG.md#metabolism), [references](CONFIG.md#references-and-figure-credits-references-figure_credit-citations));
the author guide (`vidgen guide scenes`) has the short version. The worked example is
[`examples/gene-to-secreted-protein`](../examples/gene-to-secreted-protein/README.md): a protein's
route from its gene to the blood in about three and a half minutes, through all five types. The
[scene gallery](gallery/README.md#cell-biology) shows each type and a showcase of each.

## 1. Choose the scene by the question

| the viewer should understand | scene | the level |
|---|---|---|
| where something is, how big, what is next to it | `cell` | tissue → cell → organelle → complex, in µm, with a scale bar |
| how one molecule works: a pump's cycle, a channel's gate, ATP synthase | `molecule` | nm; a membrane across the view |
| how a gene becomes a protein, step by step | `molecule` with a `gene` | bases and amino acids written out (schematic) |
| the same route across the whole cell | `cell` with a `gene` | the products as markers, the camera following |
| who activates whom: receptors, kinases, second messengers, genes | `pathway` | a graph in compartment bands |
| the cycle, its checkpoints, mitosis or meiosis with counts | `cell_cycle` | a ring, or one dividing cell |
| glycolysis, the citric acid cycle, the respiratory chain, the light reactions | `metabolism` | steps with enzymes, a membrane with complexes |

A good lecture moves between levels on purpose: the place (a `cell`), then the mechanism (a
`molecule` close-up), then back out (the same route in the `cell`), then the control (a
`pathway`). Say when the scale changes ("Up close", "Now the whole route at the scale of the
cell"): a viewer who loses the scale loses the story.

## 2. Accuracy: stylised, never wrong

- **Pick an example that is true at every step you show.** The example video follows
  α1-antitrypsin, not insulin: α1-antitrypsin is N-glycosylated (three glycans) and secreted
  constitutively, so ER glycosylation, calnexin, Golgi glycan remodelling and secretion without a
  trigger are all true of it. Insulin is not glycosylated and is cut from proinsulin by PC1/3,
  PC2 and carboxypeptidase E in regulated secretory granules (releasing C-peptide) — another video.
- **Say what is a model.** The gene close-up uses a short generated gene; the narration says "a
  short model gene stands in for it" and the scene writes *schematic: not to scale*. A drawn size
  larger than real gets `not_to_scale: true` on the `cell` (else `science_scale` reports it).
- **Directions** are where scripts go wrong most: template read 3′→5′, RNA made 5′→3′, a ribosome
  reads mRNA 5′→3′ and the chain grows N→C; kinesin to the plus end, dynein to the minus end;
  protons pumped out of the matrix; the Na⁺/K⁺ pump moves 3 Na⁺ out and 2 K⁺ in per ATP.
- **Places and counts**: translation starts in the cytosol (never in the nucleus), glycosylation
  in the ER lumen, glycolysis in the cytosol; net 2 ATP per glucose from glycolysis, 3 NADH per
  turn of the citric acid cycle. `vidgen validate` refuses the impossible (with the reason) and
  `vidgen lint`'s `science_*` rules flag what reads wrong in the narration.
- **Notes on screen are part of the claim.** The step captions name real molecules (NXF1–NXT1,
  calnexin, the OST). If a caption is too specific for your cell (the exocytosis caption names
  the neuronal SNAREs), turn it off for that action (`notes: false`) and let the narration say it
  more generally ("SNARE proteins on both membranes zip together").
- **Regulation is often indirect.** Draw an arc you cannot vouch for as direct with
  `indirect: true` (dashed): IL-6 → STAT3 → *SERPINA1* acts with other factors.

## 3. Names and notation

- Genes in italics, proteins in roman, by species: human *TP53* / p53, mouse *Trp53* / TRP53;
  `gene:` and `protein:` are checked. In a label written as markup, `<i>SERPINA1</i>`.
- Formulas are typeset from plain text: `Ca2+` → Ca²⁺, `Pi` → Pᵢ, `F_o` → Fₒ.
- Say the symbol, show the symbol: `pronunciation:` gives the voice "serpin A one", "stat three",
  "cop two", "sec sixty-one" while the screen and the subtitles keep *SERPINA1*, STAT3, COPII,
  Sec61. Check with `vidgen readback`: it lists what the speech recogniser heard (it writes
  "alpha-1" back as "alpha minus one" — a transcription habit, not the voice).
- `terms:` keeps one colour per concept across scenes and captions (here *messenger RNA*,
  *signal peptide*, *glycan*); three or four terms are enough.

## 4. Level of detail

- **One process per beat.** A gene step (`transcribe`, `splice`, `target_er`…) lasts as long as
  what it shows (3–15 s); give its beat enough words (20–35 for a long step) or it is squeezed.
- **Name only what the narration names.** A zoomed view labels its parts; restrict them
  (`labels: [granum, stroma]`) or turn them off on scenes whose processes move things
  (`labels: false`: labels are laid out for the view as it was).
- **Big pathways in two scenes**, not smaller text: a 16:9 frame holds about nine ranks. In 9:16
  a node in the membrane row (`in: plasma_membrane` for a kinase bound to its receptor) keeps the
  cytosol band free for the arcs.
- **Keep to the textbook level unless the research is the point**; when it is, cite it (§7).

## 5. Labelling and zooming

- Start wide (`view: tissue` or `cell`), then `zoom_to` on the word that names the target:
  `{zoom_to: nucleus, at: "@nucleus"}`. The scale bar follows; say the scale once.
- A close-up of a process at the membrane: `view: {level: complex, on: <vesicle>, width: "320 nm"}`
  frames the vesicle and the plasma membrane together.
- Labels stay readable in 9:16 because they are screen-sized; the drawing is not. Check
  `vidgen storyboard --variant <short>`: the 9:16 frame is half as wide, so a 16:9 row of
  membrane proteins or a long pathway becomes rows.

## 6. Pacing dense content

- Kokoro at `speed: 0.85` (about 2.3 words per second) leaves time for terms; lint's
  `narration_speed` expects 1.8–3.5 words per second.
- Spread a long mechanism over several beats, one step each, and let the picture lead by a
  fraction: an action at `"@factors"` starts as the word is said.
- Re-say the scale and the place at each scene change, recap at the end in a `process` (the
  route's stops), and keep the whole under four minutes for a single topic.

## 7. Narration–picture timing and references

- `vidgen lint`'s `said_before_shown` compares the words with what appears: "grows" said in beat 1
  while a caption with "growing" appears in beat 2 is reported — reword, or move the action.
- References (`references:` on the scene, `cite:` on the beat) carry a real identifier copied
  from the source (a DOI, PMID or ISBN; formats and check digits are checked offline). **Never
  invent one**: leave a reference out rather than guess. With karaoke captions use
  `citations: {show: marker}` (numbers in a corner): a footer competes with the captions.
  Every reference is listed in `<output>_chapters.txt` for the video description.

## 8. Common mistakes (and the fix)

| mistake | fix |
|---|---|
| ribosomes in the nucleus, translation before export | export first; translation starts in the cytosol |
| "the protein is glycosylated in the Golgi" for N-glycans | added in the ER (OST), trimmed and made complex in the Golgi |
| a channel doing "active transport" | channels are passive; a pump uses ATP, a symporter an ion gradient |
| a vesicle drawn 400 nm with a scale bar | real size (50–200 nm), or `not_to_scale: true` |
| a generated gene presented as the real one | say "model gene"; the close-up writes *schematic* |
| neuronal SNAREs named in a liver cell | `notes: false` on `exocytosis`, generic narration |
| a footer citation under karaoke captions | `citations: {show: marker}` |
| a 9:16 pathway whose arcs cross band names | membrane-bound kinases `in: plasma_membrane`; fewer nodes |
| one beat for transcription, splicing and export | a beat per step, 20–35 words each |

```yaml
# the pattern of the example, in short
- id: liver
  type: cell
  params: {title: "A liver cell", view: tissue}
  beats:
    - text: "Liver cells secrete alpha-1 antitrypsin into the blood."
      actions: [{zoom_to: cell, at: "@liver"}]
    - text: "Its story starts in the nucleus."
      actions: [{zoom_to: nucleus, at: "@nucleus"}]
- id: er
  type: molecule
  params:
    title: "Into the endoplasmic reticulum"
    gene: {id: gene, signal_peptide: true, glycosylation: true, start: mrna}
  beats:
    - text: "In the cytosol a ribosome scans to the start codon and begins the chain at its N terminus."
      actions: [{translate: gene, codons: 3, at: "@scans"}]
    - text: "Its first residues are a signal peptide. SRP binds it and docks the ribosome on the Sec61 translocon."
      actions: [{target_er: gene, at: "@SRP"}]
```

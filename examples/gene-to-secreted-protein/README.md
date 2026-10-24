# From gene to secreted protein

A university-level cell-biology explainer (eight scenes, about 3 min 34 s with Kokoro narration)
that follows one real protein, **α1-antitrypsin** (gene *SERPINA1*), from its gene in a liver
cell's nucleus to the blood. It uses the five scene types of the cell-biology toolkit (DESIGN §95)
the way the [cell-biology cookbook](../../docs/COOKBOOK-CELL-BIOLOGY.md) recommends.

```
vidgen validate examples/gene-to-secreted-protein          # the short (9:16) variant too
vidgen lint examples/gene-to-secreted-protein               # incl. the science_* rules
vidgen storyboard examples/gene-to-secreted-protein --per-beat 2
vidgen tts examples/gene-to-secreted-protein                # Kokoro (the kokoro extra): local and free
vidgen render examples/gene-to-secreted-protein [--variant short]
```

| scene | type | what it shows |
|---|---|---|
| `intro` | `title` | the hook: a secreted protein crosses a membrane only once |
| `liver` | `cell` | tissue → one cell → its nucleus (`zoom_to` on the spoken words) |
| `nucleus` | `molecule` with a `gene` | transcription, capping, splicing, polyadenylation, export through a pore (a short model gene, labelled schematic) |
| `er` | `molecule` with a `gene` (`start: mrna`) | scanning and the start codon, SRP targeting to Sec61, N-glycosylation by the OST, release into the lumen, folding with calnexin |
| `route` | `cell` with a `gene` | the whole route at the scale of the cell: nucleus, pores, rough ER, COPII to the cis-Golgi, the trans-Golgi network, secretion |
| `fusion` | `cell` (complex level) | exocytosis: docking, SNAREs, fusion, release |
| `inflammation` | `pathway` (nodes and edges) | constitutive secretion is set by synthesis: IL-6 → JAK1 → STAT3 (pTyr705) → *SERPINA1* |
| `recap` | `process` | the five stops |

**Choices.** α1-antitrypsin rather than insulin: it is constitutively secreted and N-glycosylated
(three N-glycans), so every step shown (ER glycosylation, calnexin, Golgi glycan remodelling,
secretion without a trigger) is true of it; insulin is not glycosylated and is processed by PC1/3,
PC2 and carboxypeptidase E in regulated secretory granules, which would need other scenes. The
close-ups use a short generated gene: the real gene's sequence would not fit, so the narration
says "a short model gene stands in for it" and the scenes say *schematic: not to scale*.

**References** (shown as markers, listed in the description file): Blobel & Dobberstein, *J. Cell
Biol.* 1975 (the signal hypothesis), DOI 10.1083/jcb.67.3.835; Alberts et al., *Molecular Biology
of the Cell*, 6th ed., ISBN 978-0-8153-4432-2.

**Checks.** `vidgen validate` and `vidgen lint` clean in 16:9 and 9:16 (with the real narration);
`vidgen readback` word error rate 3.7 %, no beat flagged. The rendered video (1920×1080, 30 fps,
214.1 s, video and audio the same length): −16.1 LUFS integrated, true peak −1.8 dBTP, loudness
range 3.6 LU; music: the `discovery` bed at −4 dB, ducked under the voice. No audio is committed.

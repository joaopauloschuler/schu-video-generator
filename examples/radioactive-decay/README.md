# Half-life: how radioactive decay keeps time

A short physics explainer (six scenes, about 2 min 52 s with Kokoro narration) that uses the two
science scene types together (DESIGN §97): `plot` for a simulation and for measured counts with a
fit, `calculation` for the numbers taken from them. Every number on screen is computed by the
scenes, and the narration says the same numbers (`vidgen lint`'s `calc_*` and `plot_*` rules check
it). The craft: [the science-charts cookbook](../../docs/COOKBOOK-SCIENCE-CHARTS.md).

```
vidgen validate examples/radioactive-decay        # the short (9:16) variant too
vidgen lint examples/radioactive-decay [--variant short]   # incl. the calc_* and plot_* rules
vidgen storyboard examples/radioactive-decay --per-beat 2
vidgen tts examples/radioactive-decay              # Kokoro (the kokoro extra): local and free
vidgen render examples/radioactive-decay [--variant short]
python examples/radioactive-decay/make_data.py     # writes assets/*.csv again (the same numbers)
```

| scene | type | what it shows |
|---|---|---|
| `intro` | `title` | random nuclei that keep time: the half-life |
| `nuclei` | `plot` (live) | a Monte Carlo of 1000 barium-137m nuclei growing beside the law exp(−λt), then 20 nuclei whose count falls in uneven steps around it |
| `counts` | `plot` (fit) | counts per 30 s for 15 min with √N (Poisson) error bars on a log axis; the fit A·exp(−λt) with its 95 % confidence band, λ = 0.276 ± 0.004 min⁻¹, χ²/ν = 0.92; normalized residuals; a zoom on the tail |
| `half` | `calculation` | t½ = ln 2/λ = 2.51 min; its uncertainty t½·σ_λ/λ = 0.040 min; the tabulated 2.552 min lies 1 standard error away |
| `carbon` | `calculation` | carbon-14: λ = ln 2/5730 yr = 1.21 × 10⁻⁴ yr⁻¹; a hearth's charcoal at 0.071 Bq/g against 0.226 Bq/g for living carbon: t = ln(A₀/A)/λ = 9.6 × 10³ yr; dates are calibrated |
| `recap` | `bullets` | random nuclei, an exponential sample, a fit gives λ and t½, the same law dates the past |

**Data.** `assets/counts.csv` and `assets/nuclei.csv` are illustrative and say so on screen; they
come from `make_data.py` (standard library, seed 227) and the tabulated half-life of
barium-137m, 2.552 min (NNDC; the isomer is eluted from a caesium-137 generator in teaching labs).
The counts are Poisson draws around the expected number per interval, background neglected; the
nuclei each get an exponentially distributed decay time. The fit weights each count by √N, which
pulls it slightly towards low counts: λ comes out about one standard error above the true
0.2716 min⁻¹, and the scene says the tabulated value lies one standard error away — an honest
uncertainty at work.

**Carbon-14.** Half-life 5730 ± 40 yr (Godwin 1962, the "Cambridge" half-life; conventional
radiocarbon ages use Libby's 5568 yr and are then calibrated); the specific activity of modern
carbon is about 0.226 Bq per gram of carbon (13.56 decays per minute per gram). The hearth's
0.071 Bq/g is an illustrative sample; with two significant figures the age is 9.6 × 10³ years.
The last beat says real dates are calibrated (tree rings, other records), because atmospheric
carbon-14 has varied.

**Choices.** A half-life because it ties the three ideas together: randomness of single events,
an exponential law for many, and a number with an uncertainty taken from a fit. Barium-137m
because a school or university lab measures it in a quarter of an hour. The fit is written
`model: custom` with `expr: "A*exp(-lambda*x)"`, so its box shows λ itself (the built-in
exponential would show k = −λ). Both calculations keep their units in the substitution (on two
lines, or one factor per line, in 9:16). No karaoke captions: the plots need the height (the SRT
file is still written).

**Checks.** `vidgen validate`; `vidgen lint` with the Kokoro narration: 0 findings in 16:9 and in
9:16. The rendered video (1920×1080, 30 fps, 172.2 s, video and audio the same length):
−16.1 LUFS integrated, true peak −1.9 dBTP, loudness range 3.2 LU; music: the `beacon` bed at −8
dB, ducked under the voice. No audio is committed.

<!-- topic: science (also: plots, plot, calculations, calculation, units, fits, physics, data) -->
## Science: plots and worked calculations

Two scene types carry the numbers of a science video, and both **compute** what they show: `plot`
(data and models on scientific axes: error bars, fits with their uncertainties, residuals,
histograms, simulations drawn as they run) and `calculation` (a formula, the values put in with
their units, the result with its significant figures). Every param: `docs/CONFIG.md`; the craft in
full: `docs/COOKBOOK-SCIENCE-CHARTS.md` in the schu-video-generator repository; a whole example:
`examples/radioactive-decay` (simulated nuclei, measured counts with a fit, the half-life worked
out, carbon-14 dating; 16:9 and 9:16).

**Plot or chart.** A comparison of a few categories or a trend for a general audience →
`bar_chart`, `line_chart`, `pie`, `scatter`, `histogram` (big labels, values on the bars).
Measurements and models → `plot`: a log or symlog axis, units in the axis titles, error bars,
a fit, a residual panel, panels sharing a time axis, an orbit at an equal aspect, a model that
grows while you narrate. A function of x for a maths lesson → `function_plot`. Worked numbers →
`calculation`, not text on a card.

**Honest axes.** Units on every physical axis (`unit:` or `time (s)` in the CSV header); a log
axis when the data span decades (decay, counts, frequencies), never to hide a zero; `min` / `max`
only to show context, not to exaggerate a change (a bar-like quantity starts at zero); say
"simulated" or "illustrative" in a `caption` when the data are not a measurement.

**Error bars and fits.** Every error bar says what it is: `error: sd | sem | ci95 | range |
poisson` (`y_err: sqrt` for counts: ± √N); say the same word in the narration. A fit shows its
parameters ± standard errors, R² and χ²/ν (about 1: the errors match the scatter); `band:
confidence` shows where the curve lies, `prediction` where a new point would; `residuals:
normalized` shows (y − fit)/σ under the plot, ticked at ±2; `residuals: background` (a peak fit
with a `background`) the data minus the fitted background with the peak drawn over it (reveal
`residuals:<fit name>` on its own word); `parameters: [mu, sigma]` lists only those in the box. Counts (`y_err: sqrt`, histograms)
are fitted by Poisson maximum likelihood, so the fit is not pulled low. Prefer a model whose parameter is the quantity you
talk about (`model: custom`, `expr: "A*exp(-lambda*x)"` gives λ itself). Say fitted values as the
box writes them, with "give or take" for the error.

**Live models.** `models:` with `kind: ode` (equations as expressions; `method: leapfrog` for
orbits and oscillators, so the energy stays put), `recurrence`, `random_walk`, `poisson` (seeded:
the same numbers every render); a CSV series with `live: true` grows point by point too. Growth
fills its beat; `grow` and `zoom` (`x: [from, to]`) time it to words.

**Units and significant figures.** Write values as you would on paper — `"0.274 min^-1"`, `532
nm`, `"5730 yr"`, `constant: G` — and give each a `meaning` and a `source`. A number with a unit
or a decimal point is measured (its figures count: `1500 m` has 2, `"1.50"` has 3); fractions and
whole numbers without a unit are exact (`2/3 × 1/25 × 1/4 = 1/150`). The result keeps the figures
the inputs allow; `sig:` asks for fewer, never more (`calc_sigfigs`). `convert: km/s` adds the
result in another unit; a later calculation (or another scene, `from_scene`) uses earlier results.
For an uncertainty, compute it as a calculation of its own (σ_t = t·σ_λ/λ). A change of
temperature is written in K (`"10 K"`): two readings in °C are not added, and a difference is
shown in K, not °C.

**Pacing calculations.** One calculation per beat, or one line per action (`substitute`,
`compute` on the word: `at: "@gives"`); say the formula in words, then the result once, with its
unit ("two point five three minutes"). Long formulas break into a chain of short calculations.
Plots: one idea per beat (the data, the error bars, the fit, the residuals), 10–25 words; add an
action every few seconds (`reveal: "errors:<series>"`, `fit`, `annotate`, `zoom`, `highlight` with
`style: flash`) so the picture keeps moving; `label_size: caption` gives a crowded 16:9 figure
room.

**Lint.** `calc_numbers`, `calc_units`, `calc_sigfigs` read numbers in the narration and on screen
against each `calculation`; `plot_units`, `plot_log`, `plot_errors`, `plot_series`,
`plot_truncated`, `plot_conserved`, `plot_fit_claims` check each `plot`. Run `vidgen lint` in 16:9
and 9:16.

```yaml
- id: half
  type: calculation
  params:
    title: "The half-life from the fit"
    symbols:
      - {name: lambda, value: "0.274 min^-1", meaning: decay constant, source: fit}
      - {name: s_lambda, value: "0.0044 min^-1", meaning: its standard error, source: fit, tex: "\\sigma_{\\lambda}"}
    calculations:
      - {name: t_half, expr: "ln(2)/lambda", unit: min, meaning: half-life}
      - {name: s_t, expr: "t_half*s_lambda/lambda", unit: min, meaning: uncertainty of the half-life}
  beats:
    - text: "The half-life is the natural log of two over lambda: two point five three minutes."
    - text: "Its relative uncertainty is the same as lambda's: about zero point zero four minutes."
```


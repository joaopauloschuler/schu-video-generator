# Cookbook: scientific plots and worked calculations

Craft notes for physics, chemistry, biology and engineering videos that show data and work out
numbers with schu-video-generator's science scene types (DESIGN §97): [`plot`](CONFIG.md#plot) (measurements and
models on scientific axes: error bars, fits with their uncertainties, residuals, histograms,
simulations drawn as they run) and [`calculation`](CONFIG.md#calculation) (a formula, the values
put in with their units, the result with its significant figures). The author guide has the short
version (`vidgen guide science`); every key is in `docs/CONFIG.md`. The worked example is
[`examples/radioactive-decay`](../examples/radioactive-decay/README.md): simulated nuclei decaying
at random, counts with √N error bars and an exponential fit, the half-life worked out with its
uncertainty, and carbon-14 dating, in under three minutes. The
[scene gallery](gallery/README.md#science-charts) shows both types.

## 1. Plot, chart or calculation?

| the viewer should understand | scene | why |
|---|---|---|
| a few categories compared, a trend, a share — for a general audience | `bar_chart`, `line_chart`, `pie`, `scatter`, `histogram` | big labels and values on the bars; no units or errors to read |
| measurements: values with uncertainties, a law they follow | `plot` with `y_err` + `error`, `fits` | error bars with a stated meaning, a fit with its parameters ± errors, residuals |
| data across decades (decay, counts, spectra, frequencies) | `plot` with `scale: log` (or `symlog` across zero) | a straight line for an exponential or a power law |
| a model run in front of the viewer (an oscillator, an orbit, predator and prey, random events) | `plot` with `models:` | the series grow while you speak; seeded, the same every render |
| a number worked out from others | `calculation` | the formula, the substitution with units, the result with its figures — not a sentence on a card |
| a function of x in a maths lesson | `function_plot` | maths axes through the origin |

One idea per scene: the data, then the fit, then the number you take from it — the example uses a
`plot` for the counts and the fit, then a `calculation` for the half-life the fit gives.

## 2. Honest axes

- **Units on every physical axis.** `unit:` on the axis, or `name (unit)` in the CSV header
  (`time (min)`, `activity (Bq)`); a count or a share needs none ("counts per 30 s", "share of
  nuclei left"). Powers of ten go into the title (`distance (10⁶ km)`), SI prefixes with
  `format: si` (`time (µs)`).
- **Log axes for decades, never to hide a zero.** Decay, counts and spectra span decades: on a log
  axis an exponential is a straight line, and small values stay visible. Nothing on a log axis
  may reach zero or below — the data, an error bar's lower end, a fit's band, a reference line.
- **Zero for bar-like quantities.** A bar or a histogram starts at zero; `min:` above zero on
  data where size is the message exaggerates a change. Use `min` / `max` to give context (a full
  0–1 share, a fixed time window), not to zoom into noise — `zoom` does that for a moment.
- **Say what is simulated.** A `caption` such as "Simulated measurement: Poisson noise, background
  neglected" whenever the data are not a real measurement; a seed makes them reproducible.

## 3. Error bars: say what they mean

| `error:` | the bar is | use it for |
|---|---|---|
| `sd` | ± one standard deviation | the spread of individual measurements |
| `sem` | ± the standard error of the mean (SD/√n) | how well a mean is known |
| `ci95` | the 95 % confidence interval | a mean or a parameter, with its confidence |
| `range` | minimum to maximum | a few repeats |
| `poisson` | ± √N (`y_err: sqrt`) | counts: decays, events, photons |
| `other` | — | anything else; say it in the caption |

The legend writes the meaning (`counts (± √N)`), and the narration should use the same word:
"each count has a Poisson uncertainty, its square root". SD and SEM differ by √n — mixing them up
is the commonest error-bar mistake.

## 4. Fits and their uncertainties

- **The model whose parameter you talk about.** `model: exponential` fits A·exp(k·x), so its box
  shows k = −0.274 min⁻¹; to talk about a decay constant, fit `model: custom` with `expr:
  "A*exp(-lambda*x)"` and the box shows λ = 0.274 ± 0.004 min⁻¹ directly.
- **Read the box.** Parameters ± standard errors (two significant digits in the error, the value
  to the same place), R², and with error bars χ²/ν: about 1 means the scatter matches the errors;
  much more than 1, the model or the errors are wrong; much less, the errors are too large.
- **Bands.** `band: confidence` is where the true curve lies (narrow with many points);
  `prediction` is where a new point would fall (wider). Say which.
- **Residuals.** `residuals: normalized` shows (y − fit)/σ under the plot: they should scatter
  evenly around zero, about two thirds within ±1 and nearly all within ±2 (the panel is ticked at
  ±2). A curve or a trend in the residuals means the model misses something, whatever R² says.
- **Fits of counts.** Counts with `y_err: sqrt` (and histograms) are fitted by Poisson maximum
  likelihood: the weights come from the fitted curve, not from the counts, because √N weights
  from the data pull a fit towards low counts (by about half a standard error for the example's
  data). Bins with very few counts are still fine; an empty one counts as a 0.
- **R² is unweighted.** It compares the squared residuals with the data's spread whatever the
  weights; with error bars, χ²/ν is the number to read.

## 5. Live models

`models:` turn a plot into a simulation: `kind: ode` (equations as expressions, `method:
leapfrog` for orbits and oscillators so the energy stays bounded; `conserved: [E]` lets lint check
the drift), `recurrence`, `random_walk`, `poisson`, or a Python function registered with
`vidgen.api.register_model`. A CSV series with `live: true` grows point by point too — the example
grows a Monte Carlo of 1000 nuclei beside the exponential law, then 20 nuclei, whose steps show
chance. Growth fills its beat; `grow` (`to:`) and `zoom` (`x: [from, to]`) time it to words. Fix
the axes (`min` / `max`) when several live series share a panel.

## 6. Units and significant figures

- **Write values as on paper**, with units: `"0.274 min^-1"`, `532 nm`, `"5730 yr"`, `"0.226
  Bq/g"`, `constant: G` (CODATA / IAU values with their source). Give each symbol a `meaning` and a
  `source`: they are the table under the work, and lint uses them.
- **Figures come from how a value is written.** A decimal or a value with a unit is measured: `532
  nm` has 3 figures, `1500 m` has 2, `"1.50"` has 3 (write it as a string to keep the zero).
  Fractions and whole numbers without a unit are exact: 2/3 × 1/25 × 1/4 = 1/150. The result
  keeps the fewest figures of a product's inputs, the coarsest decimal place of a sum; `sig:` may
  ask for fewer, not more.
- **Convert at the end.** `unit: min` for the result, `convert: [s, h]` for extra lines; a
  substituted value keeps its unit on screen (on two lines, or one factor per line, when it is
  long) and falls back to SI numbers only when units would make the line unreadably small.
- **Uncertainties are calculations too.** The engine carries significant figures, not ±; work an
  uncertainty out as its own calculation (σ_t = t·σ_λ/λ) and compare with a reference value as a
  number of standard errors ((t_tab − t)/σ_t).

## 7. Pacing a calculation

- One calculation per beat, or one line per action: `substitute` on the word that names the
  values, `compute` on "gives" or the result's first word, `convert` on the new unit.
- Say the formula in words ("the natural log of two over lambda"), then the result once, with its
  unit and the figures the screen shows ("two point five three minutes"); "about" for a rounding.
- Chains: a long formula is two short calculations (the decay constant, then the age); a later one
  uses the earlier result by name, another scene by `from_scene`.
- Plots: one idea per beat (the data, the error bars, the fit, the residuals), 10–25 words, and
  something that moves every few seconds (`reveal: "errors:<series>"`, `fit`, `annotate`,
  `zoom`, `highlight` with `style: flash`). In a crowded 16:9 figure (a fit box, a legend and a
  residual panel) `label_size: caption` gives the plots room.

## 8. Common mistakes and the rule that catches each

| mistake | rule |
|---|---|
| a number said or shown that is not what the `calculation` computes ("thirty-five kilometres per second" for 29.8 km/s) | `calc_numbers` |
| the wrong unit or prefix for a value ("30 metres per second" for 29.8 km/s; "a speed of 30 kilometres") | `calc_units` |
| more figures than the inputs allow ("29.7847 km/s"), or a `sig` beyond them | `calc_sigfigs` (info) |
| an axis of a physical quantity without its unit; a fit with units on a unitless x | `plot_units` |
| error bars, a fit, its band or a line at or below zero on a log axis | `plot_log` |
| error bars without `error:`, or narrated as another kind ("standard errors" for √N bars) | `plot_errors` |
| several series and no legend or labels; placeholder names | `plot_series` |
| bars not starting at zero (a broken y axis under a histogram, a `bar_chart` baseline) | `plot_truncated` (info) |
| a `conserved` quantity drifting in a model (RK4 on an orbit) | `plot_conserved` |
| a fitted value said otherwise ("a half-life of twelve days" for 8.0 ± 0.1 d) | `plot_fit_claims` |

Run `vidgen lint` on the preview in 16:9 and 9:16 before the final render; the rules read the
config and the narration (in words too), and each message gives the fix.

Orbits have their own rules, on the same number reader: an [`orbit`](CONFIG.md#orbit) scene's
periods, speeds, Δv, transfer times, distances and event dates are checked against what the scene
computes (`orbit_period`, `orbit_speed`, `orbit_dv`, `orbit_transfer`, `orbit_distance`,
`orbit_date`), "to scale" against what is drawn to scale (`orbit_scale`), an n-body run's energy
drift like `plot_conserved` (`orbit_conserved`), and a periapsis in the air (`orbit_crash`). A
`calculation` that takes its Δv `from_scene` an orbit scene is checked by the `calc_*` rules.

## 9. The pattern

```yaml
- id: counts
  type: plot
  params:
    title: "Counting decays"
    caption: "Simulated measurement: Poisson noise"
    x: {label: time, unit: min}
    y: {label: counts per 30 s, scale: log}
    series:
      - {name: counts, style: points, y_err: sqrt, error: poisson,
         x: [0, 1, 2, 3, 4, 5, 6, 7, 8], y: [713, 511, 391, 317, 253, 193, 136, 96, 82]}
    fits:
      - {name: decay, series: counts, model: custom, expr: "A*exp(-lambda*x)",
         params: {A: 700, lambda: {value: 0.3, unit: min⁻¹}}, band: confidence, residuals: normalized}
  beats:
    - text: "A detector counts the decays in every thirty seconds; each count has a Poisson uncertainty."
    - text: "An exponential fits them, and gives the decay constant."
      actions: [{fit: "fit:decay", at: "@exponential"}]
- id: half
  type: calculation
  params:
    title: "The half-life"
    symbols:
      - {name: lambda, value: "0.274 min^-1", meaning: decay constant, source: fit}
    calculations:
      - {name: t_half, expr: "ln(2)/lambda", unit: min, convert: s, meaning: half-life}
  beats:
    - text: "The half-life is the natural log of two over lambda: two point five three minutes."
```

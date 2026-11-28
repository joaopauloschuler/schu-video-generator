<!-- topic: examples (also: good-bad, before-after, patterns, antipatterns) -->
## Good vs bad: before and after

**1. A wall of text → a progressive grid.** Bad: six long items appear together while the voice
reads the first one; 40 words on screen.

```yaml
- id: features_bad
  type: bullets
  params:
    heading: "Key features of the platform you should know about"
    reveal: all
    items:
      - "Our compute layer scales automatically with your workload"
      - "Storage is replicated across three regions for durability"
      - "The network is software-defined and fully encrypted"
      - "Security follows a zero-trust model everywhere"
  beats:
    - text: "The platform has many features: compute that scales automatically, storage replicated across three regions, a software-defined encrypted network, and zero-trust security everywhere."
```

Good: one or two labels per beat, icons carry the category, the voice adds the detail.

```yaml
- id: features_good
  type: icon_grid
  params:
    heading: "What you get"
    icon_color: palette
    items:
      - {icon: cpu, label: "Compute", sublabel: "scales itself"}
      - {icon: database, label: "Storage", sublabel: "3 regions"}
      - {icon: network, label: "Network", sublabel: "encrypted"}
      - {icon: shield-check, label: "Security", sublabel: "zero trust"}
  beats:
    - text: "Compute grows and shrinks with your workload."
    - text: "Every file is stored in three regions."
    - text: "All traffic is encrypted."
    - text: "And nothing is trusted by default."
```

**2. Reading the slide → complementing it.** Bad: the voice says exactly what is written.

```yaml
- id: claim_bad
  type: text_card
  params: {text: "Smaller models can be just as accurate"}
  beats: [{text: "Smaller models can be just as accurate."}]
```

Good: the screen holds the claim, the voice gives the reason and the stakes.

```yaml
- id: claim_good
  type: text_card
  params: {text: "Smaller ≠ worse"}
  beats:
    - text: "We assumed size bought accuracy."
    - text: "On our benchmark, a model half the size scored the same."
      actions: [{highlight: text, style: underline, at: 0.4}]
```

**3. A raw number → a `stat` with a comparison.** Bad: a sentence of digits.

```yaml
- id: latency_bad
  type: text_card
  params: {text: "Median latency went from 18 ms to 12.5 ms after the change"}
  beats: [{text: "Median latency went from eighteen milliseconds to twelve and a half milliseconds after the change."}]
```

Good: one big number that counts, the change coloured by whether it is good.

```yaml
- id: latency_good
  type: stat
  params:
    value: 12.5
    unit: "ms"
    label: "median latency"
    comparison: {value: 18, kind: before, better: lower, delta: percent}
  beats:
    - text: "Requests now take twelve and a half milliseconds."
    - text: "That is almost a third faster than before."
```

**4. An unexplained chart → a chart that points.** Bad: bars appear, the voice talks about
something the viewer has to find.

```yaml
- id: costs_bad
  type: bar_chart
  params: {labels: ["Jan", "Feb", "Mar", "Apr", "May", "Jun"], values: [12, 13, 12, 31, 14, 13]}
  beats: [{text: "As you can see, something unusual happened in one of these months, which we investigated."}]
```

Good: a title that says what the chart is, the outlier highlighted while it is named, a callout
with the reason, and the source in the caption.

```yaml
- id: costs_good
  type: bar_chart
  params:
    title: "Cloud cost per month (k$)"
    labels: ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    values: [12, 13, 12, 31, 14, 13]
    caption: "Source: billing export, 2025"
  beats:
    - text: "Our cloud bill is usually flat."
    - text: "Except in April, when it more than doubled."
      actions:
        - {highlight: "bar:Apr"}
        - {callout: "bar:Apr", kind: arrow, label: "Test cluster left on", at: 0.5}
    - text: "One forgotten cluster cost nineteen thousand dollars."
```

**5. A long beat → short beats with their own reveals.** Bad: 45 words over one picture: 18 s of
the same frame (lint `dead_air`).

```yaml
- id: pipeline_bad
  type: process
  params: {stages: ["Write", "Check", "Render", "Publish"], reveal: all}
  beats:
    - text: "You write the config, then you check it with validate and storyboard and lint until everything is clean, then you render the final video with the real voice, and finally you publish it together with its chapters, thumbnail and subtitles so people can find it."
```

Good: one stage per beat, the token moves while each is named.

```yaml
- id: pipeline_good
  type: process
  params:
    heading: "From idea to video"
    stages: [{label: "Write", icon: pencil}, {label: "Check", icon: search}, {label: "Render", icon: play}, {label: "Publish", icon: megaphone}]
  beats:
    - text: "You write one config file."
    - text: "Storyboard and lint check it."
    - text: "Then the real voice and the final render."
    - text: "And it ships with chapters and subtitles."
```

**6. A slow opening → a hook.** Bad: 6 s of logo and title before anything is said.

```yaml
- id: opening_bad
  type: title
  params: {title: "Quarterly Infrastructure Review", subtitle: "Platform Team", kicker: "Q3 2025"}
  beats: [{text: "Welcome to the quarterly infrastructure review by the platform team. In this video we will look at a number of topics."}]
```

Good: the result first, then the context.

```yaml
- id: opening_good
  type: stat
  params: {value: 41, suffix: "%", label: "lower cloud bill", context: "Q3 vs Q2 2025"}
  beats:
    - text: "We cut our cloud bill by forty-one percent."
    - text: "Here is how, in three changes."
```


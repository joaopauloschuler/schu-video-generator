# Third-party notices

vidgen itself is MIT-licensed (see `LICENSE`). It bundles the following fonts as package data in
`src/vidgen/data/fonts/`, each under the **SIL Open Font License 1.1**; the full licence text is
in the `OFL.txt` next to each family's files. The fonts are distributed unmodified (Inter and
JetBrains Mono NL were decompressed from WOFF2 to TTF, a lossless format conversion). They may be
used, embedded in rendered videos and redistributed with vidgen under the OFL's terms; they may
not be sold on their own.

| Family (Pango name) | Files | Version | Copyright | Obtained from |
|---|---|---|---|---|
| Inter (`Inter`) | `Inter/Inter-Regular.ttf`, `Inter-Bold.ttf`, `Inter-Italic.ttf` (~0.98 MB) | 4.001 | © 2016 The Inter Project Authors (https://github.com/rsms/inter) | npm package `inter-ui` 4.1.1 (`web/*.woff2`) |
| Source Serif 4 (`Source Serif 4`) | `SourceSerif4/SourceSerif4-Regular.ttf`, `-Bold.ttf`, `-It.ttf` (~0.72 MB) | 4.005 | © 2014–2023 Adobe (http://www.adobe.com/), with Reserved Font Name ‘Source’ | npm package `source-serif` 4.5.1 (Adobe's release, `TTF/`) |
| JetBrains Mono NL (`JetBrains Mono NL`) | `JetBrainsMono/JetBrainsMonoNL-Regular.ttf`, `-Bold.ttf` (~0.29 MB) | 2.242 | © 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono) | npm package `jetbrains-mono` 1.0.6 (`fonts/webfonts/*.woff2`); licence text from `@fontsource/jetbrains-mono` 5.3.0 |

JetBrains Mono NL is the variant of JetBrains Mono without coding ligatures, so code listings
show exactly the characters that were typed.

## Icons

vidgen bundles icons from **Lucide** (https://lucide.dev) as package data in
`src/vidgen/data/icons/lucide/` (the SVG files unmodified, each keeps its `@license` comment),
obtained from the npm package `lucide-static` 1.52.0. Lucide is under the **ISC License**,
© Lucide Icons and Contributors; the icons Lucide derived from Feather are also under the
**MIT License**, © 2013-present Cole Bemis. Both licence texts, and the list of the
Feather-derived icons, are in `src/vidgen/data/icons/lucide/LICENSE`. The icon names, categories
and search tags are in `src/vidgen/data/icons/manifest.json` (tags from Lucide's `tags.json`,
plus a few added by vidgen); `tools/vendor_icons.py` re-creates the folder from
`tools/icon_set.json`.

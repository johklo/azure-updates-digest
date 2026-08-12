# Design — Azure Product Updates Digest

A locked design system for this site. Every page redesign reads this file before
emitting code. Do not regenerate per page — extend or amend this file when the
system needs to grow.

## Genre

editorial

A broadsheet for release communications: the content is a dated, categorised index
of announcements, so the page behaves like newsprint rather than like a product
marketing site. Hairlines instead of card borders, roman serif display, machine
metadata set in mono.

## Macrostructure family

- **Browse pages** (`index.html`, `archive.html`, `categories.html`): Index-First.
  The page *is* the list. Filters and the summary table qualify the index; they do
  not become a hero. Section order is fixed: stats → filters → deck → summary table →
  category panels.
- **Presentation surface** (the in-page deck and its exports): Split Studio.
  One update per screen, headline and standfirst on the left half, numbered key
  points on the right half, gutter only, no divider rule.
- **Content pages** (`digests/*.html`): Long Document. The digest source is shown
  verbatim in a mono block; typography only.

## Theme

Custom — vibe: *"broadsheet, azure ink, hairline rules"*. Anchor hue 252 (cool).
The brand's Azure blue is preserved as the accent but deepened for print weight.

- `--color-paper`         oklch(97.5% 0.006 252)
- `--color-paper-2`       oklch(94.6% 0.009 252)
- `--color-paper-3`       oklch(91.8% 0.011 252)
- `--color-rule`          oklch(87%   0.014 252)
- `--color-rule-strong`   oklch(72%   0.022 252) — decorative hairlines
- `--color-control`       oklch(60%   0.028 252) — interactive boundaries, clears 3:1 on every paper tint
- `--color-muted`         oklch(52%   0.024 252)
- `--color-ink-2`         oklch(38%   0.026 252)
- `--color-ink`           oklch(23%   0.028 252)
- `--color-accent`        oklch(50%   0.152 252)
- `--color-focus`         oklch(50%   0.152 252)

Dark band (deck cover only):

- `--color-cover`         oklch(26%   0.055 252)
- `--color-cover-ink`     oklch(95%   0.012 252)
- `--color-cover-muted`   oklch(74%   0.03  252)

Release stage is *data*, not decoration. Each stage owns one hue and is drawn as a
square swatch plus a small-caps label — never a filled oval:

- `--color-stage-ga`  oklch(45% 0.12 150) · `--color-stage-pv` oklch(50% 0.11 70)
- `--color-stage-pp`  oklch(45% 0.15 300) · `--color-stage-rt` oklch(48% 0.16 25)
- `--color-stage-dv`  oklch(46% 0.09 235)

## Typography

Two families plus one outlier. **Korean is a script fallback inside the same two
role stacks, not additional families** — Latin resolves to Newsreader / IBM Plex
Sans, Hangul falls through to Noto Serif KR / Noto Sans KR.

- Display: Newsreader, weight 500, style normal
- Body:    IBM Plex Sans, weight 400
- Mono:    JetBrains Mono, weight 400–500
- Display tracking: −0.015em to −0.025em; Korean display relaxes toward −0.005em
- Type scale anchor: `--text-display` = `clamp(1.9rem, 2.6vw + 1rem, 3rem)`

**The outlier carries exactly one role: machine metadata.** Nav, kickers, meta
lines, folios, counts, table headers, numerals, colophon. Never running prose —
a descriptive sentence belongs to the body face even when it sits beside metadata.

## Spacing

4-point named scale. The values are in `tokens.css`. Pages must use named tokens
(`var(--space-md)`), never raw values. The only permitted inline dimension is a
data-driven one (the summary table's proportional bar width).

## Motion

- Easing: `cubic-bezier(0.16, 1, 0.3, 1)` named `--ease-out`
- Durations: `--dur-short` 220ms, `--dur-mid` 380ms
- Reveal pattern: none on browse pages. The deck gets one quiet entrance per slide.
- Only `transform` and `opacity` animate. The progress bar uses `scaleX`, never `width`.
- Reduced-motion fallback: opacity only, ≤ 150 ms; all transitions collapse to 1 ms.

## Microinteractions stance

- Silent success. No toasts anywhere.
- Hover and focus are separate: hover restyles, `:focus-visible` draws a 2 px accent
  ring at `outline-offset` 2–4 px. **The ring never animates in.**
- Links underline by drawing an inset hairline, not by `text-decoration`.
- Disclosure uses `+` / `−`, not a rotating chevron.

## CTA voice

There is no marketing CTA on this site. Actions are typographic:

- Primary action: square outlined control, hairline border, accent on hover.
  Labels are plain verbs — `Reset filters`, `Expand all`, `PowerPoint`.
- Selected state inverts to ink fill rather than brand fill, except release-stage
  chips which invert to their own semantic hue so the filter stays readable as data.

## Per-page allowances

- Browse pages: typography only. No enrichment, no illustration, no imagery.
- The deck: one entrance animation and the progress bar. Nothing else.
- Content pages: typography only.

## What pages MUST share

- The masthead wordmark and its serif setting.
- The accent colour and its placement (≤ 3 % per viewport; rules, marks, links).
- The display + body + outlier faces and the outlier's single role.
- Square geometry — no border radius anywhere.
- Hairline rules as the divider language; no card borders with radius, no shadows.
- The stage-colour mapping.

## What pages MAY differ on

- Macrostructure within the page-type family.
- Panel density (the deck is generous; the browse index is dense).
- Footer archetype: browse pages use Ft4 dense colophon, the deck uses Ft2 inline rule.

## Chrome archetypes

- Nav: **N6 newspaper masthead** — large serif wordmark, description line, rule,
  then a thin mono link row. The deck's running head is the same voice at slide scale.
- Footer: **Ft4 dense colophon** — a labelled block naming generation time, source
  and the faces used.

## Exports

See [`tokens.css`](tokens.css) for the canonical CSS custom-property export.
The standalone HTML deck export in `scripts/assets/app.js` intentionally carries its
own shortened token names, because it ships as a single self-contained document.

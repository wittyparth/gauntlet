---
name: Gauntlet Landing (Figure Plate)
description: A results paper rendered as a scientific figure plate in a viridis colormap; the public marketing surface of Gauntlet.
colors:
  plate: "#1a1230"
  plate-deep: "#120b24"
  bone-ink: "#ece4d3"
  ink-dim: "#b9aec6"
  ramp-indigo: "#7a6ee0"
  ramp-teal: "#2fb5a8"
  ramp-green: "#5ec962"
  ramp-yellow: "#fde725"
  yellow-hover: "#fff27a"
  fail: "#ff6a4a"
typography:
  display:
    fontFamily: "Host Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(2.6rem, 4.6vw, 4.6rem)"
    fontWeight: 680
    lineHeight: 0.98
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Host Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(2rem, 3.8vw, 3.4rem)"
    fontWeight: 640
    lineHeight: 1.02
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Host Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.6rem"
    fontWeight: 640
    lineHeight: 1.02
    letterSpacing: "-0.03em"
  body:
    fontFamily: "Host Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.6
  readout:
    fontFamily: "Fragment Mono, ui-monospace, monospace"
    fontSize: "clamp(2.2rem, 3.4vw, 3rem)"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "-0.04em"
  label:
    fontFamily: "Fragment Mono, ui-monospace, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    letterSpacing: "0.01em"
rounded:
  none: "0px"
spacing:
  gutter: "clamp(1.25rem, 4vw, 3.5rem)"
  column-gap: "clamp(2rem, 4vw, 4.5rem)"
  section: "clamp(3.5rem, 8vw, 7rem)"
  panel-gap: "clamp(1.5rem, 3vw, 3rem)"
components:
  button-primary:
    backgroundColor: "{colors.ramp-yellow}"
    textColor: "{colors.plate-deep}"
    rounded: "{rounded.none}"
    padding: "0.95rem 1.4rem 0.95rem 1.1rem"
    typography: "{typography.body}"
  button-primary-hover:
    backgroundColor: "{colors.yellow-hover}"
  link-secondary:
    textColor: "{colors.bone-ink}"
  fig-frame:
    backgroundColor: "{colors.plate-deep}"
    rounded: "{rounded.none}"
  term-plate:
    backgroundColor: "{colors.plate-deep}"
    textColor: "{colors.bone-ink}"
    typography: "{typography.label}"
    padding: "1rem 3.4rem 1rem 1rem"
---

# Design System: Gauntlet Landing (Figure Plate)

## Scope

This system governs the public marketing surface only (`src/app/landing/`, route `/landing`). It is scoped under the `.lp` class and its own fonts (loaded in the landing layout). The authenticated console under `src/app/(app)` keeps its own incumbent look and is NOT described here and must not inherit this world. New marketing pages may use it; console screens may not.

## Overview

**Creative North Star: "The Figure Plate"**

The page is a results paper whose figures are live. One deep plum plate owns every region; data and emphasis run along a viridis colormap from indigo through teal and green to a sulphur-yellow hot end. Prose is bone ink. Failures are the only off-ramp hue. Structure comes from figure numbering (Fig. 1, Fig. 2a-c, Fig. 3, Table 1), hairline axis rules, tick marks and whitespace. It refuses the category default of a dark-neon shield hero, feature-card grid and logo strip.

Density is editorial and calm: wide gutters, large display type against small mono annotation. Honesty is part of the look: unflattering numbers are drawn in the same plate as flattering ones, with the fail hue marking them.

**Key Characteristics:**
- One plum plate, no cream paper, no glow, no glass, no decorative gradient.
- Viridis ramp carries meaning (hot yellow = the number that matters, green/teal = healthy data, indigo = the cold end).
- Grotesk for prose and headings, mono for every figure label, axis, numeral and code.
- Identical small-multiple panels are the page's ruler.
- Hairline rules and ticks instead of boxes and cards.

## Colors

A single committed plate colour with a perceptual ramp as the only accent system.

### Primary
- **Sulphur Yellow** (ramp-yellow): the hot end of the ramp. Primary button fill, the headline numeral of a figure, focus ring, text selection, figure-number emphasis, link-hover underline. Rare per screen; it marks the one thing to read.

### Secondary
- **Ramp Green** (ramp-green): healthy data readouts, positive annotations, "good" table cells, fact numerals.
- **Ramp Teal** (ramp-teal): hit marks in strips, inline code on the surfaces list.
- **Ramp Indigo** (ramp-indigo): the cold end of the ramp; scrollbar and the last steps of the Fig. 3 ramp.

### Tertiary
- **Fail Coral** (fail): the only off-ramp hue. Failures, misses and bad table cells. Never decorative.

### Neutral
- **Plum Plate** (plate): page background.
- **Deep Plate** (plate-deep): recessed regions only: film frame, terminal plate, the tinted band.
- **Bone Ink** (bone-ink): prose and primary text; also the base of rules at 28% (`--rule`) and 12% (`--rule-faint`) opacity.
- **Dim Ink** (ink-dim): captions, axis text, secondary prose, labels.

The Fig. 3 interval series steps through an eight-stop viridis ramp (`#fde725` to `#7a6ee0`, defined in `reliability.tsx`); it is data encoding, not additional palette.

### Named Rules
**The Ramp Is Data Rule.** Ramp hues encode value or emphasis. A ramp colour never appears as pure decoration, and no colour outside the ramp, bone and fail appears at all.

**The Fail Is Off-Ramp Rule.** Only failures use the coral. Nothing good is ever coral and nothing bad is ever on-ramp.

## Typography

**Display Font:** Host Grotesk (with ui-sans-serif, system-ui)
**Body Font:** Host Grotesk
**Label/Mono Font:** Fragment Mono (with ui-monospace), tabular numerals

**Character:** A grotesk with plot-label character for argument, a light mono for everything measured. Headlines are tightly tracked and heavy (640-680); mono is regular weight and never tracked.

### Hierarchy
- **Display** (680, clamp 2.6-4.6rem, 0.98, -0.04em): the hero title only. One word may be tinted sulphur yellow, upright.
- **Headline** (640, clamp 2-3.4rem, 1.02, -0.03em): section titles; an XL variant (clamp 2.4-5.2rem, -0.045em) for the closing band.
- **Title** (640, 1.6rem): panel titles in the small multiples.
- **Body** (400, 1.0625rem, 1.6): prose capped near 62ch; abstract 44ch; captions 70ch in dim ink.
- **Readout** (mono, clamp 2.2-3rem, -0.04em): the big number in a panel or Fig. 3, yellow (or coral for failure).
- **Label** (mono, 0.8125rem, 0.01em): figure labels, table headers, axis ticks (0.6875rem), SVG annotations (9.5-11px).

### Named Rules
**The Numerals Are Mono Rule.** Any measured value, axis, figure number or code is set in Fragment Mono with tabular figures. Prose numbers stay grotesk.

## Layout

A 92rem max-width container with a fluid gutter (clamp 1.25-3.5rem). The recurring spine is a 2fr/3fr two-column split (hero, section heads, reliability, run, close) with a fluid gap (clamp 2-4.5rem). Sections are separated by a single faint top rule and generous vertical rhythm (clamp 3.5-7rem). Fig. 2 is three identical equal columns (panels). Fig. 3 is a tall sticky scroll stage (320vh, 280vh on small screens) whose bounds narrow with scroll position. Table 1 scrolls horizontally on narrow screens and collapses to labelled stacked rows under 40rem. At 62rem every grid collapses to one column. The film expands in place to full width when played.

## Elevation & Depth

Flat. Depth is tonal: Deep Plate recesses against Plum Plate for frames, terminal and one band. The only shadow is a 1px hairline ring (`box-shadow: 0 0 0 1px` in dim ink) that draws the Fig. 1 frame; there are no offset or blurred shadows. Interactive lift is a 2px translateY on the primary button.

### Named Rules
**The Flat Plate Rule.** Hierarchy comes from tone, rules and whitespace. No blur, glow, glass or offset shadow.

## Shapes

Square. Radius is 0 everywhere; frames, buttons, terminal and tables are rectangles. Geometry is plotted: hairline axis lines with major and minor ticks on the Fig. 1 frame and terminal gutter, step-function interval bars, thin strip glyphs (6x14px blocks) in tables.

## Components

### Buttons
- **Shape:** square (0px).
- **Primary:** sulphur-yellow fill, deep-plate text, grotesk 600 at 1.0625rem, padding 0.95rem 1.4rem 0.95rem 1.1rem, with a leading inline-SVG play mark.
- **Hover / Focus:** fill lightens to a pale yellow, lifts 2px, returns on active; focus is a 2px yellow outline offset 3px. Motion is removed under reduced-motion.
- **Secondary:** plain bone-ink link at weight 560, underlined with a faint rule that turns yellow on hover.

### Cards / Containers
There are none by design. Grouping is by whitespace and rules. Recessed regions (film frame, terminal plate) use Deep Plate with a hairline ring or top and bottom rules, never a rounded box.

### Navigation
Masthead: wordmark left as a figure label (bold grotesk with a mono sub-label hidden on mobile), nav right at 0.9375rem, underline-free, with a yellow bottom border on hover; a single hairline under the bar.

### Fig. 1 film frame
16:9 Deep Plate frame with a 1px ring, axis ticks on the left and bottom edges, the poster dimmed (brightness 0.72) inset with a clear play button at bottom-left, and a caption beneath. Playing removes the dimming and fills the frame.

### Small-multiple panel
Title, a large mono readout, a plotted SVG with mono annotations (green, or coral for failure), and a two-column dt/dd list. Three identical panels (find, fix, prove) repeat as the ruler of the page.

### Table 1
Hairline header rule in dim ink, faint row rules, grotesk row headers with small dim sub-text, mono numerals coloured good (green), mid (yellow) or bad (coral).

### Terminal plate
Deep Plate with top and bottom dim-ink rules, a tick gutter on the left, mono 0.8125rem on a 1.75 line height, a blinking yellow caret (steps, disabled under reduced-motion) and a square outlined copy button.

## Do's and Don'ts

### Do:
- **Do** number every figure and caption it in the form "Fig. N." with mono labels.
- **Do** draw failures in Fail Coral in the same plate as successes.
- **Do** group with whitespace and 1px rules at 12% or 28% bone opacity.
- **Do** keep radius at 0 and shadows to the 1px hairline ring.
- **Do** keep sulphur yellow to the single most important element in view.
- **Do** honour `prefers-reduced-motion` for every transition and animation.

### Don't:
- **Don't** use cards, boxes with fill and radius, glassmorphism, glow, or gradient decoration on this surface.
- **Don't** use cream paper, italic serif display, or neon.
- **Don't** introduce a hue outside the viridis ramp, bone and fail coral.
- **Don't** apply this world to the console under `src/app/(app)`.
- **Don't** use invented customers, logos, testimonials or pricing as proof.

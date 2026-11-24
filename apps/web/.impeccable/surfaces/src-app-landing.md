---
version: 1
slug: "src-app-landing"
primary_target: "src/app/landing"
related_targets: []
---

# Surface: public landing page (`/landing`, route `src/app/landing/`)

Mode: Persuade. Audience: teams shipping LLM agents, and portfolio viewers (engineers, founders, hiring managers). Primary action: watch the 2:49 demo film (playable in place, first viewport). Secondary: open the live console (`/login`), the public arena (`/arena`), benchmarks (`/benchmarks`), self-host docs. Proof: real demo run (finding, policy block, verify 0/5), live benchmark numbers including unflattering ones, ~$0.11 demo spend, $0.24 full 297-attack run, ~2190 tests. Constraints: Animate UI components (repo already has `src/components/animate-ui`); no invented customers, logos, testimonials, pricing; "open source" claim allowed by user but LICENSE not yet added.

## Direction contract

THESIS: Gauntlet doesn't claim, it publishes. The landing page is a results paper whose figures are live: abstract as hero, the film as Fig. 1, find/fix/prove as Fig. 2a-c, reliability as Fig. 3 with confidence intervals. Refuses the category default: dark-neon shield hero, feature-card grid, logo strip.

OWN-WORLD: a scientific figure plate rendered in a perceptual colormap. Committed colour: deep viridis-plum plate (#1a1230-ish) owns every region; data and emphasis run along the viridis ramp (indigo, teal, green, sulphur yellow at the hot end); failures are the only off-ramp hue. Bone ink for prose. No cream paper, no italic serif display, no neon glow. Type: one grotesk display with plot-label character (not Inter/DM/Space/Plex/Instrument), one mono for figures, axes and numerals (not Space/IBM Plex/JetBrains). Structure by figure numbering, axis rules, tick marks and whitespace; no cards, no boxes, no gradients-as-decoration, no glass. Identical small-multiple panels repeat as the ruler of the page.

STORY: In one viewport the visitor learns what Gauntlet is, sees it prove a fix, and can press play. Scrolling, they see the loop (find, fix, prove) as three identical panels drawn from the real demo run, then reliability with error bars, then honest benchmarks as Table 1, then how to run it (one VPS, cheap models, MCP/CLI/CI), then a close: watch, try the arena, open the console.

FIRST VIEWPORT: thin masthead (wordmark left as a figure label, nav right: Film, Method, Results, Arena, Console). Left two-fifths: title "Test, attack, and guard your AI agents." at display scale, a 3-line abstract, primary button "Watch the film (2:49)" and secondary "Try the arena". Right three-fifths: Fig. 1, the film poster in a plotted frame with axis ticks on its edges and a caption underneath ("Fig. 1. One real run, end to end. Live model spend: $0.11."). Pressing play expands the film in place.

FORM: The Paper (results paper with live figures), position 4 of 7 on the ordered list; seed:8fa090e96186ab7a. Raises: identical small multiples as the page's ruler (from the VU-meter bridge); no boxes or dividers, grouping by whitespace and axis rules only (from the cathode gauze). Signature interaction: Fig. 3 confidence-interval bars that narrow as the visitor scrolls through repetitions k=1..8 (pass^k), with the numbers updating in mono.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

# Variance Analysis Agent: interface design

Status: Phase 1. The tokens below are in `src/variance_agent/static/chat.css`; `tests/test_interface_design.py` holds what a test can hold. Each decision names the alternative it rejected.

## Direction

- **Subject.** A month-end variance review: an FP&A analyst (the intake rules call her Maya) brings a budget-versus-actual file and needs to see which lines moved, whether each move helped or hurt, and why.
- **Reference class.** A quiet financial workbench: the restraint of Linear, Stripe's dashboard and a well-set annual report. The product is mostly a table, so the table gets the care.
- **Page pattern.** One column of conversation, 960 px wide at most, centred. Prose is held to 72 characters a line; a reply that carries a table or a result view takes the full column. Your messages sit on the right in a tinted block; the tool's replies are plain text on the page, with no bubble. A result renders as a document view (Phase 4), not as a message.
- **One job per screen.**
  - First screen: upload a file.
  - Each intake step: answer one question.
  - Intake summary: confirm how the file was read.
  - Results: read the headline figures, then the material variances.
  - Drill-down: see what drove one line.
  - Error: understand what is wrong with the file and fix it.

## Tokens

### Colour

A warm-neutral grey ramp of nine steps per theme (0 is the raised surface, 8 is body text), one ink-blue accent, and three meaning colours. Colour carries meaning and nothing else: favorable, unfavorable, needs attention. Light is the default; dark follows `prefers-color-scheme`. Every colour is a `#rrggbb` token so the contrast tests read both themes.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--grey-0` | `#ffffff` | `#1b1b1a` | raised surface (light) · page (dark) |
| `--grey-1` | `#f7f7f5` | `#222221` | page (light) · raised surface (dark) |
| `--grey-2` | `#efeeea` | `#2a2a28` | sunken: your messages, code |
| `--grey-3` | `#e7e6e1` | `#31312f` | hover and pressed |
| `--grey-4` | `#dcdbd5` | `#3b3b38` | hairlines |
| `--grey-5` | `#c4c2bb` | `#52514c` | rules under table heads, control borders |
| `--grey-6` | `#67655f` | `#a09e97` | muted text (4.66:1 or better on every surface) |
| `--grey-7` | `#4a4844` | `#c6c4bd` | secondary text |
| `--grey-8` | `#1c1b19` | `#edece8` | body text |
| `--accent` | `#2a4c99` | `#3a5cb0` | the one filled button (white text 8.1:1 / 6.3:1) |
| `--accent-text` | `#2a4c99` | `#a0b5ee` | links, row drill-downs, focus ring |
| `--green` | `#175f40` | `#7fd1a7` | favorable |
| `--red-text` | `#b03e1b` | `#ef8f74` | unfavorable |
| `--amber` | `#855600` | `#ddb05a` | needs attention (the rule beside a refusal) |

Favorable and unfavorable differ in lightness as well as hue (contrast between them 1.3:1 in each theme), and Phase 4 puts the word beside every status colour, so a reader who cannot tell red from green loses nothing. The semantic names the existing tests use (`bg-primary`, `bg-secondary`, `bg-surface`, `bg-card`, `text-*`, `accent*`, `green*`, `red-text`) are kept and point at the ramp.

### Type

- **Stack.** The system UI face (`-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, Roboto, …`), with tabular figures set on `body`. Monospace (`ui-monospace, "SF Mono", …`) only on code spans.
- **Scale.** 12 px meta (column heads, the phase, row counts) · 13 px code · 14 px body and table cells · 16 px the wordmark and section heads · 20 px a result title · 28 px a headline figure. The last two are defined now and used from Phase 4.
- **Weights.** 400 body · 500 labels, buttons, status words · 600 headings and the wordmark.
- **Line height.** 1.5 for body; headings 1.25 or tighter.

### Space, shape, depth

- **Space.** A 4 px scale: 4, 8, 12, 16, 24, 32, 40. Every padding, margin and gap comes from it (a test checks).
- **Radii.** Two: 4 px for controls (chips, buttons, inputs, code), 8 px for panels (tables, your messages, the drop zone).
- **Borders and depth.** Hairlines in place of shadows. One shadow token, `--shadow-overlay`, reserved for overlays; nothing on the page uses it yet.
- **Width.** Content 960 px; prose 72 ch.

### Motion

- A new message fades in over 150 ms (opacity and a 4 px rise).
- The working indicator is three squares pulsing in opacity on a 1.2 s cycle.
- Nothing else moves: no hover transitions, no pulsing status dot. `prefers-reduced-motion` stops all of it.

## Components

| Component | Now (Phase 1) | Later |
|---|---|---|
| Header and mark | Drawn mark (a budget bar outlined beside a taller actual bar, on a baseline), name, Help, Reset, the phase as plain text after a hairline | Phase 2: wordmark, favicon, phone layout |
| Drop zone | Dashed hairline panel, drawn upload icon | Phase 2 first screen |
| Message | Yours: tinted block on the right. The tool's: plain text, 72 ch | Phase 2 copy |
| Chips | Bordered 4 px buttons in body text | Phase 2: only the latest turn's chips respond (T7) |
| Input bar | Bordered box, filled ink-blue Send | — |
| Intake panel | Markdown bullets | Phase 3: rows from a sibling of `format_intake_summary` |
| Headline strip | — | Phase 4: three or four figures, label above, value at 28 px, comparison and variance at 12 px, status as a word |
| Results table | Framed panel, hairline rows 40 px, 12 px heads, right-aligned tabular numbers, drawn sort icons | Phase 4: `view` field, sentence-case heads, status words, phone layout, totals rule |
| Drill-down, driver breakdown | Markdown | Phase 4 |
| Earnings table | Same frame | Phase 5: column groups under spanning heads |
| Error | Amber rule beside the text | Phase 2: `level` field |
| Loading | Three squares, opacity only | — |
| Print | Header kept, controls dropped, log height released | Phase 4: results view on paper |
| Forced colours | Controls, panels and the attention rule keep system-colour borders | — |

## Glyphs kept by name (T1 allowlist)

None. `•` (U+2022) in Markdown bullets and `…` (U+2026) in previews are punctuation, outside the T1 ranges.

## Copy

_One rewritten example per screen, from Phase 2 on._

## Decisions

| Decision | Chosen | Rejected, and why |
|---|---|---|
| Accent | Ink blue `#2a4c99` | Banker's green: a green link in a finance table reads as "favorable". Violet and teal: the generated defaults the brief names. Red or amber: taken by meaning. |
| Favorable and unfavorable | Green and vermilion, split by lightness, always with the word | Blue and orange (the textbook colour-blind pair): the analyst reads red as unfavorable every working day, so a blue favorable makes the table read wrong to its audience; the word beside the colour carries the meaning for everyone. |
| Grey ramp | Warm-neutral, near-white page `#f7f7f5` | Cream (`#f4f1ea`-like) and slate: both are generated defaults; a cool slate also clashes with the ink accent. |
| Type | System UI stack | IBM Plex Sans bundled: open licence and good tabular figures, but it adds a font file to every allowlist, the wheel and the CSP review for a gain the system faces already give (tabular digits checked in Chromium). Revisit at STOP 1 if the owner wants one face on every system. |
| Body size | 14 px | 16 px (the typography skill's default): section 3 asks 14 to 15 px, and a dense table reads better at 14. |
| Layout | One column, 960 px, results as full-width views | Conversation beside a result canvas: twice the layout work and state, and the phone collapses it to one column anyway. |
| Agent replies | Plain text, no bubble | A bubble around every reply: the chat-app default, and it puts a card around the result table. |
| Sender labels | Announced to screen readers, not shown | Uppercase "AGENT" / "YOU" eyebrows: a generated tell; position and tint already say who spoke. |
| Icons | One drawn set, 20-unit grid, 1.5 px non-scaling stroke, drawn at 16 and 20 px | Emoji and arrows: render differently on every system (T1). An icon font: a new asset and a remote-looking dependency. |
| Status marker shapes | (Phase 4) a dot for favorable, a square for unfavorable, beside the word | Colour alone (T9). |
| Phone header | The name truncates so nothing overlaps | Two header rows (the old layout, 124 px): Phase 2 redesigns the shell. |

## Tell status

| # | Tell | Status | Proof |
|---|---|---|---|
| T1 | Emoji as icons | page and stylesheet clean; `handlers.py` and `knowledge.py` reply text still carries glyphs | P (`test_no_emoji_arrows_or_dingbats_in_the_page`, `test_reply_text_built_by_chat_has_no_glyphs`) |
| T2 | Violet, gradients, glow | done for the stylesheet; accent reach to be read at STOP 1 | P (`test_no_gradient_glow_or_text_shadow`, theme tests) + S |
| T3 | Type without a scale | done: 4 sizes and 3 weights in use, tabular figures, mono on code only | P |
| T4 | Spacing and shape by feel | done for the stylesheet: 4 px scale, 2 radii, 1 overlay shadow | P + S |
| T5 | Result as a chat bubble | todo (Phase 4) | P + S |
| T6 | Capability essay | todo (Phase 2) | P + S |
| T7 | Old chips left live | todo (Phase 2) | P + S |
| T8 | Phone table | todo (Phase 4) | S |
| T9 | Status by colour alone | todo (Phase 4) | P |
| T10 | Decorative motion | done: 150 ms fade, 1.2 s opacity loader, reduced motion stops both | P |
| T11 | Emoji brand | mark drawn; wordmark and favicon in Phase 2 | P + S |
| T12 | Screen-only design | print block in place; results on paper in Phase 4 | P + S |

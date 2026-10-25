# Variance Analysis Agent: interface design

Status: Phase 5. The tokens below are in `src/variance_agent/static/chat.css`; `tests/test_interface_design.py` holds what a test can hold. Each decision names the alternative it rejected.

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
| Header and mark | Drawn mark (a budget bar outlined beside a taller actual bar, on a baseline), wordmark, the step as plain text after a hairline, Help and Start over with icons; on a phone the step takes a second row and the buttons show icons only | — |
| Drop zone | Dashed hairline panel, drawn upload icon | Phase 2 first screen |
| Message | Yours: tinted block on the right. The tool's: plain text, 72 ch | Phase 2 copy |
| Chips | Bordered 4 px buttons in body text; earlier turns' chips are disabled, announced as no longer available, and set as small muted text | — |
| Input bar | Bordered box, filled ink-blue Send | — |
| Intake panel | A bordered panel, 72 ch wide: title, one hairline row per fact (label left in secondary text, the file's words right), notes under a stronger rule, the question last; stacked on a phone | — |
| Headline strip | Three or four figures between hairlines: label, 28 px value, comparison and change at 12 px, status word with its shape; one per row on a phone | — |
| Results table | Framed, hairline rows 40 px, sentence-case 12 px heads, numeric columns right-aligned by value, status words, bars on the variance column only, sticky first column and cue on a phone | — |
| Drill-down, driver breakdown | Figures view: budget, actual, variance; the decomposition as label/value rows; the evidence status as a sentence | — |
| Earnings table | Each comparison's columns under one spanning head with short labels; Beat, Miss, In line as words with shapes; units as the engine formats them | — |
| Error | Attention-coloured rule beside the text, from `level: "error"` | — |
| Loading | Nothing under 100 ms; then three squares pulsing in opacity and a line saying what is happening; after a second a flat three-bar skeleton | — |
| Print | Header kept, controls dropped, log height released | Phase 4: results view on paper |
| Forced colours | Controls, panels and the attention rule keep system-colour borders | — |

## Glyphs kept by name (T1 allowlist)

None. `•` (U+2022) in Markdown bullets and `…` (U+2026) in previews are punctuation, outside the T1 ranges.

## Copy

| Screen | Before | After |
|---|---|---|
| First screen | "Welcome! Upload your financial data to get started." | "Upload a budget-versus-actual file to start. It needs an Actual column and a Budget, Forecast or Prior Period column." |
| First reply after upload | 👋 plus a three-heading essay ("What it's for", "Who it's for", "What you can do") before the question | "Welcome to the Variance Analysis Agent. I compare each line's Actual against your budget, flag the gaps big enough to matter, and say whether each one helped or hurt profit. Type `help` for everything you can ask." then the file line and the question |
| Help | "`biggest risks` — Top material unfavorable variances and mitigation advice" | "`biggest risks`: the largest material unfavorable variances" |
| A refusal | "⚠️ 'file.pdf' looks like a scanned image…" | the same sentence with no sign, beside an attention-coloured rule, carried by `level: "error"` |
| Intake summary | "Here's how I read your file:" and double-spaced bullets with bold labels | A panel titled "How I read your file" with one row per fact and "Adjustments I made" |
| Step reminder | "🎯 **Next Step:** Please enter your materiality thresholds" | "**Next:** Enter your materiality thresholds (for example `$10,000 or 5%`), or choose a preset below." |
| Header | "? Help", "↺ Reset", "SET PERIOD" with a pulsing dot | Help and Start over with drawn icons; "Set the period" as plain text |
| Placeholder | "Enter the reporting period (e.g., Q3 2026)..." | "Reporting period, for example Q3 2026" |
| Drop zone | "Drop file here or click to browse" / ".csv, .json, .xlsx, .xlsm, .pdf (10-K / 10-Q)" | "Drop a file here, or choose one" / "CSV, JSON, Excel (.xlsx, .xlsm) or a PDF 10-K or 10-Q, up to 32 MB" |

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
| Status marker shapes | A dot for favorable, a square for unfavorable, a ring for neutral, beside the word | Colour alone (T9). Icons per status: heavier than the word needs. |
| Phone table | Sticky first column, horizontal scroll, a "More columns" cue until the right edge | Cards per row: loses the column comparison that is the point of the table. A gradient fade: gradients are out (T2). |
| Chart | None | The budget-to-actual bridge: the waterfall reply already lists each step in a table, and a chart would add a second rendering of the same numbers without answering anything the table does not. |
| Phone header | Name and icon buttons on one row, the step on a thin second row | Shortening the name to fit one row: the product's name is not this run's to change, and tests and the page title use it. Hiding the step: the tests forbid it and it is the only progress cue. |
| Old chips | Kept, disabled, announced and muted | Removed: a reply can say "choose a preset below", and a removed chip leaves that sentence pointing at nothing. Left live: a click on an old "USD" sent it again in whatever step was current. |
| Error marker | A rule in the attention colour, from a `level` field | A warning sign in the text: renders differently everywhere and is not a contract. A red tint: red means unfavorable here. |
| Intro | One sentence and a pointer to `help` | The capability essay: it pushed the first question below the fold on every screen size. |

## Tell status

| # | Tell | Status | Proof |
|---|---|---|---|
| T1 | Emoji as icons | done: no glyph in `static/` or `chat/` | P (`test_no_emoji_arrows_or_dingbats_in_the_page`, `test_reply_text_built_by_chat_has_no_glyphs`) |
| T2 | Violet, gradients, glow | done for the stylesheet; accent reach to be read at STOP 1 | P (`test_no_gradient_glow_or_text_shadow`, theme tests) + S |
| T3 | Type without a scale | done: 4 sizes and 3 weights in use, tabular figures, mono on code only | P |
| T4 | Spacing and shape by feel | done for the stylesheet: 4 px scale, 2 radii, 1 overlay shadow | P + S |
| T5 | Result as a chat bubble | done: results, drill-down, drivers, risks and what-if render from `view` | P (`test_the_results_view_carries_the_same_figures_as_the_text`) + S |
| T6 | Capability essay | done | P (`test_first_upload_opens_with_a_short_welcome_and_help_holds_the_capabilities`) + S |
| T7 | Old chips left live | done | P (`test_only_the_latest_turns_chips_respond`) + S |
| T8 | Phone table | done: sticky first column and a cue | S (`phone_tables.py`) |
| T9 | Status by colour alone | done: a word and a shape | P (`test_status_words_mirror_the_servers_map`, `test_status_cells_show_a_word_and_a_shape`) |
| T10 | Decorative motion | done: 150 ms fade, 1.2 s opacity loader, reduced motion stops both | P |
| T11 | Emoji brand | done | P (`test_the_header_has_a_drawn_mark_a_wordmark_and_a_matching_favicon`) + S |
| T12 | Screen-only design | done: print stylesheet, results printed and read | P + S |

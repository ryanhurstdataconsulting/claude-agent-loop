---
name: document-render
description: Use when rendering a markdown deliverable to PDF (reports, leadership briefs, legal contracts) or converting a generated .pptx / .docx deck to PDF or per-slide images for QA. Carries the canonical pandoc + WeasyPrint toolchain and the headless-LibreOffice deck path, with every gotcha already rediscovered on this engagement. Triggers include mojibake in a rendered PDF (â€œ / â€™ for smart quotes), $-delimited text vanishing from a table cell, a duplicated document title, a hung macOS headless Chrome, a "which interpreter has weasyprint vs reportlab" probe, a Keynote/PowerPoint automation failure with no GUI-free fallback, a Mermaid diagram rendering as blank/textless colored shapes, or a table row's content splitting oddly across a page boundary.
---

# document-render

## Overview

Every client-facing PDF and deck-to-image render on this machine goes
through **one of two toolchains**:

1. **Markdown → PDF** via `pandoc` (markdown → HTML fragment) then `weasyprint`
   (HTML + paged-media CSS → PDF). This is the path for reports, leadership
   briefs, and legal contracts.
2. **`.pptx` / `.docx` → PDF or images** via **headless LibreOffice**
   (`soffice --headless --convert-to ...`), the GUI-free fallback when Keynote /
   PowerPoint automation is unavailable.

This toolchain was independently rediscovered at least four times across the
portfolio, re-hitting the same gotchas each time. This skill is the single
canonical reference so it is never re-derived again. Copy-paste recipes, a
minimal paged-media CSS stub, and the post-render verifier live in
[`references/render-recipes.md`](references/render-recipes.md).

## Environment capability map (this machine)

Probe before you assume — but on this workstation the current, verified layout is:

| Tool | Where | Notes |
|---|---|---|
| `pandoc` | `/opt/homebrew/bin/pandoc` (v3.9) | Homebrew. markdown → HTML. |
| `weasyprint` | `/opt/homebrew/bin/weasyprint` (v68.1) | **Use the CLI.** Its interpreter is the isolated Homebrew env `/opt/homebrew/Cellar/weasyprint/.../libexec/bin/python`. |
| system `python3` | `/usr/bin/python3` | **Has NO weasyprint and no reportlab.** Do not `python3 -c "import weasyprint"` and conclude it is missing — call the CLI. |
| LibreOffice (`soffice`) | **NOT installed** | Needed for deck export. Install: `brew install --cask libreoffice`, then `soffice` is at `/Applications/LibreOffice.app/Contents/MacOS/soffice`. |
| Chrome | `/Applications/Google Chrome.app/...` | Present — relevant only to the headless-Chrome gotcha below. Not the render engine. |
| DejaVu fonts | **Not staged** | WeasyPrint falls back to system fonts; stage DejaVu for consistent glyphs (see gotcha 5). |

**Rule of thumb:** the reliable weasyprint entry point on this machine is the
Homebrew **CLI**, not any `import weasyprint` in an arbitrary interpreter. A
project `.venv` may or may not carry it; the CLI always does.

## Path 1 — Markdown → PDF (pandoc + WeasyPrint)

Run from the folder that holds the paged-media stylesheet (`.pdf_style.css`):

```bash
pandoc --from=markdown-tex_math_dollars FILE.md -o FILE.html
weasyprint --encoding utf-8 FILE.html FILE.pdf -s .pdf_style.css
```

Two flags are load-bearing and both are in the command above. Here is why each
one matters, plus the three other traps.

### Gotcha 1 — Latin-1 mojibake on a charset-less fragment (`--encoding utf-8` is mandatory)

**Symptom:** every smart quote, apostrophe, and em-dash in the PDF renders as
mojibake — `"` → `â€œ`, `'` → `â€™`, `—` → `â€"`.

**Root cause:** pandoc emits a **charset-less HTML fragment**. WeasyPrint then
defaults to Latin-1 and misdecodes every multi-byte UTF-8 sequence.

**Fix:** pass `--encoding utf-8` to WeasyPrint (as above). Alternatively emit a
standalone document with an explicit `<meta charset="utf-8">` — but see gotcha 3
before reaching for `-s`. When UTF-8 is forced correctly, the output byte size
matches the original PDFs almost exactly, which confirms this is the intended
toolchain.

### Gotcha 2 — `tex_math_dollars` eats `$` in figure and table cells (`--from=markdown-tex_math_dollars`)

**Symptom:** a table or figure cell containing two `$` signs loses them and
leaks literal `**` / `|` markup. Example inputs that break: an invoice rate cell
`$40.00/hr | **$[hours × 40]**`, or a termination clause
`($1,600.00 ÷ 7) = $1,600.00`.

**Root cause:** pandoc's default markdown reader treats text between two `$` as
inline LaTeX math, consumes the delimiters, and mangles the surrounding markup.

**Fix:** disable the extension with `--from=markdown-tex_math_dollars` (the `-`
turns the extension off). Any financial figure, price, or dollar amount in a
deliverable needs this. The original shipped legal PDFs actually carried this
bug; the corrected render is strictly better.

### Gotcha 3 — pandoc title duplication

**Symptom:** the rendered document shows its title **twice** — once as a title
block at the top and again as the first body heading.

**Root cause:** when you render standalone (`-s` / `--standalone`) **and** the
source has both a YAML `title:` and a leading `# H1`, pandoc's HTML template
emits a `<header id="title-block-header">` from the metadata *and* the body H1.

**Fix:** the canonical path emits a **bare fragment (no `-s`)** and lets
WeasyPrint own the charset via `--encoding utf-8`, so no template runs and this
cannot happen. Paged-media stylesheets that set `string-set: doctitle` from the
body `h1` for running headers depend on that single H1 existing. If you must go
standalone for some other reason, reconcile the title to **one** source — keep
the body `# H1` and drop the YAML `title:`, or vice versa.

### Gotcha 4 — the macOS `--headless=new` Chrome hang

**Symptom:** a render script that shells out to headless Chrome
(`--headless=new --print-to-pdf`) **hangs indefinitely** on macOS and never
writes the PDF.

**Root cause:** Chrome's newer `--headless=new` mode does not terminate cleanly
in this print-to-PDF flow on macOS.

**Fix:** **use WeasyPrint, not Chrome** — it is the canonical engine and
does not hang. If a legacy script genuinely needs Chrome, fall back to the old
`--headless` mode, add `--virtual-time-budget=10000`, and wrap the call in
`timeout 60` so a hang fails loudly instead of blocking the pipeline.

### Gotcha 5 — DejaVu / font staging

**Symptom:** unicode symbols, box-drawing characters, or specific glyphs render
as tofu (`□`) or silently substitute a different font, so the PDF looks
inconsistent across machines.

**Root cause:** WeasyPrint resolves fonts through fontconfig and can only use
what is installed. This machine has **no DejaVu family staged**, so any CSS
`font-family: "DejaVu Sans"` falls through to a system default.

**Fix:** either stage the family (`brew install --cask font-dejavu`) and
reference it in the stylesheet, or point the CSS `font-family` at a font you have
confirmed is present. Pin the font in the stylesheet rather than relying on the
WeasyPrint default so the same input renders identically on every machine.

### Gotcha 6 — Mermaid diagrams render as blank, textless colored boxes

**Symptom:** a Mermaid flowchart pre-rendered to SVG (via `mmdc`,
`@mermaid-js/mermaid-cli`) and embedded as an `<img>` shows correctly shaped,
correctly colored nodes and arrows in the PDF — but every node is **empty, with
no label text at all**. This happens with Mermaid's default config
(`htmlLabels: true`, which wraps labels in `<foreignObject>`) — WeasyPrint's SVG
engine (CairoSVG) does not support `<foreignObject>`, so the HTML-in-SVG label
never renders. It **also** happens with `flowchart: { htmlLabels: false }`
(forcing pure SVG `<text>`): at least one `@mermaid-js/mermaid-cli` version
emits a `<text><tspan .../></text>` with the `tspan` **self-closing and empty**
regardless of plain-string or backtick/markdown-string node labels — a rendering
bug in that version's non-HTML text layout path, not a WeasyPrint limitation.
Confirm which failure mode you're hitting with:
`grep -c foreignObject FILE.svg` (foreignObject path) vs.
`python3 -c "import re; print(re.findall(r'<text.*?</text>', open('FILE.svg').read(), re.DOTALL)[:2])"`
(shows empty `tspan`s if it's the second bug).

**Root cause:** two independent, stacking incompatibilities between
Mermaid-CLI's SVG output and CairoSVG — there is no single flag that fixes both.

**Fix:** don't round-trip diagrams through Mermaid for a WeasyPrint-rendered
PDF at all. Hand-author the diagram as plain HTML/CSS (a flexbox row of styled
`<div>` "nodes" with arrow characters or small CSS connectors between them) and
inline it directly in the markdown/HTML source. This renders through the exact
same, already-proven CSS pipeline as the rest of the document — no external
tool, no headless-browser dependency, no font/text-layout risk. For a linear
cause → effect → impact narrative (the common case in an audit/incident report),
3–5 boxes in a `flex-wrap: wrap` row reads as well as a real flowchart and is
far more robust. Reserve real Mermaid/Graphviz rendering for contexts that
render it live in-browser (an Artifact, a Markdown viewer with native Mermaid
support) — never for a WeasyPrint PDF pipeline.

### Gotcha 7 — a table row's cells split across a page boundary

**Symptom:** in a multi-page table, one row's content (e.g., a styled
`<span class="pill">` badge) goes missing on the page where the row starts,
then reappears alone — stripped of its sibling cells — at the top of the next
page.

**Root cause:** WeasyPrint will break a table row across a page if the row
doesn't fit in the remaining space, by default. A cell containing an inline
block-ish element (a padded/bordered `span`, in this case) can end up visually
orphaned by the split.

**Fix:** add `break-inside: avoid;` to the table's `tr` (and to any other
repeating card-like block you don't want split — a "finding" card, a flow
diagram row): `table.summary tr { break-inside: avoid; }`. Verify by rendering
the page straddling a table's row count and eyeballing it (text-only
`pdftotext` extraction won't catch this — it's a layout defect, not a text
defect).

## Path 2 — `.pptx` / `.docx` → PDF or images (headless LibreOffice)

The GUI-free fallback for deck QA when Keynote / PowerPoint automation fails
(this has blocked more than one project). Requires LibreOffice
(`brew install --cask libreoffice` — not installed by default here).

**Deck → PDF:**

```bash
soffice --headless --convert-to pdf --outdir OUT/ DECK.pptx
```

**Deck → per-slide images** (do **not** use `--convert-to png` directly):

```bash
# Step 1: deck → PDF, Step 2: PDF → one PNG per page
soffice --headless --convert-to pdf --outdir OUT/ DECK.pptx
pdftoppm -png -r 150 OUT/DECK.pdf OUT/slide   # → OUT/slide-1.png, slide-2.png, ...
```

**Two LibreOffice gotchas:**

- **`--convert-to png` exports only the first slide** of a multi-slide `.pptx`
  (the Impress PNG filter is single-page). For per-slide images, always go
  through PDF first, then `pdftoppm` (part of poppler; `brew install poppler`).
- **A running LibreOffice GUI blocks `--headless`** — LibreOffice is
  single-instance by default, so a headless call silently attaches to (or is
  blocked by) an open GUI. Give the headless run its own profile:
  `soffice --headless -env:UserInstallation=file:///tmp/lo_headless --convert-to pdf ...`.

## Verify every render before you ship it

A render that "ran" is not a render that is correct. Extract text and assert:

```bash
pdftotext -layout FILE.pdf - | \
  grep -c 'â€'          # → 0  (zero mojibake)
# also confirm: zero literal '**' leaked, and every expected $ figure is present
```

The three assertions that catch the gotchas above: **zero `â€`** (charset),
**zero literal `**`** (tex_math_dollars), and **all dollar figures present**.
Full verifier in [`references/render-recipes.md`](references/render-recipes.md).

## Composition

- Confirm the toolchain is present first (pandoc, weasyprint CLI, LibreOffice,
  fonts) — the capability map above is the manual version of that preflight.
- Run the **grammar gate on the prose before you render it**, not after — the
  user is a stickler for grammar, and a mojibake-free PDF of a sentence with a
  bad *a/an* is still a defect. Proofread number-aware indefinite articles
  ("an 8.1", "a 5.0"), subject-verb agreement, and its/it's in any
  client-facing copy first.
- After regenerating a multi-file deliverable, check the whole set for stale
  figures, dates, and totals against the current source of truth.

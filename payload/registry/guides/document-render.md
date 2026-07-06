# Guide — document-render

**Category:** skill
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The document and deck rendering toolchain was rediscovered independently
across multiple projects, each time re-hitting the same gotchas: Latin-1
mojibake on a charset-less HTML fragment, `tex_math_dollars` eating `$` in
figure cells, pandoc title duplication, the macOS `--headless=new` Chrome
hang, and DejaVu/font staging. Separately, more than one project was blocked
when Keynote/PowerPoint automation failed and needed a headless
`.pptx`/`.docx` → PDF/images path. This skill merges the pandoc+weasyprint
rediscoveries and the deck-export blocks into one reference, distinct from the
catalog `legal-advisor`.

## When to deploy (triggers)
- Rendering any markdown deliverable to PDF (reports, briefs, legal docs).
- Converting a generated `.pptx` or `.docx` deck to PDF or images for QA.
- Symptoms it resolves: mojibake in a rendered PDF, `$`-delimited text
  vanishing from a table cell, a duplicated document title, a hung headless
  Chrome, a "which interpreter has weasyprint vs reportlab" probe, a Keynote
  automation failure with no GUI-free fallback.

## Interface (how to invoke)
`Skill(document-render)`. The skill carries the canonical invocations:
`pandoc ... --pdf-engine=weasyprint` for markdown → PDF (with the utf-8 and
`tex_math_dollars` flags set correctly), and headless LibreOffice
(`soffice --headless --convert-to pdf` / `--convert-to png`) for deck → PDF or
images.

## Composition (pairs with / hands off to)
Depends on `env-tooling-preflight` to confirm pandoc, weasyprint, LibreOffice,
and fonts are present. Pairs with `deliverable-consistency-checker` (deferred)
for post-render figure checks, and with `machine-prose-grammar-gate` before any
client-facing prose is rendered. Surfaced by `resource-loop` on any render
task.

## Build & maintenance notes
Build sketch: one skill file carrying the canonical pandoc+weasyprint and
headless-LibreOffice invocations, an environment-capability map (which
interpreter holds which renderer), and an install note for LibreOffice to
enable GUI-free deck export. Lives at `~/.claude/skills/document-render/`;
test by rendering a fixture markdown doc and a fixture deck end to end.

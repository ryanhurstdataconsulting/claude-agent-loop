# render-recipes — copy-paste toolchain for document-render

Exact commands, a minimal paged-media stylesheet, and the post-render verifier.
Load the parent [`SKILL.md`](../SKILL.md) for the why behind each flag.

## 0. Capability probe (run first on an unfamiliar machine)

```bash
which pandoc && pandoc --version | head -1
which weasyprint && weasyprint --version          # the CLI is the reliable entry point
which soffice || ls /Applications/LibreOffice.app/Contents/MacOS/soffice 2>/dev/null \
  || echo "LibreOffice missing → brew install --cask libreoffice"
which pdftoppm pdftotext || echo "poppler missing → brew install poppler"
```

Do **not** gate the render on `python3 -c "import weasyprint"` — the system
`/usr/bin/python3` has no weasyprint even when the CLI is installed and working.

## 1. Markdown → PDF

```bash
# From the folder holding .pdf_style.css:
pandoc --from=markdown-tex_math_dollars FILE.md -o FILE.html
weasyprint --encoding utf-8 FILE.html FILE.pdf -s .pdf_style.css
```

- `--from=markdown-tex_math_dollars` — stops `$` from being read as inline math
  (protects invoice / price / financial cells).
- `--encoding utf-8` — stops Latin-1 mojibake on pandoc's charset-less fragment.
- No `-s` on pandoc — a bare fragment avoids the double-title bug; WeasyPrint
  owns the charset.

## 2. Minimal paged-media stylesheet (`.pdf_style.css`)

A lean starting point. Pin a font that is actually installed (see SKILL gotcha 5).

```css
@page {
  size: letter;
  margin: 1in 0.9in;
  @bottom-center { content: counter(page) " / " counter(pages); font-size: 9pt; color: #666; }
  @top-center   { content: string(doctitle); font-size: 9pt; color: #666; }
}
h1 { string-set: doctitle content(); font-size: 20pt; margin: 0 0 0.4in; }
body { font-family: "DejaVu Serif", Georgia, serif; font-size: 11pt; line-height: 1.45; color: #111; }
table { border-collapse: collapse; width: 100%; font-size: 10pt; }
th, td { border: 1px solid #ccc; padding: 4px 7px; text-align: left; }
```

`string-set: doctitle` reads the single body `# H1` for the running header — one
more reason to keep exactly one H1 and skip pandoc's `-s` title block.

## 3. Deck → PDF and per-slide images

```bash
# PDF:
soffice --headless -env:UserInstallation=file:///tmp/lo_headless \
  --convert-to pdf --outdir OUT/ DECK.pptx

# Per-slide PNGs (via PDF — NOT `--convert-to png`, which only exports slide 1):
pdftoppm -png -r 150 OUT/DECK.pdf OUT/slide      # → OUT/slide-1.png, slide-2.png, ...
```

The `-env:UserInstallation=...` flag gives the headless run its own profile so
an open LibreOffice GUI cannot block it.

## 4. Verify (assert, do not eyeball)

```bash
txt="$(pdftotext -layout FILE.pdf -)"
echo "$txt" | grep -c 'â€'      # expect 0  — charset / mojibake
echo "$txt" | grep -c '\*\*'    # expect 0  — leaked markdown from tex_math_dollars
# then confirm every expected $ figure is present, e.g.:
for amt in '$1,875.00' '$7,500.00'; do
  echo "$txt" | grep -qF "$amt" && echo "ok $amt" || echo "MISSING $amt"
done
```

Ship only when mojibake and leaked `**` are both zero and every figure is
accounted for.

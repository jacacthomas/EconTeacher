# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
poetry install

# Syllabus pipeline (run in order)
poetry run python scripts/build_syllabus_from_pdf.py   # downloads spec PDF if needed, writes output/intermediate/pdf/
poetry run python scripts/build_syllabus_from_web.py   # scrapes AQA website, writes output/intermediate/web/
poetry run python scripts/validate_syllabus.py         # compares sources, writes output/authoritative/

# MCQ extraction
poetry run python scripts/download_past_papers.py
poetry run python scripts/extract_all_as_paper1_mcqs.py

# Run a single module directly (quick smoke test)
poetry run python econteacher/extract_mcqs.py
poetry run python econteacher/parse_aqa_a_level_syllabus_pdf.py
```

There are no automated tests.

## Architecture

The project has two parallel pipelines:

### 1. Syllabus pipeline

**Goal:** produce authoritative YAML/JSON files of the AQA Economics syllabus (AS and A-level).

**Flow:**
1. `econteacher/download_aqa_a_level_syllabus_pdf.py` — downloads the spec PDF to `data/aqa_economics_spec.pdf`
2. `econteacher/parse_aqa_a_level_syllabus_pdf.py` — parses it using `pdfplumber` word/character positions; splits pages into left (content) and right (additional info) columns at `x=380pt`; handles multi-line headings and the section 4.1 implicit heading quirk
3. `econteacher/scrape_aqa_a_level_syllabus_web.py` — scrapes the same content from the AQA website HTML (`h2/h3/h4/table` structure); remaps A-level page section numbers from `3.x → 4.x` to match the PDF scheme
4. `scripts/validate_syllabus.py` — diffs PDF vs web output (diagnostics only), then writes the **web-scraped version** as authoritative to `output/authoritative/`

The web-scraped version is authoritative because the AQA website parses more cleanly than the PDF.

**Output structure** (both sources produce identical schema):
```python
{
  "3.1": {
    "title": "...",
    "subsections": {
      "3.1.1": {
        "title": "...",
        "topics": {
          "3.1.1.1": {
            "title": "...",
            "content": ["bullet point", ...],
            "additional_info": ["teacher guidance note", ...]
          }
        }
      }
    }
  }
}
```
Sections `3.x` = AS level; `4.x` = A-level.

### 2. MCQ extraction pipeline

**Goal:** extract the 20 Section A MCQs from AQA AS Economics past papers as structured JSON, with diagram images as PNGs.

**Flow:**
1. `scripts/download_past_papers.py` — downloads question papers and mark schemes to `data/past_papers/as_paper_1/qp/` and `.../ms/`
2. `econteacher/extract_mcqs.py` — extracts questions from a question-paper PDF using `pdfplumber` character-level data; reconstructs text as LaTeX (handles subscripts, bold); locates diagram regions via large vertical gaps; renders diagram PNGs via `PyMuPDF (fitz)`
3. `econteacher/extract_mcq_answers.py` — extracts the answer key from a mark-scheme PDF by finding the "KEY LIST" table
4. `scripts/extract_all_as_paper1_mcqs.py` — orchestrates both modules across all downloaded papers; merges questions + answers; saves to `output/mcqs/as_paper_1_{session}.json` with figures in `output/mcqs/figures/`

**MCQ output schema per question:**
```python
{
  "question_number": 1,
  "question_text": "LaTeX string; [FIGURE] marks diagram position",
  "options": {
    "A": "text or {'figure': 'path/to.png'}",
    ...
  },
  "question_figure": "path/to.png or null",
  "has_figure": bool,
  "correct_answer": "A",
  "answer_explanation": "string or null",
  "notes": ["..."]
}
```

### Key extraction constants (`extract_mcqs.py`)

Several thresholds control PDF parsing behaviour — adjust carefully if papers from new years break extraction:
- `LINE_GAP_THRESHOLD = 7.0` — vertical gap (pt) that starts a new text line (must be > subscript offset ~4.6pt, < line spacing ~13pt)
- `DIAGRAM_GAP_THRESHOLD = 30.0` — gap indicating a diagram is present
- `DIAGRAM_DPI = 200` — resolution of extracted PNG images
- `RIGHT_MARGIN_FRACTION = 0.88` — cuts off "Do not write outside the box" margin text

## Authoritative data sources

When generating teaching resources (slides, worksheets, etc.) or any task requiring syllabus or scheme of work content, always read from these JSON files — do not infer, reconstruct, or use other sources:

| Data | File |
|------|------|
| AS-level syllabus | `output/authoritative/as_syllabus.json` |
| A-level syllabus | `output/authoritative/alevel_syllabus.json` |
| Scheme of work (AS + A-level) | `output/authoritative/sow.json` |

If a required file does not exist, stop and warn the user before proceeding. Do not attempt to generate content without the authoritative data.

### Data directories

```
data/
  aqa_economics_spec.pdf          # downloaded by build_syllabus_from_pdf.py
  past_papers/as_paper_1/
    qp/  *.pdf                    # question papers (naming: {session}_qp.pdf)
    ms/  *.pdf                    # mark schemes   (naming: {session}_ms.pdf)

output/
  intermediate/pdf/               # PDF parser output (JSON)
  intermediate/web/               # web scraper output (JSON)
  authoritative/                  # final YAML + JSON syllabus files
  mcqs/
    as_paper_1_{session}.json     # merged questions + answers
    figures/                      # extracted diagram PNGs
```

## TikZ / pgfplots diagram conventions

All economics diagrams (AD/AS, supply & demand, labour market, etc.) must follow this workflow:

1. **Solve intersections algebraically before writing any code.** Work out every key coordinate (curve intersections, equilibria) on paper from the curve equations.
2. **Document the equations and results in a comment block** directly above the `\begin{tikzpicture}`, e.g.:
   ```latex
   % SRAS:  P = 0.8Y
   % AD1:   P = 9 - Y    =>  E1: Y=5, P=4
   % AD2:   P = 12.6 - Y =>  E2: Y=7, P=5.6
   % LRAS:  Y = 9
   ```
3. **Set `xtick`/`ytick` from the calculated values** so axis labels sit exactly at the equilibrium points.
4. **Use `\coordinate` to name every key point** (equilibria, intersections). Reference those names for dots, dashed lines, and labels — never repeat a raw coordinate pair.
5. **Draw dashed reference lines** from each equilibrium point to both axes so price-level and output readings are clear.

These rules ensure elements are provably in the correct positions and diagrams remain easy to edit.

### Curve label placement

Use `anchor=west` for every curve type — the label extends into the whitespace to the right of the placement point. Avoid `anchor=south` above a curve top: if the top is near `ymax`, the label is clipped.

| Curve type | Label position | Anchor |
|---|---|---|
| Vertical (LRAS) | To the right of the line at mid-height (e.g. `(Yf + 0.2, 0.75 * ymax)`) | `anchor=west` |
| Upward-sloping (SRAS) | Just beyond the rightmost plotted point | `anchor=west` |
| Downward-sloping (AD) | Just beyond the bottom-right end of the curve's domain | `anchor=west` |

When LRAS and SRAS labels would collide (both on the right), place LRAS at a lower y than SRAS so they sit on different horizontal bands.

### Axis label placement

Add `yshift=-10pt` to `xlabel style` to prevent the xlabel from overlapping xtick labels near the right end of the axis:
```latex
xlabel style={at={(axis description cs:1,0)}, anchor=north east, yshift=-10pt, font=\small},
```

### Axis sizing

Set `xmax`/`ymax` to at least 20% beyond the rightmost/topmost plotted element so curve labels and axis labels have room.

### Naming convention

- `$Y_e$` — equilibrium output (intersection of AD and SRAS)
- `$Y_f$` — full-employment / potential output (LRAS position)
- `$P_e$` — equilibrium price level
- `$Y_1$`, `$Y_2$` — successive equilibria after a shift

## Teaching resources

Resources live in `resources/` — never in `output/` (which is generated data only).

```
resources/
  assets/
    style/
      econteacher.sty     # shared LaTeX style — loaded via \input{} in all .tex files
    images/               # shared image assets
  templates/
    slides/lesson_slides.tex      # Beamer template (one example of every block type)
    worksheets/worksheet.tex      # Worksheet template (one example of every section type)
  generated/
    slides/               # generated .tex slide files (e.g. 3_2_3_2_topic.tex)
    worksheets/           # generated .tex worksheet files
    worksheets/markschemes/  # mark schemes, paired with worksheets
```

### econteacher.sty

Always load with `\input{path/to/econteacher.sty}`. Never use `\usepackage{}` — the file is not a proper package. The file must not contain `\NeedsTeXFormat` or `\ProvidesPackage`; those commands conflict when a file is loaded via `\input{}`.

**Slide environments:**
- `\begin{keypoint}` — yellow; single most important idea on a slide
- `\begin{formula}[TITLE]` — blue; named equation + variable key
- `\begin{examplequestion}[TITLE]` — teal; exam-style question posed to students
- `\begin{examplesolution}[TITLE]` — green; solution to the preceding question

**Worksheet environments:**
- `\begin{instructions}` — blue; worksheet-level instructions block
- `\begin{scenario}{TITLE}` — blue; group discussion scenario. **Mandatory `{}` argument, not `[]`**
- `\begin{extract}{SOURCE}` — grey; data response source text. **Mandatory `{}` argument, not `[]`**

  Both use `{}` because tcolorbox parses `[]` as comma-separated key-value pairs — any comma in the title (e.g. "Tata Steel, Port Talbot" or "Author, Year") will break the optional-arg form.
- `\begin{keypoint}` — yellow; evaluation tips (shared with slides)

### Slides

- Beamer, Madrid theme, 16pt, `aspectratio=169`
- Subtitle format: `TOPIC TITLE | AQA AS/A-level Economics`
- Generated files: `resources/generated/slides/X_X_X_X_topic_name.tex`

### Worksheets

- Article class, 12pt, A4, 1in margins, fancyhdr
- **Topic label format: "Topic index: X.X.X.X"** — used in both `\rhead{}` and the title block. Never "Worksheet: X.X.X.X".
- No single monolithic template — compose from section-level blocks:

| Section | Key features |
|---|---|
| Key Terms | `\\[Xcm]` blank space below each term; 2 marks each, stated inline |
| Group Discussion | `scenario` boxes + `\dotfill` structured response lines |
| Multiple Choice | `(\Alph*)` option labels; 1 mark per question |
| Short Response | Mark inline, then answer space: `QUESTION \hfill (X marks)\\[Xcm]` |
| Quantitative | Mark inline after question; sub-parts `(\roman*)`; "show your working" prompt |
| Diagram | Blank pgfplots axes (`xtick=\empty, ytick=\empty`) for student drawing; marks inline |
| Data Response | `extract{SOURCE}` box followed by numbered questions; marks inline |
| Essay | Mark inline after question; `keypoint` eval tips box; `\vspace{12cm}` minimum (use 14cm+ for 15-mark questions) |

**Mark allocation convention:** marks always appear inline at the end of the question text, before the answer space — never floating at the bottom of the space. Pattern: `QUESTION TEXT \hfill (X marks)\\[Xcm]`. This applies to every section type.

- Generated files: `resources/generated/worksheets/X_X_X_X_topic_name.tex`
- Mark schemes: `resources/generated/worksheets/markschemes/X_X_X_X_topic_name_ms.tex`
  - Use `../../../assets/style/econteacher.sty` (one extra `../` vs the worksheet)
  - Use `\begin{extract}{...}` for mark band descriptor tables
  - Header: `\lhead{Dr Jac Thomas \quad\textit{Mark Scheme}}`
  - Include per-section marking guidance, worked answers for calculations (with follow-through notes), level descriptors for essays, and indicative content for group discussion (ungraded)

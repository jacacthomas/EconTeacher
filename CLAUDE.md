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

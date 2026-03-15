"""
extract_mcqs.py
---------------
Core logic for extracting multiple-choice questions (MCQs) from AQA
AS Economics past paper PDFs.

Uses pdfplumber's character-level data to reconstruct question text as
LaTeX — correctly handling subscripts (e.g. S_{1}, E_{2}) and bold text.
Diagram regions are located by finding large vertical gaps between text
lines, then rendered as PNG images using PyMuPDF.

Each question has this structure (some elements may be absent):
  - Question number (left-aligned, same line as first text)
  - One or more lines of question text (possibly with paragraph breaks)
  - Optionally a diagram (centre-aligned, full-width gap in text)
  - Optionally more question text below the diagram
  - Four answer options (A–D), each either a line of text or a diagram
    (when options are diagrams, the letter label appears left-aligned
    and the diagram is centred below it)

Each question always fits entirely on one page.
"""

import os
import re
from collections import Counter

import pdfplumber
import fitz  # PyMuPDF


# ── Constants ─────────────────────────────────────────────────────────────────

# Section A of AS Papers 1 and 2 always contains exactly 20 MCQs.
MCQ_COUNT = 20

# Vertical gap (pt) between character tops that triggers a new text line.
# Subscripts in AQA PDFs sit ~4.6pt below the baseline, so this threshold
# must be larger than 4.6pt (to keep subscripts on the same line) but
# smaller than normal line spacing (~13pt).
LINE_GAP_THRESHOLD = 7.0

# Vertical gap (pt) between consecutive text lines that indicates a diagram
# is present in that space. Paragraph breaks (the only non-diagram gap
# larger than normal line spacing seen in these papers) are ~24pt, so
# anything above 30pt is treated as a diagram.
DIAGRAM_GAP_THRESHOLD = 30.0

# Vertical gap (pt) that is treated as a paragraph break (rendered as \n\n
# in the LaTeX output). Gaps between this value and DIAGRAM_GAP_THRESHOLD
# represent blank lines within question text.
PARAGRAPH_GAP_THRESHOLD = 10.0

# Vertical offset (pt) from the line baseline that classifies a character
# as a subscript (positive = below baseline). Typical AQA value: ~4.6pt.
SUBSCRIPT_THRESHOLD = 3.0

# Horizontal gap (pt) between consecutive character bounding boxes that
# is treated as a word space. Within-word gaps in this PDF are ~0pt;
# word spaces are ~3.07pt, so any threshold between those works.
X_TOLERANCE = 1.5

# Fraction of page height used to exclude the header / footer regions.
HEADER_FRACTION = 0.07   # top 7%  of page
FOOTER_FRACTION = 0.94   # bottom 6% of page

# Fraction of page width beyond which characters are treated as right-margin
# boilerplate and discarded. The "Do not write outside the box" text sits at
# ~91% across a 595pt A4 page. Legitimate content never exceeds ~89%.
RIGHT_MARGIN_FRACTION = 0.88

# Minimum blank vertical space (pt) between the question stem and the page
# footer that indicates the answer options are four diagrams with their
# A/B/C/D labels embedded in the images (not as separate text characters).
# In these questions the page contains no option-letter text at all, so the
# blank region is split into four equal strips for extraction.
EMBEDDED_DIAGRAM_MIN_GAP = 200

# Resolution (DPI) for rendered diagram PNG images.
DIAGRAM_DPI = 200

# Horizontal margin (pt) cropped from each side of the page when
# extracting a diagram — removes the answer-circle gutter and margin text.
DIAGRAM_X_MARGIN = 50

# Phrases in the question stem that signal a question-body diagram.
FIGURE_PHRASES = (
    "diagram below", "diagrams below",
    "figure below", "graph below", "chart below",
    "illustrated",
)


# ── Boilerplate patterns ──────────────────────────────────────────────────────

# Lines matching these patterns are stripped from extracted page text.
# They originate from page headers, footers, and standard instructions
# printed on every page of AQA exam papers.
_BOILERPLATE_RE = re.compile(
    "|".join([
        r"^PMT$",
        # "Do not write [n] outside the box" appears in the right margin.
        # pdfplumber splits it into up to three lines in various ways.
        r"^Do not write$",
        r"^outside the$",
        r"^\d+\s+outside the$",    # e.g. "4 outside the"
        r"^box$",
        r"^Turn over\s*[►▶]?$",
        r"^\*\s+\*$",
        r"^\d{1,2}$",                              # lone page numbers
        r"^IB/[A-Z]/[A-Za-z0-9/]+$",             # AQA document reference codes (IB/G/, IB/M/, etc.)
        r"^QUESTION \d+ IS THE.*$",               # "QUESTION 20 IS THE LAST..." (split across lines)
        r"^LAST QUESTION IN SECTION A$",
        r"^QUESTION IN SECTION A$",
        r"^END OF SECTION A$",                    # used in 2022+ papers instead of "QUESTION 20..."
        r"^Section A(?:\s+box)?$",                # "Section A" or "Section A box" (2022+ header)
        r"^Answer all questions in this section\.$",
        r"^Only one answer per question is allowed\.$",
        r"^For each (?:answer|question) completely fill in.*$",  # wording varies by year
        r"^CORRECT METHOD.*$",
        r"^WRONG METHODS?.*$",
        r"^If you want to change.*$",
        r"^If you wish to return.*$",
    ]),
    re.IGNORECASE,
)

def _strip_latex(text):
    """
    Removes LaTeX markup to get plain text, used for pattern matching.
    The LaTeX is kept in the stored line dicts; this is only used when
    deciding whether a line matches a structural pattern (question number,
    option letter, boilerplate, etc.).
    """
    text = re.sub(r'\\textbf\{([^}]*)\}', r'\1', text)   # \textbf{x} → x
    text = re.sub(r'_\{([^}]*)\}',        r'\1', text)   # _{x}       → x
    text = re.sub(r'\^\{([^}]*)\}',       r'\1', text)   # ^{x}       → x
    return text


# Matches the start of a new question: two digit tokens then question text.
# The text after the number must start with a non-digit and be at least
# 3 chars long. Using [^\d] (rather than [A-Z]) handles questions that
# open with a quotation mark, e.g. "'Large pay bonuses...' This statement".
# Stray subscript digit strings like "1 2 1" are rejected because "1" is a digit.
_Q_START_RE = re.compile(r"^(\d) (\d) ([^\d].{2,})$")

# Matches a text answer option, e.g. "A consumers expressing their tastes..."
_OPTION_WITH_TEXT_RE = re.compile(r"^([ABCD]) (.+)$")

# Matches a diagram answer option — just the letter, with the diagram
# printed as an image below it on the page.
_OPTION_LETTER_ONLY_RE = re.compile(r"^([ABCD])$")


# ── Character-level text extraction ──────────────────────────────────────────

def _group_chars_to_lines(chars):
    """
    Groups pdfplumber character dicts into text lines by vertical position.

    Sorts all characters top-to-bottom, then starts a new line only when
    the vertical gap between consecutive characters exceeds LINE_GAP_THRESHOLD.
    This keeps subscript characters (sitting ~4.6pt below the baseline)
    on the same line as their parent text.

    Returns a list of lists. Each inner list contains the chars of one line,
    sorted left-to-right by x0.
    """
    chars = [c for c in chars if c["text"].strip()]
    if not chars:
        return []

    chars = sorted(chars, key=lambda c: (c["top"], c["x0"]))

    lines = []
    current_line    = [chars[0]]
    current_max_top = chars[0]["top"]

    for char in chars[1:]:
        if char["top"] - current_max_top > LINE_GAP_THRESHOLD:
            lines.append(sorted(current_line, key=lambda c: c["x0"]))
            current_line    = [char]
            current_max_top = char["top"]
        else:
            current_line.append(char)
            current_max_top = max(current_max_top, char["top"])

    if current_line:
        lines.append(sorted(current_line, key=lambda c: c["x0"]))

    return lines


def _line_to_latex(line_chars):
    """
    Converts one text line's characters to a LaTeX string.

    Handles three things simultaneously:

    1. Word spaces — inserted when the horizontal gap between consecutive
       character bounding boxes (x0_next - x1_prev) exceeds X_TOLERANCE.

    2. Subscripts — characters whose top position exceeds the line baseline
       by more than SUBSCRIPT_THRESHOLD are wrapped in _{...}. The baseline
       is the average top of characters at the dominant (most common) font
       size on the line.

    3. Bold — characters whose font name contains "bold" are wrapped in
       \\textbf{...}. In AQA PDFs, subscripts are always plain digits and
       never bold, so bold and subscript modes do not overlap in practice.
    """
    if not line_chars:
        return ""

    # Compute the baseline from characters at the dominant font size.
    sizes = [round(c["size"], 1) for c in line_chars]
    dominant_size  = Counter(sizes).most_common(1)[0][0]
    baseline_chars = [c for c in line_chars if abs(c["size"] - dominant_size) < 0.5]
    baseline_top   = sum(c["top"] for c in baseline_chars) / len(baseline_chars)

    result    = ""
    bold_open = False
    sub_open  = False
    prev_x1   = None

    for char in line_chars:  # already sorted left-to-right

        # ── Insert a word space if there is a gap from the previous char ──
        if prev_x1 is not None and char["x0"] - prev_x1 > X_TOLERANCE:
            # Close any open LaTeX groups before the space.
            if sub_open:
                result   += "}"
                sub_open  = False
            if bold_open:
                result    += "} "
                bold_open  = False
                # bold_open is False here; it will re-open if the next char is bold
            else:
                result += " "
        prev_x1 = char["x1"]

        char_is_bold = "bold" in char.get("fontname", "").lower()
        char_is_sub  = (char["top"] - baseline_top) > SUBSCRIPT_THRESHOLD

        # ── Bold mode transition ──────────────────────────────────────────
        if bold_open and not char_is_bold:
            if sub_open:           # close subscript inside bold first
                result  += "}"
                sub_open = False
            result    += "}"
            bold_open  = False
        if not bold_open and char_is_bold:
            result    += r"\textbf{"
            bold_open  = True

        # ── Subscript mode transition ─────────────────────────────────────
        if sub_open and not char_is_sub:
            result   += "}"
            sub_open  = False
        if not sub_open and char_is_sub:
            result   += "_{"
            sub_open  = True

        result += char["text"]

    # Close any groups still open at end of line.
    if sub_open:
        result += "}"
    if bold_open:
        result += "}"

    return result.strip()


def _page_lines(page, page_idx):
    """
    Extracts all content text lines from a page as a list of dicts.

    Each dict has:
        "text"   — LaTeX string (subscripts and bold handled)
        "page"   — page index (0-based)
        "top"    — y-position of topmost character (from page top, pt)
        "bottom" — y-position of bottommost character
        "x0"     — leftmost character x0
        "x1"     — rightmost character x1

    The top HEADER_FRACTION and bottom (1 - FOOTER_FRACTION) of the page
    are excluded to remove page numbers, margin text, and document codes.
    Boilerplate lines that pass the y-filter are caught by _BOILERPLATE_RE.
    """
    h          = page.height
    header_cut = h * HEADER_FRACTION
    footer_cut = h * FOOTER_FRACTION
    right_cut  = page.width * RIGHT_MARGIN_FRACTION

    # The right-margin text "Do not write outside the box" appears at ~x=546
    # on a 595pt-wide page. It is excluded here rather than in _BOILERPLATE_RE
    # because it sits at the same vertical position as question content (within
    # LINE_GAP_THRESHOLD), which would cause the two texts to be merged into
    # the same line before the boilerplate filter can act.
    chars = [c for c in page.chars if header_cut < c["top"] < footer_cut
             and c["x0"] < right_cut]

    result = []
    for line_chars in _group_chars_to_lines(chars):
        text = _line_to_latex(line_chars)
        if not text or _BOILERPLATE_RE.match(_strip_latex(text)):
            continue
        result.append({
            "text":   text,
            "page":   page_idx,
            "top":    min(c["top"]    for c in line_chars),
            "bottom": max(c["bottom"] for c in line_chars),
            "x0":     min(c["x0"]    for c in line_chars),
            "x1":     max(c["x1"]    for c in line_chars),
        })

    return result


# ── Question parsing ──────────────────────────────────────────────────────────

def _find_option_start(line_dicts):
    """
    Returns the index where the answer options (A/B/C/D) begin in line_dicts.

    Locates option B first (no question stem ever begins with "B "), then
    scans backwards to find the A option immediately preceding it. This
    correctly handles stems that begin with "A" (e.g. "A demand curve...").

    Returns -1 if no options are found.
    """
    b_index = None
    for i, ld in enumerate(line_dicts):
        t  = _strip_latex(ld["text"])
        m  = _OPTION_WITH_TEXT_RE.match(t)
        m2 = _OPTION_LETTER_ONLY_RE.match(t)
        if (m and m.group(1) == "B") or (m2 and m2.group(1) == "B"):
            b_index = i
            break

    if b_index is None:
        return -1

    for i in range(b_index - 1, -1, -1):
        t  = _strip_latex(line_dicts[i]["text"])
        m  = _OPTION_WITH_TEXT_RE.match(t)
        m2 = _OPTION_LETTER_ONLY_RE.match(t)
        if (m and m.group(1) == "A") or (m2 and m2.group(1) == "A"):
            return i

    return b_index


def _build_stem_text(stem_lines):
    """
    Joins stem line dicts into a single LaTeX string.

    Consecutive lines are separated by:
      - a space             — if the gap is normal line spacing
      - "\\n\\n"            — if the gap is a paragraph break
      - "\\n\\n[FIGURE]\\n\\n" — if the gap is large enough to contain a diagram
        (this marks where in the text the diagram appears; the image itself
        is stored separately in the question's "question_figure" field)
    """
    result = []
    for i, ld in enumerate(stem_lines):
        if re.match(r"^\[1 mark\]$", _strip_latex(ld["text"]), re.IGNORECASE):
            continue
        if i > 0:
            gap = ld["top"] - stem_lines[i - 1]["bottom"]
            if gap > DIAGRAM_GAP_THRESHOLD:
                result.append("\n\n[FIGURE]\n\n")
            elif gap > PARAGRAPH_GAP_THRESHOLD:
                result.append("\n\n")
            else:
                result.append(" ")
        result.append(ld["text"])

    return "".join(result).strip()


# ── Diagram extraction ────────────────────────────────────────────────────────

def _render_region_png(pdf_path, page_idx, y0, y1, x0, x1, output_path):
    """
    Renders a rectangular region of a PDF page and saves it as a PNG.

    Uses PyMuPDF (fitz), which renders PDFs natively without needing
    poppler. The coordinate system matches pdfplumber: (0, 0) is the
    top-left of the page, y increases downward.

    Parameters:
        pdf_path    — path to the source PDF
        page_idx    — 0-based page index
        y0, y1      — top and bottom of the clip region (pt from page top)
        x0, x1      — left and right of the clip region (pt from left)
        output_path — destination file path (.png)
    """
    scale = DIAGRAM_DPI / 72  # PDF uses 72pt-per-inch; scale to target DPI
    mat   = fitz.Matrix(scale, scale)
    clip  = fitz.Rect(x0, y0, x1, y1)

    doc  = fitz.open(pdf_path)
    page = doc.load_page(page_idx)
    pix  = page.get_pixmap(matrix=mat, clip=clip)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pix.save(output_path)
    doc.close()


def _extract_question_diagram(pdf_path, q_lines, stem_lines, pdf_stem, q_num, figures_dir):
    """
    Locates the diagram within a question's text (the large vertical gap
    between stem line dicts) and extracts it as a PNG.

    Returns the path to the saved PNG, or None if no suitable gap is found.
    """
    # Find all large vertical gaps across all lines of the question.
    # The diagram is the largest such gap.
    best_gap = None
    for i in range(1, len(q_lines)):
        gap_size = q_lines[i]["top"] - q_lines[i - 1]["bottom"]
        if gap_size > DIAGRAM_GAP_THRESHOLD:
            if best_gap is None or gap_size > best_gap["size"]:
                best_gap = {
                    "size":     gap_size,
                    "page":     q_lines[i]["page"],
                    "y0":       q_lines[i - 1]["bottom"],
                    "y1":       q_lines[i]["top"],
                }

    if best_gap is None:
        return None

    with pdfplumber.open(pdf_path) as pdf:
        page_width = pdf.pages[best_gap["page"]].width

    png_path = os.path.join(figures_dir, f"mcq_{pdf_stem}_q{q_num:02d}_question.png")
    _render_region_png(
        pdf_path, best_gap["page"],
        best_gap["y0"], best_gap["y1"],
        DIAGRAM_X_MARGIN, page_width - DIAGRAM_X_MARGIN,
        png_path,
    )
    return png_path


def _extract_option_diagrams(pdf_path, option_lines, pdf_stem, q_num, figures_dir):
    """
    Extracts a separate PNG for each diagram answer option (A, B, C, D).

    The diagram for each option occupies the vertical space between the
    option's letter label and the next option's letter label (or the
    [1 mark] line for option D).

    Returns a dict mapping option letter → PNG path.
    """
    # Collect the y-positions of each option letter and the end sentinel.
    letter_lines = [
        ld for ld in option_lines
        if _OPTION_LETTER_ONLY_RE.match(_strip_latex(ld["text"]))
    ]

    # Find the [1 mark] line as the lower boundary of the last option's diagram.
    mark_lines = [
        ld for ld in option_lines
        if re.match(r"^\[1 mark\]$", _strip_latex(ld["text"]), re.IGNORECASE)
    ]
    end_y = mark_lines[0]["top"] if mark_lines else option_lines[-1]["bottom"]

    if not letter_lines:
        return {}

    page_idx = letter_lines[0]["page"]
    with pdfplumber.open(pdf_path) as pdf:
        page_width = pdf.pages[page_idx].width

    figure_paths = {}
    for i, opt_ld in enumerate(letter_lines):
        letter = _strip_latex(opt_ld["text"]).strip()
        y0 = opt_ld["bottom"]
        y1 = letter_lines[i + 1]["top"] if i + 1 < len(letter_lines) else end_y

        if y1 - y0 < 10:   # degenerate region — skip
            continue

        png_path = os.path.join(
            figures_dir,
            f"mcq_{pdf_stem}_q{q_num:02d}_option_{letter.lower()}.png",
        )
        _render_region_png(
            pdf_path, page_idx, y0, y1,
            DIAGRAM_X_MARGIN, page_width - DIAGRAM_X_MARGIN,
            png_path,
        )
        figure_paths[letter] = png_path

    return figure_paths


def _extract_embedded_option_diagrams(pdf_path, q_lines, pdf_stem, q_num, figures_dir):
    """
    Handles MCQs where the four diagram options carry no separate text labels
    (the A/B/C/D markers are rendered inside the vector graphic, invisible to
    pdfplumber). Found in questions such as "Which of the following AD/AS
    diagrams best illustrates...".

    Strategy: find the large blank vertical region below the question stem and
    split it into four equal horizontal strips, one per option.

    The blank region is bounded by:
      - TOP: bottom of the last non-[1 mark] text line in q_lines
      - BOTTOM: depends on where the "[1 mark]" line falls —
          * If [1 mark] appears AFTER a large gap (diagrams then mark): use
            the top of the [1 mark] line as the bottom boundary.
          * If [1 mark] appears immediately after the stem (mark then
            diagrams): use the page footer cut as the bottom boundary.

    Returns a dict mapping option letter → PNG path, or {} if no suitable
    blank region is found.
    """
    mark_lines = [
        ld for ld in q_lines
        if re.match(r"^\[1 mark\]$", _strip_latex(ld["text"]), re.IGNORECASE)
    ]
    text_lines = [
        ld for ld in q_lines
        if not re.match(r"^\[1 mark\]$", _strip_latex(ld["text"]), re.IGNORECASE)
    ]

    if not text_lines:
        return {}

    page_idx    = text_lines[0]["page"]
    text_bottom = max(ld["bottom"] for ld in text_lines)

    with pdfplumber.open(pdf_path) as pdf:
        page       = pdf.pages[page_idx]
        page_height = page.height
        page_width  = page.width

    footer_cut = page_height * FOOTER_FRACTION

    if mark_lines:
        mark_top    = min(ld["top"]    for ld in mark_lines)
        mark_bottom = max(ld["bottom"] for ld in mark_lines)
        if mark_top - text_bottom > EMBEDDED_DIAGRAM_MIN_GAP:
            # Diagrams occupy the space between the stem and [1 mark].
            region_y0, region_y1 = text_bottom, mark_top
        else:
            # [1 mark] is printed immediately below the stem; diagrams follow.
            region_y0, region_y1 = mark_bottom, footer_cut
    else:
        region_y0, region_y1 = text_bottom, footer_cut

    if region_y1 - region_y0 < EMBEDDED_DIAGRAM_MIN_GAP:
        return {}

    height_each  = (region_y1 - region_y0) / 4
    figure_paths = {}

    for i, letter in enumerate("ABCD"):
        y0       = region_y0 + i * height_each
        y1       = region_y0 + (i + 1) * height_each
        png_path = os.path.join(
            figures_dir,
            f"mcq_{pdf_stem}_q{q_num:02d}_option_{letter.lower()}.png",
        )
        _render_region_png(
            pdf_path, page_idx, y0, y1,
            DIAGRAM_X_MARGIN, page_width - DIAGRAM_X_MARGIN,
            png_path,
        )
        figure_paths[letter] = png_path

    return figure_paths


# ── Main extraction function ──────────────────────────────────────────────────

def extract_mcqs(pdf_path, figures_dir=None):
    """
    Extracts the 20 MCQs from Section A of an AQA AS Economics past paper.

    Parameters:
        pdf_path    — path to the question-paper PDF
        figures_dir — directory for output PNG files (None = skip images)

    Returns a list of 20 question dicts, each containing:
        "question_number"  — int (1–20)
        "question_text"    — LaTeX string; contains [FIGURE] as a placeholder
                             where a question-body diagram appears
        "options"          — dict with keys "A"–"D"; values are:
                               str  — for text options (LaTeX)
                               dict {"figure": path} — for diagram options
        "question_figure"  — str path to PNG of the question-body diagram,
                             or None if there is no such diagram
        "has_figure"       — bool
        "notes"            — list of str
    """
    # ── Collect all content lines from the MCQ pages ──────────────────
    all_lines = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            if page_idx == 0:
                continue   # Cover page — no questions.

            all_lines.extend(_page_lines(page, page_idx))

            raw = page.extract_text() or ""
            if "QUESTION 20 IS THE" in raw or "END OF SECTION A" in raw:
                break

    # ── Split flat line list into per-question blocks ─────────────────
    questions_raw = []
    current_num   = None
    current_lines = []

    for ld in all_lines:
        plain = _strip_latex(ld["text"])
        m = _Q_START_RE.match(plain)
        if m:
            if current_num is not None:
                questions_raw.append((current_num, current_lines))
            current_num = int(m.group(1) + m.group(2))
            # Strip the "X X " number prefix from the LaTeX text. The digits
            # are printed bold, so the prefix looks like "\textbf{X} \textbf{X} ".
            latex_after = re.sub(r'^(?:\\textbf\{\d\}\s+|\d\s+){1,2}', '', ld["text"]).strip()
            current_lines = [{**ld, "text": latex_after}]
        elif current_num is not None:
            current_lines.append(ld)

    if current_num is not None:
        questions_raw.append((current_num, current_lines))

    # ── Parse each question ───────────────────────────────────────────
    pdf_stem = os.path.splitext(os.path.basename(pdf_path))[0]
    results  = []

    for q_num, q_lines in questions_raw:
        if q_num > MCQ_COUNT:
            break

        opts_start   = _find_option_start(q_lines)
        stem_lines   = q_lines if opts_start == -1 else q_lines[:opts_start]
        option_lines = []     if opts_start == -1 else q_lines[opts_start:]

        # Strip [1 mark] from the stem (it sometimes appears there).
        stem_lines = [
            ld for ld in stem_lines
            if not re.match(r"^\[1 mark\]$", _strip_latex(ld["text"]), re.IGNORECASE)
        ]

        stem_text = _build_stem_text(stem_lines)

        # ── Parse options ─────────────────────────────────────────────
        options        = {"A": "", "B": "", "C": "", "D": ""}
        is_diagram_opt = False
        current_opt    = None

        for ld in option_lines:
            text  = ld["text"]
            plain = _strip_latex(text)
            if re.match(r"^\[1 mark\]$", plain, re.IGNORECASE):
                continue

            m_text   = _OPTION_WITH_TEXT_RE.match(plain)
            m_letter = _OPTION_LETTER_ONLY_RE.match(plain)

            if m_text:
                current_opt = m_text.group(1)
                # Strip the option-letter prefix from the LaTeX text to keep
                # just the option content. In most papers the letter is bold
                # (\textbf{A}), but in the specimen it is plain (A), so both
                # forms are handled here.
                options[current_opt] = re.sub(
                    r'^(?:\\textbf\{[ABCD]\}|[ABCD])\s+', '', text
                ).strip()
            elif m_letter:
                current_opt          = plain.strip()
                options[current_opt] = None    # replaced by figure dict later
                is_diagram_opt       = True
            elif current_opt and options[current_opt] is not None:
                options[current_opt] += " " + text

        # ── Detect embedded-label diagram options ─────────────────────
        # Some questions (e.g. "Which AD/AS diagram best illustrates...")
        # have four image-only options with no separate text labels. After
        # the option parsing loop, all options will still be empty strings.
        # Flag this case so the figures block can handle it.
        embedded_diagram_opts = (
            opts_start == -1
            and all(v == "" for v in options.values())
        )
        if embedded_diagram_opts:
            is_diagram_opt = True

        # ── Determine figure presence ─────────────────────────────────
        stem_lower = stem_text.lower()
        has_figure = (
            any(phrase in stem_lower for phrase in FIGURE_PHRASES)
            or is_diagram_opt
        )

        notes = []
        if has_figure and not is_diagram_opt:
            notes.append("question contains a diagram - extracted as PNG")
        if is_diagram_opt and not embedded_diagram_opts:
            notes.append("answer options are diagrams - each extracted as a separate PNG")
        if embedded_diagram_opts:
            notes.append(
                "answer options are diagrams with embedded labels - "
                "extracted as separate PNGs by equal vertical split"
            )
        if "table below" in stem_lower:
            notes.append(
                "answer options in a table - text extracted but layout may be imperfect"
            )

        # ── Extract diagram images ────────────────────────────────────
        question_figure = None

        if figures_dir is not None:
            if embedded_diagram_opts:
                # No letter labels — split the blank page region into four
                # equal strips and extract each as a diagram option PNG.
                figure_paths = _extract_embedded_option_diagrams(
                    pdf_path, q_lines, pdf_stem, q_num, figures_dir
                )
                for letter, path in figure_paths.items():
                    options[letter] = {"figure": path}

            elif is_diagram_opt:
                # Standard diagram options with visible letter labels.
                figure_paths = _extract_option_diagrams(
                    pdf_path, option_lines, pdf_stem, q_num, figures_dir
                )
                for letter, path in figure_paths.items():
                    options[letter] = {"figure": path}

            elif has_figure:
                question_figure = _extract_question_diagram(
                    pdf_path, q_lines, stem_lines, pdf_stem, q_num, figures_dir
                )

        results.append({
            "question_number": q_num,
            "question_text":   stem_text,
            "options":         options,
            "question_figure": question_figure,
            "has_figure":      has_figure,
            "notes":           notes,
        })

    return results

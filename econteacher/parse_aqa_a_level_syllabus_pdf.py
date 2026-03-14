"""
parse_aqa_a_level_syllabus.py
------------------------------
Reads the downloaded AQA Economics spec PDF and extracts its content
into two structured Python dictionaries:
    - as_syllabus    : AS-level content (sections numbered 3.x.x.x)
    - alevel_syllabus: A-level content  (sections numbered 4.x.x.x)

The AQA spec PDF has three levels of heading, plus content bullet points:

    3.1          The operation of markets and market failure      ← SECTION (level 1)
        3.1.1    Economic methodology and the economic problem    ← SUBSECTION (level 2)
            3.1.1.1  Economic methodology                        ← TOPIC (level 3)
                     • Economics as a social science.            ← content bullet point

Each content page also has a two-column layout:
    Left column  — the main curriculum content (bullet points students must know)
    Right column — "Additional information" (guidance notes for teachers)

We separate these using the x-coordinate of each word on the page.
Words with x < 380 are in the left (content) column.
Words with x >= 380 are in the right (additional information) column.

The split between AS and A-level is determined by the top-level section number:
    Sections 3.x → AS syllabus
    Sections 4.x → A-level syllabus

NOTE: Section 4.1 ("Individuals, firms, markets and market failure") has no
explicit "4.1 Title" heading in the PDF — it jumps straight from introductory
text to subsection 4.1.1. We handle this by auto-creating the section entry
the first time we encounter a 4.1.x subsection.

NOTE: Some topic headings in the PDF are printed across two lines — the
section number appears alone on one line, and the title text on the next.
We handle this with a 'pending_number' mechanism that carries the number
forward to the next line.
"""

import pdfplumber    # third-party: extracts text and word positions from PDFs
import re            # standard library: pattern matching
import os


# Path to the downloaded PDF
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
PDF_PATH = os.path.join(DATA_DIR, "aqa_economics_spec.pdf")

# X-coordinate threshold that separates the two columns on content pages.
# Determined by inspecting word x-positions — the gap falls between ~380 and ~401.
COLUMN_SPLIT_X = 380

# Titles for sections that lack an explicit heading in the PDF.
# Section 4.1 has no "4.1 Title" line in the spec body — it's only in the TOC.
IMPLICIT_SECTION_TITLES = {
    "4.1": "Individuals, firms, markets and market failure",
}

# Lines to skip — structural labels that appear on every content page.
SKIP_LEFT_LINES = {"Content", "Additional information"}


# ---------------------------------------------------------------------------
# Heading patterns (regular expressions)
# ---------------------------------------------------------------------------
# ⚠️  SLIGHTLY ADVANCED: These are regular expressions — a mini-language for
#     describing text patterns. Compiled once here for efficiency.
#
# Matches a section number alone on a line, OR a number followed by a title.
#   LONE_NUMBER_RE  — e.g. just "3.1.2.4" with nothing after it
#   SECTION_RE      — e.g. "3.1 The operation of markets..."
#   SUBSECTION_RE   — e.g. "3.1.1 Economic methodology and..."
#   TOPIC_RE        — e.g. "3.1.1.1 Economic methodology"

# A number pattern on its own (no title on the same line).
# Covers 2-part (3.1), 3-part (3.1.1), and 4-part (3.1.1.1) numbers.
LONE_NUMBER_RE = re.compile(r"^(\d+\.\d+(?:\.\d+)*)$")

SECTION_RE    = re.compile(r"^(\d+\.\d+)(?!\.\d)\s+(.+)")
SUBSECTION_RE = re.compile(r"^(\d+\.\d+\.\d+)(?!\.\d)\s+(.+)")
TOPIC_RE      = re.compile(r"^(\d+\.\d+\.\d+\.\d+)\s+(.+)")

# Matches a trailing standalone page number at the end of a title string,
# e.g. "Individuals, firms, markets and market failure 31" → strip " 31"
TRAILING_PAGE_NUMBER_RE = re.compile(r"\s+\d+$")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _is_heading_overflow(right_text: str, right_font_size: float) -> bool:
    """
    Returns True if the right-column text on a heading line is the overflow
    of the heading title (and should be joined to it), rather than Additional
    Information prose (which should be ignored for the title).

    We use font size as the definitive signal:
        >= 12pt  →  heading font (AQAChevinPro-Medium at 13pt or 16pt)
                    → this is title overflow, include it
        <  12pt  →  body/additional-info font (ArialMT 11pt or ChevinPro-Light 8pt)
                    → this is Additional Info prose, do not include it

    This replaces the previous word-content heuristic, which was unreliable
    for long headings whose overflow happened to start with common words.
    """
    return bool(right_text) and right_font_size >= 12.0


def _clean_title(title: str) -> str:
    """
    Strips any trailing standalone page number from a title string.
    These appear in titles parsed from the table-of-contents pages,
    e.g. "Individuals, firms, markets and market failure 31" → correct title.
    """
    return TRAILING_PAGE_NUMBER_RE.sub("", title).strip()


def _get_or_create_section(syllabus: dict, section_number: str) -> dict:
    """
    Returns the section entry for section_number, creating it first if needed.
    Used to handle section 4.1, which has no explicit heading in the PDF body.
    """
    if section_number not in syllabus:
        title = IMPLICIT_SECTION_TITLES.get(section_number, f"Section {section_number}")
        syllabus[section_number] = {"title": title, "subsections": {}}
    return syllabus[section_number]


def _normalise_text(text: str) -> str:
    """
    Replaces typographic (curly) quote and apostrophe characters from the PDF
    with plain ASCII equivalents. This ensures the output only ever contains
    the standard straight apostrophe (') and straight double quote (").

    The PDF uses Unicode 'smart quotes' which are visually distinct but can
    cause problems when text is used programmatically (e.g. string matching).

    Characters replaced:
        \u2018  '  (left single quotation mark)   → ' (apostrophe)
        \u2019  '  (right single quotation mark)  → ' (apostrophe)
        \u201C  "  (left double quotation mark)   → " (double quote)
        \u201D  "  (right double quotation mark)  → " (double quote)
        \u2013  –  (en dash)                      → - (hyphen-minus)
        \u2014  —  (em dash)                      → - (hyphen-minus)
    """
    return (
        text
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201C", '"')
        .replace("\u201D", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )


def _infer_section_from_subsection(subsection_number: str) -> str:
    """
    Derives the parent section number from a subsection number.
    e.g. "4.1.1" → "4.1",  "3.2.3" → "3.2"
    """
    parts = subsection_number.split(".")
    return f"{parts[0]}.{parts[1]}"


# Pattern to detect whether a line starts with a heading number.
# Used in _join_multiline_headings to distinguish "this IS a new heading"
# from "this is a continuation of the previous heading".
_HEADING_NUMBER_START_RE = re.compile(r"^\d+\.\d+")


def _join_multiline_headings(pages: list[list[dict]]) -> list[list[dict]]:
    """
    Pre-processes the page lines to merge heading titles that wrap across
    multiple lines in the PDF.

    In the AQA spec, some section headings (16pt) are long enough to wrap
    onto a second line. The continuation line has the same 16pt font as the
    heading but no section number prefix, so the main parser would otherwise
    mistake it for body content.

    Example (before joining):
        line 1:  left="3.1.5 The market mechanism, market failure and"  left_font=16
        line 2:  left="intervention in markets"                          left_font=16
        line 3:  left="3.1.5.1 How markets and prices..."               left_font=13

    Example (after joining):
        line 1:  left="3.1.5 The market mechanism, market failure and intervention in markets"
        line 2:  left="3.1.5.1 How markets and prices..."

    The rule for joining:
        A line is a heading continuation if:
          - Its left_font_size >= 16  (it's in the large heading font)
          - Its left text does NOT start with a heading number (it has no number prefix)
          - The previous line was also a heading-font line (so we only join consecutive
            heading-font lines, not stray 16pt text elsewhere in the document)
    """
    # 12pt catches both 16pt section headings AND 13pt topic headings (both can wrap
    # across lines). 11pt body/additional-info text is safely below this threshold.
    HEADING_FONT_THRESHOLD = 12.0

    result = []

    for page_lines in pages:
        new_lines  = []
        i = 0

        while i < len(page_lines):
            line = page_lines[i]
            left_size = line["left_font_size"]

            # Is this line a heading (large font, starts with a section number)?
            is_heading_line = (
                left_size >= HEADING_FONT_THRESHOLD
                and _HEADING_NUMBER_START_RE.match(line["left"].strip())
            )

            if is_heading_line:
                # Absorb any immediately following continuation lines (same large
                # font, no number prefix) into this heading line.
                #
                # Crucially: right-column overflow text is merged INLINE with the
                # left-column text on the same visual line, not carried forward
                # separately. This preserves correct word order.
                #
                # e.g. line 1: L="3.1.5 The market mechanism... and"  R="government"
                #      line 2: L="intervention in markets"             R=""
                # → combined: "3.1.5 The market mechanism... and government intervention in markets"

                # Merge the first line's left + right inline.
                combined = line["left"]
                if line["right"] and line["right_font_size"] >= 12.0:
                    combined += " " + line["right"]

                j = i + 1
                while j < len(page_lines):
                    next_line      = page_lines[j]
                    next_left      = next_line["left"].strip()
                    next_left_size = next_line["left_font_size"]

                    is_continuation = (
                        next_left_size >= HEADING_FONT_THRESHOLD
                        and next_left
                        and not _HEADING_NUMBER_START_RE.match(next_left)
                    )

                    if is_continuation:
                        combined += " " + next_left
                        # Also absorb right-column overflow from the continuation line.
                        if next_line["right"] and next_line["right_font_size"] >= 12.0:
                            combined += " " + next_line["right"]
                        j += 1
                    else:
                        break

                new_lines.append({
                    "left":            combined,
                    "right":           "",    # right-column text already merged into left
                    "left_font_size":  left_size,
                    "right_font_size": 0.0,
                })
                i = j

            else:
                new_lines.append(line)
                i += 1

        result.append(new_lines)

    return result


# ---------------------------------------------------------------------------
# Step 1: Extract text from the PDF, separated into left/right columns per page
# ---------------------------------------------------------------------------

def extract_pages(pdf_path: str = PDF_PATH) -> list[list[dict]]:
    """
    Opens the PDF and extracts each page as a list of line dictionaries.

    Each line dictionary has two keys:
        "left"  — text from the Content column (x < COLUMN_SPLIT_X)
        "right" — text from the Additional Information column (x >= COLUMN_SPLIT_X)

    Returns a list of pages, where each page is a list of line dicts.
    """

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(
            f"PDF not found at: {pdf_path}\n"
            "Run download_aqa_a_level_syllabus.py first."
        )

    all_pages = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:

            # extract_words() gives us one dict per word, with position info.
            # ⚠️  SLIGHTLY ADVANCED: Word-level extraction lets us read x-coordinates
            #     so we can assign each word to the left or right column.
            words = page.extract_words()
            if not words:
                continue

            # Define vertical boundaries to exclude the page header and footer.
            # The running page header appears at ~2.5% from the top (y ≈ 21pt)
            # and the footer at ~95.5% from the top (y ≈ 804pt on an 842pt page).
            # We skip any content outside these bands, which prevents footer text
            # like "resources, support and administration" leaking into the output.
            header_cutoff = page.height * 0.05   # skip top 5%
            footer_cutoff = page.height * 0.94   # skip bottom 6%

            # Group words into lines by their vertical (y) position.
            # Words on the same line have slightly different 'top' values due to
            # font rendering, so we round to the nearest 3 points to group them.
            # ⚠️  SLIGHTLY ADVANCED: This is a common "bucketing" trick to cluster
            #     values that are "close enough" without a complex algorithm.
            lines_dict: dict[int, dict] = {}
            for word in words:
                # Skip words in the header or footer bands.
                if word["top"] < header_cutoff or word["top"] > footer_cutoff:
                    continue
                y_key = round(word["top"] / 3) * 3
                if y_key not in lines_dict:
                    lines_dict[y_key] = {"left": [], "right": []}
                if word["x0"] < COLUMN_SPLIT_X:
                    lines_dict[y_key]["left"].append(word)
                else:
                    lines_dict[y_key]["right"].append(word)

            # Also collect character-level font size data for both columns.
            # We need this for two purposes:
            #   - Right column: distinguish heading title overflow (13pt+) from
            #     Additional Information prose (11pt)
            #   - Left column: detect heading continuation lines (16pt) that carry
            #     the rest of a heading title onto the next line
            # page.chars gives one dict per character, each with 'size', 'x0', 'top'.
            # ⚠️  SLIGHTLY ADVANCED: We're going one level deeper than words here —
            #     reading individual characters so we can inspect their font sizes.
            col_char_sizes: dict[str, dict[int, list[float]]] = {"left": {}, "right": {}}
            for char in page.chars:
                # Apply the same header/footer exclusion as for words.
                if char["top"] < header_cutoff or char["top"] > footer_cutoff:
                    continue
                y_key = round(char["top"] / 3) * 3
                side  = "right" if char["x0"] >= COLUMN_SPLIT_X else "left"
                if y_key not in col_char_sizes[side]:
                    col_char_sizes[side][y_key] = []
                col_char_sizes[side][y_key].append(char["size"])

            # Sort lines top-to-bottom and reconstruct text for each column.
            # Record the maximum font size in each column per line.
            # Apply _normalise_text to replace curly quotes/apostrophes with
            # plain ASCII equivalents at the point of extraction.
            page_lines = []
            for y in sorted(lines_dict.keys()):
                left_words  = sorted(lines_dict[y]["left"],  key=lambda w: w["x0"])
                right_words = sorted(lines_dict[y]["right"], key=lambda w: w["x0"])
                left_sizes  = col_char_sizes["left"].get(y, [])
                right_sizes = col_char_sizes["right"].get(y, [])
                page_lines.append({
                    "left":            _normalise_text(" ".join(w["text"] for w in left_words)),
                    "right":           _normalise_text(" ".join(w["text"] for w in right_words)),
                    "left_font_size":  max(left_sizes)  if left_sizes  else 0.0,
                    "right_font_size": max(right_sizes) if right_sizes else 0.0,
                })

            all_pages.append(page_lines)

    print(f"Extracted {len(all_pages)} pages from PDF.")
    return all_pages


# ---------------------------------------------------------------------------
# Step 2: Parse the extracted lines into a structured syllabus dictionary
# ---------------------------------------------------------------------------

def parse_syllabus(pages: list[list[dict]]) -> dict:
    """
    Takes the page-by-page line data from extract_pages() and builds a
    nested dictionary representing the full syllabus structure.

    Returns a dict structured as:
        {
            "3.1": {
                "title": "The operation of markets and market failure",
                "subsections": {
                    "3.1.1": {
                        "title": "Economic methodology and the economic problem",
                        "topics": {
                            "3.1.1.1": {
                                "title": "Economic methodology",
                                "content": ["Economics as a social science.", ...],
                                "additional_info": ["Students should understand...", ...]
                            }
                        }
                    }
                }
            },
            "4.1": { ... },
            ...
        }

    Key parsing decisions:
    - Heading numbers that appear alone on a line (e.g. "3.1.2.4" with no title)
      are stored as 'pending', and the following line's text becomes the title.
    - Heading titles that overflow into the right column are joined if the right
      text doesn't look like Additional Information prose.
    - Bullet point continuation lines (no leading "•") are appended to the
      previous bullet rather than treated as new items.
    - Section 4.1 is auto-created when its first subsection is encountered,
      since the PDF has no explicit "4.1 Title" heading.
    """

    # Pre-process: join heading titles that wrap across multiple lines.
    # This must happen before the main parse loop so that every heading is
    # on a single line with its complete title.
    pages = _join_multiline_headings(pages)

    syllabus = {}

    # Track our current position in the hierarchy.
    current_section    = None
    current_subsection = None
    current_topic      = None

    # When a heading number appears alone on a line (e.g. "3.1.2.4" with no
    # title after it), we store it here and wait for the next line to provide
    # the title. This handles a specific PDF formatting quirk.
    pending_number: str | None = None

    for page_lines in pages:
        for line in page_lines:
            left  = line["left"].strip()
            right = line["right"].strip()

            # Skip blank lines and structural labels.
            if not left and not right:
                continue
            if left in SKIP_LEFT_LINES or right in SKIP_LEFT_LINES:
                continue
            if left.startswith("AQA AS and A-level"):
                continue

            # Skip page-footer lines like "16 Visit for the most up-to-date..."
            if re.match(r"^\d+\s+Visit\s+", left):
                continue

            # Skip chapter/section intro pages that appear between syllabus sections.
            # These pages carry text like "4 Subject content - A-level" or just
            # "Subject content - A-level" at the top, followed by introductory
            # paragraphs. They have no section numbers, so without this guard their
            # text would bleed into the last active topic (causing content blobs).
            # When we detect such a marker, we also reset current_topic to stop
            # collecting content until the next real topic heading is encountered.
            if re.match(r"^(\d+\s+)?Subject\s+content", left, re.IGNORECASE):
                current_topic = None
                continue

            # -------------------------------------------------------------------
            # Handle 'pending_number': a heading number found alone on a previous
            # line. The current line's left text should be the title.
            # -------------------------------------------------------------------
            if pending_number is not None:
                # Combine the pending number with this line's text to form a
                # complete heading string, then process it normally below.
                left = f"{pending_number} {left}"
                pending_number = None

            # -------------------------------------------------------------------
            # Check if this line contains ONLY a heading number (no title yet).
            # Store it as pending and move to the next line.
            # -------------------------------------------------------------------
            lone_match = LONE_NUMBER_RE.match(left)
            if lone_match and not right:
                pending_number = lone_match.group(1)
                continue

            # -------------------------------------------------------------------
            # Detect LEVEL 3 heading: e.g. "3.1.1.1 Economic methodology"
            # (checked before levels 2 and 1 to avoid partial matches)
            # -------------------------------------------------------------------
            topic_match = TOPIC_RE.match(left)
            if topic_match:
                number = topic_match.group(1)
                title  = _clean_title(topic_match.group(2))
                if _is_heading_overflow(right, line["right_font_size"]):
                    title = _clean_title(f"{title} {right}")

                current_topic = number

                # Ensure parent section and subsection exist.
                inferred_subsection = number.rsplit(".", 1)[0]        # e.g. "3.1.1"
                inferred_section    = _infer_section_from_subsection(inferred_subsection)  # e.g. "3.1"

                section = _get_or_create_section(syllabus, inferred_section)
                current_section = inferred_section

                if inferred_subsection not in section["subsections"]:
                    section["subsections"][inferred_subsection] = {
                        "title": f"Section {inferred_subsection}",
                        "topics": {}
                    }
                current_subsection = inferred_subsection

                section["subsections"][current_subsection]["topics"][number] = {
                    "title": title,
                    "content": [],
                    "additional_info": []
                }
                continue

            # -------------------------------------------------------------------
            # Detect LEVEL 2 heading: e.g. "3.1.1 Economic methodology and the economic problem"
            # -------------------------------------------------------------------
            subsection_match = SUBSECTION_RE.match(left)
            if subsection_match:
                number = subsection_match.group(1)
                title  = _clean_title(subsection_match.group(2))
                if _is_heading_overflow(right, line["right_font_size"]):
                    title = _clean_title(f"{title} {right}")

                current_subsection = number
                current_topic = None

                inferred_section = _infer_section_from_subsection(number)
                current_section  = inferred_section
                section = _get_or_create_section(syllabus, inferred_section)
                section["subsections"][number] = {"title": title, "topics": {}}
                continue

            # -------------------------------------------------------------------
            # Detect LEVEL 1 heading: e.g. "4.2 The national and international economy"
            # -------------------------------------------------------------------
            section_match = SECTION_RE.match(left)
            if section_match:
                number = section_match.group(1)
                title  = _clean_title(section_match.group(2))
                if _is_heading_overflow(right, line["right_font_size"]):
                    title = _clean_title(f"{title} {right}")

                current_section    = number
                current_subsection = None
                current_topic      = None

                # Use _get_or_create_section to avoid wiping subsections that were
                # already added (relevant for the TOC entry being read before the body).
                section = _get_or_create_section(syllabus, number)
                section["title"] = title
                continue

            # -------------------------------------------------------------------
            # Content lines — belong to the current topic.
            # -------------------------------------------------------------------
            if not (current_section and current_subsection and current_topic):
                continue

            topic_data = (
                syllabus
                .get(current_section, {})
                .get("subsections", {})
                .get(current_subsection, {})
                .get("topics", {})
                .get(current_topic)
            )
            if topic_data is None:
                continue

            # Left column: main syllabus content.
            if left:
                if left.startswith("•"):
                    # New bullet point — strip the "•" and start a new item.
                    clean = left.lstrip("•").strip()
                    if clean:
                        topic_data["content"].append(clean)
                elif topic_data["content"]:
                    # Continuation of the previous bullet — append to it.
                    # If the previous fragment ended with a hyphen or slash (a
                    # compound word or fraction broken across PDF lines), join
                    # without a space to avoid artefacts like "short- run".
                    prev = topic_data["content"][-1]
                    if prev.endswith("-") or prev.endswith("/"):
                        topic_data["content"][-1] += left
                    else:
                        topic_data["content"][-1] += " " + left

            # Right column: additional information for teachers.
            # The right column text wraps across multiple lines in the PDF, so
            # consecutive fragments belong to the same note. We only start a new
            # item when the text begins with a recognised paragraph-starter
            # (e.g. "Students should..."); otherwise we append to the previous item.
            # Note: here we use content-based detection (not font size) because all
            # Additional Info text is the same font size — we need the text itself
            # to detect where one note ends and the next begins.
            # These are the words/phrases that signal the start of a new guidance
            # note in the right column. If a line of right-column text begins with
            # any of these, we start a new additional_info item rather than
            # appending to the previous one.
            # "They " and "It " are common second-paragraph starters that were
            # previously missed, causing two distinct notes to merge into one.
            NEW_NOTE_STARTERS = (
                "Students", "A ", "Note:", "For ", "At AS", "At A-",
                "They ", "It ", "These ", "This ", "However,",
            )
            if right:
                if topic_data["additional_info"] and not right.startswith(NEW_NOTE_STARTERS):
                    # Same hyphenation fix as for content: if the previous fragment
                    # ended with a hyphen or slash, join without a space.
                    prev = topic_data["additional_info"][-1]
                    if prev.endswith("-") or prev.endswith("/"):
                        topic_data["additional_info"][-1] += right
                    else:
                        topic_data["additional_info"][-1] += " " + right
                else:
                    topic_data["additional_info"].append(right)

    return syllabus


# ---------------------------------------------------------------------------
# Step 3: Split the combined syllabus into AS and A-level dictionaries
# ---------------------------------------------------------------------------

def split_by_qualification(syllabus: dict) -> tuple[dict, dict]:
    """
    Splits the full parsed syllabus into two separate dictionaries:
        as_syllabus      — sections starting with "3." (AS content)
        alevel_syllabus  — sections starting with "4." (A-level content)
    """
    as_syllabus     = {}
    alevel_syllabus = {}

    for section_number, section_data in syllabus.items():
        if section_number.startswith("3."):
            as_syllabus[section_number] = section_data
        elif section_number.startswith("4."):
            alevel_syllabus[section_number] = section_data

    print(f"AS sections found:      {list(as_syllabus.keys())}")
    print(f"A-level sections found: {list(alevel_syllabus.keys())}")

    return as_syllabus, alevel_syllabus


# ---------------------------------------------------------------------------
# Quick test: run end-to-end and print a structural summary
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pages    = extract_pages()
    syllabus = parse_syllabus(pages)
    as_syl, alevel_syl = split_by_qualification(syllabus)

    for label, syl in [("AS", as_syl), ("A-LEVEL", alevel_syl)]:
        print(f"\n{'='*60}")
        print(f"  {label} SYLLABUS")
        print(f"{'='*60}")
        for sec_num, sec_data in syl.items():
            print(f"\n{sec_num}  {sec_data['title']}")
            for sub_num, sub_data in sec_data["subsections"].items():
                print(f"  {sub_num}  {sub_data['title']}")
                for top_num, top_data in sub_data["topics"].items():
                    n = len(top_data["content"])
                    print(f"    {top_num}  {top_data['title']}  ({n} content items)")

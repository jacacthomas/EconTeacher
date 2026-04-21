"""
scripts/extract_textbook_section.py
-----------------------
Exploratory extractor for a single section of the AQA Economics textbook.
Produces a JSON file + a readable text dump for verification.

Currently hard-coded to section 11.2, pages 378-391.

Usage:
    poetry run python scripts/extract_textbook_section.py
"""

import os
import sys
import json
import re
from collections import Counter
from itertools import groupby

import pdfplumber

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PDF_PATH     = os.path.join(PROJECT_ROOT, "data",
                            "AQA A-Level Economics (Ray Powell, James Powell).pdf")
OUT_JSON     = os.path.join(PROJECT_ROOT, "temp", "section_11_2.json")
OUT_TEXT     = os.path.join(PROJECT_ROOT, "temp", "section_11_2.txt")

START_PAGE   = 378   # 1-indexed; section 11.2 starts part-way through this page
END_PAGE     = 391   # inclusive; section 11.3 starts part-way through this page
SECTION_ID   = "11.2"


# ── Thresholds / filters ───────────────────────────────────────────────────────

# Left margin bar (coloured spine) runs from x≈15 to x≈57.
# Any character whose centre x is left of this is noise.
MARGIN_RIGHT_CUTOFF = 57.0

# Characters smaller than this in DIN-Regular are almost always left-margin
# vertical text noise (individual letters of "CAMBRIDGE" etc.).
NOISE_SIZE_CUTOFF = 8.9   # keeps Frutiger captions (≈8pt) but drops DIN micro-text

# Rect dimensions: ignore rects that are tiny (hairlines / artefacts) or the
# full-page spine bar (very tall, very narrow).
MIN_BOX_WIDTH  = 50.0
MIN_BOX_HEIGHT = 20.0


# ── Colour constants ───────────────────────────────────────────────────────────

def colour_hex(c):
    if c is None:
        return "#000000"
    if isinstance(c, (int, float)):
        v = int(c * 255)
        return f"#{v:02x}{v:02x}{v:02x}"
    if isinstance(c, (tuple, list)):
        if len(c) == 3:
            return "#{:02x}{:02x}{:02x}".format(*(int(x * 255) for x in c))
        if len(c) == 4:
            return f"cmyk{tuple(round(x, 2) for x in c)}"
    return str(c)


# Box header colour → canonical box type label (confirmed from content)
BOX_HEADER_COLOURS = {
    "#ba1410": "KEY_TERM",
    "#922583": "STUDY_TIP",
    "#f9b000": "SUMMARY",
    "#008ad0": "SYNOPTIC_LINK",
    "#8ebf25": "EXTENSION_MATERIAL",
    "#222f85": "TEST_YOURSELF",
    "#e87c0d": "CASE_STUDY",
    "#000000": "QUESTIONS",
}

# Chapter accent colour (orange for ch.11) used in subsection headings
CH11_ACCENT = "#ec5d10"
GREY_HEADING = "#455e6a"


# ── Rect / char geometry helpers ───────────────────────────────────────────────

def rect_x1(r):
    return r["x0"] + r["width"]

def rect_y1(r):
    return r["top"] + r["height"]

def char_centre(c):
    return ((c["x0"] + c["x1"]) / 2, (c["top"] + c["bottom"]) / 2)

def char_in_rect(c, r, margin=2.0):
    cx, cy = char_centre(c)
    return (r["x0"] - margin <= cx <= rect_x1(r) + margin and
            r["top"] - margin <= cy <= rect_y1(r) + margin)

def find_box_rects(page):
    """Return rects that are likely box borders (not spine bar, not hairlines)."""
    results = []
    for r in page.rects:
        w, h = r["width"], r["height"]
        if w < MIN_BOX_WIDTH or h < MIN_BOX_HEIGHT:
            continue
        # Skip the narrow spine bar at the far left
        if r["x0"] < 20 and w < 60:
            continue
        results.append(r)
    return results


# ── Character classification helpers ──────────────────────────────────────────

def is_margin_noise(c):
    """True for left-margin artefacts and micro-text."""
    cx, _ = char_centre(c)
    if cx < MARGIN_RIGHT_CUTOFF:
        return True
    size = c.get("size", 0)
    font = c.get("fontname", "")
    colour = colour_hex(c.get("non_stroking_color"))
    # Tiny DIN-Regular chars are vertical margin text
    if size < NOISE_SIZE_CUTOFF and "DIN" in font and "Italic" not in font:
        return True
    # DIN-RegularItalic at small sizes are vertical chapter label in right margin
    if size < 8.0 and "DIN-RegularItalic" in font:
        return True
    # Helvetica = printer imprint line at bottom of page
    if "Helvetica" in font:
        return True
    # Tiny subscript/superscript chars in body text (e.g. y₁, w_FE)
    if size < 8.0 and "BerkeleyStd" in font:
        return True
    if size < 7.0 and "Frutiger" in font:
        return True
    return False

def classify_line(size, colour, font):
    """
    Return an element type string for a line with these dominant properties.
    'box_header' is returned for size-12 DIN-Bold coloured lines inside boxes.
    """
    f = font  # shorthand
    if size >= 23 and "DIN-Light" in f and colour == GREY_HEADING:
        return "section"
    if size >= 17 and "DIN-Bold" in f and colour not in (GREY_HEADING, "#000000"):
        return "subsection"          # chapter accent colour
    if size >= 13 and "DIN-Bold" in f and colour == GREY_HEADING:
        return "subsubsection"
    if size >= 19 and "DIN-Regular" in f:
        return "subsubsection"    # alternate green style (e.g. #8ebf25) used in some chapters
    if size >= 12 and size < 13 and "DIN-Medium" in f and colour == "#000000":
        return "subsubsubsection"
    if size >= 11.5 and size < 13 and "DIN-Bold" in f:
        return "box_header"          # coloured box title
    if size >= 10.5 and "BerkeleyStd" in f:
        return "body"
    if size >= 9.5 and size < 11.5 and ("DIN" in f or "Bliss" in f):
        return "box_content"
    if size >= 7.5 and "Frutiger" in f:
        return "caption"             # figure / table caption
    if size >= 8.5 and "DIN-Light" in f and colour == "#000000":
        return "caption"
    if size >= 9 and "DIN-Bold" in f and colour == GREY_HEADING:
        return "figure_ref"          # "Figure X.Y" label in grey-blue DIN-Bold
    return "misc"


# ── Line reconstruction ────────────────────────────────────────────────────────

def reconstruct_lines(chars):
    """
    Group chars into lines by their top coordinate (2pt buckets).
    Returns list of dicts: {top, text, size, colour, font, chars, x0}.
    """
    def bucket(c):
        return round(c["top"] / 2) * 2

    lines = []
    sorted_chars = sorted(chars, key=lambda c: (bucket(c), c["x0"]))
    for top_bucket, group in groupby(sorted_chars, key=bucket):
        line_chars = list(group)
        text = "".join(c.get("text", "") for c in line_chars)
        text = text.strip()
        if not text:
            continue
        sizes   = [c.get("size", 0)          for c in line_chars if c.get("text", "").strip()]
        colours = [colour_hex(c.get("non_stroking_color")) for c in line_chars if c.get("text", "").strip()]
        fonts   = [c.get("fontname", "")     for c in line_chars if c.get("text", "").strip()]
        dom_size   = round(max(sizes), 1)              if sizes   else 0
        dom_colour = Counter(colours).most_common(1)[0][0] if colours else "#000000"
        dom_font   = Counter(fonts).most_common(1)[0][0]   if fonts   else ""
        x0 = min(c["x0"] for c in line_chars)
        lines.append({
            "top":    top_bucket,
            "x0":     x0,
            "text":   text,
            "size":   dom_size,
            "colour": dom_colour,
            "font":   dom_font,
            "chars":  line_chars,
        })
    return lines


# ── Box content parser ─────────────────────────────────────────────────────────

def parse_key_term_box(box_lines):
    """
    Parse KEY TERM box lines into a list of {term, definition} dicts.
    Term name:  DIN-Bold red (#ba1410), size 10 — may wrap across multiple lines
    Definition: DIN-Regular black, size 10 — follows immediately after term name
    A new term starts only when we see red bold AND the previous line was black
    (i.e. definition text), to avoid splitting a wrapped term name.
    """
    items = []
    current_term_parts = []
    current_def_parts  = []
    in_term = False

    for line in box_lines:
        is_red_bold = (line["colour"] == "#ba1410" and "Bold" in line["font"])
        is_black    = (line["colour"] == "#000000")

        if is_red_bold:
            if in_term:
                # Still the term name wrapping to a new line
                current_term_parts.append(line["text"])
            else:
                # New term starting (we were in a definition or at start)
                if current_term_parts:
                    items.append({
                        "term":       " ".join(current_term_parts).strip(),
                        "definition": " ".join(current_def_parts).strip(),
                    })
                current_term_parts = [line["text"]]
                current_def_parts  = []
                in_term = True
        elif is_black and current_term_parts:
            in_term = False
            current_def_parts.append(line["text"])
        # Ignore other colours (e.g. stray artefacts)

    if current_term_parts:
        items.append({
            "term":       " ".join(current_term_parts).strip(),
            "definition": " ".join(current_def_parts).strip(),
        })
    return items


def parse_generic_box(box_lines):
    """Return box content as a list of text strings (one per line)."""
    return [l["text"] for l in box_lines if l["text"]]


# ── Box assembler ──────────────────────────────────────────────────────────────

def assemble_box(box_lines):
    """
    Given all lines inside a box rect, return a structured box dict.
    First line should be the box header.
    Returns None if the box doesn't start with a recognised header colour
    (e.g. it's a diagram axis frame, not a content box).
    """
    if not box_lines:
        return None

    header_line = box_lines[0]
    # Strip leading non-letter characters from header (layout artifacts)
    header_text = re.sub(r'^[^A-Za-z]+', '', header_line["text"])
    header_colour = header_line["colour"]

    if header_colour not in BOX_HEADER_COLOURS:
        return None   # not a content box (e.g. diagram frame)

    box_type = BOX_HEADER_COLOURS[header_colour]

    # For black-header boxes, the colour alone is not distinctive enough
    # (diagram axis frames also produce black DIN-Bold first lines).
    # Validate by checking the header text matches a known pattern.
    if header_colour == "#000000":
        if not re.search(r'QUESTION', header_text, re.I):
            return None

    # Skip boxes with no content (can happen at page boundaries)
    if not box_lines[1:]:
        return None

    content_lines = box_lines[1:]

    if box_type == "KEY_TERM":
        parsed = parse_key_term_box(content_lines)
        return {"type": "box", "box_type": box_type,
                "header": header_text, "items": parsed}
    else:
        parsed = parse_generic_box(content_lines)
        return {"type": "box", "box_type": box_type,
                "header": header_text, "content": parsed}


# ── Main extraction ────────────────────────────────────────────────────────────

def extract_section(start_page, end_page, section_id):
    elements = []
    in_section = False  # skip content before section heading on start page
    section_title = None

    with pdfplumber.open(PDF_PATH) as pdf:
        for page_num in range(start_page, end_page + 1):
            page = pdf.pages[page_num - 1]
            all_chars = page.chars

            # ── Get box rects ─────────────────────────────────────────────────
            box_rects = find_box_rects(page)

            # ── Partition chars into box buckets vs. main flow ─────────────
            # A char can only belong to one box (first match wins).
            box_char_sets = {i: [] for i in range(len(box_rects))}
            main_chars = []

            for c in all_chars:
                if is_margin_noise(c):
                    continue
                assigned = False
                for i, r in enumerate(box_rects):
                    if char_in_rect(c, r):
                        box_char_sets[i].append(c)
                        assigned = True
                        break
                if not assigned:
                    main_chars.append(c)

            # ── Reconstruct main flow lines ───────────────────────────────────
            main_lines = reconstruct_lines(main_chars)

            # ── Reconstruct box lines ─────────────────────────────────────────
            boxes_on_page = []
            for i, r in enumerate(box_rects):
                b_lines = reconstruct_lines(box_char_sets[i])
                if b_lines:
                    boxes_on_page.append({
                        "top": r["top"],
                        "rect": r,
                        "lines": b_lines,
                    })
            boxes_on_page.sort(key=lambda b: b["top"])

            # ── Build a merged event stream (main lines + boxes) by y-pos ─────
            events = []
            for ml in main_lines:
                events.append({"y": ml["top"], "kind": "main", "data": ml})
            for b in boxes_on_page:
                events.append({"y": b["top"], "kind": "box", "data": b})
            events.sort(key=lambda e: e["y"])

            # ── Process events ────────────────────────────────────────────────
            SECTION_NUM_RE = re.compile(r'^\d+\.\d+\s')

            for event in events:
                if event["kind"] == "main":
                    line = event["data"]
                    etype = classify_line(line["size"], line["colour"], line["font"])
                    text  = line["text"]

                    if etype == "section":
                        if SECTION_NUM_RE.match(text):
                            if text.startswith(section_id + " ") or text.startswith(section_id + "\t"):
                                # Start of our target section
                                in_section = True
                                section_title = text[len(section_id):].strip()
                            elif in_section:
                                # A different numbered section heading — stop
                                in_section = False
                                break
                        else:
                            # Continuation line of a multi-line section heading
                            if in_section and section_title is not None:
                                section_title = section_title + " " + text
                        continue

                    if not in_section:
                        continue

                    # Skip page numbers (white DIN-Medium size 9)
                    if line["colour"] == "#ffffff":
                        continue

                    # Emit element
                    if etype in ("subsection", "subsubsection", "subsubsubsection"):
                        # Merge with previous element if it's the same heading level
                        # (multi-line headings)
                        if elements and elements[-1]["type"] == etype:
                            elements[-1]["text"] += " " + text
                        else:
                            elements.append({"type": etype, "text": text})
                    elif etype == "body":
                        # Merge consecutive body lines into paragraphs later
                        elements.append({"type": "body", "text": text})
                    elif etype in ("caption", "figure_ref"):
                        pass   # inline diagram labels — deferred (figures not yet extracted)
                    elif etype == "misc":
                        # Only emit if large enough to be meaningful (not subscripts etc.)
                        if line["size"] >= 9:
                            elements.append({"type": "UNKNOWN", "text": text,
                                              "debug": f"size={line['size']} colour={line['colour']} font={line['font']}"})

                elif event["kind"] == "box":
                    if not in_section:
                        continue
                    box_data = event["data"]
                    box_elem = assemble_box(box_data["lines"])
                    if box_elem:
                        elements.append(box_elem)

    return {
        "section_id":    section_id,
        "section_title": section_title,
        "elements":      elements,
    }


# ── Output helpers ─────────────────────────────────────────────────────────────

def merge_body_paragraphs(elements):
    """
    Consecutive body lines that were wrapped across PDF lines should be joined.
    We use a simple heuristic: join lines unless the previous line ends with '.'
    or '?' or ':' (paragraph break indicator).
    Actually for now, just join ALL consecutive body lines — easier to read
    and we can split later if needed.
    """
    merged = []
    buf = []
    for el in elements:
        if el["type"] == "body":
            buf.append(el["text"])
        else:
            if buf:
                merged.append({"type": "body", "text": " ".join(buf)})
                buf = []
            merged.append(el)
    if buf:
        merged.append({"type": "body", "text": " ".join(buf)})
    return merged


def to_text(result):
    lines = []
    lines.append(f"SECTION {result['section_id']}: {result['section_title']}")
    lines.append("=" * 70)
    for el in result["elements"]:
        t = el["type"]
        if t == "subsection":
            lines.append(f"\n  [SUBSECTION]  {el['text']}")
        elif t == "subsubsection":
            lines.append(f"\n    [SUBSUBSECTION]  {el['text']}")
        elif t == "subsubsubsection":
            lines.append(f"\n      [SUB3]  {el['text']}")
        elif t == "body":
            lines.append(f"  {el['text']}")
        elif t == "caption":
            lines.append(f"  [CAPTION]  {el['text']}")
        elif t == "box":
            lines.append(f"\n  ┌── {el['box_type']}: {el['header']} ──")
            if "items" in el:
                for item in el["items"]:
                    lines.append(f"  │  TERM: {item['term']}")
                    lines.append(f"  │  DEF:  {item['definition']}")
            elif "content" in el:
                for c in el["content"]:
                    lines.append(f"  │  {c}")
            lines.append(f"  └──")
        elif t.startswith("UNKNOWN"):
            lines.append(f"  [???:{el['debug']}]  {el['text']}")
    return "\n".join(lines)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    print(f"Extracting section {SECTION_ID} from pages {START_PAGE}–{END_PAGE}...")
    result = extract_section(START_PAGE, END_PAGE, SECTION_ID)
    result["elements"] = merge_body_paragraphs(result["elements"])

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"JSON saved: {OUT_JSON}")

    text_dump = to_text(result)
    with open(OUT_TEXT, "w", encoding="utf-8") as f:
        f.write(text_dump)
    print(f"Text dump: {OUT_TEXT}")

    print("\n" + text_dump[:3000])
    if len(text_dump) > 3000:
        print(f"\n... ({len(text_dump) - 3000} more chars — see {OUT_TEXT})")


if __name__ == "__main__":
    main()

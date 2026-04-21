"""
scripts/probe_textbook_page.py
------------------
Reconnaissance script: dumps raw pdfplumber data for a single page so we can
calibrate font sizes, colours, and rect coordinates for the textbook extractor.

Usage:
    poetry run python scripts/probe_textbook_page.py

Output sections:
    1. Unique font/size/colour combinations (sorted by size desc)
    2. Rects found on the page (potential box borders)
    3. Text lines reconstructed with font metadata
"""

import os
import sys
import pdfplumber
from collections import Counter

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PDF_PATH = os.path.join(PROJECT_ROOT, "data", "AQA A-Level Economics (Ray Powell, James Powell).pdf")

PAGE_NUMBER  = 378   # 1-indexed PDF page number (single page mode)
PAGE_RANGE   = (378, 391)  # inclusive, for multi-page summary mode


def colour_hex(c):
    """Convert a pdfplumber colour value to a readable string."""
    if c is None:
        return "None"
    if isinstance(c, (int, float)):
        v = int(c * 255)
        return f"#{v:02x}{v:02x}{v:02x}"
    if isinstance(c, (tuple, list)):
        if len(c) == 3:
            return "#{:02x}{:02x}{:02x}".format(*(int(x * 255) for x in c))
        if len(c) == 4:  # CMYK
            return f"cmyk{tuple(round(x, 2) for x in c)}"
    return str(c)


def main():
    with pdfplumber.open(PDF_PATH) as pdf:
        page = pdf.pages[PAGE_NUMBER - 1]  # 0-indexed

        chars = page.chars
        rects = page.rects
        lines_raw = page.extract_text_lines(return_chars=True) if hasattr(page, 'extract_text_lines') else []

        # ── 1. Unique font/size/colour combinations ───────────────────────────
        print(f"\n{'='*70}")
        print(f"  PAGE {PAGE_NUMBER}  —  {len(chars)} chars,  {len(rects)} rects")
        print(f"{'='*70}")

        print("\n── 1. Unique (fontname, size, colour) combinations ─────────────────")
        combos = Counter(
            (c.get("fontname", "?"), round(c.get("size", 0), 1), colour_hex(c.get("non_stroking_color")))
            for c in chars
        )
        for (font, size, colour), count in sorted(combos.items(), key=lambda x: -x[0][1]):
            print(f"  size={size:5.1f}  colour={colour}  font={font}  (×{count})")

        # ── 2. Rects ──────────────────────────────────────────────────────────
        print("\n── 2. Rects (potential box borders) ────────────────────────────────")
        if not rects:
            print("  (none)")
        for r in sorted(rects, key=lambda r: r["top"]):
            w = round(r["width"], 1)
            h = round(r["height"], 1)
            colour = colour_hex(r.get("non_stroking_color") or r.get("stroking_color"))
            print(f"  top={r['top']:6.1f}  left={r['x0']:5.1f}  w={w:6.1f}  h={h:6.1f}  colour={colour}")

        # ── 3. Text lines with font metadata ─────────────────────────────────
        print("\n── 3. Text lines (font size + colour + text) ───────────────────────")
        # Group chars into lines by their top coordinate (within 2pt tolerance).
        from itertools import groupby

        def line_key(c):
            return round(c["top"] / 2) * 2  # bucket to nearest 2pt

        sorted_chars = sorted(chars, key=lambda c: (line_key(c), c["x0"]))
        for top, group in groupby(sorted_chars, key=line_key):
            line_chars = list(group)
            text = "".join(c.get("text", "") for c in line_chars).strip()
            if not text:
                continue
            # Dominant font properties on this line
            sizes   = [c.get("size", 0) for c in line_chars if c.get("text", "").strip()]
            colours = [colour_hex(c.get("non_stroking_color")) for c in line_chars if c.get("text", "").strip()]
            fonts   = [c.get("fontname", "") for c in line_chars if c.get("text", "").strip()]
            dominant_size   = round(max(sizes), 1)   if sizes   else 0
            dominant_colour = Counter(colours).most_common(1)[0][0] if colours else "?"
            dominant_font   = Counter(fonts).most_common(1)[0][0]   if fonts   else "?"
            print(f"  y={top:6.1f}  sz={dominant_size:5.1f}  col={dominant_colour}  font={dominant_font[:30]:<30}  {text[:80]}")


def survey_range():
    """Print all unique (size, colour, font) combos seen across PAGE_RANGE."""
    from collections import Counter as C2
    combos = C2()
    with pdfplumber.open(PDF_PATH) as pdf:
        for page_num in range(PAGE_RANGE[0], PAGE_RANGE[1] + 1):
            for ch in pdf.pages[page_num - 1].chars:
                combos[(
                    round(ch.get("size", 0), 1),
                    colour_hex(ch.get("non_stroking_color")),
                    ch.get("fontname", "?"),
                )] += 1
    print(f"\nUnique (size, colour, font) across pages {PAGE_RANGE[0]}–{PAGE_RANGE[1]}:\n")
    for (size, colour, font), count in sorted(combos.items(), key=lambda x: -x[0][0]):
        print(f"  size={size:5.1f}  colour={colour}  font={font}  (×{count})")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "survey":
        survey_range()
    else:
        main()

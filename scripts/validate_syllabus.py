"""
validate_syllabus.py
---------------------
Compares the intermediate syllabus files produced by the PDF parser and the
web scraper, then writes the web-scraped version as the authoritative output.

The web-scraped version is used as the authoritative source because the AQA
website is clean, structured HTML that parses reliably. The PDF parser produces
the same content in almost all cases, but has some minor layout artefacts (e.g.
hyphenation at line breaks, text blobs from intro pages) that are hard to
eliminate completely.

The comparison is a DIAGNOSTIC step — it logs any differences between the two
sources so we can spot genuine discrepancies (e.g. the website and PDF disagree
on a piece of curriculum content). Differences are reported as warnings, but
they do not block the authoritative output from being written.

Usage:
    poetry run python scripts/validate_syllabus.py

Both sets of intermediate files must exist before running this script:
    output/intermediate/pdf/as_syllabus.json
    output/intermediate/pdf/alevel_syllabus.json
    output/intermediate/web/as_syllabus.json
    output/intermediate/web/alevel_syllabus.json

Run build_syllabus_from_pdf.py and build_syllabus_from_web.py first if needed.
"""

import os
import sys
import json
import yaml


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PDF_DIR         = os.path.join(os.path.dirname(__file__), "..", "output", "intermediate", "pdf")
WEB_DIR         = os.path.join(os.path.dirname(__file__), "..", "output", "intermediate", "web")
AUTHORITATIVE_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "authoritative")


def load_json(filepath: str) -> dict:
    """Loads a JSON file and returns its contents as a Python dictionary."""
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def save_yaml(data: dict, filepath: str) -> None:
    """Saves a Python dictionary as a YAML file."""
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=float("inf"))
    print(f"  Saved: {filepath}")


def save_json(data: dict, filepath: str) -> None:
    """Saves a Python dictionary as a JSON file."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {filepath}")


def _compare_dicts(pdf: dict, web: dict, path: str = "") -> list[str]:
    """
    Recursively compares two nested dictionaries and returns a list of
    human-readable descriptions of any differences found.

    'path' tracks where in the hierarchy we are, e.g. "3.1 > 3.1.1 > content[0]".
    This makes it easy to locate a discrepancy in the actual syllabus.

    ⚠️  SLIGHTLY ADVANCED: This function calls itself ('recursion') to handle
        nested dictionaries of arbitrary depth. Each call goes one level deeper
        until it reaches a value that isn't a dict (like a string or list).
    """
    differences = []

    # Check for keys present in one source but not the other.
    for key in set(pdf.keys()) | set(web.keys()):
        location = f"{path} > {key}" if path else str(key)

        if key not in pdf:
            differences.append(f"ONLY IN WEB:  {location}")
            continue
        if key not in web:
            differences.append(f"ONLY IN PDF:  {location}")
            continue

        pdf_val = pdf[key]
        web_val = web[key]

        # Recurse into nested dicts.
        if isinstance(pdf_val, dict) and isinstance(web_val, dict):
            differences.extend(_compare_dicts(pdf_val, web_val, location))

        # Compare lists element by element.
        elif isinstance(pdf_val, list) and isinstance(web_val, list):
            if len(pdf_val) != len(web_val):
                differences.append(
                    f"LIST LENGTH MISMATCH at {location}: "
                    f"PDF has {len(pdf_val)} items, web has {len(web_val)}"
                )
            else:
                for i, (p, w) in enumerate(zip(pdf_val, web_val)):
                    if p != w:
                        differences.append(
                            f"VALUE MISMATCH at {location}[{i}]:\n"
                            f"    PDF: {p!r}\n"
                            f"    WEB: {w!r}"
                        )

        # Compare scalar values (strings, numbers, etc.)
        elif pdf_val != web_val:
            differences.append(
                f"VALUE MISMATCH at {location}:\n"
                f"    PDF: {pdf_val!r}\n"
                f"    WEB: {web_val!r}"
            )

    return differences


def validate(name: str, pdf_path: str, web_path: str, out_dir: str) -> bool:
    """
    Loads one pair of intermediate files (PDF and web), logs any differences
    as warnings, then writes the web-scraped data as the authoritative output.

    Parameters:
        name     — short label for display (e.g. "AS" or "A-level")
        pdf_path — path to the PDF-generated JSON file
        web_path — path to the web-scraped JSON file
        out_dir  — directory to write authoritative files to

    Returns True if the web file was found and written successfully.
    Returns False only if a required file is missing.
    """
    print(f"\n--- Comparing {name} syllabus (PDF vs web) ---")

    # Check intermediate files exist.
    for path in [pdf_path, web_path]:
        if not os.path.exists(path):
            print(f"  ERROR: File not found: {path}")
            print("  Run build_syllabus_from_pdf.py and build_syllabus_from_web.py first.")
            return False

    pdf_data = load_json(pdf_path)
    web_data = load_json(web_path)

    differences = _compare_dicts(pdf_data, web_data)

    if differences:
        print(f"  WARNING — {len(differences)} difference(s) between PDF and web:")
        for diff in differences:
            print(f"    • {diff}")
    else:
        print(f"  PDF and web sources agree exactly.")

    # Always write the web-scraped data as the authoritative output.
    # The website is clean HTML that parses reliably; the PDF has minor layout
    # artefacts that are hard to eliminate completely. Any genuine content
    # discrepancies will have been flagged as warnings above.
    print(f"  Writing authoritative output from web source...")
    stem = os.path.splitext(os.path.basename(web_path))[0]  # e.g. "as_syllabus"
    save_yaml(web_data, os.path.join(out_dir, f"{stem}.yaml"))
    save_json(web_data, os.path.join(out_dir, f"{stem}.json"))

    return True


def main():
    os.makedirs(AUTHORITATIVE_DIR, exist_ok=True)

    as_ok = validate(
        name     = "AS",
        pdf_path = os.path.join(PDF_DIR, "as_syllabus.json"),
        web_path = os.path.join(WEB_DIR, "as_syllabus.json"),
        out_dir  = AUTHORITATIVE_DIR,
    )

    alevel_ok = validate(
        name     = "A-level",
        pdf_path = os.path.join(PDF_DIR, "alevel_syllabus.json"),
        web_path = os.path.join(WEB_DIR, "alevel_syllabus.json"),
        out_dir  = AUTHORITATIVE_DIR,
    )

    print()
    if as_ok and alevel_ok:
        print("Done. Authoritative files written to output/authoritative/")
    else:
        print("Could not write authoritative files — check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()

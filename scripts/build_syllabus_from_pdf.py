"""
build_syllabus_from_pdf.py
--------------------------
Builds intermediate syllabus files by downloading and parsing the AQA
Economics specification PDF.

Output files are written to output/intermediate/pdf/:
    as_syllabus.yaml / .json       — AS-level syllabus
    alevel_syllabus.yaml / .json   — A-level syllabus

These are *intermediate* files — they are later compared against the web-scraped
intermediate files by validate_syllabus.py to produce the authoritative outputs.

Usage:
    poetry run python scripts/build_syllabus_from_pdf.py

The PDF will only be downloaded if it doesn't already exist in data/.
"""

import os
import sys
import json
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from econteacher.download_aqa_a_level_syllabus_pdf import download_spec
from econteacher.parse_aqa_a_level_syllabus_pdf import extract_pages, parse_syllabus, split_by_qualification


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "intermediate", "pdf")


def save_yaml(data: dict, filepath: str) -> None:
    """Saves a Python dictionary as a YAML file — human-readable, indented format."""
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=float("inf"))
    print(f"Saved: {filepath}")


def save_json(data: dict, filepath: str) -> None:
    """Saves a Python dictionary as a JSON file — standard machine-readable format."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved: {filepath}")


def main():
    print("\n--- Step 1: Downloading PDF ---")
    download_spec()

    print("\n--- Step 2: Extracting text from PDF ---")
    pages = extract_pages()

    print("\n--- Step 3: Parsing syllabus structure ---")
    syllabus = parse_syllabus(pages)

    print("\n--- Step 4: Splitting by qualification ---")
    as_syllabus, alevel_syllabus = split_by_qualification(syllabus)

    print("\n--- Step 5: Saving intermediate output files ---")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    save_yaml(as_syllabus,     os.path.join(OUTPUT_DIR, "as_syllabus.yaml"))
    save_yaml(alevel_syllabus, os.path.join(OUTPUT_DIR, "alevel_syllabus.yaml"))
    save_json(as_syllabus,     os.path.join(OUTPUT_DIR, "as_syllabus.json"))
    save_json(alevel_syllabus, os.path.join(OUTPUT_DIR, "alevel_syllabus.json"))

    print("\nDone. Intermediate PDF files written to output/intermediate/pdf/")


if __name__ == "__main__":
    main()

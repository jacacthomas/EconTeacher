"""
build_syllabus_from_web.py
--------------------------
Builds intermediate syllabus files by scraping the AQA website directly.

Output files are written to output/intermediate/web/:
    as_syllabus.yaml / .json       — AS-level syllabus
    alevel_syllabus.yaml / .json   — A-level syllabus

These are *intermediate* files — they are later compared against the PDF-parsed
intermediate files by validate_syllabus.py to produce the authoritative outputs.

Usage:
    poetry run python scripts/build_syllabus_from_web.py

Requires an internet connection.
"""

import os
import sys
import json
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from econteacher.scrape_aqa_a_level_syllabus_web import scrape_all


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "intermediate", "web")


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
    print("\n--- Scraping AQA website ---")
    as_syllabus, alevel_syllabus = scrape_all()

    print("\n--- Saving intermediate output files ---")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    save_yaml(as_syllabus,     os.path.join(OUTPUT_DIR, "as_syllabus.yaml"))
    save_yaml(alevel_syllabus, os.path.join(OUTPUT_DIR, "alevel_syllabus.yaml"))
    save_json(as_syllabus,     os.path.join(OUTPUT_DIR, "as_syllabus.json"))
    save_json(alevel_syllabus, os.path.join(OUTPUT_DIR, "alevel_syllabus.json"))

    print("\nDone. Intermediate web files written to output/intermediate/web/")


if __name__ == "__main__":
    main()

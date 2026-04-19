"""
build_sow_from_docx.py
-----------------------
Downloads the AQA Economics Scheme of Work .docx file (if not already present),
parses it, and writes the result as JSON to output/authoritative/.

Source
------
The SOW is available from the AQA A-level Economics teaching resources page:
    https://www.aqa.org.uk/subjects/economics/a-level/economics-7136/teaching-resources

The direct download URL is stored in SOW_URL below. If AQA updates the file
and the URL changes, update SOW_URL accordingly.

The downloaded file is saved to:
    data/aqa_economics_sow.docx

If you already have the file at that path, the download step is skipped.

Usage:
    poetry run python scripts/build_sow_from_docx.py
"""

import os
import sys
import json
import requests

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from econteacher.parse_aqa_sow import parse_sow

SOW_URL  = ("https://www.aqa.org.uk/files/60e6c057-6e6e-4bbe-9f71-3b0268f82345"
            "/06e40190f47b4345e03a80a4496a6b8550e7e6b3.docx")
SOW_PATH = os.path.join(PROJECT_ROOT, "data", "aqa_economics_sow.docx")
OUT_DIR  = os.path.join(PROJECT_ROOT, "output", "authoritative")


def download_sow(url: str, save_path: str) -> None:
    if os.path.exists(save_path):
        print(f"SOW already exists at: {save_path}")
        return
    print(f"Downloading SOW from AQA...")
    response = requests.get(url, stream=True)
    response.raise_for_status()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Saved to: {save_path}")


def main():
    print("--- Step 1: Download SOW ---")
    download_sow(SOW_URL, SOW_PATH)

    print("\n--- Step 2: Parse SOW ---")
    sow = parse_sow(SOW_PATH)
    as_sections     = sow["as"]["sections"]
    alevel_sections = sow["alevel"]["sections"]
    print(f"  AS sections parsed:      {list(as_sections.keys())}")
    print(f"  A-level sections parsed: {list(alevel_sections.keys())}")

    print("\n--- Step 3: Save output ---")
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "sow.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sow, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {out_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()

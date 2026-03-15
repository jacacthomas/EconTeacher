"""
extract_mcqs.py
---------------
Extracts the 20 multiple-choice questions from Section A of an AQA AS
Economics Paper 1 question paper PDF and saves them as JSON.

Diagram images are saved as PNGs alongside the JSON file.

Usage:
    poetry run python scripts/extract_mcqs.py
"""

import os
import sys
import json

# Allow importing from the econteacher package in the parent directory.
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from econteacher.extract_mcqs import extract_mcqs


INPUT_PDF   = os.path.join(PROJECT_ROOT, "data", "past_papers", "as_paper_1", "qp", "june_2016_qp.pdf")
OUTPUT_DIR  = os.path.join(PROJECT_ROOT, "output", "mcqs")
FIGURES_DIR = os.path.join(OUTPUT_DIR, "figures")
OUTPUT_JSON = os.path.join(OUTPUT_DIR, "as_paper_1_june_2016.json")


def _make_relative(path):
    """Converts an absolute path to a path relative to the project root."""
    if path is None:
        return None
    return os.path.relpath(path, PROJECT_ROOT)


def main():
    os.makedirs(OUTPUT_DIR,  exist_ok=True)
    os.makedirs(FIGURES_DIR, exist_ok=True)

    print(f"Extracting MCQs from:\n  {INPUT_PDF}\n")
    questions = extract_mcqs(INPUT_PDF, figures_dir=FIGURES_DIR)
    print(f"Extracted {len(questions)} questions.\n")

    # Convert all figure paths to be relative to the project root.
    for q in questions:
        q["question_figure"] = _make_relative(q["question_figure"])
        for letter, opt in q["options"].items():
            if isinstance(opt, dict) and "figure" in opt:
                q["options"][letter] = {"figure": _make_relative(opt["figure"])}

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(questions, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON: {OUTPUT_JSON}\n")

    # Print a summary table.
    print(f"{'Q':>3}  {'Figures':<28}  {'Question text (first 55 chars)'}")
    print("-" * 90)
    for q in questions:
        # Summarise what images were produced for this question.
        img_parts = []
        if q["question_figure"]:
            img_parts.append("question diagram")
        for letter in "ABCD":
            opt = q["options"].get(letter)
            if isinstance(opt, dict) and "figure" in opt:
                img_parts.append(f"option {letter}")
        img_str = ", ".join(img_parts) if img_parts else "-"

        # Show first line of question text only (strip LaTeX newlines).
        preview = q["question_text"].split("\n")[0][:55]
        print(f"{q['question_number']:>3}  {img_str:<28}  {preview}")


if __name__ == "__main__":
    main()

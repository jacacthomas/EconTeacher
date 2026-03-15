"""
extract_all_as_paper1_mcqs.py
------------------------------
Extracts MCQs and answers from all AQA AS Economics Paper 1 past papers
and saves each as a JSON file.

For each paper the following is produced:
  - output/mcqs/as_paper_1_{session}.json   — questions, options, answers
  - output/mcqs/figures/mcq_{session}_*     — PNG images of any diagrams

Usage:
    poetry run python scripts/extract_all_as_paper1_mcqs.py
"""

import os
import sys
import json

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from econteacher.extract_mcqs        import extract_mcqs
from econteacher.extract_mcq_answers import extract_answer_key

QP_DIR  = os.path.join(PROJECT_ROOT, "data", "past_papers", "as_paper_1", "qp")
MS_DIR  = os.path.join(PROJECT_ROOT, "data", "past_papers", "as_paper_1", "ms")
OUT_DIR = os.path.join(PROJECT_ROOT, "output", "mcqs")
FIG_DIR = os.path.join(OUT_DIR, "figures")


def _make_relative(path):
    """Converts an absolute path to one relative to the project root."""
    if path is None:
        return None
    return os.path.relpath(path, PROJECT_ROOT)


def _session_from_filename(filename):
    """
    Derives a short session label from a filename, e.g.:
        "june_2016_qp.pdf"  →  "june_2016"
        "specimen_qp.pdf"   →  "specimen"
    """
    return filename.replace("_qp.pdf", "").replace("_ms.pdf", "")


def process_paper(session, qp_path, ms_path):
    """
    Extracts questions and answers for one paper and saves the result.

    Returns the path to the saved JSON file.
    """
    print(f"  Extracting questions ...", end="", flush=True)
    questions = extract_mcqs(qp_path, figures_dir=FIG_DIR)
    print(f" {len(questions)} questions extracted.")

    print(f"  Extracting answers  ...", end="", flush=True)
    try:
        answers = extract_answer_key(ms_path)
        print(f" {len(answers)} answers extracted.")
    except ValueError as e:
        print(f" WARNING: {e}")
        answers = {}

    # Merge answers into question dicts and make figure paths relative.
    for q in questions:
        ans = answers.get(q["question_number"], {})
        q["correct_answer"]      = ans.get("letter")
        q["answer_explanation"]  = ans.get("explanation")
        q["question_figure"]     = _make_relative(q["question_figure"])
        for letter, opt in q["options"].items():
            if isinstance(opt, dict) and "figure" in opt:
                q["options"][letter] = {"figure": _make_relative(opt["figure"])}

    out_path = os.path.join(OUT_DIR, f"as_paper_1_{session}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, indent=2, ensure_ascii=False)

    return out_path


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(FIG_DIR, exist_ok=True)

    # Discover all question papers and match each to its mark scheme.
    qp_files = sorted(f for f in os.listdir(QP_DIR) if f.endswith("_qp.pdf"))

    print(f"Found {len(qp_files)} question papers.\n")

    results = []
    for qp_file in qp_files:
        session = _session_from_filename(qp_file)
        ms_file = qp_file.replace("_qp.pdf", "_ms.pdf")
        qp_path = os.path.join(QP_DIR, qp_file)
        ms_path = os.path.join(MS_DIR, ms_file)

        print(f"[{session}]")

        if not os.path.exists(ms_path):
            print(f"  WARNING: mark scheme not found ({ms_file}), skipping.\n")
            continue

        out_path = process_paper(session, qp_path, ms_path)
        results.append((session, out_path))
        print(f"  Saved: {os.path.relpath(out_path, PROJECT_ROOT)}\n")

    print(f"Done. {len(results)} papers processed.")


if __name__ == "__main__":
    main()

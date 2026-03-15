"""
extract_mcq_answers.py
----------------------
Extracts the MCQ answer key from page 4 of an AQA AS Economics Paper 1
mark scheme PDF and appends the answers to the existing questions JSON.

The answer key is stored as a 4-column, 10-row table on page 4:
  col 1: question numbers 1–10
  col 2: answers for questions 1–10  (A/B/C/D)
  col 3: question numbers 11–20
  col 4: answers for questions 11–20 (A/B/C/D)

Usage:
    poetry run python scripts/extract_mcq_answers.py
"""

import os
import sys
import json

import pdfplumber

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

MARK_SCHEME_PDF = os.path.join(
    PROJECT_ROOT, "data", "past_papers", "as_paper_1", "ms", "june_2016_ms.pdf"
)
QUESTIONS_JSON = os.path.join(
    PROJECT_ROOT, "output", "mcqs", "as_paper_1_june_2016.json"
)
# Answer key page index (0-based). The key list is always on page 4.
ANSWER_PAGE_IDX = 3


def extract_answer_key(pdf_path, page_idx=ANSWER_PAGE_IDX):
    """
    Extracts the MCQ answer key from the given page of a mark scheme PDF.

    Returns a dict mapping question number (int) to answer letter (str),
    e.g. {1: "A", 2: "D", ..., 20: "D"}.
    """
    with pdfplumber.open(pdf_path) as pdf:
        page   = pdf.pages[page_idx]
        tables = page.extract_tables()

    if not tables:
        raise ValueError(f"No tables found on page {page_idx + 1} of {pdf_path}")

    # The answer key is the first (and only relevant) table on the page.
    # Each row has the format: [q_num_1, answer_1, q_num_2, answer_2]
    table = tables[0]
    answers = {}

    for row in table:
        if len(row) != 4:
            continue
        q1, a1, q2, a2 = row
        # Each cell should be a non-empty string.
        if q1 and a1:
            answers[int(q1)] = a1.strip()
        if q2 and a2:
            answers[int(q2)] = a2.strip()

    return answers


def main():
    print(f"Extracting answer key from:\n  {MARK_SCHEME_PDF}\n")
    answers = extract_answer_key(MARK_SCHEME_PDF)

    print("Answer key:")
    for q_num in sorted(answers):
        print(f"  Q{q_num:>2}: {answers[q_num]}")

    # Load the existing questions JSON and add the correct_answer field.
    with open(QUESTIONS_JSON, encoding="utf-8") as f:
        questions = json.load(f)

    for q in questions:
        q["correct_answer"] = answers.get(q["question_number"])

    with open(QUESTIONS_JSON, "w", encoding="utf-8") as f:
        json.dump(questions, f, indent=2, ensure_ascii=False)

    print(f"\nAdded answers to: {QUESTIONS_JSON}")


if __name__ == "__main__":
    main()

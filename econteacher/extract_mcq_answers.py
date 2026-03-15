"""
extract_mcq_answers.py
----------------------
Core logic for extracting the MCQ answer key from AQA Economics mark
scheme PDFs.

The answer key appears as a 4-column table under the heading "KEY LIST":
  col 1: question numbers 1–10
  col 2: answers for questions 1–10  (A/B/C/D)
  col 3: question numbers 11–20
  col 4: answers for questions 11–20 (A/B/C/D)

From 2022 onwards, answer cells also contain a brief explanation of why
that answer is correct (e.g. "B\n(most resources are scarce.)"). The
explanation is extracted separately and stored alongside the letter.

Some papers (e.g. specimen) do not produce a table when parsed, so a
plain-text fallback is used in that case.
"""

import re
import pdfplumber


def _parse_answer_cell(cell_text):
    """
    Extracts the answer letter and optional explanation from a table cell.

    Cell text is either a plain letter ("B") or a letter followed by an
    explanation on the next lines ("B\\n(most resources are scarce.)").

    Returns a dict:
        {"letter": "B", "explanation": "most resources are scarce."}
    or
        {"letter": "B", "explanation": None}
    """
    if not cell_text:
        return {"letter": None, "explanation": None}

    # Exception: the AS Paper 2 June 2016 mark scheme lists Q2's answer as
    # "Accept: A or D or A AND D". The question paper itself states "Only one
    # answer per question is allowed", so allowing two answers is anomalous.
    # The most likely explanation is that A was the intended answer but the
    # examiners later accepted D as well following complaints from teachers or
    # students. We record A as the canonical answer and store a note explaining
    # the situation in the explanation field so the ambiguity is visible in
    # the output JSON.
    if cell_text.strip().lower().startswith("accept"):
        m = re.search(r"\b([A-D])\b", cell_text)
        return {
            "letter": m.group(1) if m else None,
            "explanation": (
                "Judgement call: recorded as A. The mark scheme anomalously "
                "accepts 'A or D or A AND D', contradicting the question "
                "paper's instruction that only one answer is allowed. A was "
                "most likely the intended answer; D was probably accepted "
                "later in response to complaints from teachers or students."
            ),
        }

    lines = cell_text.strip().splitlines()
    letter = lines[0].strip()

    # Validate — must be a single A/B/C/D character.
    if not re.match(r"^[A-D]$", letter):
        # Try to pull the letter out if there's surrounding text.
        m = re.search(r"\b([A-D])\b", letter)
        letter = m.group(1) if m else None

    explanation = None
    if len(lines) > 1:
        # Join remaining lines, stripping surrounding parentheses.
        raw = " ".join(line.strip() for line in lines[1:]).strip()
        explanation = raw.strip("()")

    return {"letter": letter, "explanation": explanation or None}


def _extract_from_table(table):
    """
    Parses the 4-column KEY LIST table into a dict of answer dicts.

    Returns {question_number (int): {"letter": str, "explanation": str|None}}
    """
    answers = {}
    for row in table:
        if len(row) != 4:
            continue
        q1, a1, q2, a2 = row
        if q1 and a1:
            try:
                answers[int(q1)] = _parse_answer_cell(a1)
            except ValueError:
                pass
        if q2 and a2:
            try:
                answers[int(q2)] = _parse_answer_cell(a2)
            except ValueError:
                pass
    return answers


def _extract_from_text(text):
    """
    Fallback parser for when pdfplumber cannot detect the KEY LIST table.

    Each line of the key list contains one or two question/answer pairs,
    e.g. "1 D 11 A" or "10 B 20 C". Uses findall to extract all pairs
    from each line regardless of how many appear.

    Returns {question_number (int): {"letter": str, "explanation": None}}
    """
    answers = {}
    for line in text.splitlines():
        for q_str, letter in re.findall(r"\b(\d{1,2})\s+([A-D])\b", line):
            answers[int(q_str)] = {"letter": letter, "explanation": None}
    return answers


def extract_answer_key(pdf_path):
    """
    Extracts the 20-question MCQ answer key from a mark scheme PDF.

    Scans all pages for the one containing "KEY LIST", then parses the
    answer table on that page. Falls back to plain-text parsing if no
    table is found.

    Returns a dict mapping question number (int) to answer info:
        {1: {"letter": "A", "explanation": None}, ...}

    Raises ValueError if the KEY LIST page cannot be found.
    """
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "KEY LIST" not in text:
                continue

            # Found the KEY LIST page — try table extraction first.
            tables = page.extract_tables()
            if tables:
                answers = _extract_from_table(tables[0])
                if answers:
                    return answers

            # Table extraction failed — fall back to text parsing.
            answers = _extract_from_text(text)
            if answers:
                return answers

    raise ValueError(f"Could not find KEY LIST in {pdf_path}")

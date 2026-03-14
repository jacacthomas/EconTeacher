# EconTeacher

A Python toolkit for automating aspects of teaching and tutoring AQA A-level Economics.

## Setup

Requires Python 3.11+ and [Poetry](https://python-poetry.org/).

```bash
poetry install
```

## Generating the syllabus

```bash
poetry run python scripts/build_syllabus_from_pdf.py
poetry run python scripts/build_syllabus_from_web.py
poetry run python scripts/validate_syllabus.py
```

Authoritative syllabus files (AS and A-level, YAML and JSON) are written to `output/authoritative/`.

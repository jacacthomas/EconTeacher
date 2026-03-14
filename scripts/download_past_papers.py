"""
download_past_papers.py
-----------------------
Downloads all available AQA Economics past paper PDFs from
physicsandmathstutor.com and saves them to data/past_papers/.

Files are organised by paper series, then by type (QP/IN/MS):

    data/past_papers/
        as_paper_1/
            qp/   june_2016_qp.pdf  ...
            in/   june_2016_in.pdf  ...
            ms/   june_2016_ms.pdf  ...
        as_paper_2/
            qp/ in/ ms/
        alevel_paper_1/
            qp/ ms/               (no inserts for A-level papers 1 and 2)
        alevel_paper_2/
            qp/ ms/
        alevel_paper_3/
            qp/ in/ ms/

Already-downloaded files are skipped, so the script is safe to re-run.

Usage:
    poetry run python scripts/download_past_papers.py
"""

import os
import sys
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_URL  = "https://pmt.physicsandmathstutor.com/download/Economics/A-level/Past-Papers/AQA"
DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data", "past_papers")
HEADERS   = {"User-Agent": "Mozilla/5.0"}


def _make_url(series: str, doc_type: str, session: str) -> str:
    """
    Builds the download URL for one PDF.

    Parameters:
        series   — folder name on the server, e.g. "AS-Paper-1" or "Paper-3"
        doc_type — "QP", "IN", or "MS"
        session  — e.g. "June 2017" or "Specimen"

    Example output:
        https://pmt.physicsandmathstutor.com/.../AS-Paper-1/QP/June%202017%20QP.pdf
    """
    filename = f"{session} {doc_type}.pdf"
    # requests will percent-encode spaces and special characters in the URL.
    return f"{BASE_URL}/{series}/{doc_type}/{filename}"


def _make_local_path(local_dir: str, doc_type: str, session: str) -> str:
    """
    Returns the local file path where a PDF should be saved.

    Converts the session label to a snake_case filename, e.g.:
        "June 2017", "QP"  →  .../qp/june_2017_qp.pdf
        "Specimen",  "MS"  →  .../ms/specimen_ms.pdf
    """
    filename = session.lower().replace(" ", "_") + "_" + doc_type.lower() + ".pdf"
    folder   = os.path.join(local_dir, doc_type.lower())
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, filename)


def download_file(url: str, local_path: str) -> None:
    """
    Downloads a single PDF from url and saves it to local_path.
    Skips the download if the file already exists.
    """
    if os.path.exists(local_path):
        print(f"  Already exists, skipping: {os.path.basename(local_path)}")
        return

    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        with open(local_path, "wb") as f:
            f.write(response.content)
        print(f"  Downloaded: {os.path.basename(local_path)}")
    else:
        print(f"  FAILED ({response.status_code}): {url}")


def download_series(label: str, series: str, local_dir: str,
                    sessions: list[str], doc_types: list[str]) -> None:
    """
    Downloads all PDFs for one paper series (e.g. AS Paper 1).

    Parameters:
        label     — human-readable name for display, e.g. "AS Paper 1"
        series    — server-side folder name, e.g. "AS-Paper-1"
        local_dir — local directory to save files in, e.g. ".../as_paper_1"
        sessions  — list of session labels, e.g. ["June 2016", ..., "Specimen"]
        doc_types — list of document types to download, e.g. ["QP", "IN", "MS"]
    """
    print(f"\n--- {label} ---")
    os.makedirs(local_dir, exist_ok=True)

    for session in sessions:
        for doc_type in doc_types:
            url        = _make_url(series, doc_type, session)
            local_path = _make_local_path(local_dir, doc_type, session)
            download_file(url, local_path)


def main():
    # Sessions available for each paper series.
    # Note: there was no June 2021 AS exam (cancelled due to Covid).
    # A-level exams ran in 2021 under teacher-assessed grades.
    as_sessions     = ["June 2016", "June 2017", "June 2018", "June 2019",
                       "June 2020", "June 2022", "June 2023", "June 2024",
                       "Specimen"]
    alevel_sessions = ["June 2017", "June 2018", "June 2019", "June 2020",
                       "June 2021", "June 2022", "June 2023", "June 2024",
                       "Specimen"]

    download_series(
        label     = "AS Paper 1",
        series    = "AS-Paper-1",
        local_dir = os.path.join(DATA_DIR, "as_paper_1"),
        sessions  = as_sessions,
        doc_types = ["QP", "IN", "MS"],
    )

    download_series(
        label     = "AS Paper 2",
        series    = "AS-Paper-2",
        local_dir = os.path.join(DATA_DIR, "as_paper_2"),
        sessions  = as_sessions,
        doc_types = ["QP", "IN", "MS"],
    )

    download_series(
        label     = "A-level Paper 1",
        series    = "Paper-1",
        local_dir = os.path.join(DATA_DIR, "alevel_paper_1"),
        sessions  = alevel_sessions,
        doc_types = ["QP", "MS"],          # no inserts for A-level papers 1 and 2
    )

    download_series(
        label     = "A-level Paper 2",
        series    = "Paper-2",
        local_dir = os.path.join(DATA_DIR, "alevel_paper_2"),
        sessions  = alevel_sessions,
        doc_types = ["QP", "MS"],
    )

    download_series(
        label     = "A-level Paper 3",
        series    = "Paper-3",
        local_dir = os.path.join(DATA_DIR, "alevel_paper_3"),
        sessions  = alevel_sessions,
        doc_types = ["QP", "IN", "MS"],
    )

    print("\nDone.")


if __name__ == "__main__":
    main()

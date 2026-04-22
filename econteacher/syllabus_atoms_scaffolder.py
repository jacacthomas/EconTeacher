"""
syllabus_atoms_scaffolder.py

Reads the indexed AS and A-level AQA Economics syllabus JSON files and
produces blank pedagogical atoms scaffold files. Each syllabus content item
gets exactly one atom, with empty fields ready to be filled in later.

Input files  (relative to this script's location):
    ../output/authoritative/as_syllabus_content_indexed.json
    ../output/authoritative/alevel_syllabus_content_indexed.json

Output files (same directory as inputs):
    ../output/authoritative/as_syllabus_pedalogical_atoms_BLANK.json
    ../output/authoritative/alevel_syllabus_pedalogical_atoms_BLANK.json

Output structure
----------------
The output mirrors the hierarchy of the indexed syllabus files:
    section -> subsection -> topic -> content_item -> atoms

Each content item gets a single blank atom with the ID <content_item_id>.1
For example, content item 3.1.1.1.1 gets atom 3.1.1.1.1.1

Atom fields
-----------
    type         : null  (to be filled in later) — see docs/atom_types.txt
    atom_content : ""    (to be filled in later)
    notes        : ""    (to be filled in later)

Valid values for "type"
-----------------------
    definition   — State a precise definition of a key term
    concept      — Explain a concept, mechanism, or relationship in your own words
    diagram      — Draw, label, and/or interpret a specific diagram
    calculation  — Apply a formula or method to compute a numerical result
    application  — Use a concept or model to analyse an unfamiliar real-world context
    evaluation   — Assess strengths, limitations, or trade-offs of a theory, policy, or argument
    recall       — Memorise a specific fact, statistic, or institutional detail
                   (no deep understanding required; e.g. MPC inflation target = 2%)
"""

import json
import os
from datetime import date


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def make_blank_atom() -> dict:
    """
    Returns a single blank atom dict with all fields in their default state.
    This is the template that every content item starts with.
    """
    return {
        "type": None,
        "atom_content": "",
        "notes": ""
    }


def build_atoms_scaffold(indexed_syllabus: dict, syllabus_label: str) -> dict:
    """
    Walks the indexed syllabus and builds a parallel structure where each
    content item contains a single blank atom.

    Parameters
    ----------
    indexed_syllabus : the parsed JSON dict from one of the indexed files
    syllabus_label   : human-readable label for the metadata block
                       e.g. "AQA Economics AS Level"

    Returns
    -------
    A fully structured atoms scaffold dict, ready to be written to JSON.
    """

    scaffold = {
        "metadata": {
            "syllabus": syllabus_label,
            "version": "1.0",
            "created": str(date.today()),
            "last_updated": str(date.today())
        },
        "sections": {}
    }

    # Iterate over top-level sections (e.g. "3.1", "3.2" for AS)
    for section_id, section_data in indexed_syllabus.items():

        scaffold["sections"][section_id] = {
            "title": section_data["title"],
            "subsections": {}
        }

        # Iterate over subsections (e.g. "3.1.1", "3.1.2")
        for subsection_id, subsection_data in section_data["subsections"].items():

            subsection_node = {
                "title": subsection_data["title"],
                "topics": {
                    f"{subsection_id}.0": {
                        "title": "General subsection atoms",
                        "atoms": {f"{subsection_id}.0.1": make_blank_atom()}
                    }
                }
            }
            scaffold["sections"][section_id]["subsections"][subsection_id] = subsection_node

            # Iterate over topics (e.g. "3.1.1.1", "3.1.1.2")
            for topic_id, topic_data in subsection_data["topics"].items():

                topic_node = {
                    "title": topic_data["title"],
                    "content_items": {
                        f"{topic_id}.0": {
                            "text": "General topic atoms",
                            "atoms": {f"{topic_id}.0.1": make_blank_atom()}
                        }
                    }
                }
                subsection_node["topics"][topic_id] = topic_node

                # Iterate over indexed content items (e.g. "3.1.1.1.1", "3.1.1.1.2")
                for item_id, item_text in topic_data["content"].items():

                    # Each content item gets exactly one blank atom.
                    # The atom ID is the content item ID with ".1" appended.
                    atom_id = f"{item_id}.1"

                    topic_node["content_items"][item_id] = {
                        "text": item_text,
                        "atoms": {
                            atom_id: make_blank_atom()
                        }
                    }

    return scaffold


def process_syllabus_file(
    input_path: str,
    output_path: str,
    syllabus_label: str
) -> None:
    """
    Reads an indexed syllabus JSON file, builds the atoms scaffold, and
    writes the result.

    Parameters
    ----------
    input_path     : full path to the indexed syllabus .json file
    output_path    : full path where the atoms scaffold should be written
    syllabus_label : human-readable label used in the metadata block
    """

    print(f"Reading  : {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        indexed_syllabus = json.load(f)

    scaffold = build_atoms_scaffold(indexed_syllabus, syllabus_label)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(scaffold, f, indent=2, ensure_ascii=False)

    print(f"Written  : {output_path}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """
    Resolves file paths relative to this script's location and processes
    both the AS and A-level indexed syllabus files.
    """

    # Build an absolute path to the directory this script lives in
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # The input/output directory sits at ../output/authoritative relative
    # to the script
    authoritative_dir = os.path.normpath(
        os.path.join(script_dir, "..", "output", "authoritative")
    )

    # Each tuple is (input_filename, output_filename, syllabus_label)
    file_configs = [
        (
            "as_syllabus_content_indexed.json",
            "as_syllabus_pedagogical_atoms_BLANK.json",
            "AQA Economics AS Level"
        ),
        (
            "alevel_syllabus_content_indexed.json",
            "alevel_syllabus_pedagogical_atoms_BLANK.json",
            "AQA Economics A Level"
        ),
    ]

    for input_filename, output_filename, syllabus_label in file_configs:
        input_path  = os.path.join(authoritative_dir, input_filename)
        output_path = os.path.join(authoritative_dir, output_filename)

        if not os.path.exists(input_path):
            print(f"ERROR: Source file not found: {input_path}")
            print("       Have you run syllabus_indexer.py first?")
            continue

        process_syllabus_file(input_path, output_path, syllabus_label)

    print("\nDone.")


if __name__ == "__main__":
    main()

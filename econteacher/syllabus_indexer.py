"""
syllabus_indexer.py

Reads the raw AS and A-level AQA Economics syllabus JSON files and produces
indexed versions where every content item and additional_info item is given
a unique, hierarchical ID.

Input files  (relative to this script's location):
    ../output/authoritative/as_syllabus.json
    ../output/authoritative/alevel_syllabus.json

Output files (same directory as inputs):
    ../output/authoritative/as_syllabus_content_indexed.json
    ../output/authoritative/alevel_syllabus_content_indexed.json

ID convention
-------------
Content items      : <topic_id>.<n>      e.g. 3.1.1.1.1, 3.1.1.1.2
Additional info    : <topic_id>.A<n>     e.g. 3.1.1.1.A1, 3.1.1.1.A2

Using the "A" prefix for additional_info means a downstream application can
instantly tell from the ID alone which category an item belongs to.
"""

import json
import os


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def index_topic(topic_id: str, topic_data: dict) -> dict:
    """
    Takes a single topic dict (with 'title', 'content', 'additional_info'
    keys) and returns a new dict where the content and additional_info lists
    have been replaced by ordered dicts keyed by generated index IDs.

    Parameters
    ----------
    topic_id   : the dot-separated ID string for this topic, e.g. '3.1.1.1'
    topic_data : the raw topic dict from the source JSON

    Returns
    -------
    A new dict with the same structure but indexed content/additional_info.
    """

    indexed_topic = {
        "title": topic_data["title"]
    }

    # --- Index the main content items ---
    # Each item in the list gets a numeric suffix: <topic_id>.1, .2, .3 …
    indexed_content = {}
    for position, text in enumerate(topic_data.get("content", []), start=1):
        item_id = f"{topic_id}.{position}"
        indexed_content[item_id] = text

    indexed_topic["content"] = indexed_content

    # --- Index the additional_info items ---
    # Each item gets an alpha-numeric suffix: <topic_id>.A1, .A2 …
    # The "A" prefix clearly distinguishes these from content items.
    indexed_additional = {}
    for position, text in enumerate(topic_data.get("additional_info", []), start=1):
        item_id = f"{topic_id}.A{position}"
        indexed_additional[item_id] = text

    indexed_topic["additional_info"] = indexed_additional

    return indexed_topic


def index_syllabus(raw_syllabus: dict) -> dict:
    """
    Walks the full nested syllabus structure and applies index_topic() to
    every topic it finds.

    The expected nesting is:
        section -> subsections -> topics -> (title, content, additional_info)

    Parameters
    ----------
    raw_syllabus : the parsed JSON dict from one of the source files

    Returns
    -------
    A fully indexed copy of the syllabus dict.
    """

    indexed_syllabus = {}

    # Iterate over top-level sections (e.g. "3.1", "3.2" for AS)
    for section_id, section_data in raw_syllabus.items():

        indexed_syllabus[section_id] = {
            "title": section_data["title"],
            "subsections": {}
        }

        # Iterate over subsections (e.g. "3.1.1", "3.1.2")
        for subsection_id, subsection_data in section_data["subsections"].items():

            indexed_syllabus[section_id]["subsections"][subsection_id] = {
                "title": subsection_data["title"],
                "topics": {}
            }

            # Iterate over topics (e.g. "3.1.1.1", "3.1.1.2")
            for topic_id, topic_data in subsection_data["topics"].items():

                # index_topic() does the actual work of assigning IDs
                indexed_topic = index_topic(topic_id, topic_data)

                indexed_syllabus[section_id]["subsections"][subsection_id] \
                    ["topics"][topic_id] = indexed_topic

    return indexed_syllabus


def process_syllabus_file(input_path: str, output_path: str) -> None:
    """
    Reads a raw syllabus JSON file, indexes it, and writes the result.

    Parameters
    ----------
    input_path  : full path to the source .json file
    output_path : full path where the indexed .json file should be written
    """

    print(f"Reading  : {input_path}")

    # Read the raw syllabus file
    with open(input_path, "r", encoding="utf-8") as f:
        raw_syllabus = json.load(f)

    # Produce the indexed version
    indexed_syllabus = index_syllabus(raw_syllabus)

    # Write the result, using indent=2 for readable output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(indexed_syllabus, f, indent=2, ensure_ascii=False)

    print(f"Written  : {output_path}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """
    Resolves file paths relative to this script's location and processes
    both the AS and A-level syllabus files.
    """

    # Build an absolute path to the directory this script lives in.
    # Using __file__ means the script works correctly regardless of the
    # working directory it is called from.
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # The input/output directory is one level up from the script, then into
    # output/authoritative.
    authoritative_dir = os.path.join(script_dir, "..", "output", "authoritative")

    # Normalise the path (resolves the ".." cleanly on all platforms)
    authoritative_dir = os.path.normpath(authoritative_dir)

    # Define input and output file pairs as (input_filename, output_filename)
    file_pairs = [
        ("as_syllabus.json",      "as_syllabus_content_indexed.json"),
        ("alevel_syllabus.json",  "alevel_syllabus_content_indexed.json"),
    ]

    for input_filename, output_filename in file_pairs:
        input_path  = os.path.join(authoritative_dir, input_filename)
        output_path = os.path.join(authoritative_dir, output_filename)

        # Guard against missing source files with a clear error message
        if not os.path.exists(input_path):
            print(f"ERROR: Source file not found: {input_path}")
            print("       Check that the file exists and the directory structure is correct.")
            continue

        process_syllabus_file(input_path, output_path)

    print("\nDone.")


if __name__ == "__main__":
    main()
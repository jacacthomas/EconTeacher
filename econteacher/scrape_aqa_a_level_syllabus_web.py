"""
scrape_aqa_a_level_syllabus_web.py
------------------------------------
Scrapes the AQA Economics specification directly from the AQA website,
producing the same nested dictionary structure as the PDF parser.

The specification content lives across four pages — two for AS, two for A-level:

    AS-level:
        3.1  https://...the-operation-of-markets-and-market-failure
        3.2  https://...the-national-economy-in-a-global-context

    A-level:
        4.1  https://...individuals-firms-markets-and-market-failure
        4.2  https://...the-national-and-international-economy

HTML structure on each page (confirmed by manual inspection):
    <h2>   — section heading      e.g. "3.1 The operation of markets..."
    <h3>   — subsection heading   e.g. "3.1.1 Economic methodology..."
    <h4>   — topic heading        e.g. "3.1.1.1 Economic methodology"
    <table>
        <th>Content</th>          — marks the content column
        <td><ul><li>...</li></ul> — bullet point content items
        <th>Additional information</th>
        <td><span>...</span>      — teacher guidance notes

IMPORTANT — section numbering difference between website and PDF:
    The website uses 3.x numbering for BOTH the AS and A-level pages.
    The PDF uses 3.x for AS content and 4.x for A-level content.

    Website A-level page:  3.1 Individuals, firms, markets and market failure
    PDF A-level section:   4.1 Individuals, firms, markets and market failure

    To make the web output comparable to the PDF output, we remap all
    section numbers on the A-level pages from 3.x → 4.x when scraping.
    This is controlled by the 'remap_3_to_4' parameter in scrape_page().

The output dictionary structure is identical to that produced by
parse_aqa_a_level_syllabus_pdf.py, so the two can be directly compared
for validation purposes.
"""

import requests                      # fetches web pages
from bs4 import BeautifulSoup        # parses HTML
import re                            # pattern matching for section numbers


# The four URLs that together make up the full AQA Economics specification.
# Each URL corresponds to one top-level section (3.1, 3.2, 4.1, or 4.2).
AS_URLS = [
    "https://www.aqa.org.uk/subjects/economics/as-level/economics-7135/specification/subject-content/the-operation-of-markets-and-market-failure",
    "https://www.aqa.org.uk/subjects/economics/as-level/economics-7135/specification/subject-content/the-national-economy-in-a-global-context",
]

ALEVEL_URLS = [
    "https://www.aqa.org.uk/subjects/economics/a-level/economics-7136/specification/subject-content/individuals-firms-markets-and-market-failure",
    "https://www.aqa.org.uk/subjects/economics/a-level/economics-7136/specification/subject-content/the-national-and-international-economy",
]

# HTTP headers to send with each request.
# Some websites block requests that don't look like they come from a browser.
# Setting a User-Agent header makes our request look like a normal browser visit.
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Regular expressions to detect section numbers at the start of heading text.
# Used to extract the number (e.g. "3.1") from a heading like "3.1 The operation of..."
SECTION_NUMBER_RE    = re.compile(r"^(\d+\.\d+)(?!\.\d)")       # e.g. "3.1"
SUBSECTION_NUMBER_RE = re.compile(r"^(\d+\.\d+\.\d+)(?!\.\d)")  # e.g. "3.1.1"
TOPIC_NUMBER_RE      = re.compile(r"^(\d+\.\d+\.\d+\.\d+)")     # e.g. "3.1.1.1"


def _remap_section_numbers(data: dict) -> dict:
    """
    Remaps all section numbers in a scraped dict from the 3.x scheme used
    on the website's A-level pages to the 4.x scheme used in the PDF.

    e.g.  "3.1"     → "4.1"
          "3.1.2"   → "4.1.2"
          "3.2.1.3" → "4.2.1.3"

    The website uses 3.x for both AS and A-level pages. The PDF uses 3.x for
    AS and 4.x for A-level. We apply this remap only to the A-level pages so
    the two sources use a consistent numbering scheme.
    """
    remapped = {}
    for key, value in data.items():
        # Replace the leading "3." with "4." in every section number key.
        new_key = "4" + key[1:] if key.startswith("3") else key

        if isinstance(value, dict):
            # Recurse into nested dicts (subsections, topics).
            new_value = _remap_section_numbers(value)
        else:
            new_value = value

        remapped[new_key] = new_value

    return remapped


def _normalise_text(text: str) -> str:
    """
    Replaces curly/typographic quotes and dashes with plain ASCII equivalents.
    Kept in sync with the same function in parse_aqa_a_level_syllabus_pdf.py
    so that both sources produce identical text for comparison.
    """
    return (
        text
        .replace("\u2018", "'").replace("\u2019", "'")
        .replace("\u201C", '"').replace("\u201D", '"')
        .replace("\u2013", "-").replace("\u2014", "-")
    )


def _fetch_page(url: str) -> BeautifulSoup:
    """
    Downloads a page and returns a BeautifulSoup object for parsing its HTML.
    Raises an exception if the request fails.
    """
    print(f"  Fetching: {url}")
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _parse_content_table(table) -> tuple[list[str], list[str]]:
    """
    Extracts content bullet points and additional information from a topic's
    HTML table.

    The table has two columns:
        Column 1: "Content"              — <ul><li> bullet points
        Column 2: "Additional information" — <span> text blocks

    Returns:
        content        — list of strings, one per bullet point
        additional_info — list of strings, one per guidance note
    """
    content         = []
    additional_info = []

    # Find all table body rows — each row has one content cell and one
    # additional-info cell.
    rows = table.find("tbody")
    if not rows:
        return content, additional_info

    for row in rows.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        # Left cell: content bullet points in a <ul>
        left_cell  = cells[0]
        right_cell = cells[1]

        ul = left_cell.find("ul")
        if ul:
            for li in ul.find_all("li"):
                text = _normalise_text(li.get_text(strip=True))
                if text:
                    content.append(text)

        # Right cell: additional information.
        # The HTML structure is inconsistent across topics on the AQA website:
        #   - Some cells:  <td><span>full note text</span></td>
        #   - Other cells: <td><p>note 1</p><p>note 2</p></td>
        # We search for direct child <p> and <span> elements (recursive=False
        # ensures we only get top-level tags, not <strong> or <em> nested
        # inside them). Each top-level element is treated as a separate note.
        #
        # We pass " " as the separator to get_text() so that inline emphasis
        # elements (e.g. <strong>not</strong>) don't merge with surrounding
        # words. The website also inserts HTML comment nodes (<!-- -->) around
        # inline elements as a React rendering artefact; these are ignored by
        # get_text(), and the space separator bridges the gap correctly.
        for block in right_cell.find_all(["p", "span"], recursive=False):
            text = _normalise_text(block.get_text(" ", strip=True))
            if text:
                additional_info.append(text)

    return content, additional_info


def scrape_page(url: str, remap_3_to_4: bool = False) -> dict:
    """
    Scrapes a single AQA specification page and returns a dictionary
    representing one top-level section (e.g. section 3.1 or 4.2).

    The returned structure matches the PDF parser output:
        {
            "3.1": {
                "title": "The operation of markets and market failure",
                "subsections": {
                    "3.1.1": {
                        "title": "Economic methodology and the economic problem",
                        "topics": {
                            "3.1.1.1": {
                                "title": "Economic methodology",
                                "content": ["Economics as a social science.", ...],
                                "additional_info": ["Students should understand..."]
                            }
                        }
                    }
                }
            }
        }
    """

    soup = _fetch_page(url)

    # The specification content lives inside a <div> with the class
    # "subject-specification". Everything else on the page (navigation,
    # footer, etc.) is outside this container.
    spec_div = soup.find("div", class_="subject-specification")
    if not spec_div:
        raise ValueError(f"Could not find subject-specification div on: {url}")

    section_data = {}
    current_section_num    = None
    current_subsection_num = None

    # Iterate through every element inside the spec div in document order.
    # ⚠️  SLIGHTLY ADVANCED: .children gives us the direct child elements of
    #     spec_div. .descendants would give everything nested inside — we use
    #     .children here because the h2/h3/h4/table elements are all at the
    #     same level inside the spec div, not nested inside each other.
    #
    # We also use a recursive helper to flatten nested tags, since BeautifulSoup
    # returns both Tag objects and NavigableString objects as children.
    for element in spec_div.find_all(["h2", "h3", "h4", "table"], recursive=True):

        tag = element.name
        text = _normalise_text(element.get_text(" ", strip=True))

        # ---------------------------------------------------------------
        # <h2> — top-level section heading, e.g. "3.1 The operation of..."
        # ---------------------------------------------------------------
        if tag == "h2":
            match = SECTION_NUMBER_RE.match(text)
            if match:
                num   = match.group(1)
                title = text[len(num):].strip()
                current_section_num    = num
                current_subsection_num = None
                section_data[num] = {"title": title, "subsections": {}}

        # ---------------------------------------------------------------
        # <h3> — subsection heading, e.g. "3.1.1 Economic methodology..."
        # ---------------------------------------------------------------
        elif tag == "h3":
            match = SUBSECTION_NUMBER_RE.match(text)
            if match and current_section_num:
                num   = match.group(1)
                title = text[len(num):].strip()
                current_subsection_num = num
                section_data[current_section_num]["subsections"][num] = {
                    "title": title,
                    "topics": {}
                }

        # ---------------------------------------------------------------
        # <h4> — topic heading, e.g. "3.1.1.1 Economic methodology"
        # ---------------------------------------------------------------
        elif tag == "h4":
            match = TOPIC_NUMBER_RE.match(text)
            if match and current_section_num and current_subsection_num:
                num   = match.group(1)
                title = text[len(num):].strip()
                # Add the topic entry — content will be filled when we hit
                # the <table> immediately following this heading.
                section_data[current_section_num]["subsections"][current_subsection_num]["topics"][num] = {
                    "title": title,
                    "content": [],
                    "additional_info": []
                }

        # ---------------------------------------------------------------
        # <table> — content + additional information for the current topic
        # ---------------------------------------------------------------
        elif tag == "table":
            if not (current_section_num and current_subsection_num):
                continue

            # Find the most recently added topic in the current subsection.
            topics = section_data[current_section_num]["subsections"][current_subsection_num]["topics"]
            if not topics:
                continue

            # The last topic in insertion order is the one this table belongs to.
            # ⚠️  SLIGHTLY ADVANCED: In Python 3.7+, regular dicts remember the
            #     order items were inserted. So 'next(reversed(topics))' gives us
            #     the key of the most recently added topic — the one whose <h4>
            #     we just processed.
            last_topic_num = next(reversed(topics))
            content, additional_info = _parse_content_table(element)
            topics[last_topic_num]["content"]         = content
            topics[last_topic_num]["additional_info"] = additional_info

    if remap_3_to_4:
        section_data = _remap_section_numbers(section_data)

    return section_data


def scrape_all() -> tuple[dict, dict]:
    """
    Scrapes all four AQA specification pages and returns two dictionaries:
        as_syllabus     — sections 3.1 and 3.2 (AS-level content)
        alevel_syllabus — sections 4.1 and 4.2 (A-level content)
    """
    as_syllabus     = {}
    alevel_syllabus = {}

    print("Scraping AS-level pages...")
    for url in AS_URLS:
        section = scrape_page(url, remap_3_to_4=False)
        as_syllabus.update(section)

    print("\nScraping A-level pages...")
    for url in ALEVEL_URLS:
        # The A-level website pages use 3.x numbering; remap to 4.x to match the PDF.
        section = scrape_page(url, remap_3_to_4=True)
        alevel_syllabus.update(section)

    print(f"\nAS sections scraped:      {list(as_syllabus.keys())}")
    print(f"A-level sections scraped: {list(alevel_syllabus.keys())}")

    return as_syllabus, alevel_syllabus


# Quick test when run directly.
if __name__ == "__main__":
    as_syl, alevel_syl = scrape_all()

    for label, syl in [("AS", as_syl), ("A-LEVEL", alevel_syl)]:
        print(f"\n{'='*60}\n  {label}\n{'='*60}")
        for sec_num, sec in syl.items():
            print(f"\n{sec_num}  {sec['title']}")
            for sub_num, sub in sec["subsections"].items():
                print(f"  {sub_num}  {sub['title']}")
                for top_num, top in sub["topics"].items():
                    print(f"    {top_num}  {top['title']}  ({len(top['content'])} content items)")

"""
parse_aqa_sow.py
----------------
Parses the AQA Economics Scheme of Work .docx file into a structured dict.

The document structure (pages 1-4 are skipped automatically):

  Heading 2  : "3.0 AS Subject content" / "4.0 A-level Subject content"
  Normal      : "3.1 <title>"             — section header
  Normal      : intro paragraph(s)
  Normal      : "3.1.1 <title>"           — subsection header
  [Normal "Note" + note body]              — optional subsection-level note

  Then one or more teaching bundles per subsection, each comprising:
    Normal      : "Specification content and reference"  (or "...reference and content")
    Normal      : "3.1.1.1 <title>"        — topic header
    List Para   : spec content bullet
    [more topics + bullets]
    Normal      : "Learning outcomes"
    [Optional Normal "Be able to:"]
    List Para / Normal : learning outcome items
    [Optional Normal "Note" + note body (Normal or List Paragraph lines)]
    Normal      : "Suggested timing"
    Normal      : "<N> hour(s)"
    Normal      : "Possible teaching and learning activities"
    List Para   : activity items
    Normal      : "Resources"
    List Para / Normal : resource items (may contain hyperlinks)

Note bodies may span multiple List Paragraph lines. The note ends when a
structural marker (bundle label, heading number, etc.) is encountered.

Output dict schema
------------------
{
  "as": {
    "title": "AS Subject content",
    "sections": {
      "3.1": {
        "title": "...",
        "intro": "...",
        "note":  null,
        "subsections": {
          "3.1.1": {
            "title": "...",
            "note":  null,
            "teaching_bundles": [
              {
                "topics": {
                  "3.1.1.1": {
                    "title":        "...",
                    "spec_content": ["...", ...]
                  }
                },
                "learning_outcomes": ["...", ...],
                "note":              null,
                "suggested_timing":  "1 hour",
                "activities":        ["...", ...],
                "resources": [
                  {"text": "...", "links": [{"text": "...", "url": "..."}]}
                ]
              }
            ]
          }
        }
      }
    }
  },
  "alevel": { ... }
}
"""

import re
import docx
from docx.oxml.ns import qn


# ── Regex patterns ─────────────────────────────────────────────────────────────

SECTION_RE    = re.compile(r'^(\d+\.\d+)(?!\.\d)\s+(.+)')
SUBSECTION_RE = re.compile(r'^(\d+\.\d+\.\d+)(?!\.\d)\s+(.+)')
TOPIC_RE      = re.compile(r'^(\d+\.\d+\.\d+\.\d+)\s*(.*)')


# ── Bundle field labels ────────────────────────────────────────────────────────

BUNDLE_FIELD_LABELS = {
    'Specification content and reference': 'spec_content',
    'Specification reference and content': 'spec_content',
    'Learning outcomes':                   'learning_outcomes',
    'Suggested timing':                    'timing',
    'Possible teaching and learning activities': 'activities',
    'Resources':                           'resources',
}

NOTE_LABELS = {'Note', 'Note:'}

SKIP_NORMAL = {
    'Be able to:',
    'Continued from previous section.',
    'Version 1.0',
    'Contents',
}

_MONTH_YEAR_RE = re.compile(
    r'^(January|February|March|April|May|June|July|August|'
    r'September|October|November|December)\s+\d{4}$'
)


# ── Hyperlink extraction ───────────────────────────────────────────────────────

def _extract_links(para):
    """Returns [{"text": str, "url": str}] for every hyperlink in the paragraph."""
    links = []
    for hyperlink in para._element.findall('.//' + qn('w:hyperlink')):
        r_id = hyperlink.get(qn('r:id'))
        if not r_id:
            continue
        try:
            url = para.part.rels[r_id].target_ref
        except KeyError:
            continue
        link_text = ''.join(
            node.text for node in hyperlink.findall('.//' + qn('w:t'))
            if node.text
        )
        if link_text and url:
            links.append({"text": link_text, "url": url})
    return links


def _as_resource(para):
    """Returns {"text": str, "links": [...]} for a resource paragraph."""
    return {"text": para.text.strip(), "links": _extract_links(para)}


# ── Structural-marker detection ────────────────────────────────────────────────

def _is_structural_normal(text: str) -> bool:
    """
    Returns True if a Normal-style paragraph with this text should end an
    in-progress note and be processed as a structural element.
    """
    return (
        text in BUNDLE_FIELD_LABELS
        or text in NOTE_LABELS
        or bool(TOPIC_RE.match(text))
        or bool(SUBSECTION_RE.match(text))
        or bool(SECTION_RE.match(text))
    )


# ── Main parse function ────────────────────────────────────────────────────────

def parse_sow(docx_path: str) -> dict:
    """
    Parses the AQA Economics SOW .docx file.

    Parameters
    ----------
    docx_path : path to the .docx file

    Returns
    -------
    dict with keys "as" and "alevel".
    """
    doc = docx.Document(docx_path)

    result = {
        "as":     {"title": "AS Subject content",      "sections": {}},
        "alevel": {"title": "A-level Subject content",  "sections": {}},
    }

    current_qual          = None
    current_section_id    = None
    current_subsection_id = None
    current_bundle        = None
    current_topic_id      = None
    current_field         = None

    # Note accumulation: note body may span Normal and List Paragraph lines.
    # Collection ends when a structural Normal marker is encountered.
    in_note     = False
    note_target = None   # 'bundle' or 'section'
    note_lines  = []     # accumulated note body lines

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _new_bundle():
        return {
            "topics":            {},
            "learning_outcomes": [],
            "note":              None,
            "suggested_timing":  None,
            "activities":        [],
            "resources":         [],
        }

    def _save_bundle():
        nonlocal current_bundle, current_topic_id, current_field
        if current_bundle is None:
            return
        if (current_qual and current_section_id and current_subsection_id
                and current_bundle["topics"]):
            (result[current_qual]["sections"]
             [current_section_id]["subsections"]
             [current_subsection_id]["teaching_bundles"]
             .append(current_bundle))
        current_bundle   = None
        current_topic_id = None
        current_field    = None

    def _current_subsection():
        if current_qual and current_section_id and current_subsection_id:
            return (result[current_qual]["sections"]
                    [current_section_id]["subsections"]
                    .get(current_subsection_id))
        return None

    def _apply_note(lines):
        """Attach accumulated note lines to the appropriate target."""
        if not lines:
            return
        note_text = ' '.join(lines)
        if note_target == 'bundle' and current_bundle is not None:
            current_bundle["note"] = note_text
        elif note_target == 'section':
            sub = _current_subsection()
            if sub is not None:
                sub["note"] = note_text
            elif current_section_id:
                sec = result[current_qual]["sections"].get(current_section_id)
                if sec:
                    sec["note"] = note_text

    def _end_note():
        nonlocal in_note, note_target, note_lines
        _apply_note(note_lines)
        in_note     = False
        note_target = None
        note_lines  = []

    # ── Main loop ─────────────────────────────────────────────────────────────

    for para in doc.paragraphs:
        style = para.style.name
        text  = para.text.strip()

        if not text:
            continue

        # ── Heading 2 always ends any active note and resets state ────────────
        if style == 'Heading 2':
            _end_note()
            _save_bundle()
            if '3.0' in text:
                current_qual = 'as'
            elif '4.0' in text:
                current_qual = 'alevel'
            current_section_id    = None
            current_subsection_id = None
            continue

        if current_qual is None:
            continue

        # ── List Paragraph ────────────────────────────────────────────────────
        if style == 'List Paragraph':
            if in_note:
                note_lines.append(text)
                continue

            if current_bundle is None or current_field is None:
                continue

            if current_field == 'spec_content' and current_topic_id:
                current_bundle["topics"][current_topic_id]["spec_content"].append(text)
            elif current_field == 'learning_outcomes':
                current_bundle["learning_outcomes"].append(text)
            elif current_field == 'activities':
                current_bundle["activities"].append(text)
            elif current_field == 'resources':
                current_bundle["resources"].append(_as_resource(para))
            continue

        # ── Normal paragraph ──────────────────────────────────────────────────
        if style != 'Normal':
            continue

        # If we're accumulating a note, check whether this Normal para ends it.
        if in_note:
            # For section-level notes, the first Normal paragraph is always
            # note body — even if it starts with a section/subsection number
            # (e.g. the 4.1.1 reference note). Only terminate on a structural
            # marker once at least one line has been collected.
            # For bundle-level notes, terminate as soon as any structural
            # marker is seen (the note body is List Paragraphs in that case).
            if _is_structural_normal(text) and (note_target == 'bundle' or note_lines):
                _end_note()
                # Fall through to process this structural paragraph normally.
            else:
                note_lines.append(text)
                continue

        # ── Skip known boilerplate ────────────────────────────────────────────
        if text in SKIP_NORMAL or _MONTH_YEAR_RE.match(text):
            continue

        # ── Note label ────────────────────────────────────────────────────────
        if text in NOTE_LABELS:
            in_note     = True
            note_target = 'bundle' if current_bundle is not None else 'section'
            note_lines  = []
            continue

        # ── Bundle field label ────────────────────────────────────────────────
        if text in BUNDLE_FIELD_LABELS:
            field_key = BUNDLE_FIELD_LABELS[text]
            if field_key == 'spec_content':
                _save_bundle()
                current_bundle   = _new_bundle()
                current_topic_id = None
            current_field = field_key
            continue

        # ── Suggested timing value ────────────────────────────────────────────
        if current_field == 'timing' and current_bundle is not None:
            current_bundle["suggested_timing"] = text
            current_field = None
            continue

        # ── Topic header (x.x.x.x) ───────────────────────────────────────────
        topic_m = TOPIC_RE.match(text)
        if topic_m and current_bundle is not None:
            current_topic_id = topic_m.group(1)
            current_bundle["topics"][current_topic_id] = {
                "title":        topic_m.group(2).strip(),
                "spec_content": [],
            }
            continue

        # ── Subsection header (x.x.x) ────────────────────────────────────────
        sub_m = SUBSECTION_RE.match(text)
        if sub_m:
            _end_note()
            _save_bundle()
            current_subsection_id = sub_m.group(1)
            sec = result[current_qual]["sections"].get(current_section_id)
            if sec is not None:
                sec["subsections"][current_subsection_id] = {
                    "title":            sub_m.group(2).strip(),
                    "note":             None,
                    "teaching_bundles": [],
                }
            current_field    = None
            current_topic_id = None
            continue

        # ── Section header (x.x) ─────────────────────────────────────────────
        sec_m = SECTION_RE.match(text)
        if sec_m:
            _end_note()
            _save_bundle()
            current_section_id    = sec_m.group(1)
            current_subsection_id = None
            current_field         = None
            current_topic_id      = None
            result[current_qual]["sections"][current_section_id] = {
                "title":       sec_m.group(2).strip(),
                "intro":       None,
                "note":        None,
                "subsections": {},
            }
            continue

        # ── Section intro (before first subsection) ───────────────────────────
        if (current_section_id
                and current_subsection_id is None
                and current_bundle is None):
            sec = result[current_qual]["sections"].get(current_section_id)
            if sec is not None and sec["intro"] is None:
                sec["intro"] = text
            continue

        # ── Catch-all: unrecognised Normal para within an active field ─────────
        # Handles cases where content appears as Normal rather than List
        # Paragraph (e.g. a single spec content sentence, a lone learning
        # outcome, a resource line).
        if current_bundle is not None and current_field == 'spec_content' and current_topic_id:
            current_bundle["topics"][current_topic_id]["spec_content"].append(text)
        elif current_bundle is not None and current_field in (
                'learning_outcomes', 'activities'):
            current_bundle[current_field].append(text)
        elif current_bundle is not None and current_field == 'resources':
            current_bundle["resources"].append(_as_resource(para))

    _end_note()
    _save_bundle()

    return result

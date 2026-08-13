"""
orchestrator.py — Phase 3 update

Run-aware, formatting-preserving write-back.
Supports both preset path (truth_path=None → uses preset_report.truth.json)
and upload path (truth_path=<path to generated truth.json>).
Includes diagram_inserter hook (Part D.5).
"""

import os
import time
from typing import TypedDict, Callable, Optional
from langgraph.graph import StateGraph, START, END
from groq import Groq
from docx import Document
from docx.shared import Pt
import shutil
from docx.enum.text import WD_ALIGN_PARAGRAPH
from logger import log
from truth_loader import load_truth

# --- Formatting helpers ------------------------------------------------------

_ALIGN_ENUM = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


def apply_formatting(run, paragraph, format_dict: dict):
    """Apply every field from a formatting dict to a run + paragraph.
    Never leave anything to a default — fully explicit."""
    if format_dict.get("bold") is not None:
        run.bold = bool(format_dict["bold"])
    if format_dict.get("italic") is not None:
        run.italic = bool(format_dict["italic"])
    if format_dict.get("font"):
        run.font.name = format_dict["font"]
    if format_dict.get("size_pt"):
        run.font.size = Pt(format_dict["size_pt"])
    if format_dict.get("underline") is not None:
        run.underline = bool(format_dict["underline"])

    alignment = format_dict.get("alignment", "left")
    paragraph.alignment = _ALIGN_ENUM.get(alignment, WD_ALIGN_PARAGRAPH.LEFT)


def _clear_paragraph_text(p):
    """Surgically clear only <w:t> (text) nodes from a paragraph's runs,
    leaving <w:br> (page/line breaks) and all other XML elements intact.
    This preserves manual page breaks that are embedded in runs.
    We blank the text instead of removing the <w:t> tag to prevent docx-preview crashes on empty runs."""
    from docx.oxml.ns import qn
    for t_elem in p._element.xpath('.//w:t'):
        t_elem.text = ''


def _strip_images(doc: Document):
    """Remove all floating/inline image XML elements from the document so the
    web viewer doesn't render them. Strips <w:drawing>, <w:pict>, and empty <mc:AlternateContent>."""
    from docx.oxml.ns import qn
    
    # Custom namespace for markup compatibility
    mc_ns = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
    
    tags_to_strip = [
        qn('w:drawing'),
        qn('w:pict'),
        f'{{{mc_ns}}}AlternateContent',
        '{urn:schemas-microsoft-com:vml}shape'
    ]
    
    for tag in tags_to_strip:
        for elem in doc.element.body.iter(tag):
            parent = elem.getparent()
            if parent is not None:
                parent.remove(elem)

def get_all_paragraphs(doc: Document) -> list:
    """Walk the document in XML order (same as template_parser) to get a flat list
    of all paragraphs and table-cell paragraphs, so we can index into it safely."""
    paragraphs = []
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "p":
            from docx.text.paragraph import Paragraph
            paragraphs.append(Paragraph(child, doc))
        elif tag == "tbl":
            from docx.table import Table
            table = Table(child, doc)
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        paragraphs.append(para)
    return paragraphs


def write_paragraph_node(doc: Document, node: dict, text: str = "", existing_p=None) -> tuple:
    """
    Add a paragraph for a node, applying all formatting from the node's
    formatting block (and per-run formatting if runs are present).

    If existing_p is provided, it clears that paragraph and replaces its runs
    in-place instead of creating a new paragraph.
    Returns (paragraph, run) for the body run (or the first run for multi-span).
    """
    if existing_p is not None:
        p = existing_p
        _clear_paragraph_text(p)  # Safe clear — preserves page breaks
    else:
        p = doc.add_paragraph()
    fmt = node.get("formatting", {})
    node_runs = node.get("runs", [])

    if node_runs and text == "":
        # Multi-span node: write each span with its own formatting
        for span in node_runs:
            run = p.add_run(span.get("text", ""))
            span_fmt = {
                "bold": span.get("bold"),
                "italic": span.get("italic"),
                "font": span.get("font"),
                "size_pt": span.get("size_pt"),
                "underline": span.get("underline"),
                "alignment": fmt.get("alignment", "left"),
            }
            apply_formatting(run, p, span_fmt)
        return p, p.runs[0] if p.runs else p.add_run("")
    else:
        # Single-span node (heading or body during streaming)
        run = p.add_run(text)
        apply_formatting(run, p, fmt)
        return p, run


# --- Safe save ---------------------------------------------------------------

def _safe_save(doc: Document, path: str):
    """Atomic write via temp file with retries for Windows file locks."""
    temp_path = path + ".tmp"
    for attempt in range(10):
        try:
            doc.save(temp_path)
            os.replace(temp_path, path)
            break
        except PermissionError:
            if attempt == 9:
                log.error("Safe save failed: Access denied after 10 retries.")
            time.sleep(0.2)
        except Exception as e:
            log.error(f"Safe save failed: {e}")
            break
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass


# --- LangGraph state ---------------------------------------------------------

class AgentState(TypedDict):
    topic: str
    docx_path: str
    current_section_index: int
    generated_text: str
    stream_chat_callback: Callable[[str], None]
    section_callback: Callable[[str], None]
    truth_nodes: list
    section_groups: list
    is_template: bool


# --- Graph node --------------------------------------------------------------

def generate_and_write_section(state: AgentState):
    idx = state["current_section_index"]
    section_name = state["section_groups"][idx]

    # Get nodes for this section (heading + body only; skip figure/metadata)
    nodes = [n for n in state["truth_nodes"] if n.get("section") == section_name]
    heading_node = next((n for n in nodes if n["role"] == "section_heading"), None)
    body_node = next((n for n in nodes if n["role"] == "body_paragraph"), None)

    topic = state["topic"]
    chat_callback = state["stream_chat_callback"]
    section_callback = state.get("section_callback")
    docx_path = state["docx_path"]

    log.info(f"Generating section {idx + 1}/{len(state['section_groups'])}: {section_name}")
    
    if section_callback:
        section_callback(section_name)

    doc_text = ""

    try:
        if not os.environ.get("GROQ_API_KEY"):
            raise ValueError("GROQ_API_KEY environment variable not set.")

        # Load current document
        doc = Document(docx_path) if os.path.exists(docx_path) else Document()
        
        # Build the index map if we are using an uploaded template
        all_paras = get_all_paragraphs(doc) if state.get("is_template") else []

        # Write heading using run-aware helper
        if heading_node:
            p_idx = heading_node.get("position", {}).get("index")
            existing = all_paras[p_idx] if all_paras and p_idx is not None and p_idx < len(all_paras) else None
            write_paragraph_node(doc, heading_node, text=section_name, existing_p=existing)

        # Prepare first body paragraph (empty, will be filled by streaming)
        body_existing = None
        if body_node:
            p_idx = body_node.get("position", {}).get("index")
            body_existing = all_paras[p_idx] if all_paras and p_idx is not None and p_idx < len(all_paras) else None
            
        body_p, body_run = write_paragraph_node(doc, body_node or {}, text="", existing_p=body_existing)
        
        # Clear any subsequent body paragraphs in this section so template lorem ipsum is removed
        all_body_nodes = [n for n in nodes if n["role"] == "body_paragraph"]
        if len(all_body_nodes) > 1:
            for extra_node in all_body_nodes[1:]:
                p_idx = extra_node.get("position", {}).get("index")
                if all_paras and p_idx is not None and p_idx < len(all_paras):
                    _clear_paragraph_text(all_paras[p_idx])  # Safe clear — preserves page breaks
                    
        client = Groq()
        prompt = (
            f"You are writing a section for a document. "
            f"The section is '{section_name}' and the topic is '{topic}'. "
            f"First, write a single short sentence explaining what you are writing "
            f"(this will go to the chat). Then, type exactly '---' on a new line. "
            f"Finally, write the actual concise academic paragraph "
            f"(this will go into the document)."
        )

        stream = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            stream=True,
        )

        full_buffer = ""
        hit_delimiter = False
        chunk_count = 0

        for chunk in stream:
            text = chunk.choices[0].delta.content
            if text:
                full_buffer += text

                if not hit_delimiter:
                    if "---" in full_buffer:
                        hit_delimiter = True
                        parts = full_buffer.split("---", 1)
                        doc_text = parts[1].lstrip("\n")
                        if chat_callback:
                            chat_callback("\n")
                    else:
                        if chat_callback:
                            chat_callback(text)
                else:
                    doc_text += text
                    time.sleep(0.04)

                    # Update run text in memory (run-aware — never paragraph.text)
                    body_run.text = doc_text
                    chunk_count += 1

                    if chunk_count % 4 == 0:
                        _safe_save(doc, docx_path)

        _safe_save(doc, docx_path)

        # Part D.5: call diagram_inserter after body is written
        try:
            from diagram_inserter import generate_and_insert_diagram
            inserted = generate_and_insert_diagram(section_name, doc_text, docx_path)
            if inserted:
                log.info(f"Diagram inserted for section '{section_name}'")
        except Exception as diagram_err:
            log.warning(f"diagram_inserter failed for '{section_name}': {diagram_err}")

    except Exception as e:
        log.error(f"Error generating section {section_name}: {e}")
        doc_text = f"[Content generation failed for {section_name}: {e}]"

    return {"current_section_index": idx + 1, "generated_text": doc_text}


def router(state: AgentState):
    if state["current_section_index"] < len(state["section_groups"]):
        return "generate_and_write_section"
    return END


# Build graph
workflow = StateGraph(AgentState)
workflow.add_node("generate_and_write_section", generate_and_write_section)
workflow.add_edge(START, "generate_and_write_section")
workflow.add_conditional_edges("generate_and_write_section", router)
app = workflow.compile()


# --- Entry point -------------------------------------------------------------

def run_full_generation(
    topic: str,
    docx_path: str,
    stream_chat_callback: Callable[[str], None] = None,
    section_callback: Callable[[str], None] = None,
    truth_path: Optional[str] = None,
):
    """
    Run full document generation.

    truth_path: path to a truth.json file.
      - None → uses preset templates/preset_report.truth.json
      - str  → uses the upload-path generated truth.json at that path
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))

    if truth_path is None:
        truth_path = os.path.join(
            os.path.dirname(current_dir), "templates", "preset_report.truth.json"
        )

    truth_nodes, source_template = load_truth(truth_path)

    # Collect unique generatable sections (skip figure/metadata/boilerplate)
    section_groups = []
    for node in truth_nodes:
        section = node.get("section")
        role = node.get("role", "")
        if section and role in ("section_heading", "body_paragraph") and section not in section_groups:
            section_groups.append(section)

    # Reset output docx for a clean run
    if os.path.exists(docx_path):
        try:
            os.remove(docx_path)
        except Exception:
            pass

    is_template = False
    if source_template and os.path.exists(source_template):
        # We have an uploaded template! Copy it so we preserve page size, margins, and page borders.
        shutil.copy2(source_template, docx_path)
        is_template = True
        # Strip all images from the copy so the web viewer renders cleanly.
        _img_doc = Document(docx_path)
        _strip_images(_img_doc)
        _safe_save(_img_doc, docx_path)
    else:
        # Fallback to default blank document
        _safe_save(Document(), docx_path)

    initial_state = AgentState(
        topic=topic,
        docx_path=docx_path,
        current_section_index=0,
        generated_text="",
        stream_chat_callback=stream_chat_callback,
        section_callback=section_callback,
        truth_nodes=truth_nodes,
        section_groups=section_groups,
        is_template=is_template
    )

    log.info(f"Starting orchestration — topic: {topic!r}, sections: {section_groups}")
    final_state = app.invoke(initial_state)
    log.info("Orchestration complete.")
    return final_state

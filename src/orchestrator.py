import os
import time
from typing import TypedDict, Callable
from langgraph.graph import StateGraph, START, END
from groq import Groq
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from logger import log
from truth_loader import load_truth
import shutil
from dotenv import load_dotenv
from diagram_agent import generate_and_insert_diagram

load_dotenv()

class AgentState(TypedDict):
    topic: str
    docx_path: str
    current_section_index: int
    generated_text: str
    stream_chat_callback: Callable[[str], None]
    truth_nodes: list
    section_groups: list

def apply_formatting(run, paragraph, format_dict):
    """Applies formatting from the truth.json node to a python-docx run and paragraph."""
    if format_dict.get("bold"):
        run.bold = True
    if format_dict.get("font"):
        run.font.name = format_dict["font"]
    if format_dict.get("size_pt"):
        run.font.size = Pt(format_dict["size_pt"])
        
    alignment = format_dict.get("alignment")
    if alignment == "left":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    elif alignment == "center":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif alignment == "right":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    elif alignment == "justify":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

def _safe_save(doc: Document, path: str):
    """Saves to a temporary file, then atomically replaces the target file to avoid read/write locks."""
    temp_path = path + ".tmp"
    
    for attempt in range(10):
        try:
            doc.save(temp_path)
            os.replace(temp_path, path)
            break
        except PermissionError:
            if attempt == 9:
                log.error(f"Safe save failed: Access denied after 10 retries.")
            time.sleep(0.2)
        except Exception as e:
            log.error(f"Safe save failed with unexpected error: {e}")
            break
            
    # Cleanup temp file if it survived
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except:
            pass

def generate_and_write_section(state: AgentState):
    idx = state["current_section_index"]
    section_name = state["section_groups"][idx]
    
    # Get nodes for this section
    nodes = [n for n in state["truth_nodes"] if n.get("section") == section_name]
    heading_node = next((n for n in nodes if n["role"] == "section_heading"), None)
    body_node = next((n for n in nodes if n["role"] == "body_paragraph"), None)
    
    topic = state["topic"]
    chat_callback = state["stream_chat_callback"]
    docx_path = state["docx_path"]
    
    log.info(f"Generating section {idx + 1}/{len(state['section_groups'])}: {section_name}")
    
    try:
        if not os.environ.get("GROQ_API_KEY"):
            raise ValueError("GROQ_API_KEY environment variable not set.")
            
        # Load or create document
        doc = Document(docx_path) if os.path.exists(docx_path) else Document()
        
        # Write heading with formatting
        if heading_node:
            p = doc.add_paragraph()
            run = p.add_run(section_name)
            apply_formatting(run, p, heading_node.get("formatting", {}))
            
        # Write body placeholder
        body_p = doc.add_paragraph()
        body_run = body_p.add_run("")
        if body_node:
            apply_formatting(body_run, body_p, body_node.get("formatting", {}))
        
        client = Groq()
        prompt = f"You are writing a section for a document. The section is '{section_name}' and the topic is '{topic}'. First, write a single short sentence explaining what you are writing (this will go to the chat). Then, type exactly '---' on a new line. Finally, write the actual concise academic paragraph (this will go into the document)."
        
        stream = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            stream=True,
        )
        
        full_buffer = ""
        doc_text = ""
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
                        # We already streamed the chat part, but the split text might have a few leftover characters
                        # that belong to the doc.
                        doc_text = parts[1].lstrip("\n")
                        
                        # Tell chat we hit the delimiter and are working on the doc
                        if chat_callback:
                            chat_callback("\n")
                    else:
                        if chat_callback:
                            chat_callback(text)
                else:
                    doc_text += text
                    
                    # Throttle stream slightly for readability and lock safety
                    time.sleep(0.02)
                    
                    # Update document memory
                    body_run.text = doc_text
                    chunk_count += 1
                    
                    # Save to disk periodically
                    if chunk_count % 20 == 0:
                        _safe_save(doc, docx_path)
                        
        # Final save for this section
        _safe_save(doc, docx_path)

        # --- Diagram injection ---
        # After the section text is written, ask Groq if a diagram is needed.
        # If yes, generate it (chart or UML flowchart) and insert it into the
        # document immediately after this section's content.
        try:
            diagram_inserted = generate_and_insert_diagram(
                section_heading=section_name,
                section_content=doc_text,
                docx_path=docx_path,
            )
            if diagram_inserted:
                log.info(f"Diagram inserted for section: {section_name}")
        except Exception as diag_err:
            log.warning(f"Diagram step skipped for '{section_name}': {diag_err}")

    except Exception as e:
        log.error(f"Error generating section {section_name}: {e}")
        doc_text = f"[Content generation failed for {section_name}: {e}]"

    return {"current_section_index": idx + 1, "generated_text": doc_text}

def router(state: AgentState):
    if state["current_section_index"] < len(state["section_groups"]):
        return "generate_and_write_section"
    return END

# Build the graph
workflow = StateGraph(AgentState)
workflow.add_node("generate_and_write_section", generate_and_write_section)

workflow.add_edge(START, "generate_and_write_section")
workflow.add_conditional_edges("generate_and_write_section", router)

app = workflow.compile()

def run_full_generation(topic: str, docx_path: str, stream_chat_callback: Callable[[str], None] = None):
    # Load truth.json
    current_dir = os.path.dirname(os.path.abspath(__file__))
    truth_path = os.path.join(os.path.dirname(current_dir), 'templates', 'preset_report.truth.json')
    truth_nodes = load_truth(truth_path)
    
    # Group by unique sections preserving order
    section_groups = []
    for node in truth_nodes:
        if node.get("section") and node["section"] not in section_groups:
            section_groups.append(node["section"])
            
    # Reset docx file for fresh generation
    if os.path.exists(docx_path):
        try:
            os.remove(docx_path)
        except:
            pass
    
    doc = Document()
    _safe_save(doc, docx_path)
            
    initial_state = AgentState(
        topic=topic,
        docx_path=docx_path,
        current_section_index=0,
        generated_text="",
        stream_chat_callback=stream_chat_callback,
        truth_nodes=truth_nodes,
        section_groups=section_groups
    )
    
    log.info(f"Starting orchestration for topic: {topic}")
    final_state = app.invoke(initial_state)
    log.info("Orchestration complete.")
    return final_state

import os
import json
from diagram_selector import select_diagram_type
from chart_generator import generate_chart
from uml_generator import generate_uml_diagram
from diagram_inserter import insert_diagram

def generate_and_insert_diagram(section_heading: str, section_content: str, docx_path: str, doc=None, target_paragraph=None) -> bool:
    """Determine diagram type, generate it, and insert into the docx.

    Returns True on success, False otherwise. Never raises exceptions.
    """
    try:
        decision = select_diagram_type(section_heading, section_content)
        diagram_type = decision.get('type', 'none')
        if diagram_type == 'none':
            return False
        # Ensure output directories exist
        img_dir = os.path.join(os.path.dirname(docx_path), 'generated_images')
        os.makedirs(img_dir, exist_ok=True)
        img_path = ''
        caption = ''
        if diagram_type == 'chart':
            spec = {
                'chart_type': decision.get('chart_type', 'bar'),
                'data': decision.get('data', {}),
                'labels': decision.get('labels', {}),
                'title': decision.get('title', f"{section_heading} Chart")
            }
            img_path = os.path.join(img_dir, f"{section_heading.replace(' ', '_')}_chart.png")
            img_path = generate_chart(spec, img_path)
            caption = f"Fig.: {spec.get('title', 'Chart')}"
        elif diagram_type == 'uml':
            description = decision.get('description', 'Diagram')
            img_path = os.path.join(img_dir, f"{section_heading.replace(' ', '_')}_uml.png")
            img_path = generate_uml_diagram(description, img_path)
            caption = f"Fig.: {description}"
        else:
            return False
        if not img_path or not os.path.exists(img_path):
            return False
        insert_diagram(docx_path, img_path, caption, section_heading, doc=doc, target_paragraph=target_paragraph)
        return True
    except Exception as e:
        print(f"Error in generate_and_insert_diagram: {e}")
        return False

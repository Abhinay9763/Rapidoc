import os
import json
from groq import Groq
from dotenv import load_dotenv

# Load environment variables from .env (if present)
load_dotenv()

def select_diagram_type(section_heading: str, section_content: str) -> dict:
    """
    Decides the diagram type for a given section.
    Returns a dict with 'type': 'chart' | 'uml' | 'none', plus spec details.
    """
    # Initialize Groq client. Assumes GROQ_API_KEY is set in environment.
    try:
        client = Groq()
    except Exception as e:
        print(f"Failed to initialize Groq client (check API key): {e}")
        return {"type": "none"}
        
    prompt = f"""
You are a Diagram Generation Agent for academic reports.
Analyze the following section heading and content. Decide if it needs a visual:
- "chart": If the section describes quantitative data, trends, or comparisons. You MUST choose one of the following chart types: 'bar', 'line', 'pie', or 'scatter'. Provide 'chart_type', 'data' (x and y values), 'labels', and 'title'.
- "uml": If the section describes structural, flow, or architectural systems. You can use any PlantUML diagram, such as: use case, class, object, activity, sequence, component, deployment, state, or timing diagrams. Provide a 'description' of what the diagram should show.
- "none": If no diagram is needed.

Respond ONLY with valid JSON.
Example for chart:
{{"type": "chart", "chart_type": "pie", "data": {{"x": ["A", "B", "C"], "y": [10, 20, 30]}}, "labels": {{"x": "Category", "y": "Value"}}, "title": "Example Distribution"}}

Example for uml:
{{"type": "uml", "description": "Component diagram showing database, backend, and frontend interactions"}}

Example for none:
{{"type": "none"}}

Section Heading: {section_heading}
Section Content summary: {section_content[:1000]}
"""

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        response_text = completion.choices[0].message.content
        return json.loads(response_text)
    except Exception as e:
        print(f"Error calling Groq for diagram selection: {e}")
        return {"type": "none"}

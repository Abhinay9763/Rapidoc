import os
import json
from groq import Groq
from logger import log

_SYSTEM_PROMPT = """You are an intent classifier for a document generation agent.
The user will provide a prompt and a list of available sections in their document.
You must classify the user's intent into one of three modes:
- "full_generation": The user wants to generate a complete document from scratch based on a topic.
- "edit": The user wants to edit, rewrite, or modify a specific section or part of the document.
- "diagrams": The user wants to add diagrams, charts, or images to the document, without modifying the text.

If the mode is "edit", you must also try to identify which section(s) the user wants to edit based on the prompt and the provided list of available sections. Return a list of the exact section names that best match.

Available sections:
{sections}

Respond with JSON ONLY in this format:
{{
    "mode": "full_generation" | "edit" | "diagrams",
    "target_sections": ["section_name_1", "section_name_2"] 
}}
If mode is not "edit", target_sections should be an empty list.
"""

def classify_intent(prompt: str, available_sections: list[str]) -> dict:
    """
    Classify the user's prompt into a generation mode.
    Returns dict: {"mode": str, "target_sections": list[str]}
    """
    if not os.environ.get("GROQ_API_KEY"):
        log.warning("GROQ_API_KEY not set — defaulting to full_generation")
        return {"mode": "full_generation", "target_sections": []}

    client = Groq()
    sections_str = "\n".join(f"- {s}" for s in available_sections) if available_sections else "None (blank document)"
    
    system_msg = _SYSTEM_PROMPT.format(sections=sections_str)
    
    log.info(f"Classifying intent for prompt: {prompt!r}")
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            model="llama-3.1-8b-instant",
            temperature=0.1,
            max_tokens=128,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)
        mode = parsed.get("mode", "full_generation")
        if mode not in ("full_generation", "edit", "diagrams"):
            mode = "full_generation"
            
        target_sections = parsed.get("target_sections", [])
        if not isinstance(target_sections, list):
            target_sections = []
            
        result = {"mode": mode, "target_sections": target_sections}
        log.info(f"Intent classified: {result}")
        return result

    except Exception as e:
        log.error(f"Intent classification failed: {e}. Defaulting to full_generation.")
        return {"mode": "full_generation", "target_sections": []}

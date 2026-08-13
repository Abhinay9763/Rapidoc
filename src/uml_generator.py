import os
import zlib
import base64
import requests
from dotenv import load_dotenv
from groq import Groq

# Load .env so GROQ_API_KEY is available
load_dotenv()

def encode_plantuml(text: str) -> str:
    """
    Encodes PlantUML text to be used in the PlantUML web server URL.
    """
    zlibbed_str = zlib.compress(text.encode('utf-8'))
    compressed_string = zlibbed_str[2:-4]
    
    b64_str = base64.b64encode(compressed_string).decode('utf-8')
    # PlantUML custom base64-like translation
    b64_str = b64_str.translate(str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/",
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
    ))
    return b64_str

def generate_uml_diagram(description: str, output_path: str) -> str:
    """
    Converts a description to PlantUML syntax via Groq, then renders it via PlantUML web server.
    """
    try:
        client = Groq()
    except Exception as e:
        print(f"Failed to initialize Groq client: {e}")
        return ""

    prompt = f"""
You are a PlantUML expert. 
Given the following description of a diagram, generate the corresponding PlantUML syntax.
Only output the raw PlantUML code between @startuml and @enduml. Do not include markdown formatting or explanations.

Description: {description}
"""

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        puml_text = completion.choices[0].message.content.strip()
        
        # Strip potential markdown fences if model ignored instruction
        if puml_text.startswith("```"):
            lines = puml_text.split('\n')
            puml_text = '\n'.join(lines[1:-1])
            if puml_text.endswith("```"):
                puml_text = puml_text[:-3]

        # Render via web server
        encoded = encode_plantuml(puml_text)
        url = f"http://www.plantuml.com/plantuml/png/{encoded}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            f.write(response.content)
            
        return output_path
    except Exception as e:
        print(f"Failed to generate UML diagram: {e}")
        return ""

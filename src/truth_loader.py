import json
import os

def load_truth(path: str) -> list[dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Truth file not found: {path}")
        
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    nodes = data.get("nodes", [])
    
    # Basic validation
    for node in nodes:
        if "node_id" not in node:
            raise ValueError(f"Missing node_id in node: {node}")
        if "role" not in node:
            raise ValueError(f"Missing role in node: {node}")
        if "formatting" not in node:
            raise ValueError(f"Missing formatting in node: {node}")
            
    return nodes

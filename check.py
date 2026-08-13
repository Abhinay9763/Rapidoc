import json
with open(r'templates\uploaded_20260813_212225_d14d3e58.truth.json', encoding='utf-8') as f:
    data = json.load(f)
for n in data['nodes'][:30]:
    txt = n.get('text', '')
    if not txt and n.get('runs'):
        txt = ''.join(r.get('text', '') for r in n['runs'])
    print(f"{n['position']['index']}: [{n['role']}] {n.get('section', 'None')} - {txt[:50]}")

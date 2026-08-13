import json, re

with open('THE-APRON.project/sf-board.json', 'r') as f:
    d = json.load(f)

ALL = {f['id']: f for s in d['scenes'] for f in s.get('sfs', [])}
TEN_PROP = {}
for i, f in ALL.items():
    if i.startswith('REF_PROP_'):
        kws = [i[9:].lower().replace('_', ' ')]
        if f.get('label'):
            lbl = f['label'].lower()
            ws = lbl.split()
            if len(ws) >= 2: kws.append(ws[0] + ' ' + ws[1])
            else: kws.append(lbl)
        TEN_PROP[i] = kws

for s in d['scenes']:
    for x in s.get('shots', []):
        if not x.get('sf'): continue
        sf_node = ALL.get(x['sf'])
        if not sf_node: continue
        
        pv = x.get('prompt') or ''
        full_text = (sf_node.get('prompt', '') + '\n' + (x.get('text') or '') + '\n' + pv)
        
        for prop_id, keywords in TEN_PROP.items():
            if any(re.search(r'\b' + re.escape(kw) + r'\b', full_text, re.I) for kw in keywords):
                chars = sf_node.setdefault('refs', {}).setdefault('chars', [])
                if prop_id not in chars:
                    chars.append(prop_id)
                    print(f"Added {prop_id} to {sf_node['id']} (from shot {x['id']})")

with open('THE-APRON.project/sf-board.json', 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print("Auto-patched all missing props")

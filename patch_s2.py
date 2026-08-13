import json

with open('THE-APRON.project/sf-board.json', 'r') as f:
    d = json.load(f)

for s in d['scenes']:
    if s['id'] == 'S2':
        for sf in s.get('sfs', []):
            if 'thiệp' in sf.get('prompt', '').lower():
                chars = sf.setdefault('refs', {}).setdefault('chars', [])
                if 'REF_PROP_THIEPMOI' not in chars:
                    chars.append('REF_PROP_THIEPMOI')

with open('THE-APRON.project/sf-board.json', 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print("Patched S2")

import json

with open('THE-APRON.project/sf-board.json', 'r') as f:
    d = json.load(f)

for s in d['scenes']:
    if s['id'] == 'S2':
        for sf in s.get('sfs', []):
            chars = sf.get('refs', {}).get('chars', [])
            if 'REF_PROP_THIEPMOI' in chars:
                chars.remove('REF_PROP_THIEPMOI')

with open('THE-APRON.project/sf-board.json', 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print("Reverted S2")

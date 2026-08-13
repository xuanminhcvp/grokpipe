import json, re
d = json.load(open('PIPELINE-ALTAR.project/sf-board.json'))
ALL = {f['id']: f for s in d['scenes'] for f in s.get('sfs', [])}
fulls = [f for f in ALL.values() if f['id'].endswith('_FULL')]
out = {}
for f in fulls:
    m = re.search(r'^REF_([^_]+)_', f['id'])
    if m:
        out.setdefault(m.group(1), []).append(f['id'])
print(json.dumps(out, indent=2))

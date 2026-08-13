import json, sys, re
d = json.load(open('PIPELINE-ALTAR.project/sf-board.json'))
ALL = {f['id']: f for s in d['scenes'] for f in s.get('sfs', [])}
TEN_NV = {t for i in ALL if i.startswith('REF_') and i.endswith('_PORTRAIT')
          for t in i[4:-9].split('_') if t}

# Build mapping: (scene_id, character) -> REF_ID
full_refs = [i for i in ALL if i.endswith('_FULL')]
scene_char_to_full = {}
for r in full_refs:
    f = ALL[r]
    desc = f.get('desc') or ''
    m = re.search(r'^\s*Dùng:\s*(.+)$', desc, re.M)
    if m:
        scenes = re.findall(r'\b(S\d+)\b', m.group(1))
        # Find character name
        # The REF is like REF_MAYA_CUOI_FULL
        char_name = None
        for t in TEN_NV:
            if f"_{t}_" in r or f"_{t}" in r:
                char_name = t
                break
        if char_name:
            for sc in scenes:
                scene_char_to_full[(sc, char_name)] = r

_GOC_SHOT = {x['sf']: x['goc'] for s in d['scenes'] for x in s.get('shots', [])
             if x.get('sf') and (x.get('goc') or '').strip()}
def goc_cua(sf_id):
    return _GOC_SHOT.get(sf_id) or (ALL.get(sf_id, {}).get('goc') or '')
def co_trong_goc(ten, goc):
    for ve in re.split(r'[·;]', goc or ''):
        if re.search(r'\b' + re.escape(ten) + r'\b', ve, re.I) and not re.search(
                r'ngoài\s+khung|off[- ]?screen', ve, re.I):
            return True
    return False

fixed = 0
for s in d['scenes']:
    scene_id = s['id']
    for f in s.get('sfs', []):
        if (f.get('luatchung') or '').strip() or f['id'].startswith('SF-M-'): continue
        _who = f.get('pose', {}).get('who') if isinstance(f.get('pose'), dict) else None
        trong_khung = set()
        if isinstance(_who, dict):
            for k in _who:
                trong_khung.update([t for t in TEN_NV if re.search(r'\b' + re.escape(t) + r'\b', k, re.I)])
        for t in TEN_NV:
            if co_trong_goc(t, goc_cua(f['id'])):
                trong_khung.add(t)
        
        for t in trong_khung:
            t_upper = t.upper()
            co_full = any(f"_{t_upper}_" in c for c in f.get('refs',{}).get('chars',[]) if c.endswith('_FULL'))
            if not co_full:
                # Find the corresponding FULL ref for this scene and character
                target_ref = scene_char_to_full.get((scene_id, t))
                if target_ref:
                    if 'refs' not in f:
                        f['refs'] = {}
                    if 'chars' not in f['refs']:
                        f['refs']['chars'] = []
                    f['refs']['chars'].append(target_ref)
                    fixed += 1
                else:
                    # fallback: if there is only 1 FULL ref for this character in the whole movie, use it.
                    cand = [r for r in full_refs if f"_{t_upper}_" in r]
                    if len(cand) == 1:
                        if 'refs' not in f: f['refs'] = {}
                        if 'chars' not in f['refs']: f['refs']['chars'] = []
                        f['refs']['chars'].append(cand[0])
                        fixed += 1

print(f"Fixed {fixed} missing FULL refs")
with open('PIPELINE-ALTAR.project/sf-board.json', 'w') as f:
    json.dump(d, f, ensure_ascii=False, indent=4)

import json, sys, re
d = json.load(open('PIPELINE-ALTAR.project/sf-board.json'))
ALL = {f['id']: f for s in d['scenes'] for f in s.get('sfs', [])}
TEN_NV = {t for i in ALL if i.startswith('REF_') and i.endswith('_PORTRAIT')
          for t in i[4:-9].split('_') if t}
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

missing_full = 0
for s in d['scenes']:
    for f in s.get('sfs', []):
        if (f.get('luatchung') or '').strip() or f['id'].startswith('SF-M-'): continue
        _who = f.get('pose', {}).get('who') if isinstance(f.get('pose'), dict) else None
        trong_khung = set()
        if isinstance(_who, dict):
            trong_khung.update(_who.keys())
        for t in TEN_NV:
            if co_trong_goc(t, goc_cua(f['id'])):
                trong_khung.add(t)
        
        for t in trong_khung:
            co_full = any(c.startswith(f"REF_{t}_") and c.endswith("_FULL") for c in f.get('refs',{}).get('chars',[]))
            if not co_full:
                print(f"LỖI: {f['id']} thiếu FULL cho {t}")
                missing_full += 1
print(f"Total missing: {missing_full}")

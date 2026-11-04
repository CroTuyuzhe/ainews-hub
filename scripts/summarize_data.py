"""Expose actual per-source outcomes in Actions logs and job summary."""
import json
import os
from pathlib import Path
root=Path(__file__).resolve().parent.parent
data=json.loads((root/'data/data.json').read_text(encoding='utf-8'))
a=data['a_share']
rows=[(m['name'],m) for m in a['indexes']]+[(k,v) for k,v in a.items() if k!='indexes']+list(data['us_market'].items())
lines=['## Data-source health','', '| Metric | Status | Trading date | Source | Reason |','|---|---|---|---|---|']
for name,m in rows:
    meta=m['meta']
    fields=[name,meta['status'],meta.get('trade_date') or '—',meta['source'],meta.get('reason') or '—']
    lines.append('| '+' | '.join(str(v).replace('|','/').replace('\n',' ') for v in fields)+' |')
text='\n'.join(lines)+'\n'
print(text)
if os.environ.get('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f:f.write(text)

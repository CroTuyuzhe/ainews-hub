"""Restore only validated production history; never publish synthetic fallback."""
import argparse
import json
from pathlib import Path
from data_model import validate
from fetch_data import save
p=argparse.ArgumentParser()
p.add_argument('path')
p.add_argument('--mark-cached', action='store_true')
args=p.parse_args()
data=json.loads(Path(args.path).read_text(encoding='utf-8'))
errors=validate(data)
if errors: raise ValueError('; '.join(errors))
metrics=data['a_share']['indexes']+[v for k,v in data['a_share'].items() if k!='indexes']+list(data['us_market'].values())
if not any(m['meta']['status'] in ('fresh','cached') for m in metrics):
    raise ValueError('No verified production observations available')
if args.mark_cached:
    for metric in metrics:
        if metric['meta']['status'] in ('fresh','cached'):
            metric['meta'].update(status='cached',reason='本次采集失败，保留上次有效行情与原采集时间')
    data['data_note']='本次采集失败，显示上次已验证缓存；请查看各项行情日期。'
save(data)
print('[OK] Restored verified snapshot')

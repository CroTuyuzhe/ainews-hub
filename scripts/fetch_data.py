#!/usr/bin/env python3
"""Dated market observations. Failed sources retain verified cache, never demo values."""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from source_adapters import cboe_vix, sina_sp500, fetch_north_flow, legu_breadth
from data_model import SOURCES, calc_panic, fallback, finite, fresh, history_merge, migrate, missing, validate

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / 'data' / 'data.json'

def get_json(url):
    last = None
    for attempt in range(2):
        try:
            req = Request(url, headers={'User-Agent':'Mozilla/5.0', 'Referer':'https://quote.eastmoney.com/'})
            with urlopen(req, timeout=12) as response:
                return json.load(response)
        except Exception as exc:
            last = exc
            if attempt == 0: time.sleep(.5)
    raise RuntimeError(type(last).__name__)

def daily_index(secid):
    params = {'secid':secid,'klt':101,'fqt':0,'lmt':120,'end':'20500101',
              'fields1':'f1,f2,f3,f4,f5,f6', 'fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'}
    local_now = datetime.now(ZoneInfo('Asia/Shanghai'))
    try:
        payload = get_json('https://push2his.eastmoney.com/api/qt/stock/kline/get?' + urlencode(params))
        rows = []
        for line in (payload.get('data') or {}).get('klines', []):
            fields = line.split(',')
            if len(fields) >= 9:
                if fields[0] == local_now.date().isoformat() and local_now.hour < 15: continue
                rows.append({'date':fields[0], 'close':float(fields[2]), 'amount':float(fields[6]),
                             'change_pct':float(fields[8]), 'source':'东方财富 · 指数日线'})
        if not rows or any(not finite(r['close']) or r['close'] <= 0 for r in rows):
            raise ValueError('Invalid index series')
        return sorted(rows, key=lambda r:r['date'])
    except Exception as exc:
        print(f'[WARN] Eastmoney {secid}: {type(exc).__name__}', file=sys.stderr)
    # Independent index-only fallback. Tencent's sixth column is share volume,
    # so it must never be mistaken for currency turnover.
    symbol = ('sh' if secid.startswith('1.') else 'sz') + secid.split('.')[1]
    url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?' + urlencode({'param':f'{symbol},day,,,120,qfq'})
    block = get_json(url)['data'][symbol]
    bars = block.get('day') or block.get('qfqday') or []
    rows = []
    for bar in sorted(bars, key=lambda row:row[0]):
        if bar[0] > local_now.date().isoformat() or (bar[0] == local_now.date().isoformat() and local_now.hour < 15): continue
        close = float(bar[2])
        if not finite(close) or close <= 0: continue
        change = round((close/rows[-1]['close']-1)*100,2) if rows else None
        rows.append({'date':bar[0], 'close':close,'amount':None,'change_pct':change,'source':'腾讯财经 · 指数日线备用源'})
    if not rows: raise ValueError('All index sources unavailable')
    return rows


def yahoo_series(symbol, key, now):
    payload = get_json('https://query1.finance.yahoo.com/v8/finance/chart/' + symbol.replace('^','%5E') + '?range=6mo&interval=1d')
    result = payload['chart']['result'][0]
    tz = ZoneInfo(result['meta'].get('exchangeTimezoneName', 'America/New_York'))
    ny_now = datetime.now(tz)
    timestamps = result.get('timestamp', [])
    quotes = result['indicators']['quote'][0]['close']
    points = []
    for stamp, value in zip(timestamps, quotes):
        day = datetime.fromtimestamp(stamp, tz).date()
        # Intraday partial candles are excluded; both US instruments use completed sessions.
        if day == ny_now.date() and ny_now.hour < 16: continue
        if finite(value) and value > 0:
            points.append({'date':day.isoformat(), 'value':round(value, 2)})
    points = history_merge([], points)
    if len(points) < 2: raise ValueError('Insufficient completed US sessions')
    last, prev = points[-1], points[-2]
    return fresh(key, last['value'], last['date'], now, history=points,
                 change_pct=round((last['value']/prev['value']-1)*100, 2))

def fetch_breadth(trade_date, now):
    params = {'fltt':2,'fields':'f104,f105,f124','secids':'1.000001,0.399106'}
    payload = get_json('https://push2.eastmoney.com/api/qt/ulist.np/get?' + urlencode(params))
    items = (payload.get('data') or {}).get('diff', [])
    if len(items) != 2: raise ValueError('Missing exchange breadth')
    dates = {datetime.fromtimestamp(int(i['f124']), ZoneInfo('Asia/Shanghai')).date().isoformat() for i in items}
    if len(dates) != 1: raise ValueError('Exchanges have different snapshot dates')
    trade_date = next(iter(dates))
    observed = max(datetime.fromtimestamp(int(i['f124']), ZoneInfo('Asia/Shanghai')) for i in items)
    counts = [(int(i['f104']), int(i['f105'])) for i in items]
    up, down = sum(i[0] for i in counts), sum(i[1] for i in counts)
    if up < 0 or down < 0 or up + down <= 0: raise ValueError('Missing breadth counts')
    result = fresh('market_sentiment', up + down, trade_date, now,
                   up_count=up, down_count=down, limit_up=None, limit_down=None)
    result['meta'].update(observed_at=observed.isoformat(), session='closed' if observed.hour >= 15 else 'intraday')
    result['meta']['source'] = '东方财富 · 上证综指＋深证综指成分涨跌家数（含B股，不含北交所）'
    result['meta']['reason'] = '涨跌停池未取得；涨跌家数仍可独立查看'
    try:
        import akshare as ak
        date_code = trade_date.replace('-','')
        lu = ak.stock_zt_pool_em(date=date_code)
        ld = ak.stock_zt_pool_dtgc_em(date=date_code)
        if lu is not None and ld is not None:
            result.update(limit_up=len(lu), limit_down=len(ld))
            result['meta']['reason'] = '涨跌停池为独立A股口径（各板块涨跌停制度不同）'
            result['meta']['source'] += ' / AKShare · A股涨跌停池'
    except Exception as exc:
        print(f'[WARN] Limit pools: {type(exc).__name__}', file=sys.stderr)
    return result

def fetch_volume(sh, sz, now):
    left = {r['date']:r['amount'] for r in sh}
    right = {r['date']:r['amount'] for r in sz}
    points = [{'date':day,'value':round((left[day]+right[day])/1e8, 2)} for day in sorted(left.keys() & right.keys())
              if finite(left[day]) and finite(right[day]) and left[day] > 0 and right[day] > 0]
    if not points: raise ValueError('No aligned turnover series')
    previous = points[-21:-1]
    avg = sum(p['value'] for p in previous)/20 if len(previous) == 20 else None
    vs = round((points[-1]['value']/avg-1)*100, 2) if avg else None
    metric = fresh('volume', points[-1]['value'], points[-1]['date'], now, unit='亿',
                   vs_20day_avg=vs, history=history_merge([], points), baseline_days=len(previous))
    metric['meta']['source'] += '（含B股，不含北交所；亿元）'
    if avg is None: metric['meta']['reason'] = '不足20个前序交易日，暂不计算偏离'
    return metric

def load_cache():
    if DATA_FILE.exists():
        return migrate(json.loads(DATA_FILE.read_text(encoding='utf-8-sig')))
    return migrate({})

def collect(previous):
    now = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    result = {'schema_version':2,'update_time':now,'mode':'live','a_share':{},'us_market':{}}
    a, prev_a = result['a_share'], previous.get('a_share', {})
    previous_indexes = {i['code']:i for i in prev_a.get('indexes', [])}
    series = {}
    a['indexes'] = []
    for code, name, secid in [('000001','上证指数','1.000001'),('399001','深证成指','0.399001'),('399006','创业板指','0.399006')]:
        try:
            rows = daily_index(secid); series[code] = rows
            last = rows[-1]
            metric = fresh('indexes', last['close'], last['date'], now, change_pct=last['change_pct'],
                           history=history_merge([], [{'date':r['date'],'value':r['close']} for r in rows]))
            metric['meta']['source'] = last.get('source', SOURCES['indexes'])
        except Exception as exc:
            metric = fallback('indexes', previous_indexes.get(code), f'采集失败：{type(exc).__name__}')
        metric['history'] = history_merge(previous_indexes.get(code, {}).get('history', []), metric.get('history', []))
        a['indexes'].append(dict(metric, code=code, name=name))
    try:
        if '000001' not in series: raise ValueError('Shanghai daily series unavailable')
        a['volume'] = fetch_volume(series['000001'], daily_index('0.399106'), now)
    except Exception as exc:
        a['volume'] = fallback('volume', prev_a.get('volume'), f'成交额不可用：{type(exc).__name__}')
        a['volume'].setdefault('vs_20day_avg', None)
    a['volume']['history'] = history_merge(prev_a.get('volume', {}).get('history', []), a['volume'].get('history', []))
    try:
        day = series.get('000001', [{}])[-1].get('date')
        a['market_sentiment'] = fetch_breadth(day, now)
        if any(a['market_sentiment'].get(k) is None for k in ('limit_up','limit_down')):
            try: a['market_sentiment'] = legu_breadth(now)
            except Exception: pass
    except Exception as exc:
        try: a['market_sentiment'] = legu_breadth(now)
        except Exception as backup_exc:
            a['market_sentiment'] = fallback('market_sentiment', prev_a.get('market_sentiment'), f'市场广度主备源不可用：{type(backup_exc).__name__}')
    try: a['north_flow'] = fetch_north_flow(now, get_json)
    except Exception as exc:
        a['north_flow'] = fallback('north_flow', prev_a.get('north_flow'), f'北向历史源不可用：{type(exc).__name__}；每日净买额已停止披露')
    for key, symbol in [('vix','^VIX'),('sp500','^GSPC')]:
        try: metric = yahoo_series(symbol, key, now)
        except Exception as exc:
            print(f'[WARN] Yahoo {key}: {type(exc).__name__}', file=sys.stderr)
            try: metric = cboe_vix(now) if key == 'vix' else sina_sp500(now)
            except Exception as backup_exc:
                metric = fallback(key, previous.get('us_market', {}).get(key), f'主备源采集失败：{type(backup_exc).__name__}')
        metric['history'] = history_merge(previous.get('us_market', {}).get(key, {}).get('history', []), metric.get('history', []))
        result['us_market'][key] = metric
    score = calc_panic(a['market_sentiment'], a['volume'], allow_partial=True)
    if score['value'] is not None:
        day = a['market_sentiment']['meta']['trade_date']
        complete = score['calculation_mode'] == 'complete'
        closed = a['market_sentiment']['meta'].get('session') == 'closed'
        reason = score.pop('reason', '')
        value = score.pop('value')
        history = prev_a.get('panic_index', {}).get('history', [])
        if complete and closed:
            history = history_merge(history, [{'date':day,'value':value}])
        a['panic_index'] = fresh('panic_index', value, day, now, **score, history=history)
        a['panic_index']['meta'].update(reason=reason, session='closed' if closed else 'intraday')
        if a['market_sentiment']['meta']['status'] == 'cached' or (complete and a['volume']['meta']['status'] == 'cached'):
            a['panic_index']['meta'].update(status='cached')
    else:
        # A temporary source outage must not erase a previously valid score.
        a['panic_index'] = fallback('panic_index', prev_a.get('panic_index'),
            score['label'] + '：本次输入不足，保留上次有效评分与原行情日期')
        a['panic_index'].setdefault('label', '数据不足')
        a['panic_index'].setdefault('components', [])
    return result

def save(data):
    errors = validate(data)
    if errors: raise ValueError('; '.join(errors))
    DATA_FILE.parent.mkdir(exist_ok=True)
    tmp = DATA_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(tmp, DATA_FILE)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--migrate-only', action='store_true', help='Invalidate undated legacy values without network access')
    args = parser.parse_args()
    previous = load_cache()
    if args.migrate_only:
        save(previous); print('[OK] Migrated legacy snapshot without inventing observations'); return
    data = collect(previous)
    metrics = data['a_share']['indexes'] + [v for k,v in data['a_share'].items() if k != 'indexes'] + list(data['us_market'].values())
    if not any(m['meta']['status'] == 'fresh' for m in metrics):
        print('[ERROR] No source returned a valid observation. Existing snapshot preserved.', file=sys.stderr)
        sys.exit(1)
    save(data)
    print('[OK] Saved independently dated observations; unavailable metrics use null or verified cache')

if __name__ == '__main__': main()

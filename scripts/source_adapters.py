"""Alternative adapters for existing Sina/Eastmoney sources; no placeholder values."""
import csv
import io
import re
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from data_model import finite, fresh, history_merge, valid_date


def download(url, encoding='utf-8'):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'})
    with urlopen(req, timeout=15) as response:
        return response.read().decode(encoding)


def cboe_vix(now):
    rows = csv.DictReader(io.StringIO(download('https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv')))
    ny = datetime.fromisoformat(now).astimezone(ZoneInfo('America/New_York'))
    points = []
    for row in rows:
        day = datetime.strptime(row['DATE'], '%m/%d/%Y').date()
        value = float(row['CLOSE'])
        if day > ny.date() or (day == ny.date() and ny.hour < 16): continue
        if finite(value) and value > 0: points.append({'date': day.isoformat(), 'value': value})
    points = history_merge([], points)
    if len(points) < 2: raise ValueError('CBOE completed sessions unavailable')
    last, previous = points[-1], points[-2]
    metric = fresh('vix', last['value'], last['date'], now, history=points,
                   change_pct=round((last['value']/previous['value']-1)*100, 2))
    metric['meta']['source'] = 'CBOE · VIX 历史日线（官方备用源）'
    return metric


def sina_sp500(now):
    raw = download('https://hq.sinajs.cn/list=gb_$inx', 'gb18030')
    parts = raw.split('"')[1].split(',')
    # Explicit exchange timestamp avoids assigning Beijing's next calendar day.
    quote = re.fullmatch(r'([A-Za-z]{3})\s+(\d{1,2})\s+(\d{1,2}):(\d{2})(AM|PM)\s+(EST|EDT)', parts[25].strip())
    if not quote: raise ValueError('Sina exchange timestamp unavailable')
    month, day, hour, minute, ampm, _ = quote.groups()
    months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    hour = int(hour) % 12 + (12 if ampm == 'PM' else 0)
    stamp = datetime(int(parts[29]), months.index(month)+1, int(day), hour, int(minute), tzinfo=ZoneInfo('America/New_York'))
    if stamp.hour < 16 or stamp > datetime.fromisoformat(now).astimezone(stamp.tzinfo):
        raise ValueError('Sina quote is not a completed session')
    value, change = float(parts[1]), float(parts[2])
    if value <= 0 or not finite(value) or not finite(change): raise ValueError('Invalid Sina quote')
    metric = fresh('sp500', round(value, 2), stamp.date().isoformat(), now, change_pct=change,
                   history=[{'date': stamp.date().isoformat(), 'value': round(value, 2)}])
    metric['meta']['source'] = '新浪财经 · 标普500（收盘快照备用源）'
    return metric


def north_history(payload, now):
    """Eastmoney mutual-type 005 is both northbound legs, raw net amount in 100M/100."""
    result = payload.get('result') or {}
    points = []
    sh = datetime.fromisoformat(now).astimezone(ZoneInfo('Asia/Shanghai'))
    for row in result.get('data') or []:
        day = str(row.get('TRADE_DATE', ''))[:10]
        raw = row.get('NET_DEAL_AMT')
        if not valid_date(day) or not finite(raw): continue
        if day > sh.date().isoformat() or (day == sh.date().isoformat() and sh.hour < 15): continue
        # Post-2024 disclosure removed daily net buys; zero-filled later rows are not observations.
        if day >= '2024-08-19': continue
        points.append({'date': day, 'value': round(raw/100, 2)})
    points = history_merge([], points)
    if not points: raise ValueError('No verified northbound net-buy history')
    last = points[-1]
    metric = fresh('north_flow', last['value'], last['date'], now, unit='亿', history=points)
    metric['meta'].update(status='cached', source='东方财富 · 沪深港通北向合计历史净买额',
                          reason='2024-08-19起不再披露每日净买额；仅展示此前历史，非当日资金流')
    return metric


def fetch_north_flow(now, get_json):
    params = {'reportName': 'RPT_MUTUAL_DEAL_HISTORY', 'columns': 'TRADE_DATE,NET_DEAL_AMT',
              'filter': '(MUTUAL_TYPE="005")(TRADE_DATE<\'2024-08-19\')',
              'pageSize':90, 'pageNumber':1, 'sortColumns':'TRADE_DATE','sortTypes':-1,
              'source':'WEB','client':'WEB'}
    return north_history(get_json('https://datacenter-web.eastmoney.com/api/data/v1/get?'+urlencode(params)), now)

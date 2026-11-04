"""Validated, dated observations for Sentiment Lab. No implicit demo fallback."""
from copy import deepcopy
from datetime import datetime
import math

SCHEMA_VERSION = 2
SOURCES = {
    'indexes': '东方财富 · 指数日线',
    'market_sentiment': '东方财富 · 沪深市场广度 / AKShare · 涨跌停池',
    'volume': '东方财富 · 上证综指与深证综指日线成交额',
    'north_flow': '沪深港通公开披露',
    'panic_index': 'Sentiment Lab · 自定义公式 v2',
    'vix': 'Yahoo Finance · ^VIX',
    'sp500': 'Yahoo Finance · ^GSPC',
}

def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def valid_date(value):
    try:
        return isinstance(value, str) and datetime.strptime(value, '%Y-%m-%d').strftime('%Y-%m-%d') == value
    except (ValueError, TypeError):
        return False

def history_merge(old, new):
    """Only accept dated finite observations; same-session reruns replace, never append."""
    points = {}
    for point in (old or []) + (new or []):
        if isinstance(point, dict) and valid_date(point.get('date')) and finite(point.get('value')):
            points[point['date']] = {'date': point['date'], 'value': round(point['value'], 4)}
    return [points[day] for day in sorted(points)][-90:]

def missing(key, reason, history=None):
    return {'value': None, 'change_pct': None, 'history': history_merge([], history),
            'meta': {'status': 'missing', 'source': SOURCES.get(key, key),
                     'trade_date': None, 'fetched_at': None, 'reason': reason}}

def fresh(key, value, trade_date, fetched_at, **fields):
    if not finite(value) or not valid_date(trade_date):
        raise ValueError(f'Invalid observation: {key}')
    return {
        'value': value, 'change_pct': None, 'history': [], **fields,
        'meta': {'status': 'fresh', 'source': SOURCES[key], 'trade_date': trade_date,
                 'fetched_at': fetched_at, 'reason': ''}}


def fallback(key, old, reason):
    if isinstance(old, dict) and finite(old.get('value')) and old.get('meta', {}).get('status') in ('fresh', 'cached') and valid_date(old['meta'].get('trade_date')):
        result = deepcopy(old)
        result['meta'].update(status='cached', reason=reason)
        result['history'] = history_merge([], old.get('history'))
        return result
    return missing(key, reason)

def calc_panic(sentiment, volume):
    values = [sentiment.get(k) for k in ('up_count', 'down_count', 'limit_up', 'limit_down')]
    vs = volume.get('vs_20day_avg')
    if not all(finite(v) and v >= 0 for v in values) or not finite(vs):
        return {'value': None, 'label': '数据不足', 'components': []}
    up, down, lu, ld = values
    if up + down <= 0 or lu + ld <= 0:
        return {'value': None, 'label': '数据不足', 'components': []}
    if not valid_date(sentiment.get('meta', {}).get('trade_date')) or sentiment.get('meta', {}).get('trade_date') != volume.get('meta', {}).get('trade_date'):
        return {'value': None, 'label': '行情日期不一致', 'components': []}
    breadth = down / (up + down) * 100
    limits = ld / (lu + ld) * 100
    liquidity = 100 if vs < -30 else 70 if vs < -10 else 50 if vs < 0 else 30 if vs < 20 else 10
    components = [{'name': name, 'score': round(score, 2), 'weight': weight,
                   'contribution': round(score * weight, 2)} for name, score, weight in
                  [('下跌占比', breadth, .4), ('跌停占比', limits, .3), ('成交额偏离', liquidity, .3)]]
    value = round(sum(c['contribution'] for c in components), 1)
    label = '乐观' if value < 20 else '平稳' if value < 40 else '恐慌' if value < 60 else '恐惧' if value < 80 else '极度恐慌'
    return {'value': value, 'label': label, 'components': components}

def migrate(data):
    """Do not invent dates for legacy histories or relabel VIXY as VIX."""
    if data.get('schema_version') == SCHEMA_VERSION:
        return deepcopy(data)
    result = {'schema_version': SCHEMA_VERSION, 'update_time': data.get('update_time'),
              'data_note': '旧版快照缺少来源与行情日期，未验证数据已隐藏。请运行一次真实采集。',
              'a_share': {'indexes': []}, 'us_market': {}}
    for code, name in [('000001', '上证指数'), ('399001', '深证成指'), ('399006', '创业板指')]:
        result['a_share']['indexes'].append(dict(missing('indexes', '旧快照未记录可验证的行情日期'), code=code, name=name))
    for key in ('market_sentiment', 'north_flow', 'volume', 'panic_index'):
        result['a_share'][key] = missing(key, '旧版数据未经验证，等待真实采集')
    result['a_share']['market_sentiment'].update(up_count=None, down_count=None, limit_up=None, limit_down=None)
    result['a_share']['volume'].update(unit='亿', vs_20day_avg=None)
    result['a_share']['north_flow']['reason_detail'] = '旧版以 0 代替缺失，无法确定是否有效。'
    result['a_share']['panic_index'].update(label='数据不足', components=[])
    result['us_market']['vix'] = missing('vix', '旧版使用 VIXY ETF，不能作为 VIX 指数保留')
    result['us_market']['sp500'] = missing('sp500', '旧快照未记录行情日期，不能推断历史')
    return result

def validate(data):
    errors = []
    if data.get('schema_version') != SCHEMA_VERSION:
        return ['Unsupported schema_version']
    if not isinstance(data.get('a_share'), dict) or not isinstance(data.get('us_market'), dict):
        return ['Missing market objects']
    a, us = data['a_share'], data['us_market']
    indexes = a.get('indexes')
    if not isinstance(indexes, list) or len(indexes) != 3 or {i.get('code') for i in indexes if isinstance(i, dict)} != {'000001', '399001', '399006'}:
        errors.append('Exactly three named A-share indexes are required')
    metrics = (indexes if isinstance(indexes, list) else []) + [a.get(k) for k in ('market_sentiment','north_flow','volume','panic_index')] + [us.get(k) for k in ('vix','sp500')]
    for metric in metrics:
        if not isinstance(metric, dict):
            errors.append('Missing metric'); continue
        meta = metric.get('meta', {})
        if meta.get('status') not in ('fresh','cached','missing','demo') or not meta.get('source'):
            errors.append('Invalid metric metadata')
        if meta.get('status') in ('fresh','cached') and (not finite(metric.get('value')) or not valid_date(meta.get('trade_date'))):
            errors.append('Valid observations need a finite value and trade_date')
        if meta.get('status') == 'missing' and metric.get('value') is not None:
            errors.append('Missing observations must use null')
        history = metric.get('history', [])
        if not isinstance(history, list) or len(history) > 90 or history != history_merge([], history):
            errors.append('History must be unique, dated, finite and ordered (max 90)')
    return errors

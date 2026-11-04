import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from data_model import *
from fetch_data import fetch_volume, collect

class ModelTests(unittest.TestCase):
    def test_missing_zero_negative(self):
        for v in (0,-23.2):
            m=fresh('north_flow',v,'2026-11-03','2026-11-04T08:00:00+08:00')
            self.assertEqual(fallback('north_flow',m,'offline')['value'],v)
        self.assertIsNone(fallback('north_flow',{'value':0},'offline')['value'])
    def test_history_upsert(self):
        points=[{'date':f'2026-10-{i:02d}','value':i} for i in range(1,29)]
        self.assertEqual(len(history_merge(points,[{'date':'2026-10-28','value':99}])),28)
        self.assertEqual(history_merge(points,[{'date':'2026-10-28','value':99}])[-1]['value'],99)
        self.assertEqual(history_merge([1,2,{'date':'wrong','value':3}],[]),[])
    def test_score_complete_same_date(self):
        s={'up_count':60,'down_count':40,'limit_up':8,'limit_down':2,'meta':{'trade_date':'2026-11-03'}}
        v={'vs_20day_avg':5,'meta':{'trade_date':'2026-11-03'}}
        result=calc_panic(s,v)
        self.assertEqual(result['value'],31)
        self.assertEqual(sum(c['weight'] for c in result['components']),1)
        v['meta']['trade_date']='2026-11-02'
        self.assertIsNone(calc_panic(s,v)['value'])
        self.assertIsNone(calc_panic({'up_count':0,'down_count':0,'limit_up':0,'limit_down':0},v)['value'])
    def test_migration_rejects_legacy(self):
        d=migrate({'us_market':{'vix':{'value':44,'history':[2,3]}}})
        self.assertIsNone(d['us_market']['vix']['value'])
        self.assertEqual(validate(d),[])
        d['a_share']['indexes'].append(d['a_share']['indexes'][0])
        self.assertTrue(validate(d))
    def test_volume_baseline_excludes_current(self):
        rows=[{'date':f'2026-10-{i:02d}','amount':100000000} for i in range(1,22)]
        rows[-1]['amount']=200000000
        result=fetch_volume(rows,rows,'2026-11-04T08:00:00+08:00')
        self.assertEqual(result['value'],4)
        self.assertEqual(result['vs_20day_avg'],100)
        self.assertEqual(result['baseline_days'],20)
    def test_independent_fallback(self):
        previous=migrate({})
        previous['us_market']['vix']=fresh('vix',18,'2026-11-03','2026-11-04T08:00:00+08:00')
        with patch('fetch_data.daily_index',side_effect=RuntimeError),patch('fetch_data.yahoo_series',side_effect=RuntimeError),patch('fetch_data.cboe_vix',side_effect=RuntimeError),patch('fetch_data.sina_sp500',side_effect=RuntimeError),patch('fetch_data.fetch_north_flow',side_effect=RuntimeError):
            data=collect(previous)
        self.assertEqual(len(data['a_share']['indexes']),3)
        self.assertEqual(data['us_market']['vix']['value'],18)
        self.assertEqual(data['us_market']['vix']['meta']['status'],'cached')
        self.assertIsNone(data['a_share']['north_flow']['value'])
        self.assertEqual(validate(data),[])

if __name__=='__main__': unittest.main()

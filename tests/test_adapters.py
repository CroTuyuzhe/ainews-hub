import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from source_adapters import sina_sp500,cboe_vix,north_history
from data_model import history_merge

NOW='2026-11-04T12:00:00+08:00'
class AdapterTests(unittest.TestCase):
    def sina(self, quote='Nov 3 04:30PM EST'):
        parts=['']*30
        parts[1]='7568.9199';parts[2]='0.36';parts[25]=quote;parts[29]='2026'
        return 'var quote="'+','.join(parts)+'";'
    def test_sina_exchange_day_not_beijing_day(self):
        with patch('source_adapters.download',return_value=self.sina()):
            result=sina_sp500(NOW)
        self.assertEqual(result['meta']['trade_date'],'2026-11-03')
        self.assertEqual(result['value'],7568.92)
    def test_sina_intraday_rejected(self):
        with patch('source_adapters.download',return_value=self.sina('Nov 3 03:30PM EST')):
            with self.assertRaises(ValueError):sina_sp500(NOW)
    def test_official_vix_only_complete_sessions(self):
        raw='DATE,OPEN,HIGH,LOW,CLOSE\n11/02/2026,1,1,1,18\n11/03/2026,1,1,1,20\n11/04/2026,1,1,1,30'
        with patch('source_adapters.download',return_value=raw):result=cboe_vix(NOW)
        self.assertEqual(result['value'],20)
        self.assertEqual(result['meta']['trade_date'],'2026-11-03')
    def test_north_combined_history_units_zero_negative_and_cutoff(self):
        result=north_history({'result':{'data':[
            {'TRADE_DATE':'2024-08-15 00:00:00','NET_DEAL_AMT':0},
            {'TRADE_DATE':'2024-08-16 00:00:00','NET_DEAL_AMT':-1250},
            {'TRADE_DATE':'2026-11-03 00:00:00','NET_DEAL_AMT':0},
            {'TRADE_DATE':'2024-08-14 00:00:00','NET_DEAL_AMT':None}]}},NOW)
        self.assertEqual(result['value'],-12.5)
        self.assertEqual(len(result['history']),2)
        self.assertEqual(result['meta']['status'],'cached')
        self.assertEqual(result['meta']['trade_date'],'2024-08-16')
    def test_missing_north_is_not_zero(self):
        with self.assertRaises(ValueError):north_history({'result':{'data':[]}},NOW)
    def test_retention_max90_across_runs(self):
        from datetime import date,timedelta
        points=[{'date':(date(2026,1,1)+timedelta(days=i)).isoformat(),'value':i} for i in range(120)]
        merged=history_merge(points[:80],points[80:])
        self.assertEqual(len(merged),90)
        self.assertEqual(merged[0],points[30])
        self.assertEqual(merged[-1],points[-1])
if __name__=='__main__':unittest.main()

import sys,unittest
from contextlib import ExitStack
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from data_model import calc_panic,migrate,fresh
from fetch_data import collect,fetch_breadth
from source_adapters import legu_breadth
NOW='2026-11-04T12:00:00+08:00'

def breadth(day='2026-11-04', session='intraday'):
    m=fresh('market_sentiment',100,day,NOW,up_count=60,down_count=40,limit_up=8,limit_down=2)
    m['meta']['session']=session
    return m
class ScoreContinuityTests(unittest.TestCase):
    def test_reference_excludes_previous_day_turnover(self):
        volume=fresh('volume',100,'2026-11-03',NOW,vs_20day_avg=-99)
        result=calc_panic(breadth(),volume,allow_partial=True)
        self.assertEqual(result['value'],31.4)
        self.assertEqual(result['coverage'],.7)
        self.assertEqual(result['calculation_mode'],'partial')
        self.assertEqual(len(result['components']),2)
        self.assertAlmostEqual(sum(c['weight'] for c in result['components']),1)
    def test_intraday_turnover_never_contaminates_reference(self):
        volume=fresh('volume',100,'2026-11-04',NOW,vs_20day_avg=-99)
        self.assertEqual(calc_panic(breadth(),volume,allow_partial=True)['value'],31.4)
        full=calc_panic(breadth(session='closed'),volume,allow_partial=True)
        self.assertEqual(full['value'],52)
        self.assertEqual(full['calculation_mode'],'complete')
    def test_single_component_does_not_create_score(self):
        m=breadth();m['limit_up']=m['limit_down']=None
        self.assertIsNone(calc_panic(m,{},allow_partial=True)['value'])
    def test_primary_snapshot_keeps_its_actual_day_and_limit_request(self):
        stamp=int(datetime.fromisoformat('2026-11-04T11:30:00+08:00').timestamp())
        data={'data':{'diff':[{'f104':30,'f105':20,'f124':stamp},{'f104':30,'f105':20,'f124':stamp}]}}
        class Frame:
            def __len__(self):return 2
        with patch('fetch_data.get_json',return_value=data),patch('akshare.stock_zt_pool_em',return_value=Frame()) as lu,patch('akshare.stock_zt_pool_dtgc_em',return_value=Frame()):
            m=fetch_breadth('2026-11-03',NOW)
        self.assertEqual(m['meta']['trade_date'],'2026-11-04')
        self.assertEqual(m['limit_up'],2)
        lu.assert_called_once_with(date='20261104')
    def test_legu_requires_timestamp_and_all_components(self):
        html='<span class="market-activity-time">2026-11-04 11:30:00</span>'
        html+=''.join(f'<div id="{key}" data-chart="{value}"></div>' for key,value in [('totalUp',60),('totalDown',40),('limitUp',8),('limitDown',2)])
        with patch('source_adapters.download',return_value=html):m=legu_breadth(NOW)
        self.assertEqual(m['meta']['session'],'intraday')
        self.assertEqual(m['limit_down'],2)
        with patch('source_adapters.download',return_value=html.replace('market-activity-time','removed')):
            with self.assertRaises(ValueError):legu_breadth(NOW)
    def test_source_outage_preserves_previous_score(self):
        previous=migrate({});previous['a_share']['panic_index']=fresh('panic_index',31,'2026-11-03',NOW,label='平稳',components=[])
        with ExitStack() as stack:
            for name in ['daily_index','fetch_breadth','legu_breadth','fetch_north_flow','yahoo_series','cboe_vix','sina_sp500']:
                stack.enter_context(patch('fetch_data.'+name,side_effect=RuntimeError))
            result=collect(previous)['a_share']['panic_index']
        self.assertEqual(result['value'],31)
        self.assertEqual(result['meta']['trade_date'],'2026-11-03')
        self.assertEqual(result['meta']['status'],'cached')
    def test_reference_not_written_to_close_history(self):
        previous=migrate({})
        with ExitStack() as stack:
            for name in ['daily_index','fetch_breadth','fetch_north_flow','yahoo_series','cboe_vix','sina_sp500']:
                stack.enter_context(patch('fetch_data.'+name,side_effect=RuntimeError))
            stack.enter_context(patch('fetch_data.legu_breadth',return_value=breadth()))
            result=collect(previous)['a_share']['panic_index']
        self.assertEqual(result['calculation_mode'],'partial')
        self.assertEqual(result['history'],[])
        self.assertEqual(result['value'],31.4)
if __name__=='__main__':unittest.main()

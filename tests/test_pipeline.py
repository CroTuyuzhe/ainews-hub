import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from data_model import migrate,fresh
from fetch_data import daily_index,fetch_volume

class PipelineTests(unittest.TestCase):
    def test_tencent_fallback_does_not_fake_turnover(self):
        quote={'data':{'sh000001':{'day':[['2026-01-01','100','100','101','99','99999'],['2026-01-02','100','110','111','99','99999']]}}}
        with patch('fetch_data.get_json',side_effect=[RuntimeError(),quote]):rows=daily_index('1.000001')
        self.assertEqual(rows[-1]['change_pct'],10)
        self.assertIsNone(rows[-1]['amount'])
        self.assertIn('腾讯',rows[-1]['source'])
        with self.assertRaises(ValueError):fetch_volume(rows,rows,'2026-11-04T12:00:00+08:00')
    def test_restore_collect_build_contract(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)
            shutil.copytree(root/'scripts',dest/'scripts')
            (dest/'data').mkdir()
            for name in ('index.html','app.js'):shutil.copy2(root/name,dest/name)
            data=migrate({})
            data['us_market']['vix']=fresh('vix',20,'2026-11-03','2026-11-04T08:00:00+08:00',history=[{'date':'2026-11-03','value':20}])
            (dest/'published.json').write_text(json.dumps(data),encoding='utf-8')
            def run(*args):return subprocess.run([sys.executable,*args],cwd=dest,capture_output=True,text=True)
            self.assertEqual(run('scripts/restore_cache.py','published.json').returncode,0)
            self.assertEqual(run('scripts/restore_cache.py','data/data.json','--mark-cached').returncode,0)
            cached=json.loads((dest/'data/data.json').read_text(encoding='utf-8'))
            self.assertEqual(cached['us_market']['vix']['meta']['trade_date'],'2026-11-03')
            self.assertEqual(cached['us_market']['vix']['meta']['status'],'cached')
            self.assertEqual(run('scripts/build_site.py').returncode,0)
            self.assertTrue((dest/'dist/app.js').is_file())
            self.assertEqual(json.loads((dest/'dist/data.json').read_text(encoding='utf-8')),cached)
            (dest/'data/data.json').write_text('{"schema_version":1}',encoding='utf-8')
            self.assertNotEqual(run('scripts/build_site.py').returncode,0)
            self.assertEqual(json.loads((dest/'dist/data.json').read_text(encoding='utf-8')),cached)
if __name__=='__main__':unittest.main()

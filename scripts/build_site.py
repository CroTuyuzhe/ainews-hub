"""Strict static build: invalid snapshots never reach deployment."""
import json
import os
import hashlib
import shutil
from pathlib import Path
from data_model import validate
ROOT = Path(__file__).resolve().parent.parent

def build():
    data = json.loads((ROOT/'data/data.json').read_text(encoding='utf-8'))
    errors = validate(data)
    if errors:
        raise ValueError('; '.join(errors))
    (ROOT/'dist').mkdir(exist_ok=True)
    for name in ('index.html', 'app.js'):
        shutil.copy2(ROOT/name, ROOT/'dist'/name)
    shutil.copy2(ROOT/'data/data.json', ROOT/'dist/data.json')
    # Root preview uses the same canonical snapshot.
    shutil.copy2(ROOT/'data/data.json', ROOT/'data.json')
    archive=ROOT/'data/legacy-data.json'
    if archive.exists(): shutil.copy2(archive,ROOT/'dist/legacy-data.json')
    (ROOT/'dist/.nojekyll').touch()
    (ROOT/'dist/version.json').write_text(json.dumps({'source_commit':os.environ.get('GITHUB_SHA','local'), 'snapshot_sha256':hashlib.sha256((ROOT/'dist/data.json').read_bytes()).hexdigest()}),encoding='utf-8')
    print('[OK] Schema validated; HTML, JS and canonical snapshot built')

if __name__ == '__main__': build()

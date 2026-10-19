"""Exercise manager HTTP persistence and failure recovery using disposable data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from store import Store, atomic_json


def run():
    with tempfile.TemporaryDirectory() as folder:
        store = Store(folder)
        course = store.save_course({'name': '验证课程', 'root': folder, 'notes': '原备注'}, 0)
        path = str(Path(folder) / '作业要求.md')
        atomic_json(store.root / 'indexes' / (course['id'] + '.json'), {'files': [{'path': path, 'type': 'lab'}]})
        process = subprocess.Popen([sys.executable, str(ROOT / 'runtime/app.py'), '--data-root', folder, 'serve'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            info = json.loads(process.stdout.readline())
            base, token = info['url'].split('#')

            def request(path, body=None, auth=True, origin=None):
                headers = {'X-Campus-Token': token} if auth else {}
                if origin:
                    headers['Origin'] = origin
                if body is not None:
                    headers['Content-Type'] = 'application/json'
                req = urllib.request.Request(base + path, headers=headers,
                    data=json.dumps(body).encode() if body is not None else None)
                with urllib.request.urlopen(req, timeout=5) as res:
                    return json.loads(res.read())

            for cycle in range(3):
                state = request('api/state')
                request('api/materials', {'course_id': course['id'], 'revision': state['revision'],
                    'paths': [path], 'type': 'assignment-brief', 'notes': f'验证 {cycle}'})
                result = request('api/index/' + course['id'])['files'][0]
                assert result['confirmed'] and result['source'] == 'manual'
                assert result['notes'] == f'验证 {cycle}'
                try:
                    request('api/materials', {'course_id': course['id'], 'revision': state['revision'], 'paths': [path], 'type': 'other'})
                    raise AssertionError('Stale revision accepted')
                except urllib.error.HTTPError as exc:
                    assert exc.code == 400
                assert request('api/index/' + course['id'])['files'][0]['notes'] == f'验证 {cycle}'
            for auth, origin in [(False, None), (True, 'https://example.org')]:
                try:
                    request('api/state', auth=auth, origin=origin)
                    raise AssertionError('Unauthenticated or cross-origin request accepted')
                except urllib.error.HTTPError as exc:
                    assert exc.code == 403
            with urllib.request.urlopen(base, timeout=5) as res:
                assert b'assets/' in res.read()
            print('PASS: 3 HTTP save/readback/revision-conflict cycles; auth/origin rejection; built UI entry')
        finally:
            process.terminate()
            process.communicate(timeout=5)


if __name__ == '__main__':
    run()

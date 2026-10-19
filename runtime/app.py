"""Local course manager and workflow CLI; Python standard library only."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, urlencode

from store import Store, atomic_json, read_json, now, valid_id, lock
from catalog import catalog, update_materials
from notes import list_notes, read_note
import course_info

ROOT = Path(__file__).resolve().parent.parent


def request_index(store, course_id):
    """Persist a request for the host Agent; never substitute a CLI model."""
    valid_id(course_id)
    if not store.course(course_id):
        raise ValueError('课程不存在')
    path = store.root / 'jobs' / (course_id + '.json')
    with lock(store.root, 'jobs'):
        old = read_json(path, {})
        if old.get('status') in ('awaiting_agent', 'running'):
            return old
        job = {'course_id': course_id, 'status': 'awaiting_agent', 'model': 'gpt-6-luna', 'reasoning_effort': 'high', 'created_at': now()}
        atomic_json(path, job)
        return job


def update_job(store, course_id, status, error=''):
    valid_id(course_id)
    with lock(store.root, 'jobs'):
        path = store.root / 'jobs' / (course_id + '.json')
        job = read_json(path, {})
        if not job:
            raise ValueError('没有待处理的索引请求')
        job.update(status=status, error=error)
        job['started_at' if status == 'running' else 'finished_at'] = now()
        atomic_json(path, job)
        return job


def state(store):
    reg = store.registry()
    jobs = [read_json(p, {}) for p in (store.root / 'jobs').glob('*.json')]
    return {**reg, 'data_root': str(store.root), 'jobs': jobs}


def serve(store, port=0):
    token = secrets.token_urlsafe(32)
    previews = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, value, mime='application/json; charset=utf-8', preview=False):
            data = json.dumps(value, ensure_ascii=False).encode() if mime.startswith('application/json') else value
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            policy = ("sandbox allow-scripts; default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; font-src data:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'" if preview else "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'; frame-src 'self'; frame-ancestors 'none'")
            self.send_header('Content-Security-Policy', policy)
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            expected = '127.0.0.1:' + str(self.server.server_port)
            origin = self.headers.get('Origin')
            return self.headers.get('Host') == expected and (not origin or origin == 'http://' + expected)

        def do_GET(self):
            if not self.allowed():
                return self.respond(403, {'error': '不允许的访问来源'})
            path = urlsplit(self.path).path
            if path.startswith('/preview/'):
                entry = previews.get(path.rsplit('/', 1)[-1])
                if not entry or entry['expires'] < time.monotonic():
                    return self.respond(404, b'Preview expired. Close and reopen the note.', 'text/plain; charset=utf-8')
                try:
                    return self.respond(200, read_note(store, entry['course_id'], entry['note_id']), 'text/html; charset=utf-8', preview=True)
                except (ValueError, OSError):
                    return self.respond(404, b'Note is no longer available.', 'text/plain; charset=utf-8')
            if path.startswith('/api/'):
                if self.headers.get('X-Campus-Token') != token:
                    return self.respond(403, {'error': '请从技能提供的管理链接打开'})
                try:
                    if path == '/api/state':
                        return self.respond(200, state(store))
                    if path.startswith('/api/index/'):
                        return self.respond(200, catalog(store, path.rsplit('/', 1)[1]))
                    if path.startswith('/api/notes/'):
                        return self.respond(200, list_notes(store, path.rsplit('/', 1)[1]))
                    if path.startswith('/api/course-info/'):
                        return self.respond(200, course_info.view(store, path.rsplit('/', 1)[1]))
                    if path == '/api/records':
                        return self.respond(200, store.records())
                    return self.respond(404, {'error': '接口不存在'})
                except (ValueError, OSError) as exc:
                    return self.respond(400, {'error': str(exc)})
            files = {'/': ('ui/index.html', 'text/html; charset=utf-8'), '/app.js': ('ui/app.js', 'text/javascript; charset=utf-8'), '/style.css': ('ui/style.css', 'text/css; charset=utf-8'), '/icon.png': ('assets/icon.png', 'image/png')}
            if path.startswith('/assets/'):
                import mimetypes
                file = (ROOT / 'ui' / path.lstrip('/')).resolve()
                if not file.is_relative_to((ROOT / 'ui' / 'assets').resolve()) or not file.is_file():
                    return self.respond(404, {'error': '资源不存在'})
                return self.respond(200, file.read_bytes(), mimetypes.guess_type(file)[0] or 'application/octet-stream')
            if path not in files:
                return self.respond(404, {'error': '页面不存在'})
            file, mime = files[path]
            return self.respond(200, (ROOT / file).read_bytes(), mime)

        def do_POST(self):
            if not self.allowed() or self.headers.get('X-Campus-Token') != token:
                return self.respond(403, {'error': '访问凭据无效'})
            try:
                size = int(self.headers.get('Content-Length', 0))
                if size <= 0 or size > 2_000_000:
                    raise ValueError('请求大小无效')
                body = json.loads(self.rfile.read(size))
                if self.path == '/api/course':
                    value = store.save_course(body['course'], body['revision'])
                elif self.path == '/api/materials':
                    value = update_materials(store, body)
                elif self.path == '/api/validate-directory':
                    folder = Path(str(body.get('path', ''))).expanduser()
                    if not folder.is_absolute() or not folder.is_dir():
                        raise ValueError('请选择存在的完整目录路径')
                    value = {'path': str(folder.resolve()), 'broad': len([p for p in folder.iterdir() if p.is_dir()]) > 8}
                elif self.path == '/api/pick-directory':
                    # Run outside the HTTP thread: Tk requires a process main thread.
                    script = "import tkinter as t;from tkinter import filedialog;import json;r=t.Tk();r.withdraw();r.attributes('-topmost',True);p=filedialog.askdirectory(title='选择课程资料目录');r.destroy();print(json.dumps({'path':p},ensure_ascii=False))"
                    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, encoding='utf-8', timeout=180,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
                    if result.returncode:
                        raise ValueError('系统目录选择器不可用，请粘贴完整目录路径')
                    value = json.loads(result.stdout)
                elif self.path == '/api/reindex':
                    value = request_index(store, body['course_id'])
                elif self.path == '/api/feishu':
                    store.set_feishu(str(body['url']).strip())
                    value = {'saved': True}
                elif self.path == '/api/note-preview':
                    read_note(store, body['course_id'], body['note_id'])
                    for key in list(previews):
                        if previews[key]['expires'] < time.monotonic(): previews.pop(key, None)
                    ticket = secrets.token_urlsafe(32)
                    previews[ticket] = {**body, 'expires': time.monotonic() + 3600}
                    value = {'url': '/preview/' + ticket}
                elif self.path == '/api/course-info-edit':
                    value = course_info.edit(store, body)
                elif self.path == '/api/course-info-resolve':
                    value = course_info.resolve(store, body)
                elif self.path == '/api/course-info-sync':
                    value = course_info.sync(store, body['course_id'], push=body.get('push', True))
                else:
                    return self.respond(404, {'error': '接口不存在'})
                return self.respond(200, value)
            except (ValueError, KeyError, TypeError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                return self.respond(400, {'error': str(exc)})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = 'http://127.0.0.1:' + str(server.server_port) + '/#' + token
    atomic_json(store.root / 'manager.json', {'pid': os.getpid(), 'url': url, 'port': server.server_port, 'created_at': now(), 'runtime_root': str(ROOT)})
    print(json.dumps({'url': url, 'data_root': str(store.root)}, ensure_ascii=False), flush=True)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list')
    sub.add_parser('records')
    p = sub.add_parser('serve'); p.add_argument('--port', type=int, default=0)
    p = sub.add_parser('open'); p.add_argument('--course-id'); p.add_argument('--view', choices=['materials','notes','info','settings'], default='materials')
    p = sub.add_parser('notes'); p.add_argument('--course-id', required=True)
    p = sub.add_parser('course-info'); p.add_argument('--course-id', required=True)
    p = sub.add_parser('sync-info'); p.add_argument('--course-id'); p.add_argument('--pull-only', action='store_true')
    for cmd in ('save-course', 'ingest', 'confirm', 'export', 'complete', 'edit-info', 'transcripts'):
        p = sub.add_parser(cmd); p.add_argument('--input', required=True)
    p = sub.add_parser('feishu'); p.add_argument('--url', required=True)
    p = sub.add_parser('index'); p.add_argument('--course-id', required=True)
    p = sub.add_parser('job-status'); p.add_argument('--course-id', required=True); p.add_argument('--status', required=True, choices=['running', 'completed', 'failed']); p.add_argument('--error', default='')
    args = parser.parse_args()
    store = Store(args.data_root)
    result = None
    if args.command == 'serve':
        return serve(store, args.port)
    if args.command == 'open':
        import urllib.request
        info = read_json(store.root / 'manager.json', {})
        if info and info.get('runtime_root') == str(ROOT):
            try:
                token = info['url'].split('#')[1]
                req = urllib.request.Request(info['url'].split('#')[0] + 'api/state', headers={'X-Campus-Token': token})
                with urllib.request.urlopen(req, timeout=2) as response:
                    if response.status == 200:
                        result = info
            except Exception:
                pass
        if result is None:
            creation = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--data-root', str(store.root), 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation)
            for _ in range(50):
                info = read_json(store.root / 'manager.json', {})
                if info and info.get('runtime_root') == str(ROOT) and info.get('pid') != (result or {}).get('pid'):
                    try:
                        req = urllib.request.Request(info['url'].split('#')[0] + 'api/state', headers={'X-Campus-Token': info['url'].split('#')[1]})
                        with urllib.request.urlopen(req, timeout=1):
                            result = info
                            break
                    except Exception:
                        pass
                time.sleep(.1)
            if result is None:
                raise RuntimeError('管理服务启动失败')
        result = dict(result)
        base, credential = result['url'].split('#', 1)
        if args.course_id and not store.course(args.course_id): raise ValueError('课程不存在')
        result['url'] = base + '?' + urlencode({'course': args.course_id or '', 'view': args.view}) + '#' + credential
    elif args.command == 'list': result = state(store)
    elif args.command == 'records': result = store.records()
    elif args.command == 'notes': result = list_notes(store, args.course_id)
    elif args.command == 'course-info': result = course_info.view(store, args.course_id)
    elif args.command == 'sync-info': result = course_info.sync(store, args.course_id, push=not args.pull_only)
    elif args.command == 'feishu': store.set_feishu(args.url); result = {'saved': True}
    elif args.command == 'index': result = request_index(store, args.course_id)
    elif args.command == 'job-status': result = update_job(store, args.course_id, args.status, args.error)
    else:
        source = json.loads(Path(args.input).read_text(encoding='utf-8-sig'))
        if args.command == 'save-course': result = store.save_course(source['course'], source['revision'])
        elif args.command == 'ingest': result = store.ingest(source)
        elif args.command == 'confirm': result = store.confirm_records(source['ids'], source['course_id'])
        elif args.command == 'export': result = store.export_records(source['ids'], source['course_id'])
        elif args.command == 'complete': result = store.complete_records(source['items'])
        elif args.command == 'edit-info': result = course_info.edit(store, source)
        elif args.command == 'transcripts':
            from transcripts import evidence
            result = evidence(store, source['ids'])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

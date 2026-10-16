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
from urllib.parse import urlsplit

from store import Store, atomic_json, read_json, now, valid_id, lock

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

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, value, mime='application/json; charset=utf-8'):
            data = json.dumps(value, ensure_ascii=False).encode() if mime.startswith('application/json') else value
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
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
            if path.startswith('/api/'):
                if self.headers.get('X-Campus-Token') != token:
                    return self.respond(403, {'error': '请从技能提供的管理链接打开'})
                try:
                    if path == '/api/state':
                        return self.respond(200, state(store))
                    if path.startswith('/api/index/'):
                        return self.respond(200, store.index(path.rsplit('/', 1)[1]))
                    if path == '/api/records':
                        return self.respond(200, store.records())
                    return self.respond(404, {'error': '接口不存在'})
                except (ValueError, OSError) as exc:
                    return self.respond(400, {'error': str(exc)})
            files = {'/': ('ui/index.html', 'text/html; charset=utf-8'), '/app.js': ('ui/app.js', 'text/javascript; charset=utf-8'), '/style.css': ('ui/style.css', 'text/css; charset=utf-8'), '/icon.png': ('assets/icon.png', 'image/png')}
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
                elif self.path == '/api/reindex':
                    value = request_index(store, body['course_id'])
                elif self.path == '/api/feishu':
                    store.set_feishu(str(body['url']).strip())
                    value = {'saved': True}
                else:
                    return self.respond(404, {'error': '接口不存在'})
                return self.respond(200, value)
            except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
                return self.respond(400, {'error': str(exc)})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = 'http://127.0.0.1:' + str(server.server_port) + '/#' + token
    atomic_json(store.root / 'manager.json', {'pid': os.getpid(), 'url': url, 'port': server.server_port, 'created_at': now()})
    print(json.dumps({'url': url, 'data_root': str(store.root)}, ensure_ascii=False), flush=True)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list')
    sub.add_parser('records')
    p = sub.add_parser('serve'); p.add_argument('--port', type=int, default=0)
    sub.add_parser('open')
    for cmd in ('save-course', 'ingest', 'confirm', 'export', 'complete'):
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
        if info:
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
                if info and info.get('pid') != (result or {}).get('pid'):
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
    elif args.command == 'list': result = state(store)
    elif args.command == 'records': result = store.records()
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

"""Central, versioned local state. No user data is stored in the plugin package."""
import contextlib
import datetime as dt
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

ICON_NAMES = frozenset(json.loads(Path(__file__).with_name('icon_catalog.json').read_text(encoding='utf-8')))
LEGACY_ICONS = {'📚':'BookOpen','🎓':'GraduationCap','💻':'Display','📐':'TriangleRight','🧪':'Flask','🔬':'Microscope','⚙️':'Gear','📊':'ChartColumn','🌐':'Globe','🎨':'Palette','📝':'Pencil','📖':'BookOpen'}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def data_path(value=None):
    base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'Documents')
    return Path(value or os.environ.get('OPPO_AI_PIN_DATA') or (Path(base) / 'OPPO-AI-Pin-Campus')).resolve()


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return default


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextlib.contextmanager
def lock(root, name='registry'):
    root.mkdir(parents=True, exist_ok=True)
    path = root / ('.' + name + '.lock')
    deadline = time.monotonic() + 15
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                raise RuntimeError('数据正在被其他操作使用，请稍后重试；若上次进程异常退出，请先检查锁文件。')
            time.sleep(.1)
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        path.unlink(missing_ok=True)


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value):
        raise ValueError('无效的课程标识')
    return value


class Store:
    def __init__(self, root=None):
        self.root = data_path(root)

    def registry(self):
        return read_json(self.root / 'registry.json', {'schema_version': 1, 'revision': 0, 'courses': [], 'feishu_document': ''})

    def course(self, course_id):
        valid_id(course_id)
        return next((c for c in self.registry()['courses'] if c['id'] == course_id), None)

    def index(self, course_id):
        return read_json(self.root / 'indexes' / (valid_id(course_id) + '.json'), {'course_id': course_id, 'files': []})

    def save_course(self, source, revision):
        with lock(self.root):
            reg = self.registry()
            if reg['revision'] != revision:
                raise ValueError('课程信息已发生变化，请刷新后重新编辑；本次输入仍保留。')
            cid = valid_id(source.get('id') or uuid.uuid4().hex)
            old = next((c for c in reg['courses'] if c['id'] == cid), {})
            name, root = str(source.get('name', '')).strip(), str(source.get('root', '')).strip()
            if not name or not root:
                raise ValueError('请填写课程名称和本地资料目录')
            if not Path(root).expanduser().is_absolute():
                raise ValueError('资料目录需要填写完整的绝对路径')
            fields = ('name', 'aliases', 'semester', 'teacher', 'notes', 'root', 'extra_roots', 'schedule', 'materials', 'icon')
            c = {**old, 'id': cid}
            for key in fields:
                if key in source:
                    c[key] = source[key]
            for key in ('aliases', 'extra_roots', 'schedule', 'materials'):
                c.setdefault(key, [])
                if not isinstance(c[key], list):
                    raise ValueError(key + ' 必须是列表')
            for key in ('name', 'root', 'semester', 'teacher', 'notes'):
                c.setdefault(key, '')
                if not isinstance(c[key], str):
                    raise ValueError(key + ' 必须是文字')
            icon = source.get('icon', old.get('icon', 'BookOpen'))
            if not isinstance(icon, str):
                raise ValueError('请选择有效的图标')
            icon = LEGACY_ICONS.get(icon, icon)
            if icon not in ICON_NAMES:
                raise ValueError('请选择图标库中的图标')
            c['icon'] = icon
            c['name'] = name
            c['root'] = str(Path(root).expanduser().resolve())
            for key in ('aliases', 'extra_roots', 'schedule'):
                if not all(isinstance(v, str) for v in c[key]):
                    raise ValueError(key + ' 必须是文字列表')
            if any(not Path(v).expanduser().is_absolute() for v in c['extra_roots']):
                raise ValueError('额外资料目录需要填写完整的绝对路径')
            c['extra_roots'] = [str(Path(v).expanduser().resolve()) for v in c['extra_roots']]
            if any(not isinstance(m, dict) or not isinstance(m.get('path'), str) for m in c['materials']):
                raise ValueError('资料必须包含有效路径')
            if any(not Path(m['path']).expanduser().is_absolute() for m in c['materials']):
                raise ValueError('指定资料需要填写完整的绝对路径')
            c['materials'] = [{**m, 'path': str(Path(m['path']).expanduser().resolve())} for m in c['materials']]
            changed = old.get('root') != c['root'] or old.get('extra_roots') != c['extra_roots']
            c['last_indexed_at'] = None if changed else old.get('last_indexed_at')
            if old:
                reg['courses'] = [c if x['id'] == cid else x for x in reg['courses']]
            else:
                reg['courses'].append(c)
            reg['revision'] += 1
            atomic_json(self.root / 'registry.json', reg)
            return c

    def set_feishu(self, url):
        if url and not re.match(r'https://[^/]+/(docx|wiki)/[^/?#]+', url):
            raise ValueError('请输入飞书文档或知识库文档链接')
        with lock(self.root):
            reg = self.registry()
            reg['feishu_document'] = url
            reg['revision'] += 1
            atomic_json(self.root / 'registry.json', reg)

    def records(self):
        return read_json(self.root / 'records.json', {'schema_version': 1, 'items': [], 'collection_end_ms': None})

    def ingest(self, batch):
        """Batch pages are retained only locally; a cursor advances only after both streams finish."""
        import hashlib
        pages = batch.get('pages', [])
        normalized, streams = [], {}
        for page in pages:
            kind = page['kind']
            if kind not in ('memory', 'note'):
                raise ValueError('未知记录类型')
            payload = page['payload']
            if isinstance(payload, str):
                payload = json.loads(payload)
            if 'structuredContent' in payload:
                payload = json.loads(payload['structuredContent']['result'])
            if 'body' in payload:
                if not payload.get('ok') or not payload['body'].get('success'):
                    raise ValueError('接口返回失败，未推进采集进度')
                payload = payload['body']['data']
            if not isinstance(payload.get('content'), list):
                raise ValueError('接口数据缺少 content')
            streams.setdefault(kind, []).append(payload)
            for raw in payload['content']:
                rid = raw.get('sessionId') if kind == 'memory' else raw.get('asrId')
                if not rid:
                    raise ValueError('记录缺少稳定标识')
                digest = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                normalized.append({'id': kind + ':' + str(rid), 'kind': kind, 'hash': digest, 'raw': raw})
        complete = batch.get('complete', False)
        if complete:
            for kind in ('memory', 'note'):
                parts = streams.get(kind, [])
                expected = parts[0].get('totalPages', 1) if parts else 0
                numbers = {p.get('number', 0) for p in parts}
                if not parts or numbers != set(range(max(expected, 1))) or not any(p.get('last') is True for p in parts):
                    raise ValueError('必须收齐全时记与随口记的所有分页，才能推进进度')
            if not isinstance(batch.get('end_time'), int):
                raise ValueError('缺少本次采集结束时间')
        with lock(self.root, 'records'):
            records = self.records()
            items = {r['id']: r for r in records['items']}
            for item in normalized:
                old = items.get(item['id'], {})
                changed = old.get('hash') != item['hash']
                items[item['id']] = {**old, **item, 'course_id': old.get('course_id'), 'confirmed': old.get('confirmed', False), 'review_state': 'pending' if changed else old.get('review_state', 'pending'), 'collected_at': now()}
            records['items'] = list(items.values())
            if complete:
                records['collection_end_ms'] = max(records.get('collection_end_ms') or 0, batch['end_time'])
            atomic_json(self.root / 'records.json', records)
            return {'total': len(items), 'received': len(normalized), 'collection_end_ms': records['collection_end_ms']}

    def confirm_records(self, ids, course_id):
        course = self.course(course_id)
        if not course:
            raise ValueError('课程不存在')
        with lock(self.root, 'records'):
            records = self.records()
            known = {r['id'] for r in records['items']}
            if not ids or any(i not in known for i in ids):
                raise ValueError('记录选择为空或包含不存在的记录')
            for item in records['items']:
                if item['id'] in ids:
                    item.update(course_id=course_id, confirmed=True)
            atomic_json(self.root / 'records.json', records)
        return {'confirmed': ids, 'course_id': course_id}

    def export_records(self, ids, course_id):
        c = self.course(course_id)
        if not c:
            raise ValueError('课程不存在')
        root = Path(c['root']).expanduser().resolve()
        if not root.is_dir():
            raise ValueError('课程目录不存在')
        items = {i['id']: i for i in self.records()['items']}
        if not ids or any(i not in items or not items[i].get('confirmed') or items[i].get('course_id') != course_id for i in ids):
            raise ValueError('请先由用户确认记录及课程归属')
        out = root / 'OPPO-AI-Pin' / '元数据'
        for rid in ids:
            atomic_json(out / (rid.replace(':', '-') + '.json'), items[rid])
        (root / 'OPPO-AI-Pin' / '课堂笔记').mkdir(parents=True, exist_ok=True)
        return {'metadata_dir': str(out), 'notes_dir': str(root / 'OPPO-AI-Pin' / '课堂笔记')}

    def complete_records(self, completions):
        with lock(self.root, 'records'):
            records = self.records()
            items = {i['id']: i for i in records['items']}
            for c in completions:
                item = items.get(c['id'])
                if not item or not item.get('confirmed') or item['hash'] != c['hash']:
                    raise ValueError('记录已变化或尚未确认，请重新核对后生成；未标记完成')
                artifact = Path(c['artifact']).resolve()
                course = self.course(item['course_id'])
                notes_root = (Path(course['root']) / 'OPPO-AI-Pin' / '课堂笔记').resolve()
                if not artifact.is_file() or artifact.suffix.lower() != '.html' or not artifact.is_relative_to(notes_root):
                    raise ValueError('笔记产物不存在或不在对应课程的课堂笔记目录')
            for c in completions:
                item = items[c['id']]
                item['review_state'] = 'completed'
                item.setdefault('artifacts', []).append({'path': str(Path(c['artifact']).resolve()), 'source_hash': c['hash'], 'created_at': now()})
            atomic_json(self.root / 'records.json', records)
            return {'completed': [c['id'] for c in completions]}

"""Discover generated HTML artifacts only; never scan or rebuild teaching indexes."""
import hashlib
from html.parser import HTMLParser
from pathlib import Path


class Title(HTMLParser):
    def __init__(self):
        super().__init__(); self.active = False; self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag == 'title': self.active = True
    def handle_endtag(self, tag):
        if tag == 'title': self.active = False
    def handle_data(self, value):
        if self.active: self.parts.append(value)


def note_files(store, course_id):
    course = store.course(course_id)
    if not course: raise ValueError('课程不存在')
    root = Path(course['root']).resolve()
    folder = root / 'OPPO-AI-Pin' / '课堂笔记'
    # A junction/symlink must not make the artifact viewer expose another directory.
    if not folder.resolve().is_relative_to(root): raise ValueError('笔记目录不能指向课程目录之外')
    if not folder.is_dir(): return []
    return [p for p in folder.glob('*.html') if p.is_file() and not p.is_symlink() and p.resolve().parent == folder.resolve()]


def note_id(path):
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:24]


def list_notes(store, course_id):
    records = store.records()['items']
    result = []
    for file in note_files(store, course_id):
        parser = Title()
        with file.open(encoding='utf-8-sig', errors='replace') as handle:
            parser.feed(handle.read(65536))
        sources = []
        for record in records:
            if record.get('course_id') != course_id: continue
            if any(str(Path(a['path']).resolve()) == str(file.resolve()) for a in record.get('artifacts', [])):
                sources.append(record['id'])
        result.append({'id': note_id(file), 'filename': file.name,
                       'title': ''.join(parser.parts).strip() or file.stem,
                       'modified_ms': int(file.stat().st_mtime * 1000),
                       'size': file.stat().st_size, 'source_ids': sources})
    return {'course_id': course_id, 'notes': sorted(result, key=lambda n: n['filename'], reverse=True)}


def read_note(store, course_id, identifier):
    file = next((f for f in note_files(store, course_id) if note_id(f) == identifier), None)
    if file is None: raise ValueError('笔记不存在，请刷新列表')
    if file.stat().st_size > 30_000_000: raise ValueError('笔记超过 30 MB，请从课程目录打开')
    return file.read_bytes()

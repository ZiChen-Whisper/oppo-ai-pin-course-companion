"""Material roles and provenance, separate from immutable index metadata."""
from pathlib import Path

TYPES = {
    'textbook': '教材', 'reference': '参考阅读', 'slides': '课件',
    'assignment-brief': '作业要求', 'assignment': '作业成果',
    'lab-guide': '实验指导', 'lab-report': '实验报告', 'revision': '复习资料',
    'notes': '课堂笔记', 'code-data': '代码 / 数据', 'other': '其他资料',
    'unclassified': '待分类',
}


def suggest(file):
    p = Path(file['path'])
    path, name, ext = str(p).lower(), p.stem.lower(), p.suffix.lower()
    hidden = any(part.lower() in {'.firecrawl', '.tmpdeps', '99_过程文件', 'node_modules', '__pycache__', '.git'} for part in p.parts) or p.name.startswith('~$') or name.lower() in {'skill', 'agents'}
    rules = [
        ('lab-report', ('实验报告',), name), ('lab-guide', ('实验指导', '实验任务'), name),
        ('assignment-brief', ('作业要求', '作业说明', '作业题', 'assignment brief'), name),
        ('revision', ('复习', '试卷', '往年', '习题'), name),
        ('notes', ('课堂笔记', '课程笔记'), name),
        ('textbook', ('教材', '课本', 'textbook'), name),
        ('reference', ('参考', '阅读'), name),
    ]
    role, reason = 'unclassified', '暂无可靠用途依据，请确认'
    for kind, words, value in rules:
        hit = next((w for w in words if w in value), None)
        if hit:
            role, reason = kind, f'文件名包含“{hit}”'
            break
    if role == 'unclassified':
        if ext in {'.py', '.js', '.ts', '.cpp', '.c', '.h', '.json', '.csv', '.sql'}:
            role, reason = 'code-data', '文件格式为代码或数据'
        elif ext in {'.ppt', '.pptx', '.key'} or '课件' in path:
            role, reason = 'slides', '演示文件格式或位于课件目录'
        elif '作业' in path:
            role, reason = 'assignment', '位于作业目录，具体用途待确认'
        elif '参考' in path:
            role, reason = 'reference', '位于参考资料目录'
    return {'type': role, 'reason': reason, 'source': 'rule', 'confirmed': False,
            'format': ext.lstrip('.').upper() or '无扩展名', 'hidden': hidden}


def catalog(store, course_id):
    course = store.course(course_id)
    if not course:
        raise ValueError('课程不存在')
    index = store.index(course_id)
    expected = {str(Path(p).resolve()) for p in [course['root'], *course.get('extra_roots', [])]}
    if index.get('roots') and {str(Path(p).resolve()) for p in index['roots']} != expected:
        index = {**index, 'files': [], 'warnings': ['资料目录已变更，旧索引暂不展示，请重新建立索引。']}
    files = {f['path']: {**f, **suggest(f)} for f in index.get('files', [])}
    for override in course.get('materials', []):
        path = override['path']
        original = files.get(path, {'path': path, 'name': Path(path).name, **suggest({'path': path})})
        role = override.get('type', 'other')
        role = {'textbook-markdown': 'textbook', 'lab': 'lab-guide'}.get(role, role)
        files[path] = {**original, **override, 'type': role, 'source': override.get('source', 'manual'),
                       'confirmed': override.get('confirmed', True), 'reason': override.get('reason', '由你指定'), 'hidden': False}
    return {**index, 'files': list(files.values()), 'types': TYPES}


def update_materials(store, body):
    course = store.course(body['course_id'])
    if not course:
        raise ValueError('课程不存在')
    files = {f['path']: f for f in catalog(store, course['id'])['files']}
    paths = body.get('paths', [])
    role = body.get('type')
    if not paths or len(paths) > 5000 or any(p not in files for p in paths):
        raise ValueError('请选择本课程索引中的有效资料')
    if role is not None and role not in TYPES:
        raise ValueError('资料用途无效')
    overrides = {m['path']: m for m in course.get('materials', [])}
    if body.get('primary') and len(paths) != 1:
        raise ValueError('主要教材只能选择一个文件')
    if body.get('primary'):
        for entry in overrides.values():
            entry.pop('primary', None)
    for path in paths:
        f = files[path]
        overrides[path] = {**overrides.get(path, {}), 'path': path, 'type': role or f['type'],
                           'source': 'manual', 'confirmed': True, 'reason': '由你确认',
                           'notes': body.get('notes', f.get('notes', ''))}
        if body.get('primary'):
            overrides[path].update(primary=True, type='textbook')
    return store.save_course({**course, 'materials': list(overrides.values())}, body['revision'])

"""Local editable mirror of Feishu paragraphs with explicit three-way conflicts.

No credential is stored here. Remote writes are precise block replacements or
insertions, guarded by document revision and followed by a full readback.
"""
import copy
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
import xml.etree.ElementTree as ET
from store import atomic_json, read_json, now, lock


def cli_command():
    exe = shutil.which('lark-cli') or shutil.which('lark-cli.cmd')
    if not exe: raise ValueError('未找到 lark-cli，请先安装飞书官方 CLI 并完成用户授权')
    path = Path(exe)
    # npm's Windows shim forwards arbitrary arguments through cmd.exe; bypass it.
    if path.suffix.lower() in ('.cmd', '.ps1', '.bat'):
        script = path.parent / 'node_modules' / '@larksuite' / 'cli' / 'scripts' / 'run.js'
        node = shutil.which('node')
        if not node or not script.is_file(): raise ValueError('飞书 CLI 启动器不可用，请重新安装官方 lark-cli')
        return [node, str(script)]
    return [exe]


class Feishu:
    def run(self, args, content=None):
        proc = subprocess.run(cli_command() + args + ['--as', 'user'], input=content,
                              capture_output=True, text=True, encoding='utf-8', timeout=90,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                              env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        try: result = json.loads(proc.stdout)
        except ValueError: raise ValueError('飞书未返回有效结果，请检查 lark-cli 用户授权')
        if proc.returncode or not result.get('ok'):
            raise ValueError('飞书同步失败：' + str(result.get('error') or result.get('message') or '请检查授权与文档权限')[:700])
        return result
    def fetch(self, url):
        return self.run(['docs', '+fetch', '--doc', url, '--detail', 'full'])
    def write(self, url, command, block_id, content, revision):
        args = ['docs', '+update', '--doc', url, '--command', command, '--content', '-', '--revision-id', str(revision)]
        if block_id: args += ['--block-id', block_id]
        return self.run(args, content)


def parse_document(response, courses):
    document = response['data']['document']
    root = ET.fromstring('<root>' + document['content'] + '</root>')
    refs = [document.get('reference_map', {}), response['data'].get('reference_map', {}), response.get('reference_map', {})]
    protected = set()
    # Comments may be represented as XML strings inside the reference map.
    for block_id in re.findall(r'block-id=["\']([^"\']+)', json.dumps(refs, ensure_ascii=False).replace('\\"', '"')):
        protected.add(block_id)
    course_id = None; course_level = 0; section = ''; blocks = []
    for element in root:
        tag = element.tag
        heading = re.fullmatch(r'h([1-6])', tag)
        text = ''.join(element.itertext()).strip()
        if heading:
            level = int(heading[1])
            matched = [c for c in courses if text in [c['name'], *c.get('aliases', [])]]
            if len(matched) == 1:
                course_id = matched[0]['id']; course_level = level; section = ''
            elif course_id and level <= course_level:
                course_id = None; section = ''
            elif course_id: section = text
        if not course_id: continue
        identifier = element.get('id')
        if not identifier: continue
        # Keep formatting, links, media and comments intact. Only plain paragraphs
        # (with optional line breaks) are editable from this compact mirror.
        editable = tag == 'p' and all(e.tag == 'br' for e in element) and identifier not in protected
        if editable:
            text = (element.text or '') + ''.join('\n' + (e.tail or '') for e in element)
        blocks.append({'id': identifier, 'course_id': course_id, 'section': section or '其他课程信息',
                       'tag': tag, 'text': text, 'editable': editable,
                       'xml': ET.tostring(element, encoding='unicode'), 'base_text': text})
    return blocks, document.get('revision_id')


def empty_state(url=''):
    return {'revision': 0, 'document_url': url, 'remote_revision': None, 'last_synced_at': None, 'blocks': []}


def state(store):
    url = store.registry().get('feishu_document', '')
    value = read_json(store.root / 'course-info.json', empty_state(url))
    # A changed association must not send the previous document's edits elsewhere.
    if value['document_url'] != url:
        return {**empty_state(url), 'association_changed': bool(value['blocks'])}
    return value


def view(store, course_id):
    if not store.course(course_id): raise ValueError('课程不存在')
    data = state(store)
    return {**data, 'blocks': [b for b in data['blocks'] if b['course_id'] == course_id]}


def edit(store, body):
    with lock(store.root, 'course-info'):
        data = state(store)
        if data['revision'] != body['revision']: raise ValueError('课程信息已变化，请刷新后重新编辑；输入仍保留')
        course_id = body['course_id']
        if not store.course(course_id): raise ValueError('课程不存在')
        text = body.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > 20000: raise ValueError('请输入 1～20000 字的信息')
        identifier = body.get('id')
        if identifier:
            block = next((b for b in data['blocks'] if b['id'] == identifier and b['course_id'] == course_id), None)
            if not block or not block['editable'] or block.get('conflict'): raise ValueError('该条目不可编辑，请先处理冲突或到飞书编辑')
            block.update(text=text.strip(), dirty=text.strip() != block['base_text'])
        else:
            if not data['document_url'] or not data['last_synced_at']: raise ValueError('请先关联文档并读取飞书信息')
            section = str(body.get('section') or '其他课程信息').strip()[:120]
            data['blocks'].append({'id': 'local-' + uuid.uuid4().hex, 'course_id': course_id,
                                   'section': section, 'tag': 'p', 'text': text.strip(),
                                   'base_text': None, 'editable': True, 'dirty': True, 'new': True})
        data['revision'] += 1
        atomic_json(store.root / 'course-info.json', data)
    return view(store, course_id)


def merge(local, remote):
    result = copy.deepcopy(remote)
    by_id = {b['id']: b for b in result}
    for old in local:
        if not old.get('dirty'): continue
        current = by_id.get(old['id'])
        if old.get('conflict'):
            # An unresolved decision is durable, even when its stored XML is
            # now identical to the latest remote snapshot. Only resolve() may
            # turn it back into a pending replacement.
            same_scope = current and current['course_id'] == old['course_id'] and current['section'] == old['section']
            conflict = copy.deepcopy(old)
            if current:
                conflict['conflict'] = {'remote_text':current['text'], 'remote_xml':current['xml'],
                                        'editable':current['editable'] if same_scope else False,
                                        'moved':not same_scope}
            elif not old.get('new'):
                conflict['conflict'] = {'remote_text':None, 'remote_xml':None, 'editable':False}
            if same_scope: result[result.index(current)] = conflict
            else: result.append(conflict)
            continue
        if old.get('new'):
            marker = '[CC:' + old['id'].removeprefix('local-') + ']'
            inserted = [b for b in result if not b.get('new') and marker in b['text']]
            if len(inserted) == 1:
                current = inserted[0]
                if current['course_id'] == old['course_id'] and current['section'] == old['section']:
                    remote_text = current['text'].removesuffix('\n' + marker)
                    sent = old.get('insert_sent_text')
                    if remote_text == old['text'] or old['text'] == sent:
                        continue  # Already delivered, or only Feishu changed.
                    if remote_text == sent and current['editable']:
                        current.update(text=old['text'] + '\n' + marker, dirty=True)
                    else:
                        # Both sides changed, or comments/rich formatting were
                        # added after the insertion reached the document.
                        conflict = {**current, 'text':old['text'], 'dirty':True}
                        conflict['conflict'] = {'remote_text':current['text'], 'remote_xml':current['xml'], 'editable':current['editable']}
                        result[result.index(current)] = conflict
                    continue
                moved = copy.deepcopy(old)
                moved.update(new=False, conflict={'remote_text':current['text'], 'remote_xml':current['xml'], 'editable':False, 'moved':True})
                result.append(moved)
            elif inserted:
                conflict = copy.deepcopy(old)
                conflict['conflict'] = {'remote_text':'存在多个相同来源标记，请到飞书核对', 'remote_xml':None, 'editable':False, 'moved':True}
                result.append(conflict)
            else: result.append(copy.deepcopy(old))
            continue
        same_scope = current and current['course_id'] == old['course_id'] and current['section'] == old['section']
        if same_scope and current['text'] == old['text']:
            continue  # A previous write succeeded before a transport interruption.
        if not current and old.get('write_prior_ids'):
            matches = [b for b in remote if b['id'] not in old['write_prior_ids'] and b['course_id'] == old['course_id'] and b['section'] == old['section'] and b['text'] == old['text']]
            if len(matches) == 1: continue
        if same_scope and current['xml'] == old.get('xml') and current['editable']:
            current.update(text=old['text'], dirty=True)
        else:
            conflict = copy.deepcopy(old)
            conflict['conflict'] = {'remote_text': current['text'] if current else None,
                                    'remote_xml': current['xml'] if current else None,
                                    'editable': current['editable'] if same_scope else False,
                                    'moved': bool(current and not same_scope)}
            if same_scope: result[result.index(current)] = conflict
            else: result.append(conflict)
    return result


def resolve(store, body):
    with lock(store.root, 'course-info'):
        data = state(store)
        if data['revision'] != body['revision']: raise ValueError('课程信息已变化，请刷新后重试')
        block = next((b for b in data['blocks'] if b['id'] == body['id'] and b['course_id'] == body['course_id']), None)
        if not block or not block.get('conflict'): raise ValueError('冲突已变化，请刷新')
        conflict = block['conflict']
        if body['choice'] == 'remote':
            if conflict['remote_text'] is None or conflict.get('moved'): data['blocks'].remove(block)
            else:
                block.update(text=conflict['remote_text'], base_text=conflict['remote_text'], xml=conflict['remote_xml'], editable=conflict['editable'], dirty=False)
                block.pop('conflict')
        elif body['choice'] == 'local':
            if not conflict['editable']: raise ValueError('远端条目已删除、含批注或富文本，请在飞书合并，避免丢失内容')
            block.update(base_text=conflict['remote_text'], xml=conflict['remote_xml'], dirty=True)
            block.pop('conflict')
        else: raise ValueError('未知冲突处理方式')
        data['revision'] += 1
        atomic_json(store.root / 'course-info.json', data)
    return view(store, body['course_id'])


def paragraph(text):
    return '<p>' + html.escape(text).replace('\n', '<br/>') + '</p>'


def sync(store, course_id=None, push=True, client=None):
    """Pull full document, push only selected course, persist each verified step."""
    client = client or Feishu()
    if course_id and not store.course(course_id): raise ValueError('课程不存在')
    with lock(store.root, 'course-info'):
        data = state(store)
        previous = read_json(store.root / 'course-info.json', {})
        if previous and previous.get('document_url') != data['document_url']:
            # Retain pending edits from a previous document, without applying
            # them to a newly associated document or losing them on first pull.
            atomic_json(store.root / 'course-info-history' / ('document-' + str(previous.get('revision', 0)) + '-' + uuid.uuid4().hex + '.json'), previous)
        url = data['document_url']
        if not url: raise ValueError('请先关联飞书课程文档')
        courses = store.registry()['courses']
        remote_blocks = []
        def pull():
            nonlocal data, remote_blocks
            response = client.fetch(url)
            remote, revision = parse_document(response, courses)
            if store.registry().get('feishu_document') != url:
                raise ValueError('飞书关联已改变，本次同步已停止；原文档编辑仍保留')
            remote_blocks = remote
            data.update(blocks=merge(data['blocks'], remote), remote_revision=revision, last_synced_at=now(), revision=data['revision'] + 1)
            atomic_json(store.root / 'course-info-remote.json', response)
            atomic_json(store.root / 'course-info.json', data)
        pull()
        if push:
            # Persist a write intent before sending, so retries can identify an
            # insertion after an uncertain network outcome without duplicating it.
            for identifier, target_course in [(b['id'], b['course_id']) for b in data['blocks'] if b.get('dirty') and not b.get('conflict') and (not course_id or b['course_id'] == course_id)]:
                block = next(b for b in data['blocks'] if b['id'] == identifier and b['course_id'] == target_course)
                if block.get('new'):
                    # Stable marker stored as visible provenance, not a hidden
                    # credential, enables readback after a failed response.
                    marker = '[CC:' + identifier.removeprefix('local-') + ']'
                    prior = next((b for b in data['blocks'] if not b.get('new') and b['course_id'] == block['course_id'] and marker in b['text']), None)
                    if prior:
                        raise ValueError('新增信息已在飞书出现，请重新同步核对内容；本地更改仍保留')
                    siblings = [b for b in remote_blocks if b['course_id'] == block['course_id']]
                    section_blocks = [b for b in siblings if b['section'] == block['section']]
                    content = paragraph(block['text'] + '\n' + marker)
                    if section_blocks:
                        command, anchor = 'block_insert_after', section_blocks[-1]['id']
                    elif siblings:
                        command, anchor = 'block_insert_after', siblings[-1]['id']
                        content = '<h3>' + html.escape(block['section']) + '</h3>' + content
                    else:
                        command, anchor = ('block_insert_after', remote_blocks[-1]['id']) if remote_blocks else ('append', None)
                        course = store.course(block['course_id'])
                        content = '<h2>' + html.escape(course['name']) + '</h2><h3>' + html.escape(block['section']) + '</h3>' + content
                    block['insert_sent_text'] = block['text']
                    atomic_json(store.root / 'course-info.json', data)
                    if store.registry().get('feishu_document') != url: raise ValueError('飞书关联已改变，请重新打开课程信息')
                    client.write(url, command, anchor, content, data['remote_revision'])
                    pull()
                    found = next((b for b in data['blocks'] if not b.get('new') and b['course_id'] == block['course_id'] and marker in b['text']), None)
                    if not found: raise ValueError('飞书写入结果未能回读核实，本地编辑仍保留，请重试同步')
                    data['blocks'] = [b for b in data['blocks'] if b['id'] != identifier or b['course_id'] != target_course]
                else:
                    expected_text = block['text']; cid = block['course_id']; section = block['section']
                    block['write_prior_ids'] = [b['id'] for b in data['blocks'] if not b.get('new')]
                    atomic_json(store.root / 'course-info.json', data)
                    if store.registry().get('feishu_document') != url: raise ValueError('飞书关联已改变，请重新打开课程信息')
                    client.write(url, 'block_replace', identifier, paragraph(expected_text), data['remote_revision'])
                    pull()
                    found = next((b for b in data['blocks'] if not b.get('conflict') and b['course_id'] == cid and b['section'] == section and b['text'] == expected_text), None)
                    if not found: raise ValueError('飞书写入结果未能回读核实，本地编辑仍保留，请重试同步')
                    # block_replace can assign a new block id.
                    data['blocks'] = [b for b in data['blocks'] if b['id'] != identifier or b['course_id'] != cid or b is found]
                data['revision'] += 1
                atomic_json(store.root / 'course-info.json', data)
        return view(store, course_id) if course_id else data

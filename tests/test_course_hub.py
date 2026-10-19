import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from store import Store
import course_info as info
from notes import list_notes, read_note
from transcripts import evidence


class Cloud:
    def __init__(self):
        self.xml = '<h1 id="all">课程记录</h1><h2 id="os">操作系统</h2><h3 id="exam">考试与考核</h3><p id="entry">第 1～3 章</p><p id="rich"><a href="https://example.org">课程链接</a></p><h2 id="math">数学</h2><h3 id="homework">作业</h3><p id="other">周五提交</p>'
        self.revision = 1; self.writes = []; self.fail_after_write = False
    def fetch(self, url):
        return {'ok': True, 'data': {'document': {'content': self.xml, 'revision_id': self.revision}}}
    def write(self, url, command, block_id, content, revision):
        if revision != self.revision: raise ValueError('revision conflict')
        root = ET.fromstring('<root>' + self.xml + '</root>')
        new = list(ET.fromstring('<root>' + content + '</root>'))
        for e in new: e.set('id', uuid.uuid4().hex)
        if command == 'append': root.extend(new)
        else:
            old = next(e for e in root if e.get('id') == block_id)
            index = list(root).index(old) + (command == 'block_insert_after')
            if command == 'block_replace': root.remove(old)
            for i,e in enumerate(new): root.insert(index+i,e)
        self.xml = ''.join(ET.tostring(e,encoding='unicode') for e in root)
        self.revision += 1; self.writes.append((command,block_id))
        if self.fail_after_write:
            self.fail_after_write = False
            raise ValueError('response lost')


class HubTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.store = Store(self.root / 'state')
        self.store.save_course({'id':'os','name':'操作系统','root':str(self.root / 'os')},0)
        self.store.save_course({'id':'math','name':'数学','root':str(self.root / 'math')},1)
        self.store.set_feishu('https://example.feishu.cn/docx/test')
        self.cloud = Cloud()
    def tearDown(self): self.temp.cleanup()
    def pull(self): return info.sync(self.store,'os',push=False,client=self.cloud)
    def edit(self, text, identifier='entry', cid='os'):
        return info.edit(self.store,{'course_id':cid,'id':identifier,'text':text,'section':'考试与考核','revision':info.state(self.store)['revision']})

    def test_bidirectional_sync_is_scoped_and_preserves_rich_blocks(self):
        self.pull(); self.edit('第 1～4 章'); self.edit('周六提交','other','math')
        value = info.sync(self.store,'os',client=self.cloud)
        self.assertIn('第 1～4 章',self.cloud.xml)
        self.assertIn('周五提交',self.cloud.xml)
        self.assertIn('<a href=',self.cloud.xml)
        self.assertFalse(any(b.get('dirty') for b in value['blocks']))
        self.assertTrue(any(b.get('dirty') for b in info.view(self.store,'math')['blocks']))
        self.cloud.xml=self.cloud.xml.replace('第 1～4 章','第 1～5 章')
        self.assertTrue(any(b['text']=='第 1～5 章' for b in self.pull()['blocks']))

    def test_concurrent_change_conflicts_then_explicit_choice(self):
        self.pull(); self.edit('本地修改')
        self.cloud.xml=self.cloud.xml.replace('第 1～3 章','飞书修改')
        value=info.sync(self.store,'os',client=self.cloud)
        block=next(b for b in value['blocks'] if b['id']=='entry')
        self.assertEqual(block['conflict']['remote_text'],'飞书修改')
        self.assertEqual(self.cloud.writes,[])
        info.resolve(self.store,{'course_id':'os','id':'entry','choice':'local','revision':value['revision']})
        info.sync(self.store,'os',client=self.cloud)
        self.assertIn('本地修改',self.cloud.xml)

    def test_uncertain_insert_and_replace_do_not_duplicate_or_drop_edits(self):
        self.pull(); self.edit('新通知',None)
        self.cloud.fail_after_write=True
        with self.assertRaises(ValueError): info.sync(self.store,'os',client=self.cloud)
        info.sync(self.store,'os',client=self.cloud)
        self.assertEqual(self.cloud.xml.count('新通知'),1)
        self.edit('更新内容')
        self.cloud.fail_after_write=True
        with self.assertRaises(ValueError): info.sync(self.store,'os',client=self.cloud)
        value=info.sync(self.store,'os',client=self.cloud)
        self.assertFalse(any(b.get('dirty') or b.get('conflict') for b in value['blocks']))

    def test_comments_and_remote_deletion_cannot_be_overwritten(self):
        response=self.cloud.fetch('')
        response['data']['document']['reference_map']={'comments':{'x':{'data':'<comment block-id="entry">批注</comment>'}}}
        blocks,_=info.parse_document(response,self.store.registry()['courses'])
        self.assertFalse(next(b for b in blocks if b['id']=='entry')['editable'])
        self.pull(); self.edit('本地编辑')
        self.cloud.xml=self.cloud.xml.replace('<p id="entry">第 1～3 章</p>','')
        value=info.sync(self.store,'os',client=self.cloud)
        with self.assertRaises(ValueError): info.resolve(self.store,{'course_id':'os','id':'entry','choice':'local','revision':value['revision']})
        self.assertFalse(self.cloud.writes)

    def test_edit_after_uncertain_insert_preserves_latest_text(self):
        self.pull(); value=self.edit('原先内容',None)
        identifier=next(b['id'] for b in value['blocks'] if b.get('new'))
        self.cloud.fail_after_write=True
        with self.assertRaises(ValueError): info.sync(self.store,'os',client=self.cloud)
        self.edit('重新修改的内容',identifier)
        value=info.sync(self.store,'os',client=self.cloud)
        self.assertIn('重新修改的内容',self.cloud.xml)
        self.assertNotIn('原先内容',self.cloud.xml)
        self.assertFalse(any(b.get('dirty') or b.get('conflict') for b in value['blocks']))

    def test_remote_move_does_not_move_local_edit_into_another_course(self):
        self.pull(); self.edit('操作系统本地编辑')
        self.cloud.xml=self.cloud.xml.replace('<p id="entry">第 1～3 章</p>','')+'<p id="entry">第 1～3 章</p>'
        value=info.sync(self.store,'math',client=self.cloud)
        self.assertFalse(self.cloud.writes)
        own=info.view(self.store,'os')
        block=next(b for b in own['blocks'] if b['id']=='entry')
        self.assertTrue(block['conflict']['moved'])
        self.assertFalse(block['conflict']['editable'])
        info.resolve(self.store,{'course_id':'os','id':'entry','choice':'remote','revision':own['revision']})
        self.assertFalse(any(b['id']=='entry' for b in info.view(self.store,'os')['blocks']))
        self.assertTrue(any(b['id']=='entry' for b in info.view(self.store,'math')['blocks']))

    def test_uncertain_insert_cannot_overwrite_later_cloud_edit_or_comments(self):
        self.pull(); value=self.edit('最初发送',None)
        identifier=next(b['id'] for b in value['blocks'] if b.get('new'))
        self.cloud.fail_after_write=True
        with self.assertRaises(ValueError): info.sync(self.store,'os',client=self.cloud)
        self.cloud.xml=self.cloud.xml.replace('最初发送','飞书后续修改')
        count=len(self.cloud.writes)
        info.sync(self.store,'os',client=self.cloud)
        self.assertEqual(len(self.cloud.writes),count)
        self.assertIn('飞书后续修改',self.cloud.xml)
        value=self.edit('第二条通知',None)
        identifier=next(b['id'] for b in value['blocks'] if b.get('new'))
        self.cloud.fail_after_write=True
        with self.assertRaises(ValueError): info.sync(self.store,'os',client=self.cloud)
        self.edit('本地后续修改',identifier)
        fetch=self.cloud.fetch
        def fetch_with_comment(url):
            response=fetch(url)
            root=ET.fromstring('<root>'+self.cloud.xml+'</root>')
            target=next(e.get('id') for e in root if '第二条通知' in ''.join(e.itertext()))
            response['data']['document']['reference_map']={'comments':{'x':{'data':'<comment block-id="'+target+'">批注</comment>'}}}
            return response
        self.cloud.fetch=fetch_with_comment
        count=len(self.cloud.writes)
        value=info.sync(self.store,'os',client=self.cloud)
        self.assertEqual(len(self.cloud.writes),count)
        self.assertTrue(any(b.get('conflict') and not b['conflict']['editable'] for b in value['blocks']))

    def test_repeated_sync_keeps_unresolved_insert_conflict(self):
        self.pull(); value=self.edit('首次发送',None)
        identifier=next(b['id'] for b in value['blocks'] if b.get('new'))
        self.cloud.fail_after_write=True
        with self.assertRaises(ValueError): info.sync(self.store,'os',client=self.cloud)
        self.edit('本地又改',identifier)
        self.cloud.xml=self.cloud.xml.replace('首次发送','飞书也改')
        first=info.sync(self.store,'os',client=self.cloud)
        self.assertTrue(any(b.get('conflict') for b in first['blocks']))
        count=len(self.cloud.writes)
        second=info.sync(self.store,'os',client=self.cloud)
        self.assertTrue(any(b.get('conflict') for b in second['blocks']))
        self.assertEqual(len(self.cloud.writes),count)
        self.assertIn('飞书也改',self.cloud.xml)

    def test_document_switch_keeps_old_pending_data_off_new_document(self):
        self.pull(); self.edit('本地编辑')
        self.store.set_feishu('https://example.feishu.cn/docx/another')
        self.assertTrue(info.state(self.store)['association_changed'])
        self.assertFalse(info.state(self.store)['blocks'])

    def test_artifacts_appear_without_teaching_index_and_cannot_escape(self):
        folder=self.root/'os'/'OPPO-AI-Pin'/'课堂笔记'; folder.mkdir(parents=True)
        (folder/'20261019-操作系统-1.2 分类.html').write_text('<title>操作系统 &amp; 分类</title><h1>正文</h1>',encoding='utf-8')
        (self.root/'secret.html').write_text('private',encoding='utf-8')
        notes=list_notes(self.store,'os')['notes']
        self.assertEqual(notes[0]['title'],'操作系统 & 分类')
        self.assertIn(b'<h1>',read_note(self.store,'os',notes[0]['id']))
        with self.assertRaises(ValueError): read_note(self.store,'os','../../secret.html')
        self.assertFalse((self.store.root/'indexes').exists())

    def test_transcript_evidence_extends_past_summary_end(self):
        self.store.ingest({'complete':False,'pages':[{'kind':'memory','payload':{'content':[{'sessionId':'s','results':[{'endTime':1000,'sentences':[{'text':'继续讲课','startTime':1000,'endTime':3000}]}]}]}}]})
        result=evidence(self.store,['memory:s'])
        self.assertEqual(result['summary_ranges'][0]['end'],1000)
        self.assertEqual(result['transcript_ranges'],[[1000,3000]])


if __name__=='__main__': unittest.main()

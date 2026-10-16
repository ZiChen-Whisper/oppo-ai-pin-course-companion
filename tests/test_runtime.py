import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

RUNTIME=Path(__file__).resolve().parents[1]/'runtime'
sys.path.insert(0,str(RUNTIME))
from store import Store


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.store=Store(self.root/'state')
        self.course=self.store.save_course({'id':'os','name':'操作系统','root':str(self.root),'materials':[]},0)

    def tearDown(self): self.temp.cleanup()

    def page(self,kind,content,number=0,last=True,total=1):
        return {'kind':kind,'payload':{'content':content,'number':number,'last':last,'totalPages':total}}

    def batch(self,text='第一版'):
        return {'end_time':1000,'complete':True,'pages':[self.page('memory',[{'sessionId':'s1','startTime':10,'results':[{'summaryMarkdown':text}]}]),self.page('note',[])]}

    def test_stale_revision_cannot_overwrite(self):
        with self.assertRaises(ValueError): self.store.save_course({'id':'os','name':'错误','root':str(self.root)},0)
        self.assertEqual(self.store.course('os')['name'],'操作系统')

    def test_missing_pages_never_advance_cursor(self):
        b=self.batch();b['pages'][0]['payload'].update(last=False,totalPages=2)
        with self.assertRaises(ValueError):self.store.ingest(b)
        self.assertIsNone(self.store.records()['collection_end_ms'])
        b['complete']=False;self.store.ingest(b)
        self.assertEqual(len(self.store.records()['items']),1)
        self.assertIsNone(self.store.records()['collection_end_ms'])

    def test_repeat_dedup_update_and_confirmation(self):
        self.store.ingest(self.batch());self.store.ingest(self.batch())
        self.assertEqual(len(self.store.records()['items']),1)
        self.store.confirm_records(['memory:s1'],'os')
        self.store.ingest(self.batch('补充版'))
        item=self.store.records()['items'][0]
        self.assertTrue(item['confirmed']);self.assertEqual(item['course_id'],'os');self.assertEqual(item['review_state'],'pending')

    def test_export_requires_user_confirmation(self):
        self.store.ingest(self.batch())
        with self.assertRaises(ValueError):self.store.export_records(['memory:s1'],'os')
        self.store.confirm_records(['memory:s1'],'os')
        out=self.store.export_records(['memory:s1'],'os')
        self.assertTrue((Path(out['metadata_dir'])/'memory-s1.json').exists())

    def test_mcp_handshake_and_list(self):
        reqs=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05'}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'},{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'list_courses','arguments':{}}}]
        result=subprocess.run([sys.executable,str(RUNTIME/'mcp_server.py')],input='\n'.join(json.dumps(x) for x in reqs)+'\n',text=True,capture_output=True,encoding='utf-8',env={**os.environ,'OPPO_AI_PIN_DATA':str(self.store.root)})
        self.assertEqual(result.returncode,0,result.stderr)
        lines=[json.loads(l) for l in result.stdout.splitlines()]
        self.assertEqual(len(lines),3)
        self.assertEqual(lines[0]['result']['serverInfo']['name'],'oppo-ai-pin-campus-local')
        self.assertEqual(len(lines[1]['result']['tools']),4)
        self.assertEqual(json.loads(lines[2]['result']['content'][0]['text'])['courses'][0]['name'],'操作系统')

    def test_completion_rejects_new_source_revision(self):
        self.store.ingest(self.batch());self.store.confirm_records(['memory:s1'],'os')
        old_hash=self.store.records()['items'][0]['hash']
        out=self.store.export_records(['memory:s1'],'os')
        html=Path(out['notes_dir'])/'notes.html';html.write_text('<html>test</html>',encoding='utf-8')
        self.store.ingest(self.batch('原文已更新'))
        with self.assertRaises(ValueError): self.store.complete_records([{'id':'memory:s1','hash':old_hash,'artifact':str(html)}])
        new_hash=self.store.records()['items'][0]['hash']
        self.store.complete_records([{'id':'memory:s1','hash':new_hash,'artifact':str(html)}])
        self.assertEqual(self.store.records()['items'][0]['review_state'],'completed')


if __name__=='__main__':unittest.main()

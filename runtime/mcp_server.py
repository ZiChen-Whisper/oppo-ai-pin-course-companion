"""Newline-delimited JSON-RPC stdio MCP; exposes local state and manager entrypoint."""
import json
import subprocess
import sys
from pathlib import Path
from store import Store

for stream in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8')

TOOLS = [
    {'name': 'list_courses', 'description': '读取集中维护的全部课程、路径、手工指定资料、备注、索引时间和飞书文档链接；不扫描或更新索引。', 'inputSchema': {'type':'object','properties':{},'additionalProperties':False}},
    {'name': 'get_course_index', 'description': '读取一门课程的既有资料索引；不更新。所有更新必须交给 gpt-6-luna high 子 Agent。', 'inputSchema': {'type':'object','properties':{'course_id':{'type':'string'}},'required':['course_id'],'additionalProperties':False}},
    {'name': 'open_course_manager', 'description': '启动本地可视化课程管理，返回浏览器可打开的本机链接。首次调用时在界面添加课程，不预设用户课程目录。', 'inputSchema': {'type':'object','properties':{},'additionalProperties':False}},
    {'name': 'list_class_records', 'description': '读取已经收集到本地的课堂候选及状态。每次课堂回顾还必须先用远程全时记和随口记接口补齐新记录，此工具不是远程同步。', 'inputSchema': {'type':'object','properties':{},'additionalProperties':False}}
]


def handle(req):
    method = req.get('method')
    if method == 'initialize':
        return {'protocolVersion': req.get('params',{}).get('protocolVersion','2024-11-05'), 'capabilities': {'tools': {}}, 'serverInfo': {'name':'oppo-ai-pin-campus-local','version':'0.1.0'}}
    if method == 'ping': return {}
    if method == 'tools/list': return {'tools': TOOLS}
    if method == 'resources/list': return {'resources':[]}
    if method == 'prompts/list': return {'prompts':[]}
    if method == 'tools/call':
        try:
            params=req['params']; name=params['name']; args=params.get('arguments',{}); store=Store()
            if name=='list_courses':
                from app import state
                result=state(store)
            elif name=='get_course_index':
                from catalog import catalog
                result=catalog(store,args['course_id'])
            elif name=='list_class_records': result=store.records()
            elif name=='open_course_manager':
                run=subprocess.run([sys.executable,str(Path(__file__).with_name('app.py')),'open'],capture_output=True,text=True,encoding='utf-8',timeout=15)
                if run.returncode: raise RuntimeError(run.stderr)
                result=json.loads(run.stdout)
            else: raise ValueError('未知工具')
            return {'content':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError':True,'content':[{'type':'text','text':str(exc)}]}
    raise ValueError('Method not found')


def main():
    for line in sys.stdin:
        req={}
        try:
            req=json.loads(line)
            if 'id' not in req: continue
            response={'jsonrpc':'2.0','id':req['id'],'result':handle(req)}
        except Exception as exc:
            response={'jsonrpc':'2.0','id':req.get('id'),'error':{'code':-32603,'message':str(exc)}}
        print(json.dumps(response,ensure_ascii=False),flush=True)


if __name__=='__main__': main()

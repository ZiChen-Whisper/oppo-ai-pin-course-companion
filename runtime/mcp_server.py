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
    {'name': 'open_course_manager', 'description': '返回课程统一入口；可直达指定课程的资料、笔记、课程信息或设置。所有课程技能均须给出此入口。', 'inputSchema': {'type':'object','properties':{'course_id':{'type':'string'},'view':{'type':'string','enum':['materials','notes','info','settings']}},'additionalProperties':False}},
    {'name': 'list_course_notes', 'description': '列出一门课程已经生成的 HTML 笔记；只读取产物目录，不更新教材索引。', 'inputSchema': {'type':'object','properties':{'course_id':{'type':'string'}},'required':['course_id'],'additionalProperties':False}},
    {'name': 'get_course_info', 'description': '读取本地飞书镜像与待上传或冲突状态；不代表实时云端内容。', 'inputSchema': {'type':'object','properties':{'course_id':{'type':'string'}},'required':['course_id'],'additionalProperties':False}},
    {'name': 'sync_course_info', 'description': '读取完整飞书课程文档并刷新本地镜像；默认仅拉取。显式 push=true 时提交指定课程的本地待上传编辑，保留冲突、富文本和批注。需安装并授权飞书官方 lark-cli。', 'inputSchema': {'type':'object','properties':{'course_id':{'type':'string'},'push':{'type':'boolean','default':False}},'required':['course_id'],'additionalProperties':False}},
    {'name': 'list_class_records', 'description': '读取已经收集到本地的课堂候选及状态。每次课堂回顾还必须先用远程全时记和随口记接口补齐新记录，此工具不是远程同步。', 'inputSchema': {'type':'object','properties':{},'additionalProperties':False}}
]


def handle(req):
    method = req.get('method')
    if method == 'initialize':
        return {'protocolVersion': req.get('params',{}).get('protocolVersion','2024-11-05'), 'capabilities': {'tools': {}}, 'serverInfo': {'name':'oppo-ai-pin-campus-local','version':'0.4.0'}}
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
            elif name=='list_course_notes':
                from notes import list_notes
                result=list_notes(store,args['course_id'])
            elif name=='get_course_info':
                from course_info import view
                result=view(store,args['course_id'])
            elif name=='sync_course_info':
                from course_info import sync
                result=sync(store,args['course_id'],push=args.get('push',False))
            elif name=='open_course_manager':
                command=[sys.executable,str(Path(__file__).with_name('app.py')),'open']
                if args.get('course_id'): command+=['--course-id',args['course_id']]
                if args.get('view'): command+=['--view',args['view']]
                run=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=15)
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

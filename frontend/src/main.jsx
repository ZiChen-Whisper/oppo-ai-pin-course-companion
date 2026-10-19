import React, {useState,useEffect,useMemo} from 'react';
import {createRoot} from 'react-dom/client';
import {Button,Chip,TextField,Input,Label,TextArea,Select,ListBox,Tabs,Modal,Checkbox,SearchField,TimeField,Spinner} from '@heroui/react';
import {Time} from '@internationalized/date';
import {DataGrid} from '@question-bank/ui-pro/data-grid';
import {ActionBar} from '@question-bank/ui-pro/action-bar';
import {BookOpen,FolderOpen,Plus,Search,RefreshCw,Settings,FileText,Check,ChevronRight,X,ExternalLink,ArrowLeft,CalendarDays,GraduationCap,SlidersHorizontal} from 'lucide-react';
import './style.css';

const API_TOKEN=location.hash.slice(1);
async function api(path,body){
  const response=await fetch('/api/'+path,{headers:{'X-Campus-Token':API_TOKEN,...(body?{'Content-Type':'application/json'}:{})},method:body?'POST':'GET',body:body?JSON.stringify(body):undefined});
  const value=await response.json(); if(!response.ok)throw Error(value.error||'请求失败');return value;
}
const TYPES={'textbook':'教材','reference':'参考阅读','slides':'课件','assignment-brief':'作业要求','assignment':'作业成果','lab-guide':'实验指导','lab-report':'实验报告','revision':'复习资料','notes':'课堂笔记','code-data':'代码 / 数据','other':'其他资料','unclassified':'待分类'};
const SOURCES={rule:'规则建议',model:'模型建议',manual:'人工指定'};
const nameOf=f=>f.name||f.path.split(/[\\/]/).pop();
const shortPath=p=>p.split(/[\\/]/).slice(-2).join(' / ');
const date=v=>v?new Date(v).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}):'尚未建立';

function Field({label,value,onChange,placeholder,area=false,...props}){return <TextField value={value||''} onChange={onChange} {...props}><Label>{label}</Label>{area?<TextArea placeholder={placeholder}/>:<Input placeholder={placeholder}/>}</TextField>}
function Choice({label,value,onChange,options,compact=false,displayLabel}){return <Select aria-label={label} value={value||null} onChange={v=>onChange(String(v||''))} className={compact?'compact-select':''}>
  {!compact&&<Label>{label}</Label>}<Select.Trigger><Select.Value>{displayLabel||options.find(o=>o[0]===value)?.[1]||label}</Select.Value><Select.Indicator/></Select.Trigger>
  <Select.Popover><ListBox>{options.map(([id,title])=><ListBox.Item key={id} id={id} textValue={title}>{title}<ListBox.ItemIndicator/></ListBox.Item>)}</ListBox></Select.Popover>
</Select>}
function Find({label,value,onChange,placeholder}){return <SearchField aria-label={label} value={value} onChange={onChange}><SearchField.Group><SearchField.SearchIcon/><SearchField.Input placeholder={placeholder}/><SearchField.ClearButton/></SearchField.Group></SearchField>}
function Dialog({open,onClose,title,children,footer,wide=false}){return <Modal isOpen={open} onOpenChange={v=>!v&&onClose()}><Modal.Backdrop><Modal.Container><Modal.Dialog className={wide?'course-dialog wide':'course-dialog'}><Modal.CloseTrigger aria-label="关闭"/><Modal.Header><Modal.Heading>{title}</Modal.Heading></Modal.Header><Modal.Body>{children}</Modal.Body>{footer&&<Modal.Footer>{footer}</Modal.Footer>}</Modal.Dialog></Modal.Container></Modal.Backdrop></Modal>}
function ErrorMessage({children}){return children?<p className="error-message" role="alert">{children}</p>:null}
function TimeControl({label,value,onChange}){let time;try{const [h,m]=value.split(':').map(Number);time=new Time(h,m)}catch{time=new Time(8,0)}return <TimeField aria-label={label} value={time} hourCycle={24} onChange={v=>v&&onChange(v.toString().slice(0,5))}><Label>{label}</Label><TimeField.Group><TimeField.Input>{segment=><TimeField.Segment segment={segment}/>}</TimeField.Input></TimeField.Group></TimeField>}
function parseSchedule(raw){const m=raw.match(/(周[一二三四五六日天])\s*(\d{2}:\d{2})[–—-](\d{2}:\d{2})/);return m?{day:m[1].replace('天','日'),start:m[2],end:m[3],original:raw,extra:raw.slice(m.index+m[0].length)}:{original:raw,legacy:true}}

function CourseSettings({course,revision,onSaved,onCancel,create=false,onDirty}){
  const [draft,setDraft]=useState(()=>({...course,aliases:[...(course.aliases||[])],extra_roots:[...(course.extra_roots||[])]}));
  const [times,setTimes]=useState(()=>(course.schedule||[]).map(parseSchedule));
  const [customSemester,setCustomSemester]=useState(Boolean(course.semester&&!/^大[一二三四][上下]学期$/.test(course.semester)));
  const [alias,setAlias]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[picking,setPicking]=useState(false),[changed,setChanged]=useState(false),[broad,setBroad]=useState(false),[approvedBroad,setApprovedBroad]=useState(false);
  useEffect(()=>{onDirty?.(changed)},[changed]);
  useEffect(()=>()=>onDirty?.(false),[]);
  function update(key,value){setDraft(d=>({...d,[key]:value}));setChanged(true);setBroad(false);setApprovedBroad(false)}
  async function choose(extra=false){setPicking(true);setError('');try{const {path}=await api('pick-directory',{});if(path)update(extra?'extra_roots':'root',extra?[...draft.extra_roots,path]:path)}catch(e){setError(e.message)}finally{setPicking(false)}}
  function addAlias(){if(alias.trim()){update('aliases',[...new Set([...draft.aliases,alias.trim()])]);setAlias('')}}
  async function save(e){e.preventDefault();setError('');setBusy(true);try{
    const folder=await api('validate-directory',{path:draft.root});
    if(folder.broad&&!approvedBroad){setBroad(true);setBusy(false);return}
    for(const t of times)if(!t.legacy&&t.start>=t.end)throw Error('下课时间应晚于上课时间');
    for(const path of draft.extra_roots)await api('validate-directory',{path});
    await api('course',{revision,course:{...draft,root:folder.path,schedule:times.map(t=>t.legacy?t.original:`${t.day} ${t.start}-${t.end}${t.extra||''}`)}});
    await onSaved();setChanged(false);
  }catch(e){setError(e.message)}finally{setBusy(false)}}
  useEffect(()=>{const before=e=>{if(changed){e.preventDefault();e.returnValue=''}};window.addEventListener('beforeunload',before);return()=>window.removeEventListener('beforeunload',before)},[changed]);
  return <form className="settings-form" onSubmit={save}>
    <div className="settings-title"><div><h2>{create?'添加课程':'课程设置'}</h2><p>课程信息与资料位置统一保存在本机。</p></div>{changed&&<Chip size="sm" variant="soft">未保存</Chip>}</div>
    <section><h3>基本信息</h3><div className="field-grid"><Field label="课程名称" value={draft.name} onChange={v=>update('name',v)} isRequired/><Field label="任课教师（选填）" value={draft.teacher} onChange={v=>update('teacher',v)}/>
    <Choice label="学期" value={customSemester?'__custom':draft.semester||''} onChange={v=>{setCustomSemester(v==='__custom');update('semester',v==='__custom'?'':v)}} options={['大一上学期','大一下学期','大二上学期','大二下学期','大三上学期','大三下学期','大四上学期','大四下学期'].map(v=>[v,v]).concat([['__custom','自定义学期…']])}/>{customSemester&&<Field label="学期名称" value={draft.semester} onChange={v=>update('semester',v)} placeholder="如 2026 秋季"/>}</div>
    <div className="alias-editor"><Label>课程别名（选填）</Label><div className="inline-input"><Input aria-label="新别名" value={alias} onChange={e=>setAlias(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();addAlias()}}} placeholder="输入一个别名"/><Button type="button" variant="secondary" onPress={addAlias}>添加</Button></div><div className="tags">{draft.aliases.map(a=><Chip key={a} size="sm"><Chip.Label>{a}</Chip.Label><Button aria-label={'移除别名 '+a} isIconOnly size="sm" variant="ghost" onPress={()=>update('aliases',draft.aliases.filter(v=>v!==a))}><X size={12}/></Button></Chip>)}</div></div></section>
    <section><h3>资料位置</h3><div className="path-row"><Field label="课程主目录" value={draft.root} onChange={v=>update('root',v)} isRequired placeholder="选择目录，或粘贴完整路径"/><Button type="button" variant="secondary" onPress={()=>choose()} isPending={picking}><FolderOpen size={16}/>选择目录</Button></div>
    <p className="field-help">选择这门课程的资料文件夹；课堂笔记也会保存到该目录下。</p>
    {draft.extra_roots.map((path,i)=><div className="extra-path" key={i}><span title={path}>{path}</span><Button type="button" size="sm" variant="ghost" onPress={()=>update('extra_roots',draft.extra_roots.filter((_,j)=>i!==j))}>移除</Button></div>)}
    <Button type="button" variant="ghost" size="sm" onPress={()=>choose(true)} isDisabled={picking}><Plus size={14}/>关联额外目录</Button>
    {broad&&<div className="warning"><p>该目录包含较多子文件夹，请确认它没有混入其他课程。</p><Checkbox isSelected={approvedBroad} onChange={setApprovedBroad}><Checkbox.Content><Checkbox.Control><Checkbox.Indicator/></Checkbox.Control><Label>确认使用这个目录</Label></Checkbox.Content></Checkbox></div>}</section>
    <section><div className="section-heading"><h3>上课时间</h3><Button type="button" variant="ghost" size="sm" onPress={()=>{setTimes([...times,{day:'周一',start:'08:00',end:'09:40'}]);setChanged(true)}}><Plus size={14}/>添加时段</Button></div>
    {times.length===0&&<p className="field-help">尚未设置，可用于辅助匹配课堂记录。</p>}
    {times.map((t,i)=><div className="schedule-row" key={i}>{t.legacy?<Field label="原有上课时间" value={t.original} onChange={v=>{setTimes(times.map((s,j)=>j===i?{...s,original:v}:s));setChanged(true)}}/>:<><Choice label="星期" value={t.day} options={['一','二','三','四','五','六','日'].map(d=>['周'+d,'周'+d])} onChange={v=>{setTimes(times.map((s,j)=>j===i?{...s,day:v}:s));setChanged(true)}}/>{['start','end'].map(k=><TimeControl key={k} label={k==='start'?'上课':'下课'} value={t[k]} onChange={v=>{setTimes(times.map((s,j)=>j===i?{...s,[k]:v}:s));setChanged(true)}}/>)}</>}<Button type="button" size="sm" variant="ghost" aria-label={'移除第 '+(i+1)+' 个时段'} onPress={()=>{setTimes(times.filter((_,j)=>i!==j));setChanged(true)}} isIconOnly><X size={16}/></Button></div>)}</section>
    <section><Field label="课程备注（选填）" area value={draft.notes} onChange={v=>update('notes',v)} placeholder="课程习惯、资料使用说明等"/></section>
    <div className="save-bar"><div><ErrorMessage>{error}</ErrorMessage>{!error&&<span className="muted">{changed?'更改尚未保存':'课程资料与索引独立维护'}</span>}</div><div className="actions">{onCancel&&<Button type="button" variant="secondary" onPress={onCancel}>取消</Button>}<Button type="submit" isPending={busy} isDisabled={picking||(!create&&!changed)}>{busy?'保存中':'保存课程'}</Button></div></div>
  </form>
}

function App(){
  const [narrow,setNarrow]=useState(()=>matchMedia('(max-width:620px)').matches);
  useEffect(()=>{const media=matchMedia('(max-width:620px)'),change=()=>setNarrow(media.matches);media.addEventListener('change',change);return()=>media.removeEventListener('change',change)},[]);
  const [state,setState]=useState(null),[cid,setCid]=useState(''),[courseQuery,setCourseQuery]=useState(''),[tab,setTab]=useState('materials');
  const [catalog,setCatalog]=useState(null),[loading,setLoading]=useState(true),[loadError,setLoadError]=useState(''),[notice,setNotice]=useState('');
  const [query,setQuery]=useState(''),[kind,setKind]=useState('all'),[status,setStatus]=useState('all'),[format,setFormat]=useState('all'),[showHidden,setShowHidden]=useState(false),[selected,setSelected]=useState(new Set());
  const [detail,setDetail]=useState(null),[add,setAdd]=useState(false),[batch,setBatch]=useState(false),[batchType,setBatchType]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [cloud,setCloud]=useState(false),[cloudUrl,setCloudUrl]=useState('');
  const [dirty,setDirty]=useState(false),[pendingNav,setPendingNav]=useState(null);
  function navigate(action){if(dirty)setPendingNav(()=>action);else action()}
  const course=state?.courses.find(c=>c.id===cid), job=state?.jobs.find(j=>j.course_id===cid);
  async function reload(){const value=await api('state');setState(value);setCid(old=>value.courses.some(c=>c.id===old)?old:value.courses[0]?.id||'');return value}
  useEffect(()=>{reload().catch(e=>setLoadError(e.message)).finally(()=>setLoading(false))},[]);
  useEffect(()=>{if(!cid)return;let alive=true;setCatalog(null);setLoadError('');api('index/'+cid).then(v=>alive&&setCatalog(v)).catch(e=>alive&&setLoadError(e.message));setSelected(new Set());setDetail(null);setQuery('');setKind('all');setStatus('all');setFormat('all');return()=>{alive=false}},[cid,course?.last_indexed_at]);
  useEffect(()=>{if(!state?.jobs.some(j=>['running','awaiting_agent'].includes(j.status)))return;let stopped=false;const timer=setInterval(()=>{if(!stopped)reload().catch(()=>{})},3000);return()=>{stopped=true;clearInterval(timer)}},[state?.jobs.some(j=>['running','awaiting_agent'].includes(j.status))]);
  useEffect(()=>{setSelected(new Set());setDetail(null)},[query,kind,status,format,showHidden]);
  const files=catalog?.files||[];
  const visible=useMemo(()=>files.filter(f=>(showHidden||!f.hidden)&&(kind==='all'||f.type===kind)&&(status==='all'||(status==='confirmed'?f.confirmed:!f.confirmed))&&(format==='all'||f.format===format)&&[nameOf(f),f.path,f.title,f.notes].some(v=>String(v||'').toLowerCase().includes(query.toLowerCase()))),[files,query,kind,status,format,showHidden]);
  const keys=selected==='all'?visible.map(f=>f.path):[...selected].filter(k=>visible.some(f=>f.path===k));
  async function refreshCatalog(){const id=cid;const [s,c]=await Promise.all([api('state'),api('index/'+id)]);setState(s);setCatalog(c);return c}
  async function updateMaterials(paths,extra={}){setBusy(true);setError('');try{const next=await api('materials',{course_id:cid,revision:state.revision,paths,...extra});const c=await refreshCatalog();if(detail)setDetail(c.files.find(f=>f.path===detail.path));setBatch(false);setSelected(new Set());setNotice(`${paths.length} 项资料已保存`);return next}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function reindex(){setBusy(true);setError('');try{await api('reindex',{course_id:cid});await reload()}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function saved(){setDirty(false);await reload();setAdd(false);setTab('materials');setNotice('课程已保存');if(cid)await refreshCatalog()}
  const columns=[
    {id:'name',header:'资料名称',isRowHeader:true,minWidth:narrow?210:250,width:'1fr',cell:f=><div className="file-cell"><span className={'file-mark '+f.format?.toLowerCase()}><FileText size={18}/></span><div><strong>{nameOf(f)}</strong><small title={f.path}>{shortPath(f.path)}</small><span className="mobile-file-meta">{TYPES[f.type]} · {f.format}<br/>{SOURCES[f.source]} · <span className={f.confirmed?'confirmed':'pending'}>{f.confirmed?'已确认':'待确认'}</span></span></div>{f.primary&&<Chip size="sm" variant="soft">主要教材</Chip>}</div>},
    {id:'type',header:'资料用途',width:120,cell:f=><span>{TYPES[f.type]||f.type}</span>},
    {id:'format',header:'格式',width:85,accessorKey:'format'},
    {id:'source',header:'分类来源',width:115,cell:f=><span className="source-label">{SOURCES[f.source]||'来源未说明'}</span>},
    {id:'status',header:'确认状态',width:100,cell:f=><span className={f.confirmed?'confirmed':'pending'}>{f.confirmed?<Check size={13}/>:<span className="status-dot"/>}{f.confirmed?'已确认':'待确认'}</span>},
    {id:'action',header:'',width:58,cell:f=><Button isIconOnly size="sm" variant="ghost" aria-label={'查看 '+nameOf(f)} onPress={()=>{setDetail(f);setError('')}}><ChevronRight size={16}/></Button>}
  ];
  return <div className="app-shell"><aside className="sidebar"><div className="brand"><img src="/icon.png" alt=""/><div><strong>Course Companion</strong><span>OPPO AI Pin</span></div></div>
    <Find label="查找课程" placeholder="查找课程" value={courseQuery} onChange={setCourseQuery}/><div className="sidebar-label">我的课程 <span>{state?.courses.length||0}</span></div>
    <nav aria-label="课程列表">{state?.courses.filter(c=>[c.name,c.teacher,c.semester].some(v=>v?.includes(courseQuery))).map(c=><Button key={c.id} variant="ghost" className={'course-nav '+(c.id===cid?'active':'')} onPress={()=>{if(c.id!==cid)navigate(()=>{setCid(c.id);setTab('materials')})}}><BookOpen size={17}/><span><strong>{c.name}</strong><small>{c.semester||'未设置学期'}</small></span></Button>)}{state&&courseQuery&&!state.courses.some(c=>[c.name,c.teacher,c.semester].some(v=>v?.includes(courseQuery)))&&<p className="muted">没有匹配的课程</p>}</nav>
    <div className="mobile-course-switch"><img className="mobile-ring" src="/icon.png" alt=""/><Choice compact label="切换课程" displayLabel="切换课程" value={cid} onChange={v=>navigate(()=>{setCid(v);setTab('materials')})} options={(state?.courses||[]).map(c=>[c.id,c.name])}/><Button variant="ghost" isIconOnly aria-label="飞书文档设置" onPress={()=>{setCloudUrl(state?.feishu_document||'');setError('');setCloud(true)}}><ExternalLink size={16}/></Button></div>
    <Button variant="secondary" className="add-course" onPress={()=>navigate(()=>setAdd(true))}><Plus size={16}/>添加课程</Button>
    <footer><Button variant="ghost" className="cloud-link" onPress={()=>{setCloudUrl(state?.feishu_document||'');setError('');setCloud(true)}}><ExternalLink size={16}/>飞书课程信息<span className={state?.feishu_document?'connected-dot':'status-dot'}/></Button><details><summary>本地数据位置</summary><p>{state?.data_root}</p></details></footer></aside>
    <main className="workspace">{loading?<div className="center-state"><Spinner/><p>正在读取课程…</p></div>:!course?<div className="center-state"><GraduationCap size={40}/><h1>从一门课程开始</h1><p>关联教材、课件和实验资料，供课堂笔记统一使用。</p><Button onPress={()=>navigate(()=>setAdd(true))}><Plus size={16}/>添加第一门课程</Button><ErrorMessage>{loadError}</ErrorMessage></div>:<>
    <header className="course-header"><div><div className="breadcrumb">我的课程 <ChevronRight size={12}/>{course.semester}</div><h1>{course.name}</h1><div className="course-meta"><span>{course.teacher||'未设置教师'}</span>{course.schedule?.length>0&&<><span className="meta-divider"/><CalendarDays size={14}/><span>{course.schedule.join(' · ')}</span></>}</div></div></header>
    <Tabs variant="secondary" align="start" selectedKey={tab} onSelectionChange={v=>{if(String(v)!==tab)navigate(()=>setTab(String(v)))}} className="workspace-tabs"><Tabs.ListContainer><Tabs.List aria-label="课程视图"><Tabs.Tab id="materials">课程资料 <span className="tab-count">{files.filter(f=>!f.hidden).length}</span><Tabs.Indicator/></Tabs.Tab><Tabs.Tab id="settings">课程设置<Tabs.Indicator/></Tabs.Tab></Tabs.List></Tabs.ListContainer>
    <Tabs.Panel id="materials"><div className="material-heading"><div><h2>资料库</h2><p>最近索引 {date(course.last_indexed_at)}{files.some(f=>f.hidden)&&<span className="hidden-count"> · 默认隐藏 {files.filter(f=>f.hidden).length} 项过程文件</span>}</p></div><Button size="sm" variant="secondary" onPress={reindex} isDisabled={busy||['awaiting_agent','running'].includes(job?.status)}><RefreshCw size={15}/>更新索引</Button></div>
    {job&&['awaiting_agent','running','failed'].includes(job.status)&&<div className={job.status==='failed'?'error-message':'job-message'} role="status">{job.status==='awaiting_agent'?'索引请求已保存。回到聊天调用课程管理，由指定子 Agent 更新。':job.status==='running'?'子 Agent 正在更新索引…':job.error||'更新失败，请重试'}</div>}
    <div className="filter-bar"><Find label="搜索资料" placeholder="搜索文件名、路径或备注" value={query} onChange={setQuery}/><Choice compact label="资料用途" value={kind} onChange={setKind} options={[["all","全部用途"],...Object.entries(TYPES)]}/><Choice compact label="确认状态" value={status} onChange={setStatus} options={[["all","全部状态"],["pending","待确认"],["confirmed","已确认"]]}/><Choice compact label="文件格式" value={format} onChange={setFormat} options={[["all","全部格式"],...[...new Set(files.map(f=>f.format))].sort().map(f=>[f,f])]}/></div>
    <div className="list-summary"><span>{visible.length} 项资料{keys.length>0&&` · 已选 ${keys.length} 项`}</span><Checkbox isSelected={showHidden} onChange={setShowHidden}><Checkbox.Content><Checkbox.Control><Checkbox.Indicator/></Checkbox.Control><Label>显示过程文件</Label></Checkbox.Content></Checkbox></div>
    <ErrorMessage>{loadError||(!detail&&!batch?error:'')}</ErrorMessage>{catalog?<DataGrid data={visible} columns={narrow?columns.filter(c=>['name','action'].includes(c.id)):columns} scrollContainerClassName="material-scroll" getRowId={f=>f.path} aria-label="课程资料" selectionMode="multiple" showSelectionCheckboxes selectedKeys={selected} onSelectionChange={setSelected} onRowAction={key=>{setDetail(files.find(f=>f.path===key));setError('')}} renderEmptyState={()=><div className="empty-files"><Search size={24}/><h3>{files.length?'没有匹配的资料':'尚未建立资料索引'}</h3><p>{files.length?'试试调整用途、状态或搜索条件。':'点击更新索引，然后回到聊天执行索引任务。'}</p>{files.length>0&&<Button variant="secondary" onPress={()=>{setQuery('');setKind('all');setStatus('all');setFormat('all');setShowHidden(true)}}>清除筛选</Button>}</div>}/>:!loadError?<div className="center-state"><Spinner/><p>正在读取资料…</p></div>:<Button variant="secondary" onPress={()=>refreshCatalog().catch(e=>setLoadError(e.message))}>重新读取</Button>}
    <div className="library-footnote"><span>自动分类仅作建议，点击资料查看依据并确认。</span><span>索引更新：gpt-6-luna / high</span></div>
    <ActionBar isOpen={keys.length>0} aria-label="批量资料操作"><ActionBar.Prefix>已选 {keys.length} 项</ActionBar.Prefix><ActionBar.Content><Button size="sm" variant="secondary" onPress={()=>{setBatchType('');setError('');setBatch(true)}}>更改用途</Button><Button size="sm" onPress={()=>updateMaterials(keys)} isPending={busy}>确认分类</Button></ActionBar.Content><ActionBar.Suffix><Button size="sm" variant="ghost" aria-label="取消选择" isIconOnly onPress={()=>setSelected(new Set())}><X size={16}/></Button></ActionBar.Suffix></ActionBar>
    </Tabs.Panel><Tabs.Panel id="settings"><CourseSettings key={cid} course={course} revision={state.revision} onSaved={saved} onDirty={setDirty}/></Tabs.Panel></Tabs></>}
    {notice&&<div className="save-notice" role="status"><Check size={16}/>{notice}<Button variant="ghost" isIconOnly size="sm" aria-label="关闭提示" onPress={()=>setNotice('')}><X size={14}/></Button></div>}</main>
    <Dialog open={!!detail} onClose={()=>setDetail(null)} title="资料详情" footer={<Button variant="secondary" onPress={()=>setDetail(null)}>关闭</Button>}>{detail&&<MaterialDetail key={detail.path+detail.type+detail.primary} file={detail} busy={busy} error={error} onSave={extra=>updateMaterials([detail.path],extra)}/>}</Dialog>
    <Dialog open={batch} onClose={()=>setBatch(false)} title={`更改 ${keys.length} 项资料用途`} footer={<><Button variant="secondary" onPress={()=>setBatch(false)}>取消</Button><Button isDisabled={!batchType} isPending={busy} onPress={()=>updateMaterials(keys,{type:batchType})}>保存并确认</Button></>}><Choice label="资料用途" value={batchType} onChange={setBatchType} options={Object.entries(TYPES)}/><p className="field-help">只修改当前筛选结果中选中的 {keys.length} 项，不移动或改写原文件。</p><ErrorMessage>{error}</ErrorMessage></Dialog>
    <Dialog wide open={add} onClose={()=>navigate(()=>setAdd(false))} title="添加课程"><CourseSettings create key={String(add)} course={{name:'',root:'',semester:'',teacher:'',notes:'',materials:[],aliases:[],extra_roots:[],schedule:[]}} revision={state?.revision||0} onSaved={saved} onCancel={()=>navigate(()=>setAdd(false))} onDirty={setDirty}/></Dialog>
    <Dialog open={!!pendingNav} onClose={()=>setPendingNav(null)} title="有尚未保存的更改" footer={<><Button variant="secondary" onPress={()=>setPendingNav(null)}>继续编辑</Button><Button onPress={()=>{const action=pendingNav;setPendingNav(null);setDirty(false);action()}}>放弃更改并离开</Button></>}><p>当前输入还没有保存。你可以继续编辑，或放弃这次更改。</p></Dialog>
    <Dialog open={cloud} onClose={()=>setCloud(false)} title="飞书课程信息" footer={<><Button variant="secondary" onPress={()=>setCloud(false)}>取消</Button><Button isPending={busy} onPress={async()=>{setBusy(true);setError('');try{await api('feishu',{url:cloudUrl.trim()});await reload();setCloud(false);setNotice('飞书文档已关联')}catch(e){setError(e.message)}finally{setBusy(false)}}}>保存关联</Button></>}><Field label="飞书文档链接" value={cloudUrl} onChange={setCloudUrl} placeholder="https://…/docx/…"/>{state?.feishu_document&&<a className="document-link" href={state.feishu_document} target="_blank" rel="noreferrer">打开已关联文档 <ExternalLink size={14}/></a>}<p className="field-help">尚未创建文档时，可在聊天中调用课程信息管理创建并关联。</p><ErrorMessage>{error}</ErrorMessage></Dialog>
  </div>
}
function MaterialDetail({file,busy,error,onSave}){const [type,setType]=useState(file.type),[notes,setNotes]=useState(file.notes||'');return <div className="material-detail"><div className="detail-file"><FileText size={26}/><h3>{nameOf(file)}</h3></div><p className="full-path">{file.path}</p><div className="detail-facts"><span>文件格式 <b>{file.format}</b></span><span>分类来源 <b>{SOURCES[file.source]||'来源未说明'}</b></span></div><div className="classification-reason"><Label>判断依据</Label><p>{file.reason}</p><span>{file.confirmed?'你已确认这项分类。':'这是一项自动建议，尚未由你确认。'}</span></div><Choice label="资料用途" value={type} onChange={setType} options={Object.entries(TYPES)}/><Field area label="资料备注（选填）" value={notes} onChange={setNotes}/><div className="detail-actions"><Button variant="secondary" onPress={()=>onSave({type,notes})} isPending={busy}>保存用途与备注</Button><Button variant="ghost" onPress={()=>onSave({primary:true,notes})} isPending={busy}><BookOpen size={15}/>{file.primary?'已设为主要教材':'设为主要教材'}</Button></div>{file.headings?.length>0&&<details><summary>{file.headings.length} 个章节标题</summary><ul>{file.headings.map((h,i)=><li key={i}>{typeof h==='string'?h:h.text}</li>)}</ul></details>}<ErrorMessage>{error}</ErrorMessage></div>}

createRoot(document.getElementById('root')).render(<App/>);

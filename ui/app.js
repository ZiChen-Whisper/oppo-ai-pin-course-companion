const $ = (s) => document.querySelector(s);
let token = location.hash.slice(1), snapshot, selected, editing, editRevision;
const types = {'textbook-markdown':'教材 Markdown','textbook':'教材','slides':'课件','lab':'实验资料','other':'其他资料'};
const text = (el, value) => { el.textContent = value || '未填写'; };
async function api(path, body) {
  const response = await fetch('/api/' + path, {method: body ? 'POST' : 'GET', headers: {'Content-Type':'application/json','X-Campus-Token':token}, body: body ? JSON.stringify(body) : undefined});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || '操作失败');
  return value;
}
function notice(message, error=false) { const el=$('#notice'); text(el,message); el.hidden=false; el.style.color=error?'var(--error)':''; }
function courseList() {
  const query=$('#search').value.trim().toLowerCase();
  $('#courses').replaceChildren();
  for (const c of snapshot.courses.filter(c=>[c.name,c.semester,c.teacher,...c.aliases].join(' ').toLowerCase().includes(query))) {
    const b=document.createElement('button'); b.className=c.id===selected?'active':''; b.setAttribute('aria-current',c.id===selected?'true':'false');
    const name=document.createElement('strong'), sub=document.createElement('span'); text(name,c.name); text(sub,[c.semester,c.teacher].filter(Boolean).join(' · ')||'课程资料'); b.append(name,sub);
    b.onclick=()=>{ selected=c.id; courseList(); showCourse().catch(e=>notice(e.message,true)); }; $('#courses').append(b);
  }
  if(query && !$('#courses').children.length){ const p=document.createElement('p');p.className='muted';text(p,'没有匹配的课程');$('#courses').append(p); }
}
async function reload() {
  snapshot=await api('state'); text($('#location'),snapshot.data_root);
  if(!snapshot.courses.some(c=>c.id===selected)) selected=snapshot.courses[0]?.id;
  courseList(); await showCourse();
}
async function showCourse() {
  const cid=selected, c=snapshot.courses.find(c=>c.id===cid);
  $('#empty').hidden=!!c; $('#detail').hidden=!c; if(!c)return;
  text($('#name'),c.name); text($('#term'),c.semester||'未设置学期');text($('#teacher'),c.teacher?'任课教师：'+c.teacher:'未设置任课教师');text($('#root'),c.root);text($('#schedule'),c.schedule.join('\n'));text($('#notes'),c.notes);
  text($('#extra'), ['别名：'+(c.aliases.join('、')||'无'), '额外目录：'+(c.extra_roots.join('；')||'无')].join('\n'));
  text($('#index-time'),c.last_indexed_at?'最近成功更新：'+new Date(c.last_indexed_at).toLocaleString():'尚未建立索引');
  const job=snapshot.jobs.find(j=>j.course_id===cid), active=job&&['awaiting_agent','running'].includes(job.status);
  $('#reindex').disabled=!!active; $('#job').hidden=!job;
  if(job) text($('#job'),job.status==='failed'?job.error:job.status==='completed'?'资料索引更新完成':job.status==='awaiting_agent'?'索引请求已保存。回到聊天调用“本地课程管理”，将由 gpt-6-luna / high 子 Agent 执行。':'正在由 gpt-6-luna / high 子 Agent 更新索引…');
  const index=await api('index/'+encodeURIComponent(cid)); if(selected!==cid)return;
  $('#warnings').hidden=!index.warnings?.length; text($('#warnings'),(index.warnings||[]).join('\n'));
  const files=new Map((index.files||[]).map(f=>[f.path,f]));
  for(const m of c.materials) files.set(m.path,{...files.get(m.path),...m});
  $('#materials').replaceChildren();$('#no-files').hidden=!!files.size;
  for(const file of files.values()) {
    const row=document.createElement('tr'), a=document.createElement('td'), b=document.createElement('td'), d=document.createElement('td');
    const title=document.createElement('strong'), path=document.createElement('small');text(title,file.title||file.name||file.path.split(/[\\/]/).pop());text(path,file.path);a.append(title,path);text(b,types[file.type]||file.type||'其他资料');
    const headings=(file.headings||[]).map(h=>typeof h==='string'?h:h.text||h.title||'').filter(Boolean);
    if(headings.length){const details=document.createElement('details'),summary=document.createElement('summary'),p=document.createElement('p');text(summary,headings.length+' 个章节');text(p,headings.join('\n'));details.append(summary,p);d.append(details);}
    if(file.notes){const p=document.createElement('p');text(p,file.notes);d.append(p);}
    if(!d.children.length)text(d,'—');row.append(a,b,d);$('#materials').append(row);
  }
}
function materialEditor(m={}) {
  const box=document.createElement('div'); box.className='material-editor';
  const row=document.createElement('div');row.className='material-row';
  const label=document.createElement('label');text(label,'资料路径');const path=document.createElement('input');path.className='material-path';path.value=m.path||'';label.append(path);
  const kind=document.createElement('label');text(kind,'资料类型');const select=document.createElement('select');select.className='material-type';
  for(const [value,title] of Object.entries(types)){const option=document.createElement('option');option.value=value;text(option,title);select.append(option);}select.value=m.type||'other';kind.append(select);row.append(label,kind);
  const notesLabel=document.createElement('label');text(notesLabel,'资料备注');const notes=document.createElement('input');notes.className='material-notes';notes.value=m.notes||'';notesLabel.append(notes);
  const remove=document.createElement('button');remove.type='button';text(remove,'移除这项指定资料');remove.onclick=()=>box.remove();box.append(row,notesLabel,remove);box._original=m;$('#material-editors').append(box);
}
function edit(c) {
  editing=c?.id; editRevision=snapshot.revision; const f=$('#course-form');f.reset();$('#form-error').hidden=true;$('#material-editors').replaceChildren();text($('#editor-title'),c?'编辑课程':'添加课程');
  for(const k of ['name','root','semester','teacher','notes']) f.elements[k].value=c?.[k]||'';
  for(const k of ['aliases','extra_roots','schedule']) f.elements[k].value=(c?.[k]||[]).join(k==='aliases'?'，':'\n');
  for(const m of c?.materials||[]) materialEditor(m);$('#editor').showModal();
}
$('#add').onclick=$('#first').onclick=()=>edit();$('#edit').onclick=()=>edit(snapshot.courses.find(c=>c.id===selected));$('#search').oninput=courseList;
$('#close').onclick=$('#cancel').onclick=()=>$('#editor').close();$('#add-material').onclick=()=>materialEditor();
$('#course-form').onsubmit=async(e)=>{
  e.preventDefault();const f=e.target,c={id:editing};
  for(const k of ['name','root','semester','teacher','notes'])c[k]=f.elements[k].value.trim();
  c.aliases=f.elements.aliases.value.split(/[,，\n]/).map(s=>s.trim()).filter(Boolean);
  for(const k of ['extra_roots','schedule'])c[k]=f.elements[k].value.split('\n').map(s=>s.trim()).filter(Boolean);
  c.materials=[...document.querySelectorAll('.material-editor')].map(b=>({...b._original,path:b.querySelector('.material-path').value.trim(),type:b.querySelector('.material-type').value,notes:b.querySelector('.material-notes').value.trim()})).filter(m=>m.path);
  $('#save').disabled=true;
  try{const saved=await api('course',{course:c,revision:editRevision});selected=saved.id;$('#editor').close();await reload();notice('课程已保存');}
  catch(err){text($('#form-error'),err.message);$('#form-error').hidden=false;}finally{$('#save').disabled=false;}
};
$('#reindex').onclick=async()=>{try{await api('reindex',{course_id:selected});await reload();}catch(e){notice(e.message,true);}};
$('#settings').onclick=()=>{$('#feishu-url').value=snapshot.feishu_document||'';$('#settings-error').hidden=true;$('#settings-dialog').showModal();};
$('#settings-close').onclick=()=>$('#settings-dialog').close();
$('#settings-form').onsubmit=async(e)=>{e.preventDefault();try{await api('feishu',{url:$('#feishu-url').value});$('#settings-dialog').close();await reload();notice('飞书文档链接已保存');}catch(err){text($('#settings-error'),err.message);$('#settings-error').hidden=false;}};
reload().catch(e=>notice(e.message,true));
setInterval(async()=>{if(snapshot?.jobs.some(j=>['awaiting_agent','running'].includes(j.status)))try{await reload();}catch(e){notice(e.message,true);}},3000);

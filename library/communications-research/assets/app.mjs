const $=id=>document.getElementById(id), number=n=>n.toLocaleString('zh-CN');
const fields=['search','scope','tier','track','group','ownership','city','degree','skill','kind','quality','status'];
let jobs=[],analysis={},terms={},page=1,filtered=[],cache=new Map(),techPage=1;
const categoryNames={agent_framework:'Agent框架',ai_concept_method:'AI方法',ai_evaluation:'AI评测',ai_ml_framework:'AI与机器学习框架',ai_model_platform:'模型与平台',backend_framework:'后端框架',business_analytics:'业务分析',cloud_platform:'云平台',data_engineering:'数据工程',database_search:'数据库与检索',design_dcc:'设计工具',developer_tool:'开发工具',embedded_platform:'嵌入式平台',frontend_framework:'前端框架',game_development:'游戏开发',gpu_hardware:'GPU与加速硬件',hardware_design_tool:'硬件设计工具',hardware_interface_radio:'硬件接口与无线',infrastructure_tool:'基础设施工具',markup_style_language:'标记与样式语言',mobile_framework:'移动端框架',network_protocol:'网络协议',observability_tool:'可观测性',programming_language:'编程语言',security_identity:'安全与身份',testing_development_tool:'测试工具'};
const el=(tag,cls,text)=>{const x=document.createElement(tag);if(cls)x.className=cls;if(text!==undefined)x.textContent=text;return x;};
const count=(rows,key)=>{const c=new Map();for(const r of rows){for(const v of new Set([r[key]].flat().filter(Boolean)))c.set(v,(c.get(v)||0)+1);}return [...c].sort((a,b)=>b[1]-a[1]||String(a[0]).localeCompare(String(b[0]),'zh-CN'));};
function notify(s){$('toast').textContent=s;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,2500);}
async function fetchJSON(path){const r=await fetch(path);if(!r.ok)throw new Error(`${r.status} ${path}`);return r.json();}
async function catalog(){if('DecompressionStream' in window){try{const r=await fetch('data/catalog.json.gz');if(!r.ok)throw new Error(r.status);return JSON.parse(await new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).text());}catch(e){console.warn('gzip加载回退',e.message);}}return fetchJSON('data/catalog.json');}
function fill(id,values,label){const s=$(id);s.replaceChildren(el('option','',label));s.firstChild.value='';for(const [v,n] of values){const o=el('option','',`${id==='skill'?(terms[v]?.label||v):v} · ${number(n)}`);o.value=v;s.append(o);}}
function state(){return Object.fromEntries(fields.map(k=>[k,$(k).value]));}
function matches(j,s){
 const text=[j.id,j.title,j.company,j.hiring_unit_name,j.parent_group,j.major_quote,j.degree_raw,...j.technology_ids.map(t=>terms[t]?.label||t)].join(' ').toLowerCase();
 const tierMatch=!s.tier||s.tier==='all'||(s.tier==='direct'?['A','B'].includes(j.tier):s.tier==='related'?j.tier==='D':j.tier===s.tier);
 return (!s.search||s.search.toLowerCase().split(/\s+/).every(w=>text.includes(w)))
  &&(s.scope!=='students'||j.student_confirmed)&&(s.scope!=='experience'||j.experience_signal)&&tierMatch
  &&(!s.track||j.career_track===s.track)&&(!s.group||j.parent_group===s.group)
  &&(!s.ownership||j.ownership_group===s.ownership)&&(!s.city||j.city_tags.includes(s.city))
  &&(!s.degree||j.degree_words.includes(s.degree))&&(!s.skill||(j.skill_eligible&&j.technology_ids.includes(s.skill)))
  &&(!s.kind||j.kind===s.kind)&&(!s.quality||j.detailed_jd)&&(!s.status||j.current_status===s.status);
}
function syncURL(){const q=new URLSearchParams();for(const [k,v]of Object.entries(state()))if(v)q.set(k,v);history.replaceState(null,'',`${location.pathname}?${q}`);}
function stat(label,value,note){const x=el('div','stat');x.append(el('span','',label),el('strong','',number(value)),el('small','',note));return x;}
function bars(id,values,action,denom){const box=$(id);box.replaceChildren();if(!values.length){box.append(el('p','muted','当前条件没有可统计记录。'));return;}const max=values[0][1];for(const [v,n] of values.slice(0,12)){const b=el('button','bar');b.type='button';b.title=`筛选：${terms[v]?.label||v}`;const label=el('span','',terms[v]?.label||v),track=el('span','bar-track'),fill=el('span','bar-fill');fill.style.width=`${100*n/max}%`;track.append(fill);const value=el('b','',number(n));if(denom)value.append(el('small','',`${(100*n/denom).toFixed(1)}%`));b.append(label,track,value);b.onclick=()=>{$(action).value=v;page=1;render();$('filters').scrollIntoView({block:'start'});};box.append(b);}}
function render(){const s=state();filtered=jobs.filter(j=>matches(j,s));page=Math.max(1,Math.min(page,Math.ceil(filtered.length/12)||1));syncURL();
 $('stats').replaceChildren(stat('当前筛选记录',filtered.length,'记录数，不等于实际招聘名额'),stat('学生入口有证据',filtered.filter(j=>j.student_confirmed).length,'仍需核对届别、学历与截止时间'),stat('母集团 / 公司',new Set(filtered.map(j=>j.parent_group)).size,`${new Set(filtered.map(j=>j.hiring_unit_key)).size} 个招聘单位名称`),stat('独立资格段JD',filtered.filter(j=>j.skill_eligible).length,'技术统计使用这一分母'));
 $('scopeNote').textContent=`专题共 ${number(jobs.length)} 条去重记录；来源采集日期：${count(jobs,'source_snapshot').map(([date,n])=>date+'（'+number(n)+'条）').join('、')}。当前是一次跨渠道基线，不能据此判断需求涨跌。`;
 $('filterSummary').textContent=`当前结果 ${number(filtered.length)} 条 · 专业、学生入口与来源完整度分别筛选`;
 bars('careerChart',count(filtered,'career_track'),'track');bars('companyChart',count(filtered,'parent_group'),'group');bars('cityChart',count(filtered,'city_tags'),'city');const eligible=filtered.filter(j=>j.skill_eligible);bars('skillChart',count(eligible,'technology_ids'),'skill',eligible.length);$('skillDenominator').textContent=`分母：${number(eligible.length)} 条具备独立资格段的完整JD；单条对同技术只计一次，表行/批次公告不进入分母。`;
 $('resultCount').textContent=`岗位候选 · ${number(filtered.length)}`;$('results').replaceChildren();for(const j of filtered.slice((page-1)*12,page*12))$('results').append(card(j));if(!filtered.length)$('results').append(el('div','empty','当前条件没有记录。可以清除城市、技术或切换为全部职业参考。'));
 $('pageInfo').textContent=`${page} / ${Math.ceil(filtered.length/12)||1}`;$('prev').disabled=page===1;$('next').disabled=page*12>=filtered.length;renderTech();
}
function renderTech(){const eligible=filtered.filter(j=>j.skill_eligible),co=new Map(count(eligible,'technology_ids')),q=$('techSearch').value.trim().toLowerCase(),cat=$('techCategory').value;let values=Object.entries(terms).filter(([id,t])=>(!q||t.label.toLowerCase().includes(q)||id.toLowerCase().includes(q))&&(!cat||t.category===cat)&&($('techZero').checked||(co.get(id)||0)>0)).sort(([a,x],[b,y])=>(co.get(b)||0)-(co.get(a)||0)||x.label.localeCompare(y.label));techPage=Math.max(1,Math.min(techPage,Math.ceil(values.length/40)||1));$('techTable').replaceChildren();for(const [id,t] of values.slice((techPage-1)*40,techPage*40)){const row=el('tr'),cell=el('td'),b=el('button','',t.label),n=co.get(id)||0;b.onclick=()=>{$('skill').value=id;page=1;render();$('resultCount').scrollIntoView();};cell.append(b);row.append(cell,el('td','',categoryNames[t.category]||t.category),el('td','',number(n)),el('td','',eligible.length?`${(100*n/eligible.length).toFixed(1)}%`:'—'));$('techTable').append(row);}$('techCount').textContent=`匹配 ${values.length} 项技术 · 分母 ${number(eligible.length)} 条完整资格JD`;$('techPage').textContent=`${techPage} / ${Math.ceil(values.length/40)||1}`;$('techPrev').disabled=techPage===1;$('techNext').disabled=techPage*40>=values.length;}
const tierLabel={A:'A · 明确通信工程',B:'B · 通信专业组/相关学科',C:'C · 本科电子信息大类',D:'相邻/批次条件待核'};
function card(j){const x=el('article','job'),top=el('div','job-top');top.append(el('span','',j.parent_group),el('span','',j.source_snapshot));const h=el('h3'),b=el('button','',j.title);b.onclick=()=>detail(j);h.append(b);const tags=el('div','tags');for(const [t,good]of [[tierLabel[j.tier],true],[j.student_confirmed?'学生入口已确认':'学生入口待核',j.student_confirmed],[j.kind_label,false],[j.current_status_label,false]])tags.append(el('span',`tag${good?' confirmed':''}`,t));const q=el('blockquote','major-quote');q.append(el('small','',`专业原文 · ${j.major_scope_label}`),document.createTextNode(j.major_quote||'原文专业证据待核'));const bottom=el('div','job-bottom'),open=el('button','','查看完整JD与证据');open.onclick=()=>detail(j);bottom.append(el('span','',`${j.degree_raw||'学历未结构化'} · ${j.city_tags.join(' / ')||'地点待核'}`),open);x.append(top,h,el('div','job-meta',j.company),tags,q,bottom);return x;}
function section(box,title,text){box.append(el('h3','',title),el('div','detail-copy',text||'本来源未单独提供；请查看完整已存文本。'));}
async function detail(j){
 const box=$('detailBody');box.replaceChildren(el('p','','正在加载已存JD…'));
 $('detailTitle').textContent=j.title;$('detail').showModal();
 try{
  if(!cache.has(j.detail_shard))cache.set(j.detail_shard,await fetchJSON(j.detail_shard));
  const d=cache.get(j.detail_shard)[j.id];if(!d)throw Error('分片缺少对应职位');
  box.replaceChildren();const meta=el('div','detail-meta');
  const values={'公司':j.company,'招聘单位':d.hiring_unit_name,'母集团':j.parent_group,'所有制分组':j.ownership_group,'城市':j.city_tags.join(' / '),'专业层级':tierLabel[j.tier],'专业证据范围':j.major_scope_label,'学历原字段':j.degree_raw||'未提供','学生入口':d.student_status,'经验信号':d.experience_note||'未检出明确年限，不能视为零经验','批次':d.batch||'见原文','来源采集日':j.source_snapshot,'当前状态':j.current_status_label};
  for(const [k,v] of Object.entries(values))meta.append(el('div','',`${k}：${v}`));
  box.append(meta);const a=el('a','','打开原始招聘来源');
  a.href=j.url;a.target='_blank';a.rel='noopener noreferrer';box.append(a);
  section(box,'专业条件原文与判断',`${j.major_quote}\n\n${d.major_note||''}`);
  section(box,'岗位职责',d.description);section(box,'任职要求',d.requirements);section(box,'完整已存文本',d.full_text);
  section(box,'资格段技术提及',j.technology_ids.map(t=>terms[t]?.label||t).join('、'));
  section(box,'需求详细度规则',`${d.clarity_score}/6 项满足，仅用于筛选写得具体的JD：\n${JSON.stringify(d.clarity_signals,null,2)}`);
  section(box,'采集溯源',JSON.stringify(d.provenance,null,2));
  const dl=el('button','','下载本条原文与证据JSON');
  dl.onclick=()=>download(JSON.stringify(d,null,2),`${j.id}.json`,'application/json');box.append(dl);
 }catch(e){box.replaceChildren(el('p','',`详情加载失败：${e.message}`));}
}
function download(text,name,type){const u=URL.createObjectURL(new Blob([text],{type})),a=el('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
function csvCell(v){let s=String(v??'');if(/^[=+@\-\t\r]|^\d{15,}$/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}
function exportCSV(){const keys=['id','title','company','hiring_unit_name','hiring_unit_key','parent_group','ownership_group','tier','major_quote','major_scope','major_scope_label','student_confirmed','student_status','experience_signal','experience_note','degree_raw','city_tags','career_track','kind_label','current_status_label','detailed_jd','clarity_score','source_snapshot','url'];const rows=[keys,...filtered.map(j=>keys.map(k=>Array.isArray(j[k])?j[k].join(' / '):j[k]))];download('\ufeff'+rows.map(r=>r.map(csvCell).join(',')).join('\r\n'),'通信工程_当前筛选.csv','text/csv;charset=utf-8');}
function theme(){const d=document.documentElement.dataset.theme==='dark';$('theme').textContent=d?'切换浅色':'切换深色';}
async function init(){try{const [data,a]=await Promise.all([catalog(),fetchJSON('data/analysis.json')]);
jobs=data.jobs;analysis=a;terms=data.terms;document.querySelector('.stamp b').textContent=a.compiled_at.replaceAll('-','.');
fill('track',count(jobs,'career_track'),'全部方向');
fill('techCategory',Object.entries(categoryNames).filter(([id])=>Object.values(terms).some(t=>t.category===id)).map(([id])=>[id,Object.values(terms).filter(t=>t.category===id).length]),'全部技术类别');
for(const o of $('techCategory').options)if(o.value)o.textContent=categoryNames[o.value];
$('techSearch').oninput=$('techCategory').onchange=$('techZero').onchange=()=>{techPage=1;renderTech();};
$('techPrev').onclick=()=>{techPage--;renderTech();};$('techNext').onclick=()=>{techPage++;renderTech();};
fill('group',count(jobs,'parent_group'),'全部母集团/公司');fill('ownership',count(jobs,'ownership_group'),'全部所有制分组');fill('city',count(jobs,'city_tags'),'全部城市');
const allTechCounts=new Map(count(jobs.filter(j=>j.skill_eligible),'technology_ids'));fill('skill',Object.keys(terms).map(id=>[id,allTechCounts.get(id)||0]).sort((a,b)=>b[1]-a[1]||terms[a[0]].label.localeCompare(terms[b[0]].label)),'全部技术');
const q=new URLSearchParams(location.search);for(const k of fields)if(q.has(k)){const v=q.get(k);if(k==='search'||[...$(k).options].some(o=>o.value===v))$(k).value=v;}
 for(const item of analysis.insights){const x=el('article','insight');x.append(el('h3','',item.title),el('p','evidence',item.finding),el('p','',item.implication));$('insights').append(x);}for(const s of analysis.sources){const x=el('div','source-item'),a=el('a','',s.name);a.href=s.url;a.target='_blank';a.rel='noopener noreferrer';x.append(a,el('small','',s.note));$('sources').append(x);}
 for(const k of fields)$(k).oninput=()=>{page=1;render();};
 $('filters').onsubmit=e=>e.preventDefault();$('reset').onclick=()=>{for(const k of fields)$(k).value=k==='scope'?'students':k==='tier'?'direct':'';page=1;render();};$('prev').onclick=()=>{page--;render();$('resultCount').scrollIntoView();};$('next').onclick=()=>{page++;render();$('resultCount').scrollIntoView();};$('csv').onclick=exportCSV;$('share').onclick=async()=>{try{await navigator.clipboard.writeText(location.href);notify('已复制当前筛选链接');}catch{notify('请复制浏览器地址栏中的筛选链接');}};$('loading').hidden=true;render();window.__telecom={jobs,analysis,terms,state,filtered:()=>filtered,matches};}catch(e){$('loading').hidden=true;$('error').hidden=false;$('error').textContent=`数据加载失败：${e.message}。请通过HTTP服务打开，文件双击模式不支持数据请求。`;}}
$('closeDetail').onclick=()=>$('detail').close();$('detail').onclick=e=>{if(e.target===$('detail'))$('detail').close();};document.documentElement.dataset.theme=localStorage.getItem('telecom-theme')||'light';theme();$('theme').onclick=()=>{document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark';localStorage.setItem('telecom-theme',document.documentElement.dataset.theme);theme();};init();

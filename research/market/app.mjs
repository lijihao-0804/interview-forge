const el = id => document.getElementById(id)
const scopes = ['AI应用与智能体开发','Agent算法与应用研究','通信工程与通信专业组','电子信息工程与电子信息专业组']
const intersection = 'AI岗位 × 电子信息或通信专业'
const names = ['AI 应用开发','Agent 算法与应用研究','通信工程','电子信息']
const accents = ['var(--app)','var(--alg)','var(--com)','var(--ele)']
const controls = ['q','scope','major','region','city','company','size','source','career','owner','tech','field','student','detail','active']
const checks = ['student','detail','active']
const fmt = n=>n.toLocaleString('zh-CN')
const norm = s=>String(s??'').trim().toLocaleLowerCase()
const unique = a=>[...new Set(a.filter(Boolean))].sort((x,y)=>x.localeCompare(y,'zh-CN'))
const closed = s=>/已下线|已结束|已关闭|已截止|截止日已过|已过期|deadline_passed/i.test(s)
const count = vals=>{
  const m=new Map()
  vals.forEach(v=>m.set(v,(m.get(v)||0)+1))
  return [...m].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0],'zh-CN'))
}
function node(tag,content,cls){
  const e=document.createElement(tag)
  if(content!==undefined)e.textContent=content
  if(cls)e.className=cls
  return e
}
function option(value,label=value){const e=node('option',label);e.value=value;return e}
function select(id,arr,labels={}){el(id).replaceChildren(option('','全部'),...arr.map(x=>option(x,labels[x]||x)))}
function dataList(id,arr){el(id).replaceChildren(...arr.map(x=>option(x)))}
function displayTheme(theme){document.documentElement.dataset.theme=theme}
try{displayTheme(localStorage.getItem('research-ui-theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'))}catch{}
el('theme').onclick=()=>{const v=document.documentElement.dataset.theme==='dark'?'light':'dark';displayTheme(v);try{localStorage.setItem('research-ui-theme',v)}catch{}}
let catalog=[],terms=[],sources={},results=[],page=1,currentDetail=0
let termById=new Map(),typedTerms=new Map(),cache=new Map()
async function get(url){const response=await fetch(url);if(!response.ok)throw Error('读取失败 '+response.status);return response.json()}
function initialize(){
  select('scope',[...scopes,intersection,...unique(catalog.flatMap(j=>j.scopes).filter(s=>!scopes.includes(s)))])
  select('major',unique(catalog.flatMap(j=>j.major_tags)))
  select('region',unique(catalog.map(j=>j.region)))
  select('source',Object.keys(sources),sources)
  for(const [id,key] of [['size','size_band'],['career','career'],['owner','ownership']])select(id,unique(catalog.map(j=>j[key])))
  dataList('cityList',unique(catalog.flatMap(j=>j.cities)))
  dataList('companyList',unique(catalog.map(j=>j.company)))
  dataList('techList',unique(terms.map(t=>t.name)))
  termById=new Map(terms.map(t=>[t.id,t.name]))
  for(const t of terms)for(const alias of [t.name,...t.aliases])typedTerms.set(norm(alias),t.id)
  scopes.forEach((s,i)=>{
    const cohort=catalog.filter(j=>j.scopes.includes(s))
    const card=node('button',undefined,'card')
    card.style.setProperty('--accent',accents[i]);card.dataset.scope=s
    card.append(node('b',names[i]),node('strong',fmt(cohort.length)),node('span',fmt(new Set(cohort.map(j=>j.company)).size)+' 个雇主名称'))
    card.onclick=()=>{el('scope').value=el('scope').value===s?'':s;update()}
    el('cards').append(card)
  })
  const p=new URLSearchParams(location.search)
  for(const id of controls){
    if(checks.includes(id))el(id).checked=p.get(id)==='1'
    else if(p.has(id))el(id).value=p.get(id)
    el(id).addEventListener(el(id).tagName==='INPUT'&&!checks.includes(id)?'input':'change',()=>update())
  }
  el('reset').onclick=()=>{for(const id of controls){if(checks.includes(id))el(id).checked=false;else el(id).value=id==='field'?'tech':''}update()}
  el('prev').onclick=()=>{page--;showPage()};el('next').onclick=()=>{page++;showPage()}
  el('export').onclick=exportRows
  el('close').onclick=()=>el('viewer').close()
  update()
}
function update(){
  const f=Object.fromEntries(controls.map(id=>[id,checks.includes(id)?el(id).checked:el(id).value]))
  const words=norm(f.q).split(/\s+/).filter(Boolean),tech=typedTerms.get(norm(f.tech))
  results=catalog.filter(j=>{
    if(f.scope===intersection){if(!j.scopes.some(s=>scopes.slice(0,2).includes(s))||!j.scopes.some(s=>scopes.slice(2).includes(s)))return false}
    else if(f.scope&&!j.scopes.includes(f.scope))return false
    if(f.major&&!j.major_tags.includes(f.major))return false
    if(f.region&&f.region!==j.region||f.source&&f.source!==j.source||f.size&&f.size!==j.size_band||
       f.career&&f.career!==j.career||f.owner&&f.owner!==j.ownership)return false
    if(f.city&&!j.cities.some(c=>norm(c)===norm(f.city))&&norm(j.city)!==norm(f.city))return false
    if(f.company&&![j.company,j.brand,j.hiring_unit].some(c=>norm(c).includes(norm(f.company))))return false
    if(f.tech&&!(j[f.field]||[]).includes(tech))return false
    if(f.student&&!j.student||f.detail&&!j.detailed||f.active&&closed(j.status))return false
    const text=norm([j.title,j.company,j.brand,j.hiring_unit,j.city,j.id].join(' '))
    return words.every(w=>text.includes(w))
  })
  const u=new URL(location.href);u.search=''
  for(const id of controls)if(f[id]&&!(id==='field'&&f[id]==='tech'))u.searchParams.set(id,checks.includes(id)?'1':f[id])
  history.replaceState(null,'',u)
  document.querySelectorAll('.card').forEach(c=>c.setAttribute('aria-pressed',String(c.dataset.scope===f.scope)))
  const eligible=results.filter(j=>j.eligible)
  el('summary').textContent=fmt(results.length)+' 条记录 · '+fmt(new Set(results.map(j=>j.company)).size)+' 个雇主名称 · '+fmt(eligible.length)+' 份可分析资格段'
  bars('companybars',count(results.map(j=>j.company)),(x)=>{el('company').value=x;update()},false)
  bars('skillbars',count(eligible.flatMap(j=>j.tech.map(t=>termById.get(t)))),(x)=>{el('tech').value=x;el('field').value='tech';update()},eligible.length)
  page=1;el('export').disabled=!results.length;showPage()
}
function bars(id,data,action,denom){
  const host=el(id);host.replaceChildren()
  data.slice(0,5).forEach(([name,n])=>{
    const b=node('button',undefined,'bar');b.title=name+' · '+n+' 条';b.setAttribute('aria-label','筛选 '+name)
    const bar=node('i');bar.style.width=(100*n/data[0][1])+'%'
    b.append(node('span',name),bar,node('b',denom?(100*n/denom).toFixed(1)+'%':fmt(n)))
    b.onclick=()=>action(name);host.append(b)
  })
  if(!data.length)host.append(node('small','当前筛选下没有可统计的记录'))
}
function showPage(){
  const total=Math.ceil(results.length/12)
  el('page').textContent=total?page+' / '+total+' 页':'0 条结果'
  el('prev').disabled=page<=1;el('next').disabled=page>=total
  const h=el('jobs');h.replaceChildren()
  for(const j of results.slice((page-1)*12,page*12)){
    const b=node('button',undefined,'job')
    b.append(node('strong',j.title),node('span',[j.company,j.city||'地点未披露',j.size,j.student?'学生入口':'',j.status].filter(Boolean).join(' · ')))
    b.onclick=()=>openJob(j);h.append(b)
  }
  if(!total)h.append(node('p','没有匹配岗位。可清空雇主、地点或技术名称，再逐项筛选。'))
}
async function openJob(j){
  const token=++currentDetail
  const box=el('body');box.replaceChildren(node('p','正在读取归档正文…'))
  el('jobCompany').textContent=j.company+' · '+sources[j.source]
  el('viewer').showModal()
  try{
    if(!cache.has(j.part))cache.set(j.part,await get('data/'+j.part))
    if(token!==currentDetail)return
    const d=cache.get(j.part)[j.id],title=node('h2',d.title);title.id='jobTitle';box.replaceChildren(title)
    box.append(node('p',[d.city,d.degree,d.size,d.status].filter(Boolean).join(' · ')))
    const url=new URL(d.url)
    if(['http:','https:'].includes(url.protocol)){const link=node('a','查看招聘来源');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';box.append(link)}
    box.append(node('p','采集 '+d.observed+' · '+d.source_id))
    const section=(heading,txt,cls)=>{if(txt){box.append(node('h3',heading),node('p',txt,cls))}}
    const proof=Object.entries(d.major_evidence).map(([m,e])=>m+'\n'+e.quote).join('\n\n')
    section('专业依据',proof,'evidence')
    section('招聘渠道',d.campaign)
    section('地区与远程条件',[d.remote,...(d.remote_evidence||[])].filter(Boolean).join('\n'))
    section('工作职责',d.description);section('任职资格',d.requirements)
    section('资格段技术',d.tech.map(x=>termById.get(x)).join('、'))
    const details=node('details');details.append(node('summary','展开归档全文'),node('pre',d.full_text||'此来源仅存岗位简表'));box.append(details)
  }catch(error){if(token===currentDetail)box.replaceChildren(node('p','未能读取这份 JD。请刷新重试。'))}
}
function exportRows(){
  const safe=x=>{let s=String(x??'');if(/^[\s]*[=+@\-]|^\d{15,}$/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"'}
  const columns=['岗位编号','雇主','招聘单位','名称','方向','专业','地点','学生入口','规模原值','性质','来源','状态','观察时间','技术（资格段）','详细JD']
  const lines=[columns,...results.map(j=>[j.id,j.company,j.hiring_unit,j.title,j.scopes.join('|'),j.major_tags.join('|'),j.city,j.student?'有':'未确认',j.size,j.ownership,sources[j.source],j.status,j.observed,j.tech.map(x=>termById.get(x)).join('|'),j.detailed?'是':'否'])]
  const blob=new Blob(['\uFEFF',lines.map(r=>r.map(safe).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'})
  const a=node('a');a.href=URL.createObjectURL(blob);a.download='就业研究_筛选结果.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)
}
Promise.all([get('data/catalog.json'),get('data/terms.json'),get('data/release.json')]).then(([rows,t,r])=>{
  catalog=rows;terms=t;sources=r.sources;initialize()
}).catch(()=>{el('summary').textContent='无法读取岗位索引。请通过站点或本地 HTTP 服务打开本页。'})

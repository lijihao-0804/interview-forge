// Pure query/aggregation functions shared by the Worker and integration tests.
export const DIRECTIONS=['AI应用/Agent开发','Agent算法或交叉研究','AI Infra','后训练'];
const cityOrder=['北京','上海','深圳','杭州','广州','成都','南京','武汉','西安','苏州','重庆','合肥','长沙','天津','东莞','厦门'],cityRank=name=>cityOrder.includes(name)?cityOrder.indexOf(name):cityOrder.length;
export const DEFAULT_FILTERS={q:'',exclude:'',companies:[],companyGroup:'',families:[],directions:[],cities:[],skills:[],skillMode:'all',technologies:[],technologyMode:'any',technologyField:'requirement',degrees:[],degreeMode:'any',geography:'',hasBody:'',hasRequirements:'',clarityMin:0,reviewed:false,clearOnly:false,experienceKnown:'',posttrainingSignal:'',dedup:false,excludePools:false,sort:'company',favoritesOnly:false,postedFrom:''};
const count=(map,key,n=1)=>map.set(key,(map.get(key)||0)+n);
const rows=map=>[...map].map(([name,n])=>({name,n})).sort((a,b)=>b.n-a.n||a.name.localeCompare(b.name,'zh-CN'));
export function dateValue(value){
 const s=String(value||'');let m=s.match(/(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})/);
 if(m)return Date.UTC(+m[1],+m[2]-1,+m[3]);
 if(/^\d{13}$/.test(s))return +s;
 const n=Date.parse(s);return Number.isFinite(n)?n:0;
}
export function prepareJobs(data){return data.map(x=>({...x,_q:[x.title,x.company,x.id,x.source_job_id,x.job_code_raw,x.city,x.summary,...(x.skills_in_requirement||[]),...(x.tech_requirement_names||[]),...(x.tech_duty_names||[]),...(x.tech_fulltext_names||[])].join(' ').toLocaleLowerCase(),_date:dateValue(x.posted_date),_experienceKnown:!!x.experience&&!/未知|未明示|未提供|未结构化/.test(x.experience)}));}
function selected(values,actual,mode='any'){return !values.length||(mode==='all'?values.every(v=>actual.includes(v)):values.some(v=>actual.includes(v)));}
export function filterJobs(jobs,f={},favoriteIds=[]){
 const z={...DEFAULT_FILTERS,...f};const words=z.q.trim().toLowerCase().split(/\s+/).filter(Boolean),omit=z.exclude.trim().toLowerCase().split(/\s+/).filter(Boolean),favorites=new Set(favoriteIds),minDate=dateValue(z.postedFrom),seen=new Set();
 let filtered=jobs.filter(x=>{
  if(words.some(w=>!x._q.includes(w))||omit.some(w=>x._q.includes(w)))return false;
  if(z.companies.length&&!z.companies.includes(x.company)||z.companyGroup&&x.company_group!==z.companyGroup)return false;
  if(z.families.length&&!z.families.includes(x.job_family)||z.directions.length&&!z.directions.includes(x.title_direction))return false;
  if(!selected(z.cities,x.city_tags||[])||!selected(z.skills,x.skills_in_requirement,z.skillMode)||!selected(z.degrees,x.education_mentions,z.degreeMode))return false;
  if(z.geography==='mainland'&&!/含中国大陆|含大陆及港/.test(x.geography))return false;
  if(z.geography&&z.geography!=='mainland'&&x.geography!==z.geography)return false;
  if(z.hasBody==='yes'&&!x.body_chars||z.hasBody==='no'&&x.body_chars)return false;
  if(z.hasRequirements==='yes'&&!x.requirements_available||z.hasRequirements==='no'&&x.requirements_available)return false;
  if(x.clarity_score<+z.clarityMin||z.reviewed&&!x.reviewed_clarity||z.clearOnly&&!x.clarity_candidate&&!x.reviewed_clarity)return false;
  if(z.technologies.length){const field=['requirement','duty','fulltext'].includes(z.technologyField)?z.technologyField:'requirement';if(!selected(z.technologies,x['tech_'+field]||[],z.technologyMode))return false;}
  if(z.experienceKnown==='yes'&&!x._experienceKnown||z.experienceKnown==='no'&&x._experienceKnown)return false;
  if(z.favoritesOnly&&!favorites.has(x.id)||minDate&&(!x._date||x._date<minDate))return false;
  if(z.excludePools&&x.record_kind!=='具体职位广告')return false;
  if(z.posttrainingSignal==='duty'&&!x.posttraining_duty_signal||z.posttrainingSignal==='requirement'&&!x.posttraining_requirement_signal||z.posttrainingSignal==='either'&&!(x.posttraining_duty_signal||x.posttraining_requirement_signal)||z.posttrainingSignal==='candidate'&&!x.posttraining_candidate)return false;
  return true;
 });
 if(z.dedup)filtered=filtered.sort((a,b)=>a.id.localeCompare(b.id)).filter(x=>{if(!x.text_sha256)return true;const key=x.company+'|'+x.text_sha256;if(seen.has(key))return false;seen.add(key);return true;});
 filtered.sort((a,b)=>z.sort==='date'?b._date-a._date||a.id.localeCompare(b.id):z.sort==='clarity'?Number(b.reviewed_clarity)-Number(a.reviewed_clarity)||b.clarity_score-a.clarity_score||a.id.localeCompare(b.id):z.sort==='length'?b.body_chars-a.body_chars||a.id.localeCompare(b.id):a.company.localeCompare(b.company,'zh-CN')||a.title.localeCompare(b.title,'zh-CN')||a.id.localeCompare(b.id));
 return filtered;
}
export function makeFacets(jobs,technologyTerms=[]){
 const legacy=[...new Set(jobs.flatMap(x=>x.skills_in_requirement||[]))].sort((a,b)=>a.localeCompare(b,'zh-CN')).map(name=>({id:name,name,category:'旧版资格技能',aliases:[]}));
 const technologies=(technologyTerms||[]).map(x=>({id:String(x.id??x.name),name:String(x.name??x.id),category:String(x.category||x.group||'未分类'),aliases:Array.isArray(x.aliases)?x.aliases:[]})).sort((a,b)=>a.category.localeCompare(b.category,'zh-CN')||a.name.localeCompare(b.name,'zh-CN'));
 return {companies:[...new Set(jobs.map(x=>x.company))].sort((a,b)=>a.localeCompare(b,'zh-CN')),families:[...new Set(jobs.map(x=>x.job_family))].sort((a,b)=>a.localeCompare(b,'zh-CN')),directions:[...DIRECTIONS,...[...new Set(jobs.map(x=>x.title_direction))].filter(x=>!DIRECTIONS.includes(x)).sort((a,b)=>a.localeCompare(b,'zh-CN'))],cities:[...new Set(jobs.flatMap(x=>x.city_tags||[]))].sort((a,b)=>cityRank(a)-cityRank(b)||a.localeCompare(b,'zh-CN')),skills:[...new Set(jobs.flatMap(x=>x.skills_in_requirement||[]))].sort((a,b)=>a.localeCompare(b,'zh-CN')),technologies:technologies.length?technologies:legacy};
}
const redundant=new Set(['SQL|MySQL/PostgreSQL','MySQL/PostgreSQL|SQL','数据库/缓存|Redis','Redis|数据库/缓存','数据库/缓存|MySQL/PostgreSQL','MySQL/PostgreSQL|数据库/缓存','数据库/缓存|SQL','SQL|数据库/缓存']);
export function aggregate(jobs,technologyTerms=[]){
 const company=new Map(),family=new Map(),city=new Map(),geo=new Map(),skills=new Map(),pairs=new Map(),score=new Map();
 const q=jobs.filter(x=>x.requirements_available);const qCount=q.length;
 for(const x of jobs){
  if(!company.has(x.company))company.set(x.company,{name:x.company,n:0,body:0,q:0});const co=company.get(x.company);co.n++;co.body+=Number(!!x.body_chars);co.q+=Number(x.requirements_available);
  count(family,x.job_family);count(geo,x.geography);count(score,String(x.clarity_score));for(const c of new Set(x.city_tags||[]))count(city,c);
 }
 for(const x of q){const ss=[...new Set(x.skills_in_requirement)].sort();for(const k of ss)count(skills,k);for(let a=0;a<ss.length;a++)for(let b=a+1;b<ss.length;b++)if(!redundant.has(ss[a]+'|'+ss[b]))count(pairs,ss[a]+'\u001f'+ss[b]);}
 const combos=[...pairs].filter(([,n])=>n>=20).map(([key,n])=>{const [a,b]=key.split('\u001f');return {a,b,n,denominator:qCount,pct:qCount?n/qCount*100:0,lift:n*qCount/(skills.get(a)*skills.get(b))};});
 const termMap=new Map((technologyTerms||[]).map(term=>[String(term.id??term.name),{...term,id:String(term.id??term.name),name:String(term.name??term.id),category:String(term.category||term.group||'未分类')}]));
 const technologyFields=['requirement','duty','fulltext'];
 function technologyRows(sourceMap,denominator){return [...sourceMap].map(([id,n])=>{const term=termMap.get(id)||{id,name:id,category:'未分类'};return {...term,n,denominator,pct:denominator?n/denominator*100:0};}).sort((a,b)=>b.n-a.n||a.category.localeCompare(b.category,'zh-CN')||a.name.localeCompare(b.name,'zh-CN'));}
 function technologyCounts(rows,field){const map=new Map();for(const x of rows)for(const id of new Set(x['tech_'+field]||[]))count(map,String(id));return map;}
 const bodyDenominator=jobs.filter(x=>x.body_chars).length;
 const technologyFrequency=Object.fromEntries(technologyFields.map(field=>[field,technologyRows(technologyCounts(field==='requirement'?q:jobs,field),field==='requirement'?qCount:bodyDenominator)]));
 const cityDirection=new Map();
 for(const x of jobs){if(!DIRECTIONS.includes(x.title_direction))continue;for(const cityName of new Set(x.city_tags||[])){if(!cityDirection.has(cityName))cityDirection.set(cityName,new Map());count(cityDirection.get(cityName),x.title_direction);}}
 const cityDirectionStats=[...cityDirection].map(([cityName,values])=>{const directions=DIRECTIONS.map(name=>({name,n:values.get(name)||0})),total=directions.reduce((n,x)=>n+x.n,0);return {name:cityName,n:total,directions:directions.map(x=>({...x,pct:total?x.n/total*100:0}))};}).sort((a,b)=>b.n-a.n||a.name.localeCompare(b.name,'zh-CN'));
 const directionStats=DIRECTIONS.map(name=>{
  const all=jobs.filter(x=>x.title_direction===name),subset=all.filter(x=>x.requirements_available),co=new Map(),sk=new Map(),ed=new Map();
  for(const x of subset){if(!co.has(x.company))co.set(x.company,{n:0,skills:new Map()});const c=co.get(x.company);c.n++;for(const s of new Set(x.skills_in_requirement)){count(sk,s);count(c.skills,s);}for(const e of new Set(x.education_mentions))count(ed,e);}
  const eligible=[...co.values()].filter(x=>x.n>=5),skillMap={};for(const [s,n] of sk)skillMap[s]={n,denominator:subset.length,pct:n/subset.length*100,companyAveragePct:eligible.length?eligible.reduce((t,c)=>t+(c.skills.get(s)||0)/c.n,0)/eligible.length*100:null};
  const technologies=Object.fromEntries(technologyFields.map(field=>[field,technologyRows(technologyCounts(field==='requirement'?subset:all,field),field==='requirement'?subset.length:all.filter(x=>x.body_chars).length)]));
  return {name,n:all.length,q:subset.length,body:all.filter(x=>x.body_chars).length,employers:co.size,eligibleEmployers:eligible.length,skills:skillMap,technologies,education:rows(ed),topEmployers:[...co].map(([company,v])=>({name:company,n:v.n})).sort((a,b)=>b.n-a.n),examples:all.filter(x=>x.reviewed_clarity).slice(0,3).map(x=>({id:x.id,title:x.title,company:x.company}))};
 });
 return {records:jobs.length,body:jobs.filter(x=>x.body_chars).length,q:qCount,employers:company.size,clear:jobs.filter(x=>x.clarity_candidate).length,reviewed:jobs.filter(x=>x.reviewed_clarity).length,metadata:jobs.filter(x=>!x.body_chars).length,experienceKnown:jobs.filter(x=>x._experienceKnown).length,educationNoWord:q.filter(x=>!x.education_mentions.length).length,pools:jobs.filter(x=>x.record_kind!=='具体职位广告').length,companies:[...company.values()].sort((a,b)=>b.n-a.n),families:rows(family),cities:rows(city),cityDirectionStats,geography:rows(geo),skillFrequency:rows(skills).map(x=>({...x,denominator:qCount,pct:qCount?x.n/qCount*100:0})),technologyFrequency,directionStats,combos:combos.sort((a,b)=>b.n-a.n),scores:rows(score)};
}
export function csvText(jobs){
 const fields=['id','company','source_job_id','job_code_raw','title','job_family','title_direction','city','geography','experience','degree_raw','skills_in_requirement','tech_requirement_names','tech_duty_names','tech_fulltext_names','summary','archive_status','clarity_score','reviewed_clarity','url','detail_shard','posttraining_duty_signal','posttraining_requirement_signal','posttraining_candidate'];
 const safe=(key,value)=>{let s=Array.isArray(value)?value.join('；'):String(value??'');if(key==='source_job_id'&&/^\d{16,}$/.test(s))s='ID:'+s;if(/^[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
 return '\ufeff'+[fields.map(k=>safe(k,k)).join(','),...jobs.map(x=>fields.map(k=>safe(k,x[k])).join(','))].join('\r\n');
}

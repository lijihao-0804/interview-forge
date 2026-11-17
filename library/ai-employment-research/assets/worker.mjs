import {prepareJobs,makeFacets,filterJobs,aggregate,csvText} from './engine.mjs';
let jobs=[],byId=new Map(),matches=[],technologyTerms=[],technologyIndexAvailable=false,technologyDictionaryVersion='';let sequence=0;
async function loadCatalog(){
 if(typeof DecompressionStream==='function'){
  try{
   const compressed=await fetch(new URL('../data/catalog.json.gz',import.meta.url));
   if(compressed.ok){
    if((compressed.headers.get('Content-Encoding')||'').includes('gzip'))return await compressed.json();
    return await new Response(compressed.body.pipeThrough(new DecompressionStream('gzip'))).json();
   }
  }catch{/* A host/browser without binary gzip support can use the plain JSON. */}
 }
 const response=await fetch(new URL('../data/catalog.json',import.meta.url));if(!response.ok)throw Error('岗位目录HTTP '+response.status);return response.json();
}
async function loadTechnologyIndex(){
 try{
  if(typeof DecompressionStream==='function'){
   try{const compressed=await fetch(new URL('../data/technology-index.json.gz',import.meta.url));if(compressed.ok){const index=(compressed.headers.get('Content-Encoding')||'').includes('gzip')?await compressed.json():await new Response(compressed.body.pipeThrough(new DecompressionStream('gzip'))).json();if(Array.isArray(index.terms)&&index.jobs&&typeof index.jobs==='object')return index;}}catch{/* Plain JSON remains the portable fallback. */}
  }
  const response=await fetch(new URL('../data/technology-index.json',import.meta.url));
  if(!response.ok)return null;
  const index=await response.json();
  return Array.isArray(index.terms)&&index.jobs&&typeof index.jobs==='object'?index:null;
 }catch{return null;}
}
function mergeTechnologyIndex(raw,index){
 const sourceRows=Array.isArray(raw)?raw:raw.jobs;
 const terms=Array.isArray(index?.terms)?index.terms:[];
 const termById=new Map(terms.map(term=>[String(term.id??term.name),term]));
 const signals=index?.jobs&&typeof index.jobs==='object'?index.jobs:{};
 if(terms.length){
  if(Object.keys(signals).length!==sourceRows.length||sourceRows.some(job=>!Object.hasOwn(signals,job.id)))throw Error('技术索引与岗位目录的ID集合不一致，请使用同一批次的数据文件。');
  technologyTerms=terms.map(term=>({id:String(term.id??term.name),name:String(term.name??term.id),category:String(term.category||term.group||'未分类'),aliases:Array.isArray(term.aliases)?term.aliases:[]}));
  technologyDictionaryVersion=String(index.dictionary_version||'');technologyIndexAvailable=true;
  return sourceRows.map(job=>{
   const signal=signals[job.id]||signals[job.source_job_id]||{};
   const idsFor=field=>[...new Set((Array.isArray(signal[field])?signal[field]:[]).map(String).filter(id=>termById.has(id)))];
   const tech_requirement=idsFor('requirement'),tech_duty=idsFor('duty'),tech_fulltext=idsFor('fulltext');
   const namesFor=ids=>ids.map(id=>String(termById.get(id).name??id));
   return {...job,tech_requirement,tech_duty,tech_fulltext,tech_requirement_names:namesFor(tech_requirement),tech_duty_names:namesFor(tech_duty),tech_fulltext_names:namesFor(tech_fulltext)};
  });
 }
 // Preserve the v3 legacy skill list as a graceful, requirement-only fallback.
 const legacy=[...new Set(sourceRows.flatMap(job=>job.skills_in_requirement||[]))].map(name=>({id:String(name),name:String(name),category:'旧版资格技能',aliases:[]}));
 technologyTerms=legacy;technologyDictionaryVersion='legacy-skills';technologyIndexAvailable=false;
 return sourceRows.map(job=>{const termsForJob=[...new Set(job.skills_in_requirement||[])].map(String);return {...job,tech_requirement:termsForJob,tech_duty:[],tech_fulltext:[],tech_requirement_names:termsForJob,tech_duty_names:[],tech_fulltext_names:[]};});
}
self.onmessage=async({data})=>{
 const {type,requestId}=data;
 try{
  if(type==='INIT'){
   const [raw,index]=await Promise.all([loadCatalog(),loadTechnologyIndex()]);
   jobs=prepareJobs(mergeTechnologyIndex(raw,index));byId=new Map(jobs.map(x=>[x.id,x]));
   self.postMessage({type:'READY',requestId,facets:makeFacets(jobs,technologyTerms),total:jobs.length,technologyIndexAvailable,technologyDictionaryVersion});
  }else if(type==='QUERY'){
   sequence=requestId;matches=filterJobs(jobs,data.filters,data.favoriteIds);const stats=aggregate(matches,technologyTerms),page=Math.max(0,Math.min(data.page||0,Math.max(0,Math.ceil(matches.length/24)-1)));
   self.postMessage({type:'RESULT',requestId,page,total:matches.length,stats,jobs:matches.slice(page*24,(page+1)*24)});
  }else if(type==='PAGE'){
   const page=Math.max(0,Math.min(data.page||0,Math.max(0,Math.ceil(matches.length/24)-1)));self.postMessage({type:'PAGE_RESULT',requestId,page,total:matches.length,jobs:matches.slice(page*24,(page+1)*24)});
  }else if(type==='LOOKUP')self.postMessage({type:'LOOKUP_RESULT',requestId,jobs:data.ids.map(id=>byId.get(id)).filter(Boolean)});
  else if(type==='EXPORT')self.postMessage({type:'EXPORT_RESULT',requestId,csv:csvText(matches),count:matches.length});
 }catch(error){self.postMessage({type:'ERROR',requestId,message:String(error.message||error)});}
};

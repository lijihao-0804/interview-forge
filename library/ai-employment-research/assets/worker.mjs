import {prepareJobs,makeFacets,filterJobs,aggregate,csvText} from './engine.mjs';
let jobs=[],byId=new Map(),matches=[];let sequence=0;
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
self.onmessage=async({data})=>{
 const {type,requestId}=data;
 try{
  if(type==='INIT'){
   const raw=await loadCatalog();jobs=prepareJobs(Array.isArray(raw)?raw:raw.jobs);byId=new Map(jobs.map(x=>[x.id,x]));
   self.postMessage({type:'READY',requestId,facets:makeFacets(jobs),total:jobs.length});
  }else if(type==='QUERY'){
   sequence=requestId;matches=filterJobs(jobs,data.filters,data.favoriteIds);const stats=aggregate(matches),page=Math.max(0,Math.min(data.page||0,Math.max(0,Math.ceil(matches.length/24)-1)));
   self.postMessage({type:'RESULT',requestId,page,total:matches.length,stats,jobs:matches.slice(page*24,(page+1)*24)});
  }else if(type==='PAGE'){
   const page=Math.max(0,Math.min(data.page||0,Math.max(0,Math.ceil(matches.length/24)-1)));self.postMessage({type:'PAGE_RESULT',requestId,page,total:matches.length,jobs:matches.slice(page*24,(page+1)*24)});
  }else if(type==='LOOKUP')self.postMessage({type:'LOOKUP_RESULT',requestId,jobs:data.ids.map(id=>byId.get(id)).filter(Boolean)});
  else if(type==='EXPORT')self.postMessage({type:'EXPORT_RESULT',requestId,csv:csvText(matches),count:matches.length});
 }catch(error){self.postMessage({type:'ERROR',requestId,message:String(error.message||error)});}
};

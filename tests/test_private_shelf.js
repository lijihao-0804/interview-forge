const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Node {
  constructor() { this.children=[]; this.style={}; this.attributes={}; this.hidden=true; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children=nodes; }
  setAttribute(k,v) { this.attributes[k]=v; }
  removeAttribute(k) { delete this.attributes[k]; }
  cloneNode() { const n=new Node(); n.href=this.href;n.target=this.target;n.rel=this.rel;return n; }
}
const host=new Node(), events={}, requests=[];
const document={visibilityState:'visible',getElementById:id=>id==='privateTeachingShelf'?host:null,createElement:()=>new Node(),addEventListener:(name,fn)=>events[name]=fn};
let poll;
vm.runInNewContext(fs.readFileSync('assets/private-archive-entry.js','utf8'), {
  document,AbortController,setTimeout,clearTimeout,
  setInterval:fn=>{poll=fn;},addEventListener:(name,fn)=>events[name]=fn,
  fetch:(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}))
});
const metadata={available:true,entry:{title:'SYNTHETIC_PRIVATE_TITLE',description:'synthetic',url:'/api/private-archive/index.html'}};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function reply(status=200,body=metadata) {
  const req=requests.shift();
  assert.equal(req.url,'/api/private-archive-status');
  assert.equal(req.options.credentials,'same-origin');assert.equal(req.options.cache,'no-store');
  req.resolve({ok:status===200,json:async()=>body});
}
(async()=>{
  reply();await flush();assert.equal(host.hidden,false);
  const report = {title:'SECOND_FIXTURE',description:'fixture',url:'/library/development-history/index.html'};
  events.focus();reply(200,{...metadata,entries:[metadata.entry,report]});await flush();
  assert.equal(host.children.length,2);
  events.focus();reply(200,{available:false,entries:[report]});await flush();
  assert.equal(host.children.length,1);
  events.focus();assert.equal(host.hidden,true);assert.equal(host.children.length,0);
  events['interviewforge:auth-change']({detail:{status:'checking'}});
  reply();await flush();assert.equal(host.children.length,0,'late privileged response must not resurrect a card');
  for (const status of [401,403,503]) {events.focus();reply(status);await flush();assert.equal(host.hidden,true);}
  for (const body of [{available:false}, {available:true}, {...metadata,entry:{...metadata.entry,url:'https://elsewhere.invalid'}}]) {
    events.focus();reply(200,body);await flush();assert.equal(host.children.length,0);
  }
  events.pageshow();reply();await flush();assert.equal(host.hidden,false);
  events.pagehide();assert.equal(host.children.length,0,'bfcache snapshot contains no private card');
  events.pageshow();reply(401);await flush();assert.equal(host.hidden,true);
  events.storage();reply();await flush();assert.equal(host.hidden,false);
  document.visibilityState='hidden';events.visibilitychange();assert.equal(host.children.length,0);
  poll();assert.equal(requests.length,0,'background page does not retain or fetch private metadata');
  document.visibilityState='visible';events.visibilitychange();reply();await flush();assert.equal(host.hidden,false);
  poll();reply(403);await flush();assert.equal(host.children.length,0,'revocation removes card on next check');
  console.log('Private shelf: fail-closed metadata, late responses, account changes, bfcache, visibility, polling passed');
})().catch(error=>{console.error(error);process.exitCode=1;});

// Private status, documents and media must never enter the service-worker cache.
const workerEvents={};
vm.runInNewContext(fs.readFileSync('service-worker.js','utf8'),{
  URL,self:{location:{origin:'https://fixture.invalid'},addEventListener:(name,fn)=>workerEvents[name]=fn}
});
for(const path of ['/api/private-archive-status','/api/private-archive/index.html','/api/private-archive/assets/media/test.png','/library/development-history/chapters/review.html']) {
  let intercepted=false;
  workerEvents.fetch({request:{url:'https://fixture.invalid'+path,method:'GET',mode:'navigate'},respondWith:()=>{intercepted=true;}});
  assert.equal(intercepted,false);
}

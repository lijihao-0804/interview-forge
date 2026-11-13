/* Exercise the real UI script with controlled auth/runner responses. */
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const checker = require('../assets/practice-checker.js');
class Element {
  constructor() { this.children=[]; this.listeners={}; this.style={}; this.value=''; this.textContent=''; this.disabled=false; this.hidden=false; this.attrs={}; }
  addEventListener(name, fn) { this.listeners[name]=fn; }
  appendChild(el) { this.children.push(el); }
  replaceChildren() { this.children=[]; }
  setAttribute(key, value) { this.attrs[key]=value; }
  getAttribute(key) { return this.attrs[key] || ''; }
}
async function setup(responses, {guest=false, mode='tokens', samples=3}={}) {
  const elements = new Map();
  const get = id => { if(!elements.has(id)) elements.set(id,new Element()); return elements.get(id); };
  const item = {id:'one',title:'测试题',url:'one.html',suite_version:'test',checker:{mode,reason:'多解'},codes:{python:'print(1)'},samples:Array.from({length:samples},(_,i)=>({input:String(i),expected:String(i),name:'边界'+i,source:i?'supplemental':'statement'}))};
  let initialize, requests=[], prompts=0;
  const storage = {getItem:()=>null,setItem:()=>{},removeItem:()=>{}};
  const document = {readyState:'loading', documentElement:new Element(), getElementById:get, createElement:()=>new Element(), addEventListener:(n,cb)=>{if(n==='DOMContentLoaded')initialize=cb;}};
  const window = {InterviewForgePracticeChecker:checker,addEventListener:()=>{},matchMedia:()=>({matches:false}),setTimeout,clearTimeout,
    InterviewForgeAuth:{ready:true,requireUser:async()=>{prompts++;if(guest)throw Error('login');},fetchProtected:async(url,options)=>{
      requests.push(JSON.parse(options.body));
      const response=responses.shift();
      if(typeof response==='function')return response(options);
      if(response instanceof Error)throw response;
      return {ok:response.http==null || response.http===200,status:response.http||200,json:async()=>response};
    }}};
  const sandbox = {window,document,localStorage:storage,sessionStorage:storage,location:{search:'?id=one&lang=python',href:'https://test/acm?id=one'},history:{replaceState:()=>{}},URL,URLSearchParams,AbortController,Promise,Error,String,Number,Object,Array,setTimeout,clearTimeout,
    fetch:async()=>({ok:true,json:async()=>[item]})};
  vm.runInNewContext(fs.readFileSync(require.resolve('../assets/practice-reference.js'),'utf8'),sandbox);
  await initialize();
  return {get,requests,prompts:()=>prompts,click:async id=>get(id).listeners.click()};
}
(async()=>{
  let ui=await setup([{status:'ok',stdout:'0'},{status:'ok',stdout:'999'},{status:'ok',stdout:'2'}]);
  await ui.click('judge-all-btn');
  assert.equal(ui.requests.length,3,'WA must not skip subsequent cases');
  assert.match(ui.get('suite-summary').textContent,/通过 2\/3 · 未通过 1/);
  assert.equal(ui.get('suite-results').children[1].attrs['data-verdict'],'fail');
  assert.equal(ui.get('suite-results').children.length,3);
  assert.equal(ui.get('run-btn').disabled,false);
  assert.equal(ui.get('cancel-judge-btn').hidden,true);
  assert(ui.requests.every(r=>r.language==='python'&&r.code===ui.requests[0].code),'submitted code/language must be fixed');

  ui=await setup([{status:'ok',stdout:'0'},{http:503,status:'unknown'}]);
  await ui.click('judge-all-btn');
  assert.equal(ui.requests.length,2);
  assert.match(ui.get('suite-summary').textContent,/未通过 0 · 待核对 0 · 服务异常 1 · 未执行 1/);
  assert.doesNotMatch(ui.get('diff-result').textContent,/WRONG|错误/);

  ui=await setup([Object.assign(new Error('expired'),{code:'AUTH_REQUIRED'})]);
  await ui.click('judge-all-btn');
  assert.equal(ui.requests.length,1);
  assert.match(ui.get('suite-summary').textContent,/未通过 0.*服务异常 1.*未执行 2/);
  assert(ui.get('suite-results').children[0].children.some(el=>el.textContent.includes('登录已失效')));

  ui=await setup([{status:'compile_error',stderr:'syntax'}]);
  await ui.click('judge-all-btn');
  assert.equal(ui.requests.length,1,'compile errors stop repeated compiles');
  assert.match(ui.get('suite-summary').textContent,/未通过 1.*未执行 2/);

  ui=await setup([{status:'ok',stdout:'another valid output'}],{mode:'manual',samples:1});
  await ui.click('judge-all-btn');
  assert.match(ui.get('suite-summary').textContent,/未通过 0 · 待核对 1/);

  ui=await setup([],{guest:true});
  await ui.click('judge-all-btn');
  assert.equal(ui.requests.length,0); assert.equal(ui.prompts(),1);

  ui=await setup([],{samples:0});
  assert.equal(ui.get('judge-all-btn').disabled,true);
  await ui.click('judge-all-btn'); assert.equal(ui.requests.length,0);

  let started;
  const startedPromise=new Promise(resolve=>started=resolve);
  ui=await setup([options=>new Promise((_,reject)=>{started();options.signal.addEventListener('abort',()=>reject(Error('aborted')));})]);
  const run=ui.click('judge-all-btn'); await startedPromise;
  assert.equal(ui.get('language-select').disabled,true);
  await ui.click('cancel-judge-btn'); await run;
  assert.equal(ui.requests.length,1);
  assert.match(ui.get('suite-summary').textContent,/未通过 0.*未执行 3/);
  assert.equal(ui.get('run-status').textContent,'已停止');

  console.log('ACM full-suite UI behavior passed');
})().catch(error=>{console.error(error);process.exitCode=1;});

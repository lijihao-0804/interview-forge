/* Exercise the real UI script with controlled auth/runner responses. */
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const checker = require('../assets/practice-checker.js');
const templates = require('../assets/acm-input-templates.js');
class Element {
  constructor() { this.children=[]; this.listeners={}; this.style={}; this.value=''; this.textContent=''; this.disabled=false; this.hidden=false; this.attrs={}; }
  addEventListener(name, fn) { this.listeners[name]=fn; }
  appendChild(el) { this.children.push(el); }
  replaceChildren() { this.children=[]; }
  focus() {}
  setAttribute(key, value) { this.attrs[key]=value; }
  getAttribute(key) { return this.attrs[key] || ''; }
}
async function setup(responses, {guest=false, mode='tokens', samples=3, search='?id=one&lang=python', saved=new Map()}={}) {
  const elements = new Map();
  const get = id => { if(!elements.has(id)) elements.set(id,new Element()); return elements.get(id); };
  const item = {id:'one',title:'测试题',url:'one.html',suite_version:'test',checker:{mode,reason:'多解'},codes:{python:'print(1)',java:'public class Main {}'},samples:Array.from({length:samples},(_,i)=>({input:String(i),expected:String(i),name:'边界'+i,source:i?'supplemental':'statement'}))};
  let initialize, requests=[], prompts=0;
  const storage = {getItem:key=>saved.get(key) ?? null,setItem:(key,value)=>saved.set(key,String(value)),removeItem:key=>saved.delete(key)};
  const document = {readyState:'loading', documentElement:new Element(), getElementById:get, createElement:()=>new Element(), addEventListener:(n,cb)=>{if(n==='DOMContentLoaded')initialize=cb;}};
  const window = {InterviewForgePracticeChecker:checker,InterviewForgeAcmTemplates:templates,addEventListener:()=>{},matchMedia:()=>({matches:false}),setTimeout,clearTimeout,
    InterviewForgeAuth:{ready:true,requireUser:async()=>{prompts++;if(guest)throw Object.assign(Error('login'),{code:'AUTH_REQUIRED'});},fetchProtected:async(url,options)=>{
      requests.push(JSON.parse(options.body));
      const response=responses.shift();
      if(typeof response==='function')return response(options);
      if(response instanceof Error)throw response;
      return {ok:response.http==null || response.http===200,status:response.http||200,json:async()=>response};
    }}};
  const sandbox = {window,document,localStorage:storage,sessionStorage:storage,location:{search,href:'https://test/acm'+search},history:{replaceState:()=>{}},URL,URLSearchParams,AbortController,Promise,Error,String,Number,Object,Array,setTimeout,clearTimeout,
    fetch:async()=>({ok:true,json:async()=>[item]})};
  vm.runInNewContext(fs.readFileSync(require.resolve('../assets/practice-reference.js'),'utf8'),sandbox);
  await initialize();
  function change(id, value, event='change') {
    const el=get(id);
    el.value=value;
    el.listeners[event].call(el);
  }
  return {get,requests,change,prompts:()=>prompts,click:async id=>get(id).listeners.click()};
}
(async()=>{
  let ui=await setup([{status:'ok',stdout:'0'},{status:'ok',stdout:'999'},{status:'ok',stdout:'2'}]);
  assert.equal(ui.get('code-editor').value,'print(1)','opening a problem uses its actual solution');
  assert.equal(ui.get('template-select').hidden,true);
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
  assert.match(ui.get('stdout-area').textContent,/登录/);

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

  const saved=new Map([['interviewforge.practice.context',JSON.stringify({id:'old',title:'旧题',codes:{},samples:[]})]]);
  ui=await setup([{status:'ok',stdout:''},{status:'ok',stdout:'wrong'}],{search:'',saved});
  assert.equal(ui.get('template-select').hidden,false,'direct entry ignores the last visited problem');
  assert.equal(ui.get('sample-select').children.length,3);
  assert.equal(ui.get('stdin-area').value,templates.array.samples[0].input);
  ui.change('template-select','eof');
  ui.change('sample-select','2');
  assert.equal(ui.get('stdin-area').value,'');
  assert.equal(ui.get('expected-area').value,'');
  await ui.click('run-btn');
  assert.equal(ui.get('diff-result').textContent,'输出符合期望','the known empty expected stream is checked');
  await ui.click('run-btn');
  assert.equal(ui.get('diff-result').textContent,'输出不符','unexpected output fails the empty case');
  ui.change('stdin-area','20 22','input');
  ui.change('expected-area','42','input');
  ui.change('code-editor','print(42)','input');
  assert.equal(ui.get('diff-result').textContent,'');
  assert.match(ui.get('case-state').textContent,/自定义/);

  ui.change('template-select','matrix');
  assert.equal(ui.get('sample-select').value,'0');
  assert.equal(ui.get('stdin-area').value,templates.matrix.samples[0].input);
  ui.change('template-select','eof');
  assert.equal(ui.get('sample-select').value,'2');
  assert.equal(ui.get('code-editor').value,'print(42)');
  assert.equal(ui.get('stdin-area').value,'20 22');
  ui.change('language-select','java');
  assert.equal(ui.get('code-editor').value,templates.eof.codes.java);
  assert.equal(ui.get('stdin-area').value,'');
  ui.change('language-select','python');
  assert.equal(ui.get('expected-area').value,'42');
  const reload=await setup([],{search:'',saved});
  assert.equal(reload.get('template-select').value,'eof');
  assert.equal(reload.get('sample-select').value,'2');
  assert.equal(reload.get('stdin-area').value,'20 22');
  await ui.click('reset-btn');
  assert.equal(ui.get('stdin-area').value,'');
  assert.equal(ui.get('expected-area').value,'');
  assert.equal(ui.get('code-editor').value,'print(42)','restoring the sample must retain edited code');
  assert.equal(ui.get('case-state').textContent,'');
  await ui.click('initial-code-btn');
  assert.equal(ui.get('code-editor').value,templates.eof.codes.python);

  const legacy=new Map([['interviewforge.practice.draft:scratch:python:code','print(77)']]);
  ui=await setup([],{search:'',saved:legacy});
  assert.equal(ui.get('code-editor').value,'print(77)','legacy standalone code stays available');
  ui=await setup([{status:'ok',stdout:'0'},{http:503,error:'temporarily unavailable'}]);
  await ui.click('run-btn');
  assert.equal(ui.get('diff-result').textContent,'输出符合期望');
  await ui.click('run-btn');
  assert.equal(ui.get('diff-result').textContent,'','a service failure must clear the previous verdict');
  assert.match(ui.get('status-info').textContent,/暂时不可用/);

  ui=await setup([{status:'ok',stdout:'3'},{status:'ok',stdout:'42'},{status:'ok',stdout:''}],{search:''});
  ui.change('template-select','multi');
  ui.change('stdin-area','custom','input');
  await ui.click('judge-all-btn');
  assert.deepStrictEqual(ui.requests.map(r=>r.stdin),templates.multi.samples.map(s=>s.input));
  assert.equal(ui.get('suite-results').children.length,3);
  ui.change('template-select','array');
  assert.equal(ui.get('suite-results').children.length,0,'switching templates clears the previous suite');

  console.log('ACM full-suite UI behavior passed');
})().catch(error=>{console.error(error);process.exitCode=1;});

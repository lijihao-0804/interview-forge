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
  before() {}
  setAttribute(key, value) { this.attrs[key]=value; }
  getAttribute(key) { return this.attrs[key] || ''; }
}
async function setup(responses, {guest=false, mode='tokens', samples=3, search='?id=one&lang=python', saved=new Map(), progress={username:'alice',progress:{}}, missing=false, historyCalls=[], codeMirror}={}) {
  const elements = new Map();
  const get = id => { if(!elements.has(id)) elements.set(id,new Element()); return elements.get(id); };
  const item = {id:'one',title:'测试题',url:'one.html',suite_version:'test',checker:{mode,reason:'多解'},codes:{python:'print(1)',java:'public class Main {}'},samples:Array.from({length:samples},(_,i)=>({input:String(i),expected:String(i),name:'边界'+i,source:i?'supplemental':'statement'}))};
  const native = search.includes('id=hot100-');
  if (native) {
    item.id = 'hot100-1';
    item.solution_url = '/books/hot100/solution.html';
    delete item.codes;
  }
  let initialize, requests=[], prompts=0;
  const events = {};
  const storage = {getItem:key=>saved.get(key) ?? null,setItem:(key,value)=>saved.set(key,String(value)),removeItem:key=>saved.delete(key)};
  const document = {readyState:'loading', documentElement:new Element(), getElementById:get, createElement:()=>new Element(), addEventListener:(n,cb)=>{events[n]=cb;if(n==='DOMContentLoaded')initialize=cb;}};
  const systemDark = new Element();
  systemDark.matches = false;
  const window = {CodeMirror:codeMirror,InterviewForgePracticeChecker:checker,InterviewForgeAcmTemplates:templates,addEventListener:(n,cb)=>{
    const previous=events[n];
    events[n]=previous ? (...args)=>Promise.all([previous(...args), cb(...args)]) : cb;
  },matchMedia:()=>systemDark,setTimeout,clearTimeout,
    InterviewForgeAuth:{ready:true,requireUser:async()=>{prompts++;if(guest)throw Object.assign(Error('login'),{code:'AUTH_REQUIRED'});},fetchProtected:async(url,options)=>{
      requests.push(JSON.parse(options.body));
      const response=responses.shift();
      if(typeof response==='function')return response(options);
      if(response instanceof Error)throw response;
      return {ok:response.http==null || response.http===200,status:response.http||200,json:async()=>response};
    }}};
  const sandbox = {window,document,CodeMirror:codeMirror,localStorage:storage,sessionStorage:storage,location:{search,href:'https://test/acm'+search},history:{replaceState:()=>{}},URL,URLSearchParams,AbortController,Promise,Error,String,Number,Object,Array,setTimeout,clearTimeout,
    fetch:async url=>{
      if (url.includes('/history/')) {
        historyCalls.push(url);
        const detail = url.endsWith('/42');
        return {ok:true,json:async()=>detail ? {username:'alice',code:'older code'} :
          {username:'alice',submissions:[{id:42,language:'python',accepted:false,submitted_at:'2026-11-18T01:00:00Z'}]}};
      }
      if (url.endsWith('/status?details=1')) return {ok:!!progress.username,status:progress.username ? 200 : 401,json:async()=>progress};
      return {ok:!missing,json:async()=>native ? item : [item]};
    }};
  vm.runInNewContext(fs.readFileSync(require.resolve('../assets/practice-reference.js'),'utf8'),sandbox);
  await initialize();
  function change(id, value, event='change') {
    const el=get(id);
    el.value=value;
    el.listeners[event].call(el);
  }
  return {get,requests,change,events,systemDark,root:document.documentElement,prompts:()=>prompts,click:async id=>get(id).listeners.click()};
}
(async()=>{
  const themeStorage = new Map();
  const codeMirror = {fromTextArea(field, options) {
    codeMirror.options = options;
    return {on() {}, setOption(key, value) { options[key] = value; },
      setValue(value) { field.value = value; }, getValue() { return field.value; }};
  }};
  const acm = await setup([], {saved:themeStorage, codeMirror});
  function expectTheme(theme) {
    assert.equal(acm.root.getAttribute('data-theme'), theme);
    assert.equal(codeMirror.options.theme, theme === 'light' ? 'eclipse' : 'material-darker');
  }
  expectTheme('light');
  acm.systemDark.matches = true;
  acm.systemDark.listeners.change();
  expectTheme('dark');
  assert(!themeStorage.has('forge-theme'), 'following the system preserves an unset preference');
  await acm.click('theme-toggle');
  expectTheme('light');
  assert.equal(themeStorage.get('forge-theme'), 'light');
  acm.systemDark.listeners.change();
  expectTheme('light');
  themeStorage.set('forge-theme', 'dark');
  acm.events.storage({key:'forge-theme'});
  expectTheme('dark');
  acm.systemDark.matches = false;
  themeStorage.set('forge-theme', 'system');
  acm.events.pageshow();
  expectTheme('light');
  assert.equal(themeStorage.get('forge-theme'), 'system');
  themeStorage.set('forge-theme', 'dark');
  acm.events.pageshow();
  expectTheme('dark');
  themeStorage.clear();
  acm.events.storage({key:null});
  expectTheme('light');
  const blockedStorage = {get() { throw Error('blocked'); }, set() { throw Error('blocked'); }};
  const offline = await setup([], {saved:blockedStorage, search:''});
  await offline.click('theme-toggle');
  offline.events.pageshow();
  offline.systemDark.listeners.change();
  assert.equal(offline.root.getAttribute('data-theme'), 'dark');

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

  const nativeStorage = new Map();
  ui=await setup([{accepted:true,results:[{verdict:'pass'},{verdict:'pass'},{verdict:'pass'}]}],
    {search:'?id=hot100-1&lang=python',saved:nativeStorage});
  assert.match(ui.get('code-editor').value,/json.loads/);
  assert.match(ui.get('judge-all-btn').textContent,/提交评测/);
  await ui.click('judge-all-btn');
  assert.equal(ui.requests.length,1);
  assert.equal(ui.requests[0].id,'hot100-1');
  assert.strictEqual(ui.requests[0].samples,undefined);
  assert.match(ui.get('run-status').textContent,/已通过/);
  assert(nativeStorage.has('interviewforge.acm.updated'));

  const progress = {username:'alice',progress:{'hot100-1':{by_language:{java:{status:'accepted',rounds:2}}}}};
  ui=await setup([{accepted:false,results:[{verdict:'fail'}]}],{search:'?id=hot100-1&lang=java',progress});
  assert.match(ui.get('native-progress').textContent,/Java.*已通过.*2 轮/);
  await ui.click('judge-all-btn');
  assert.match(ui.get('native-progress').textContent,/已通过/);
  assert.match(ui.get('run-status').textContent,/本次提交未通过/);
  ui.change('language-select','python');
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.match(ui.get('native-progress').textContent,/Python.*未做.*0 轮/);
  progress.username='bob';progress.progress={};
  await ui.events.focus();
  assert.match(ui.get('native-progress').textContent,/未做/);
  assert.equal(ui.get('suite-summary').textContent,'');
  progress.username='';
  await ui.events.pageshow();
  assert.match(ui.get('native-progress').textContent,/登录后查看/);
  progress.username='carol';progress.progress={'hot100-1':{by_language:{python:{status:'attempted',rounds:0}}}};
  ui.events['interviewforge:auth-change']();
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.match(ui.get('native-progress').textContent,/已尝试/);
  ui=await setup([],{search:'?id=hot100-9999',missing:true});
  assert.equal(ui.get('judge-all-btn').disabled,true);
  assert.equal(ui.get('run-btn').disabled,true);
  assert.match(ui.get('context-notice').textContent,/题目不存在/);
  assert.equal(ui.get('code-editor').value,'');

  const historyCalls=[];
  ui=await setup([{accepted:false,results:[{verdict:'fail'}]}],{search:'?id=hot100-1',historyCalls});
  assert.equal(historyCalls.length,0);
  ui.change('code-editor','current draft','input');
  const historyPanel=ui.get('native-history');
  historyPanel.open=true;
  await historyPanel.listeners.toggle();
  assert.deepEqual(historyCalls,['/api/practice/hot100/history/hot100-1']);
  const entry=ui.get('native-history-list').children[0];
  entry.open=true;
  await entry.listeners.toggle();
  assert.match(entry.children[0].textContent,/Python · 未通过/);
  assert.equal(entry.children[1].textContent,'older code');
  assert.equal(ui.get('code-editor').value,'current draft');
  await ui.click('judge-all-btn');
  assert.deepEqual(historyCalls,['/api/practice/hot100/history/hot100-1','/api/practice/hot100/history/hot100-1/42','/api/practice/hot100/history/hot100-1']);
  assert.equal(ui.get('code-editor').value,'current draft');

  console.log('ACM full-suite UI behavior passed');
})().catch(error=>{console.error(error);process.exitCode=1;});

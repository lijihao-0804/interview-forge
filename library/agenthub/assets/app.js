'use strict';

const $ = id => document.getElementById(id);
const E = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const jsonInflight = new Map();
function fetchJson(url) {
  if (!jsonInflight.has(url)) {
    jsonInflight.set(
      url,
      document.getElementById(url)
        ? Promise.resolve().then(() => JSON.parse(document.getElementById(url).textContent))
        : fetch(url).then(res => {
        if (!res.ok) throw new Error('HTTP ' + res.status + ' loading ' + url);
        return res.json();
      })
    );
  }
  return jsonInflight.get(url);
}

function fnv1a32(str) {
  const bytes = new TextEncoder().encode(str);
  let h = 0x811c9dc5;
  for (let i = 0; i < bytes.length; i++) {
    h ^= bytes[i];
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h;
}

let manifest = null;
const chaptersCache = new Map();
const originalsCache = new Map();
const sourcesCache = new Map();
let visualsCache = null;
let diagramsCache = null;
let notesCache = null;
let templatesCache = null;
let searchIndexCache = null;
let historyLoaded = false;

async function ensureChapter(id) {
  if (chaptersCache.has(id)) return chaptersCache.get(id);
  if (originalsCache.has(id)) return originalsCache.get(id);
  const isOrig = manifest.originals.some(o => o.id === id);
  const path = isOrig ? './data/originals/' + encodeURIComponent(id) + '.json' : './data/chapters/' + encodeURIComponent(id) + '.json';
  const obj = await fetchJson(path);
  if (isOrig) originalsCache.set(id, obj);
  else chaptersCache.set(id, obj);
  return obj;
}

async function ensureSource(key) {
  if (sourcesCache.has(key)) return sourcesCache.get(key);
  const bIdx = String(fnv1a32(key) % 64).padStart(2, '0');
  const bucket = await fetchJson('./data/sources/b_' + bIdx + '.json');
  for (const [k, v] of Object.entries(bucket)) {
    sourcesCache.set(k, v);
  }
  return sourcesCache.get(key) || null;
}

async function ensureVisuals() {
  if (!visualsCache) visualsCache = await fetchJson('./data/visuals.json');
  return visualsCache;
}

async function ensureDiagrams() {
  if (!diagramsCache) diagramsCache = await fetchJson('./data/diagrams.json');
  return diagramsCache;
}

async function ensureNotes() {
  if (!notesCache) notesCache = await fetchJson('./data/notes.json');
  return notesCache;
}

async function ensureSearchIndex() {
  if (!searchIndexCache) searchIndexCache = await fetchJson('./data/search-index.json');
  return searchIndexCache;
}

async function ensureHistoryData() {
  if (historyLoaded) return;
  const [tpls, data, samplePkg] = await Promise.all([
    fetchJson('./data/history-templates.json'),
    fetchJson('./data/history-data.json'),
    fetchJson('./data/history-sample.json')
  ]);
  templatesCache = tpls;
  window.__ARCHIVE_DATA__ = data;
  window.__ARCHIVE_SAMPLE__ = samplePkg.sample;
  window.__ARCHIVE_SAMPLE__.sources = Object.fromEntries(
    Object.entries(samplePkg.sampleSources || {}).map(([key, blob]) => [key, data.sourceTexts[blob]])
  );
  historyLoaded = true;
}

const frames = new Map(), ready = new Set();
let current = 'learn', currentScope = 'all', ticket = 0, lastHistory = 'recent', chapterId = 'start', library = 'curriculum', tocObserver, saveTimer, bookMounted = false;
const storage = {
  get(key, otherwise) { try { return JSON.parse(localStorage.getItem('agenthub-book-' + key)) ?? otherwise; } catch { return otherwise; } },
  set(key, val) { try { localStorage.setItem('agenthub-book-' + key, JSON.stringify(val)); } catch {} }
};
const read = new Set(storage.get('read', [])), positions = storage.get('positions', {});

function resize() { $('archiveWorkspace').style.height = (innerHeight - $('archiveBar').offsetHeight) + 'px'; }
function active() {
  const learn = current === 'learn';
  $('navLearn').classList.toggle('active', learn);
  $('navHistory').classList.toggle('active', !learn);
  $('navLearn').setAttribute('aria-current', learn ? 'page' : 'false');
  $('navHistory').setAttribute('aria-current', learn ? 'false' : 'page');
  $('historyPicker').hidden = learn;
  if (!learn) $('historyView').value = current;
}
function pauseFrames() {
  $('recentHistory').hidden = true;
  stopLearningAnimations();
  for (const e of frames.values()) {
    e.frame.contentWindow.archiveApp?.pause?.();
    e.frame.hidden = true;
  }
}

window.archiveFrameState = function (app, view, scope) {
  if (!ready.has(app) || !current.startsWith(app + '-')) return;
  lastHistory = app + '-' + view;
  remember(lastHistory, scope);
};

window.archiveNavigate = async function (route, scope = 'all') {
  if (route === 'learn') { openChapter(chapterId); return; }
  const valid = ['recent', 'global-directory', 'global-git', 'full-tree', 'full-point', 'full-flow', 'full-boundaries', 'sample-tree', 'sample-graph', 'sample-flow'];
  if (!valid.includes(route)) route = 'global-directory';
  preservePosition();
  const ownTicket = ++ticket;
  lastHistory = route;
  remember(route, scope);
  $('learning').hidden = true;
  $('resources').hidden = true;
  $('loading').textContent = '正在按需加载开发历程视图数据…';
  $('loading').hidden = false;
  pauseFrames();
  if (route === 'recent') {
    const recent = await fetchJson('./data/recent-history.json');
    if (ownTicket !== ticket) return;
    $('recentArticle').innerHTML = '<header><h1>' + E(recent.title) + '</h1><p class="chapter-summary">' + E(recent.summary) + '</p></header>' + recent.html;
    $('loading').hidden = true;
    $('recentHistory').hidden = false;
    $('recentHistory').scrollTop = 0;
    return;
  }
  await ensureHistoryData();
  if (ownTicket !== ticket) return;
  const split = route.indexOf('-'), app = route.slice(0, split), view = route.slice(split + 1);
  if (!frames.has(app)) {
    const frame = document.createElement('iframe');
    frame.id = 'view-' + app;
    frame.title = app === 'global' ? '全局开发树' : app === 'full' ? '完整开发历程' : '早期设计小样';
    frame.allow = 'fullscreen';
    frame.setAttribute('allowfullscreen', '');
    frame.hidden = true;
    const loaded = new Promise(resolve => frame.onload = resolve);
    frames.set(app, { frame, loaded });
    frame.srcdoc = templatesCache[app === 'global' ? 'global_view' : app];
    $('archiveWorkspace').append(frame);
  }
  const entry = frames.get(app);
  await entry.loaded;
  if (ownTicket !== ticket) return;
  ready.add(app);
  entry.frame.hidden = false;
  if (entry.lastView !== view || entry.lastScope !== scope) {
    entry.frame.contentWindow.archiveApp.open(view, scope);
    entry.lastView = view;
    entry.lastScope = scope;
  }
  $('loading').hidden = true;
  resize();
};

function progress() {
  const done = manifest.chapters.filter(c => read.has(c.id)).length;
  $('readProgress').textContent = '已读 ' + done + ' / ' + manifest.chapters.length + ' 章 · 本机保存';
  $('readBar').max = manifest.chapters.length;
  $('readBar').value = done;
  $('markRead').textContent = read.has(chapterId) ? '已读完 · 撤销' : '标记读完';
  $('markRead').setAttribute('aria-pressed', String(read.has(chapterId)));
}

async function resource(name) {
  for (const stop of labTimers.values()) stop();
  $('resources').hidden = false;
  $('loading').hidden = true;
  $('resourceText').textContent = '正在加载说明文档…';
  const notes = await ensureNotes();
  if (!(name in notes)) name = '使用说明';
  for (const e of frames.values()) e.frame.contentWindow.archiveApp?.pause?.();
  $('resourceSelect').value = name;
  $('resourceText').textContent = notes[name];
}

window.archiveLink = function (href) {
  const [name, hash = ''] = href.split('#'), params = new URLSearchParams(hash), scope = params.get('scope') || 'all';
  if (name === 'global.html') return window.archiveNavigate('global-directory');
  if (name === 'full.html') return window.archiveNavigate('full-' + (params.get('view') || 'tree'), scope);
  if (name === 'full-flow.html') return window.archiveNavigate('full-flow', scope);
  if (name === 'flow.html') return window.archiveNavigate('sample-flow');
  if (name === 'index.html' || name === 'sample.html') return window.archiveNavigate('sample-tree');
  resource(manifest.noteKeys.includes(name) ? name : '使用说明');
};

document.addEventListener('click', e => {
  const chapter = e.target.closest('[data-chapter]');
  if (chapter) { openChapter(chapter.dataset.chapter, null, true); return; }
  const src = e.target.closest('[data-source]');
  if (src) { showSource(Number(src.dataset.source)); return; }
  const snap = e.target.closest('a[data-snapshot]');
  if (snap) {
    e.preventDefault();
    sourceView(snap.dataset.snapshot);
    return;
  }
  const a = e.target.closest('a[data-doc],a[data-section]');
  if (a) {
    e.preventDefault();
    if (a.dataset.doc) openChapter(a.dataset.doc, a.dataset.anchor || null, true);
    else {
      const target = $('chapterArticle').querySelector('#' + CSS.escape(a.dataset.section));
      target?.scrollIntoView({ block: 'start' });
    }
  }
});

$('navLearn').onclick = () => openChapter(chapterId);
$('navHistory').onclick = () => window.archiveNavigate(lastHistory);
$('historyView').onchange = e => window.archiveNavigate(e.target.value);
$('showResources').onclick = () => resource('界面与教材说明');
$('closeResources').onclick = () => { $('resources').hidden = true; };
$('resourceSelect').onchange = e => resource(e.target.value);
$('fullscreenArchive').onclick = async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  } catch {}
};

$('tabCurriculum').onclick = () => { library = 'curriculum'; list(); };
$('tabOriginals').onclick = () => { library = 'originals'; list(); };
$('bookSearch').oninput = () => list();
$('markRead').onclick = () => {
  if (read.has(chapterId)) read.delete(chapterId);
  else read.add(chapterId);
  storage.set('read', [...read]);
  progress();
  list();
};
$('fontSize').onclick = () => {
  const big = document.body.classList.toggle('large-type');
  $('fontSize').setAttribute('aria-pressed', String(big));
  $('fontSize').textContent = big ? '标准字号' : '大字阅读';
  storage.set('large', big);
};
$('printChapter').onclick = () => window.print();
$('toggleBookMenu').onclick = () => {
  const open = $('learning').classList.toggle('menu-open');
  $('toggleBookMenu').setAttribute('aria-expanded', String(open));
};
$('closeSource').onclick = () => $('sourceDialog').close();
$('sourceDialog').addEventListener('click', e => { if (e.target === $('sourceDialog')) $('sourceDialog').close(); });
$('bookScroll').addEventListener('scroll', () => { clearTimeout(saveTimer); saveTimer = setTimeout(preservePosition, 250); }, { passive: true });
window.addEventListener('beforeunload', preservePosition);
window.addEventListener('resize', resize);
document.addEventListener('keydown', event => {
  if (current !== 'global-directory' || !$('resources').hidden || event.target.matches('input,select,textarea') || event.target.isContentEditable || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
    const app = frames.get('global')?.frame.contentWindow.archiveApp;
    if (app?.browse) { event.preventDefault(); app.browse(event.key === 'ArrowDown' ? 1 : -1); }
  }
});

function mountTrace() {
  const box = $('requestTrace'); if (!box) return;
  const saved = storage.get('request-trace', { branch: 'approval', step: 0 });
  let branch = saved.branch || 'approval', i = Number(saved.step) || 0;
  const common = [
    ['1. 接收请求与权限核验', '用户提问：“退款还没到账，请帮我查一下，必要时创建工单”。系统首先校验用户身份与所在工作区权限。', '绑定会话标识 SUP-T1 与当前工作区上下文，确保后续操作不越界。'],
    ['2. 幂等登记与创建 Run', '解析当前生效的 AgentVersion，按 client_token 校验幂等性并创建（或复用）本轮执行记录 SUP-R1。', '同一 client_token 且请求正文一致时直接复用原 Run；若篡改正文则返回 409 冲突。'],
    ['3. 装配模型上下文', '创建 Run 时锁定知识库与 Wiki 快照；首次进入 prepare 节点时筛选并冻结长期记忆，最后按 Token 预算裁剪装入请求。', '“记录候选身份”、“通过预算装入请求”与“模型实际采纳”是三个不同阶段。'],
    ['4. 模型发起工具调用提议', '模型输出的 tool_calls 仅是结构化提议。运行时先校验工具是否在已发布清单内、参数是否符合 Schema，再进入治理策略判定。', '工具的副作用类型 (effect)、风险等级 (risk) 与审批策略 (approval_policy) 共同决定放行路径。']
  ];
  const routes = {
    read: { name: '路径 A：只读工具自动放行 (ALLOW_AUTO)', tool: 'query_customer', effect: 'READ', risk: 'LOW', policy: 'NEVER', steps: [['策略判定：自动放行', '参数校验通过，且满足 READ + approval_policy=NEVER，策略判定为 ALLOW_AUTO。', '注意：READ 与 risk=LOW 是两个独立维度，不能仅凭风险低就跳过策略检查。'], ['执行查询并回填观察', '调用只读工具获取客户与工单状态，将返回结果作为 ToolMessage 追加到执行上下文，交由模型继续推理。', '工具返回的是客观数据观察，后续由模型综合生成最终答复。'], ['完成响应并归档事件', '将最终回答与执行事件持久化落库并推送至前端；同一会话后续追问将开启新的 Turn 与 Run。', '只读自动链路在单次连续执行中闭环完成。']] },
    approval: { name: '路径 B：写操作进入人工审批 (REQUIRE_APPROVAL)', tool: 'create_ticket', effect: 'WRITE', risk: 'MEDIUM', policy: 'ALWAYS', steps: [['策略拦截：挂起等待审批', 'WRITE 操作触发 REQUIRE_APPROVAL。系统落库 Approval 记录并写入 LangGraph Checkpoint 断点，Run 进入 AWAITING_APPROVAL。', '此时尚未向外部系统发送任何写请求。'], ['人工批准：仅授予放行许可', '审批人点击批准后，decision_status 更新为 APPROVED，但 execution_status 仍为 NOT_STARTED。', '“批准通过”仅代表允许继续执行，不代表工单已经创建成功。'], ['恢复执行与原子认领 (CAS Claim)', 'Worker 恢复原 Run (SUP-R1)，复核权限后通过数据库条件更新（CAS）抢占执行权，状态转为 CLAIMED 后才真正发起调用。', '并发场景下只有一个 Worker 能认领成功，彻底杜绝重复派发。'], ['确认回执并完成闭环', '收到内部工单创建成功的明确回执后，记录 SUCCEEDED 并把结果交回模型生成最终回复。', '若外部写请求已发出但因超时丢失回执，则必须标记为 UNKNOWN_OUTCOME → Run NEEDS_ATTENTION，严禁盲目重试。']] },
    invalid: { name: '路径 C：参数校验未通过，直接拒绝派发', tool: 'create_ticket', effect: 'WRITE', risk: 'MEDIUM', policy: 'ALWAYS', steps: [['Schema 校验拦截', '模型提议缺少必填字段，参数校验直接拒绝该提议，不会创建审批单，更不会触发外部调用。', '拦截发生在参数校验层（而非 ToolPolicy 新增 DENY 枚举）。'], ['关联错误并交回运行时', '将校验失败原因绑定到原动作记录，由运行时按既定错误策略处理，绝不猜测参数强行执行。', '未越过派发边界的失败属于确定性未执行，不会污染外部系统状态。']] }
  };
  if (!routes[branch]) branch = 'approval';
  box.innerHTML = '<label class="trace-branch">切换推演分支 <select aria-label="请求主线的工具分支">' + Object.entries(routes).map(([id, r]) => '<option value="' + id + '">' + E(r.name) + '</option>').join('') + '</select></label><p class="trace-identity"></p><div class="trace-nav" role="group" aria-label="本路线步骤"></div><div class="trace-body" aria-live="polite"></div><div class="trace-foot"><button data-trace-prev>上一步</button><span></span><button data-trace-next>下一步</button></div>';
  box.querySelector('select').value = branch;
  function draw() {
    const r = routes[branch], steps = [...common, ...r.steps];
    i = Math.min(Math.max(0, i), steps.length - 1);
    const s = steps[i];
    box.dataset.branch = branch; box.dataset.step = i;
    box.querySelector('.trace-identity').textContent = '执行实例 SUP-R1 · 工具 ' + r.tool + ' · effect=' + r.effect + ' · risk=' + r.risk + ' · approval_policy=' + r.policy;
    box.querySelector('.trace-nav').innerHTML = steps.map((s, n) => '<button data-trace-step="' + n + '" aria-pressed="' + (n === i) + '">' + E(s[0]) + '</button>').join('');
    box.querySelector('.trace-body').innerHTML = '<h3>' + E(s[0]) + '</h3><p>' + E(s[1]) + '</p><p class="trace-status">核心边界：' + E(s[2]) + '</p>';
    box.querySelector('[data-trace-prev]').disabled = i === 0;
    box.querySelector('[data-trace-next]').disabled = i === steps.length - 1;
    box.querySelector('.trace-foot span').textContent = (i + 1) + ' / ' + steps.length;
    storage.set('request-trace', { branch, step: i });
  }
  box.querySelector('select').onchange = e => { branch = e.target.value; i = 0; draw(); };
  box.onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.traceStep !== undefined) i = Number(b.dataset.traceStep);
    else if (b.hasAttribute('data-trace-prev')) i--;
    else if (b.hasAttribute('data-trace-next')) i++;
    draw();
  };
  draw();
}

const labTimers = new Map(), labSaved = storage.get('lab-state', {}), labMotion = matchMedia('(prefers-reduced-motion: reduce)');
let labGeneration = 0;
function stopLearningAnimations() { labGeneration++; for (const stop of labTimers.values()) stop(); labTimers.clear(); }
function stepEdges(s) { return s.edges || (s.edge?.length ? [s.edge] : []); }
function cleanStepTitle(t) { return t.replace(/^(?:第\s*\d+\s*步[：:、.\s]*|\d+[.．、)）]\s*)+/, ''); }

async function mountLearningLabs() {
  const hosts = document.querySelectorAll('[data-learning-lab]');
  if (!hosts.length) { mountCalculators(); return; }
  const visuals = await ensureVisuals();
  for (const host of hosts) {
    const def = visuals.find(l => l.id === host.dataset.learningLab);
    if (!def) continue;
    const mount = host.querySelector('.lab-mount'), saved = labSaved[def.id] || {};
    let scenario = Math.max(0, def.scenarios.findIndex(s => s.id === saved.scene)), index = Math.min(Math.max(0, Number(saved.step) || 0), def.scenarios[scenario].steps.length - 1), playing = false, timer = null, gen = labGeneration;
    mount.innerHTML = '<div class="lab-controls"><label>推演场景 <select class="lab-scenario" aria-label="' + E(def.title) + '场景">' + def.scenarios.map((s, i) => '<option value="' + i + '">' + E(s.label) + '</option>').join('') + '</select></label><button class="lab-play">自动演示</button><label>步进间隔 <select class="lab-speed" aria-label="每步停留时长"><option value="4000">4 秒</option><option value="15000" selected>15 秒</option><option value="30000">30 秒</option></select></label><button class="lab-reset">回到起点</button></div><p class="lab-scenario-intro"></p><p class="lab-object-boundary" aria-live="polite"></p><div class="lab-stage"><section class="lab-visual" aria-label="当前流程与操作"><div class="lab-graphic" tabindex="0" aria-label="可滚动的教学流程图"></div><div class="lab-legend"><span class="key-current">当前活跃节点</span><span class="key-before">已流转节点</span><span>箭头代表数据流转或调用交接，非自动共享同一数据库事务</span></div><p class="lab-active-edge"></p><div class="lab-stepbar"><button class="lab-prev">上一步</button><input class="lab-range" type="range" min="0" value="0" aria-label="教学步骤"><output class="lab-position"></output><button class="lab-next">下一步</button></div><details class="lab-edge-list"><summary>查看全部流转边与分支条件</summary><div></div></details></section><section class="lab-explanation" aria-live="polite" aria-atomic="true" tabindex="0" aria-label="当前步骤解释与状态"></section></div><div class="lab-takeaways"><h3>核心设计要点</h3><ul>' + def.takeaways.map(s => '<li>' + E(s) + '</li>').join('') + '</ul></div><div class="lab-questions"><h3>场景推演自测</h3>' + def.questions.map((q, i) => '<fieldset><legend>' + E(q.q) + '</legend>' + q.options.map((o, j) => '<button data-question="' + i + '" data-answer="' + j + '">' + E(o) + '</button>').join('') + '<p class="lab-answer" data-feedback="' + i + '" aria-live="polite" hidden></p></fieldset>').join('') + '</div><p class="lab-source-note">交互式架构沙盒 · 点击图中节点或下方步骤条可随时切换状态切面。</p>';
    const find = s => mount.querySelector(s), scene = () => def.scenarios[scenario];
    find('.lab-scenario').value = scenario;
    function stop() { clearTimeout(timer); timer = null; playing = false; find('.lab-play').textContent = '自动演示'; find('.lab-play').setAttribute('aria-pressed', 'false'); mount.querySelectorAll('.flow-token').forEach(e => e.remove()); }
    labTimers.set(def.id, stop);
    function line(edge) {
      const a = def.nodes.find(n => n.id === edge.from), b = def.nodes.find(n => n.id === edge.to);
      const ax = 25 + a.col * 190, ay = 25 + a.row * 125, bx = 25 + b.col * 190, by = 25 + b.row * 125;
      let pts;
      if (a.col === b.col && Math.abs(a.row - b.row) === 1) { pts = [[ax + 79, ay + (b.row > a.row ? 62 : 0)], [bx + 79, by + (b.row > a.row ? 0 : 62)]]; }
      else if (a.col === b.col) { pts = [[ax + 158, ay + 31], [ax + 174, ay + 31], [bx + 174, by + 31], [bx + 158, by + 31]]; }
      else {
        const forward = b.col > a.col, x1 = ax + (forward ? 158 : 0), x2 = bx + (forward ? 0 : 158), y1 = ay + 31, y2 = by + 31, c1 = x1 + (forward ? 16 : -16), c2 = x2 + (forward ? -16 : 16);
        if (Math.abs(a.col - b.col) === 1) pts = [[x1, y1], [c1, y1], [c1, y2], [x2, y2]];
        else { const gutter = ay + (b.row < a.row ? -25 : 87); pts = [[x1, y1], [c1, y1], [c1, gutter], [c2, gutter], [c2, y2], [x2, y2]]; }
      }
      pts = pts.filter((p, i) => !i || p[0] !== pts[i - 1][0] || p[1] !== pts[i - 1][1]);
      let d = 'M' + pts[0].join(',');
      for (let i = 1; i < pts.length - 1; i++) {
        const p0 = pts[i - 1], p1 = pts[i], p2 = pts[i + 1], l1 = Math.hypot(p1[0] - p0[0], p1[1] - p0[1]), l2 = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]), r = Math.min(7, l1 / 2, l2 / 2);
        d += ' L' + [p1[0] - (p1[0] - p0[0]) * r / l1, p1[1] - (p1[1] - p0[1]) * r / l1].join(',') + ' Q' + p1.join(',') + ' ' + [p1[0] + (p2[0] - p1[0]) * r / l2, p1[1] + (p2[1] - p1[1]) * r / l2].join(',');
      }
      return d + ' L' + pts[pts.length - 1].join(',');
    }
    function latestStates() {
      let values = {}, lastObject = null;
      for (const s of scene().steps.slice(0, index + 1)) {
        if (lastObject && s.objectId && lastObject !== s.objectId) values = {};
        if (s.objectId) lastObject = s.objectId;
        for (const r of s.state) values[r.name] = r.after;
      }
      return values;
    }
    function graph(step) {
      const focused = document.activeElement?.closest?.('[data-node]')?.dataset.node, seen = new Set(scene().steps.slice(0, index).flatMap(s => s.active)), cur = new Set(step.active), activeEdges = new Set(stepEdges(step).map(e => e.join('>'))), state = latestStates(), prefix = 'lab-' + def.id, w = Math.max(...def.nodes.map(n => n.col)) * 190 + 210, h = Math.max(...def.nodes.map(n => n.row)) * 125 + 135;
      const labels = n => n.id === 'approval' ? '审批记录' : (step.nodeLabels?.[n.id] || n.label);
      let badgeHTML = ''; const shownFields = new Set();
      for (const n of def.nodes) {
        if (!n.dynamicFrom || (!cur.has(n.id) && n.id !== 'approval')) continue;
        let names = typeof n.dynamicFrom === 'string' ? [n.dynamicFrom] : Array.isArray(n.dynamicFrom) ? n.dynamicFrom : Object.values(n.dynamicFrom);
        names = names.filter(name => state[name] !== undefined && !shownFields.has(name));
        if (!names.length) continue;
        names.forEach(nm => shownFields.add(nm));
        badgeHTML += '<div class="object-badge"><strong>' + E(n.label.split('|')[0]) + '</strong>' + names.map(name => '<span>' + E(name) + ' = <b>' + E(state[name]) + '</b></span>').join('') + '</div>';
      }
      if (!badgeHTML) badgeHTML = '<div class="object-badge">' + step.state.slice(0, 3).map(r => '<span>' + E(r.name) + '：<b>' + E(r.after) + '</b></span>').join('') + '</div>';
      const paths = [...def.edges].sort((a, b) => Number(activeEdges.has(a.from + '>' + a.to)) - Number(activeEdges.has(b.from + '>' + b.to))).map(e => {
        const on = activeEdges.has(e.from + '>' + e.to), path = line(e);
        return '<g class="flow-edge ' + (on ? 'active' : '') + '"><path data-from="' + E(e.from) + '" data-to="' + E(e.to) + '" d="' + path + '" marker-end="url(#' + prefix + '-arrow)"/>' + (on && !labMotion.matches ? '<circle r="4.2" class="flow-token"><animateMotion dur="1.15s" path="' + path + '" fill="freeze"/></circle>' : '') + '<title>' + E(e.label) + '</title></g>';
      }).join('');
      const nodes = def.nodes.map(n => {
        const words = [];
        for (const part of labels(n).split('|')) {
          let acc = '', units = 0;
          for (const token of part.match(/[A-Za-z0-9_.]+|\s+|./gu) || []) {
            const cost = [...token].reduce((sum, c) => sum + (/[\u2e80-\uffef]/.test(c) ? 12 : 6.1), 0);
            if (units + cost > 136 && acc) { words.push(acc.trim()); acc = ''; units = 0; }
            acc += token; units += cost;
          }
          if (acc) words.push(acc.trim());
        }
        const used = scene().steps.some(s => s.active.includes(n.id)), lh = words.length > 3 ? 14 : 17;
        return '<g class="flow-node ' + (cur.has(n.id) ? 'is-current' : seen.has(n.id) ? 'is-seen' : '') + '" role="button" tabindex="' + (used ? 0 : -1) + '" aria-disabled="' + !used + '" data-node="' + E(n.id) + '" aria-label="' + E(labels(n).replace(/\|/g, ' ')) + '" transform="translate(' + (25 + n.col * 190) + ',' + (25 + n.row * 125) + ')"><rect width="158" height="62" rx="8"/>' + words.map((t, i) => '<text x="79" y="' + ((62 - (words.length - 1) * lh) / 2 + 4 + i * lh) + '" style="font-size:' + (words.length > 3 ? 10.5 : 12) + 'px" text-anchor="middle">' + E(t) + '</text>').join('') + '</g>';
      }).join('');
      const graphic = find('.lab-graphic'), oldTop = graphic.scrollTop, oldLeft = graphic.scrollLeft;
      graphic.innerHTML = '<div class="lab-state-badges" aria-live="polite">' + badgeHTML + '</div><svg viewBox="0 0 ' + w + ' ' + h + '" style="min-width:' + Math.min(w, 780) + 'px" role="group" aria-label="' + E(def.title + '；' + scene().label + '；' + cleanStepTitle(step.title)) + '"><defs><marker id="' + prefix + '-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10Z"/></marker></defs>' + paths + nodes + '</svg>';
      fitLearningLabLabels(graphic);
      graphic.scrollTop = oldTop; graphic.scrollLeft = oldLeft;
      const target = focused ? graphic.querySelector('[data-node="' + CSS.escape(focused) + '"]') : [...graphic.querySelectorAll('.flow-node.is-current')].at(-1);
      if (focused) target?.focus({ preventScroll: true });
      if (target) {
        const a = target.getBoundingClientRect(), v = graphic.getBoundingClientRect(), badge = graphic.querySelector('.lab-state-badges').offsetHeight;
        if (a.bottom > v.bottom - 12) graphic.scrollTop += a.bottom - v.bottom + 12;
        else if (a.top < v.top + badge + 8) graphic.scrollTop += a.top - v.top - badge - 8;
        if (a.right > v.right - 10) graphic.scrollLeft += a.right - v.right + 10;
        else if (a.left < v.left + 10) graphic.scrollLeft += a.left - v.left - 10;
      }
    }
    function draw(updateUrl = true) {
      const s = scene(), step = s.steps[index], object = step.objectId || s.objectId || '';
      find('.lab-scenario-intro').textContent = s.intro;
      const previous = index ? scene().steps[index - 1].objectId : null, oldER = previous?.match(/ER-\d+/)?.[0], newER = object.match(/ER-\d+/)?.[0], newExperiment = oldER && newER && oldER !== newER;
      find('.lab-object-boundary').textContent = object ? ((newExperiment ? '切换至新一轮独立实验 ' + newER + '（原 ' + oldER + ' 保留缺口状态）：' : '当前追踪对象：') + object) : '当前场景围绕同一上下文演进，可逐步对比状态字段变化';
      find('.lab-range').max = s.steps.length - 1; find('.lab-range').value = index;
      find('.lab-position').textContent = (index + 1) + ' / ' + s.steps.length;
      find('.lab-prev').disabled = index === 0; find('.lab-next').disabled = index === s.steps.length - 1;
      find('.lab-play').textContent = playing ? '暂停演示' : '自动演示';
      find('.lab-play').setAttribute('aria-pressed', String(playing));
      graph(step);
      const rows = step.state.map(r => '<tr><td>' + E(r.name) + '</td><td>' + E(r.before) + '</td><td>' + E(r.after) + '</td><td>' + E(r.why) + '</td></tr>').join('');
      const text = step.check + ' ' + step.process + ' ' + step.explain;
      const currentCh = chaptersCache.get(chapterId) || originalsCache.get(chapterId);
      let refs = (currentCh?.sources || []).filter(r => r.symbol && text.includes(r.symbol.split('.').at(-1)));
      if (!refs.length && /claim/.test(text)) refs = (currentCh?.sources || []).filter(r => r.symbol === 'ApprovalService.claim_execution');
      find('.lab-explanation').innerHTML = '<h3>第 ' + (index + 1) + ' 步：' + E(cleanStepTitle(step.title)) + '</h3><p>' + E(step.explain) + '</p><div class="lab-state-wrap"><table class="lab-state"><thead><tr><th>状态字段</th><th>变更前</th><th>变更后</th><th>变更原因</th></tr></thead><tbody>' + rows + '</tbody></table></div>' + (step.evidence?.length ? '<div class="evidence-cards">' + step.evidence.map(e => '<div><strong>' + E(e.id) + ' · ' + E(e.stage) + ' · ' + E(e.status) + '</strong><p>' + E(e.text) + '</p></div>').join('') + '</div>' : '') + '<dl class="lab-io"><div><dt>输入数据</dt><dd>' + E(step.input) + '</dd></div><div><dt>核心处理</dt><dd>' + E(step.process) + '</dd></div><div><dt>输出与状态流转</dt><dd>' + E(step.output) + '</dd></div></dl><aside class="lab-caution"><strong>架构边界提示</strong><p>' + E(step.pitfall) + '</p></aside><p class="lab-observe">源码与状态核查：' + E(step.check) + '</p>' + refs.slice(0, 2).map(r => '<button class="inline-source" data-source-key="' + E(r.key) + '">源码对照 · ' + E(r.symbol) + '</button>').join('');
      const names = stepEdges(step).map(pair => def.edges.find(e => e.from === pair[0] && e.to === pair[1])?.label).filter(Boolean);
      find('.lab-active-edge').textContent = names.length ? '当前流转：' + names.join(' → ') : '当前步骤在节点内部完成校验与状态更新';
      find('.lab-edge-list>div').innerHTML = def.edges.map(e => {
        const at = s.steps.findIndex(st => stepEdges(st).some(p => p[0] === e.from && p[1] === e.to));
        return '<button data-edge-step="' + at + '" ' + (at < 0 ? 'disabled' : '') + '>' + E(e.from + ' → ' + e.to + '：' + e.label) + (at < 0 ? '（本分支未触发）' : '') + '</button>';
      }).join('');
      host.dataset.scenario = s.id; host.dataset.step = index;
      labSaved[def.id] = { scene: s.id, step: index }; storage.set('lab-state', labSaved);
      if (updateUrl) updateReaderUrl({ lab: def.id, scene: s.id, step: index });
    }
    function advance() { if (gen !== labGeneration || !playing || document.hidden) { stop(); return; } if (index === scene().steps.length - 1) { stop(); return; } index++; draw(); timer = setTimeout(advance, Number(find('.lab-speed').value)); }
    function move(i) { stop(); index = Math.max(0, Math.min(scene().steps.length - 1, i)); draw(); }
    find('.lab-play').onclick = () => { if (playing) { stop(); return; } if (index === scene().steps.length - 1) index = 0; playing = true; draw(); timer = setTimeout(advance, Number(find('.lab-speed').value)); };
    find('.lab-prev').onclick = () => move(index - 1);
    find('.lab-next').onclick = () => move(index + 1);
    find('.lab-reset').onclick = () => move(0);
    find('.lab-range').oninput = e => move(Number(e.target.value));
    find('.lab-scenario').onchange = e => { stop(); scenario = Number(e.target.value); index = 0; draw(); };
    find('.lab-speed').onchange = () => { if (playing) { clearTimeout(timer); timer = setTimeout(advance, Number(find('.lab-speed').value)); } };
    find('.lab-graphic').onclick = e => { const node = e.target.closest('[data-node]'); if (!node) return; const at = scene().steps.findIndex(s => s.active.includes(node.dataset.node)); if (at >= 0) move(at); };
    find('.lab-graphic').onkeydown = e => { const n = e.target.closest('[data-node]'); if (n && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); n.dispatchEvent(new MouseEvent('click', { bubbles: true })); } };
    find('.lab-edge-list').onclick = e => { const b = e.target.closest('[data-edge-step]'); if (b && Number(b.dataset.edgeStep) >= 0) move(Number(b.dataset.edgeStep)); };
    find('.lab-questions').onclick = e => {
      const button = e.target.closest('[data-question]'); if (!button) return;
      const i = Number(button.dataset.question), q = def.questions[i], ok = Number(button.dataset.answer) === q.answer, feedback = find('[data-feedback="' + i + '"]');
      feedback.hidden = false; feedback.textContent = (ok ? '回答正确：' : '解析提示：') + q.explain; feedback.classList.toggle('correct', ok);
      button.closest('fieldset').querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
    };
    host.__restore = (sceneId, at) => { stop(); const n = def.scenarios.findIndex(s => s.id === sceneId); if (n >= 0) scenario = n; find('.lab-scenario').value = scenario; index = Math.min(Math.max(0, at), scene().steps.length - 1); draw(false); };
    draw(true);
  }
  mountCalculators();
}

document.addEventListener('visibilitychange', () => { if (document.hidden) for (const stop of labTimers.values()) stop(); });
labMotion.addEventListener('change', () => { for (const stop of labTimers.values()) stop(); });

function mountCalculators() {
  const r = document.getElementById('rrfCalculator');
  if (r) {
    r.innerHTML = '<p>拖动滑杆或切换词法检索列表，直观体验混合检索（Hybrid Search）中的 RRF（倒数排名融合）计分规则：</p><label>平滑常数 k <input type="range" min="1" max="100" value="60" aria-label="RRF平滑参数"><output>60</output></label><label>词法召回排序 <select aria-label="词法排序场景"><option value="0">A、C、B</option><option value="1">C、B（A 未命中）</option><option value="2">B、A、C</option></select></label><div class="calc-results" aria-live="polite"></div><p>RRF 不直接将向量相似度与 BM25 原始分数相加，而是按各自排名计算倒数贡献（未出现在某路召回时该路贡献为 0）。常数 k 越大，高排名与低排名的分差越平缓；若总分相同，则依次按最佳单路名次与 Chunk ID 稳定排序。</p>';
    function calc() {
      const k = Number(r.querySelector('input').value), dense = ['A', 'B', 'C'], lexical = [['A', 'C', 'B'], ['C', 'B'], ['B', 'A', 'C']][Number(r.querySelector('select').value)];
      r.querySelector('output').textContent = k;
      const rows = dense.map(id => { const d = dense.indexOf(id) + 1, l = lexical.indexOf(id) + 1; return { id, d, l, ds: 1 / (k + d), ls: l ? 1 / (k + l) : 0 }; }).sort((a, b) => (b.ds + b.ls) - (a.ds + a.ls) || Math.min(a.d, a.l || Infinity) - Math.min(b.d, b.l || Infinity) || a.id.localeCompare(b.id));
      r.querySelector('.calc-results').innerHTML = '<div class="lab-state-wrap"><table><thead><tr><th>融合排名 / 文档块</th><th>向量召回名次</th><th>词法召回名次</th><th>RRF 计分公式</th><th>融合总分</th></tr></thead><tbody>' + rows.map((x, i) => '<tr><td>#' + (i + 1) + ' · Chunk ' + x.id + '</td><td>第 ' + x.d + ' 名</td><td>' + (x.l ? '第 ' + x.l + ' 名' : '未命中') + '</td><td>1/(' + k + '+' + x.d + ') + ' + (x.l ? '1/(' + k + '+' + x.l + ')' : '0') + '</td><td>' + ((x.ds + x.ls).toFixed(6)) + '</td></tr>').join('') + '</tbody></table></div>';
      r.dataset.top = rows[0].id;
    }
    r.oninput = calc; r.onchange = calc; calc();
  }
  const m = document.getElementById('trialCalculator');
  if (m) {
    m.innerHTML = '<p>调整独立评测题数、重复采样次数与对比变体数，直观区分“题目分母”与“总执行单元（Trial / Case）”：</p><div class="calc-inputs"><label>独立题目数 <input type="number" min="1" max="200" value="20" aria-label="独立题目数"></label><label>每题重复次数 <input type="number" min="1" max="10" value="3" aria-label="每题重复次数"></label><label>对比变体数 <input type="number" min="1" max="5" value="2" aria-label="变体数"></label></div><div class="calc-results" aria-live="polite"></div><p>多次重复采样（Repetition）用于降低模型随机性，不会增加独立题目数（聚合时先在题内聚合重复结果，再跨变体配对比较）。例如客服评测集 20 道独立题 × 重复 3 次 = 单变体 60 次执行，评测报告分母始终锚定 20 道独立题。</p>';
    function calc() {
      const nums = [...m.querySelectorAll('input')].map(x => { const v = Number(x.value); return Number.isInteger(v) && v >= Number(x.min) && v <= Number(x.max) ? v : null; });
      const out = m.querySelector('.calc-results');
      if (nums.some(x => x === null)) { out.textContent = '请输入有效范围内的正整数。'; m.dataset.total = 'invalid'; return; }
      const [q, rCnt, v] = nums, total = q * rCnt * v; m.dataset.total = String(total);
      out.innerHTML = '<dl class="matrix-counts"><div><dt>独立题目数 (Items)</dt><dd>' + q + '</dd></div><div><dt>单变体执行次数</dt><dd>' + q + ' × ' + rCnt + ' = ' + q * rCnt + '</dd></div><div><dt>实验总执行单元 (Cases)</dt><dd>' + q + ' × ' + rCnt + ' × ' + v + ' = ' + total + '</dd></div></dl>';
    }
    m.oninput = calc; calc();
  }
}

function mountStorageRouter() {
  const box = document.getElementById('storageRouter'); if (!box) return;
  const objects = [
    { id: 'approval', name: '审批决定与执行状态', owner: 'PostgreSQL', why: '审批决定 (decision_status)、执行状态 (execution_status)、逻辑动作 ID 与 Run 绑定关系需要强一致事务与 CAS 条件更新保障。', flow: '人工审批 → ApprovalService → PostgreSQL 落库；Worker 恢复原 Run 并通过 CAS 认领执行权。', misread: 'Redis 队列消息仅负责触发调度，不代表获得执行授权；Qdrant 向量索引不参与权限与审批状态管理。' },
    { id: 'queue', name: '等待 Worker 消费的异步任务消息', owner: 'Redis / Celery broker', why: '解耦 API 请求响应与后台耗时执行；Worker 收到消息后必须回查 PostgreSQL 核验权威状态与租约。', flow: 'API / Beat 投递 → Redis Broker → Celery Worker 消费 → PostgreSQL 状态核验与业务执行。', misread: '收到队列消息不等于拿到独占执行权；Celery ACK 机制不能替代业务数据库层的幂等与 CAS 防重。' },
    { id: 'vector', name: '用于召回候选的知识向量与词法索引', owner: 'Qdrant', why: '专为高维向量与稀疏词法的高效近似召回设计；召回后的快照成员资格校验与正文组装仍以 PostgreSQL 为准。', flow: '文档分块 → 生成稠密向量/稀疏词频 → 写入 Qdrant；查询时先召回候选 ID → 回查 PostgreSQL 校验快照归属。', misread: '向量索引是可重建的检索投影，不能替代原始文档存储，检索命中也不等于最终通过上下文预算装入模型。' },
    { id: 'file', name: '上传文档（如 PDF）的原始文件字节', owner: 'LocalBlobStore', why: '原始二进制大文件适合通过 BlobStore 接口按内容哈希安全存储，供 API 与 Worker 进程共享读取。', flow: '上传文件流 → 写入临时文件 → flush/fsync/原子替换 → 生成受限 blob_key → 绑定 DocumentRevision。', misread: '代码中定义了 BlobStore 抽象契约以便未来扩展对象存储，当前默认实现为本地受限目录存储。' },
    { id: 'checkpoint', name: 'LangGraph 状态图断点 (Checkpoint)', owner: 'PostgreSQL / 框架 schema', why: '保存状态图在 interrupt 挂起时的节点位置与通道状态，按 workspace_id + run_id 唯一定位恢复点。', flow: '工具审批触发 interrupt → 写入 LangGraph Checkpoint 表 → 审批通过后加载原断点继续执行同一 Run。', misread: '虽然与业务表同处 PostgreSQL，但框架 Checkpoint 表与业务表分属不同 Schema 与写入通道，部署时由独立脚本初始化。' },
    { id: 'memory', name: '长期记忆条目与运行期冻结快照', owner: 'PostgreSQL', why: '长期记忆需支持按工作区隔离、精确状态管理、哈希校验与审计追溯，直接存储在 PostgreSQL 关系表中。', flow: 'Run 完成触发异步抽取 → 落库 Memory 记录 → 新 Run 召回并冻结候选列表 → 预算裁剪装入上下文 → 记录 Touch 事件。', misread: '记录 TOUCH 事件仅代表该条记忆被装入模型请求，不直接证明模型在生成最终回答时必然采纳了该记忆。' }
  ];
  const faults = [
    ['none', '正常运行态（架构分工）', '四类存储各司其职：PostgreSQL 管权威事实，Redis 管异步派发，Qdrant 管候选召回，BlobStore 管原始文件。'],
    ['pg', '模拟故障：PostgreSQL 不可用', '权威业务事实无法读写，认证授权、版本解析、审批认领与 Run 状态流转全部阻断。即使 Redis 或 Qdrant 正常，系统也绝不跳过数据库权限与状态校验强行派发动作。'],
    ['redis', '模拟故障：Redis 不可用', '异步任务投递与 Worker 队列消费受阻；但已落库 PostgreSQL 的 Run、Turn 与审批事实不会丢失，待队列恢复后可依据数据库状态与租约安全恢复调度。'],
    ['qdrant', '模拟故障：Qdrant 不可用', '知识库向量召回与新文档建索引受阻；PostgreSQL 中的业务元数据与审批记录依然完好，但依赖知识检索的 Run 会按检索异常链路优雅报错。'],
    ['blob', '模拟故障：Blob 原文件不可读', '新上传文档的解析入库与原文预览失败；已解析落库到 PostgreSQL 的文本块（Chunks）仍可查询，但原文件字节流需从备份恢复。']
  ];
  box.innerHTML = '<div class="storage-controls"><label>选择数据对象<select aria-label="选择数据对象">' + objects.map((x, i) => '<option value="' + i + '">' + E(x.name) + '</option>').join('') + '</select></label><label>模拟运行工况<select aria-label="选择存储故障">' + faults.map((x, i) => '<option value="' + i + '">' + E(x[1]) + '</option>').join('') + '</select></label></div><div class="storage-map" role="group" aria-label="四类存储职责"><span data-store="PostgreSQL">PostgreSQL<small>权威业务事实与断点</small></span><span data-store="Redis">Redis<small>异步任务派发队列</small></span><span data-store="Qdrant">Qdrant<small>向量与词法检索索引</small></span><span data-store="LocalBlobStore">LocalBlobStore<small>原始文档字节存储</small></span></div><div class="storage-output" aria-live="polite"></div>';
  function draw() {
    const sels = box.querySelectorAll('select'), o = objects[Number(sels[0].value)], f = faults[Number(sels[1].value)];
    box.dataset.owner = o.owner; box.dataset.fault = f[0];
    box.querySelectorAll('[data-store]').forEach(s => s.classList.toggle('selected', o.owner.startsWith(s.dataset.store)));
    box.querySelector('.storage-output').innerHTML = '<h3>' + E(o.name) + ' · 归属存储：' + E(o.owner) + '</h3><dl><div><dt>架构选型理由</dt><dd>' + E(o.why) + '</dd></div><div><dt>读写数据流</dt><dd>' + E(o.flow) + '</dd></div><div><dt>' + E(f[1]) + '</dt><dd>' + E(f[2]) + '</dd></div><div><dt>常见认知误区</dt><dd>' + E(o.misread) + '</dd></div></dl>';
  }
  box.onchange = draw; draw();
}

function mountErrorRouter() {
  const box = document.getElementById('errorRouter'); if (!box) return;
  const cases = [
    { label: '幂等冲突：复用同一 client_token 却篡改了请求正文', input: '客户端首次发送 token=A、正文=“排查延迟原因”；随后仍用 token=A 重发，但正文改为“立即执行回滚”，此时 HTTP 响应尚未开始。', answer: 0, flow: ['ThreadService 校验 input_hash 不一致', '抛出 THREAD_TURN_IDEMPOTENCY_CONFLICT', '全局异常处理器映射为 HTTP 409', '前端解析统一错误信封并提示冲突'], why: '同一幂等 Token 代表同一次逻辑提交，绝不允许静默篡改为另一个业务问题。由于尚未开启流式传输，直接通过标准 HTTP 409 错误信封拦截。', retry: '若要发起新问题，客户端必须生成新的 client_token；若仅是网络超时重发原问题，必须保持请求正文完全一致。', observe: '核查 HTTP 409 状态码、error.code 与服务端 request_id。' },
    { label: '参数校验失败：请求体不符合接口 Schema', input: '客户端提交的 JSON 缺少必填字段或类型不合法，尚未进入路由核心业务逻辑。', answer: 0, flow: ['Pydantic 请求模型验证失败', '触发 RequestValidationError 处理器', '返回 HTTP 422 / VALIDATION_ERROR', '前端展示结构化输入错误提示'], why: '入参格式错误在最外层契约校验直接拦截并返回 HTTP 422，不会向下污染业务服务或创建无效 Run。', retry: '修正请求参数后再提交，无需对同一错误入参做盲目重试。', observe: '核查 HTTP 422 响应信封；此时数据库中尚未产生任何业务 Run 记录。' },
    { label: '未预期内部异常：HTTP 响应尚未开始前发生崩溃', input: '路由处理过程中抛出未被特定业务分支捕获的异常，此时尚未向客户端发送响应头。', answer: 0, flow: ['异常冒泡至统一入口处理器', 'logger.exception 记录完整堆栈日志', '返回 HTTP 500 / INTERNAL_ERROR', '向客户端返回安全脱敏的通用错误提示'], why: '对外隐藏内部堆栈细节以保障安全，同时在服务端结构化日志中保留 request_id 与完整异常上下文供排障。', retry: '不能见 500 就无脑重试；需先根据 request_id 与持久层记录确认失败发生在哪一步、是否已触发外部副作用。', observe: '对照服务端结构化日志中的 request_id、异常堆栈及 PostgreSQL 业务表状态。' },
    { label: '流式中断：SSE 已建立且网关已吐出首包后模型流超时', input: 'HTTP 200 text/event-stream 已建立，ModelGateway 已向 Runtime 交付 MESSAGE_DELTA 或 TOOL_CALL_DELTA，随后上游模型流中断。', answer: 1, flow: ['网关在 visible=true 之后捕获流异常', '抛出 MODEL_STREAM_INTERRUPTED', 'Runtime 写入失败事件并推进 Run 状态', '客户端通过 SSE 终止事件感知并回查原 Run'], why: 'HTTP 200 响应头与部分流式数据已经发出，协议上无法再改写为 HTTP 500 JSON，必须走 SSE 流式生命周期与 Run 状态机收尾。', retry: '严禁在已吐出可见片段后静默切换备用模型拼接输出！客户端断线重连时应附着回原 Run 查看已落库事件，而非盲目新建 Run。', observe: '核查 SSE 事件流、Run 持久状态及事件游标（注意区分 Runtime 内部累积的工具片段与发往浏览器的 TOOL_REQUESTED 事件）。' },
    { label: '副作用未知：外部写操作已越过派发边界但丢失回执', input: 'REST 或 MCP 写工具请求已发往远端服务，但因网络超时或连接断开，本地未收到明确的成功或失败回执。', answer: 2, flow: ['执行器判定远端执行结局不可确认', '动作与审批执行状态标记为 UNKNOWN_OUTCOME', 'Run 状态映射为 NEEDS_ATTENTION', '冻结现场证据并转交人工核查'], why: '外部系统的写操作无法靠本地数据库回滚撤销。一旦请求越过派发边界且回执丢失，必须如实标记为“结果未知”，绝不能当成普通失败自动重发。', retry: '严禁自动重试或更换动作 ID 绕过防重！必须由运维或业务人员核查远端系统真实状态后，按人工规程处置。', observe: '核查逻辑动作 ID、派发审计记录、Approval.execution_status (UNKNOWN_OUTCOME) 与 Run.status (NEEDS_ATTENTION)。' }
  ];
  box.innerHTML = '<p>阅读下方故障发生时的上下文与阶段边界，判断系统应当走哪条异常处理通路：</p><label>选择故障场景<select aria-label="异常推演案例">' + cases.map((c, i) => '<option value="' + i + '">' + E(c.label) + '</option>').join('') + '</select></label><p class="error-case"></p><div class="error-answers" role="group" aria-label="预测异常处理通路"><button data-route-answer="0">标准 HTTP 错误信封</button><button data-route-answer="1">SSE 流式事件与生命周期收尾</button><button data-route-answer="2">持久化 UNKNOWN_OUTCOME 并转人工核查</button></div><div class="error-feedback" aria-live="polite" hidden></div>';
  let index = 0;
  function reset() { box.querySelector('.error-case').textContent = cases[index].input; box.querySelector('.error-feedback').hidden = true; box.querySelectorAll('[data-route-answer]').forEach(b => b.setAttribute('aria-pressed', 'false')); box.dataset.case = String(index); }
  box.querySelector('select').onchange = e => { index = Number(e.target.value); reset(); };
  box.querySelector('.error-answers').onclick = e => {
    const b = e.target.closest('[data-route-answer]'); if (!b) return;
    const c = cases[index], right = Number(b.dataset.routeAnswer) === c.answer;
    box.querySelectorAll('[data-route-answer]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    const f = box.querySelector('.error-feedback'); f.hidden = false; f.dataset.correct = String(right);
    f.innerHTML = '<h3>' + (right ? '判断准确' : '建议先确认响应阶段与外部副作用边界') + '</h3><p>' + E(c.why) + '</p><ol class="error-path">' + c.flow.map(s => '<li>' + E(s) + '</li>').join('') + '</ol><dl><div><dt>重试策略</dt><dd>' + E(c.retry) + '</dd></div><div><dt>排障核查点</dt><dd>' + E(c.observe) + '</dd></div></dl>';
  };
  reset();
}

let readerDepth = storage.get('depth', 'intro'), readerRestoring = false, readerBoot = true, readerSection = '', sourceReturnFocus = null;
function remember(route, scope) {
  current = route; currentScope = scope || 'all'; active();
  const q = new URLSearchParams({ view: route, scope: currentScope });
  if (route === 'learn') { q.set('chapter', chapterId); q.set('depth', readerDepth); }
  const hash = '#' + q;
  if (readerBoot || readerRestoring) history.replaceState(null, '', hash);
  else if (location.hash !== hash) history.pushState(null, '', hash);
}
function updateReaderUrl(values, push = false) {
  if (current !== 'learn') return;
  const q = new URLSearchParams(location.hash.slice(1));
  for (const [k, v] of Object.entries(values)) {
    if (v === null || v === undefined || v === '') q.delete(k);
    else q.set(k, String(v));
  }
  const hash = '#' + q;
  if (hash !== location.hash) history[push ? 'pushState' : 'replaceState'](null, '', hash);
}

async function list() {
  const q = $('bookSearch').value.trim().toLowerCase();
  const pool = library === 'curriculum' ? manifest.chapters : manifest.originals;
  if (q && !searchIndexCache) {
    await ensureSearchIndex();
    if ($('bookSearch').value.trim().toLowerCase() !== q) return;
  }
  const searchMap = searchIndexCache ? searchIndexCache[library === 'curriculum' ? 'chapters' : 'originals'] : null;
  let lastCategory = '', count = 0;
  $('chapterList').innerHTML = pool.map((c, i) => {
    const haystack = (searchMap?.[c.id] || (c.title + ' ' + c.nav + ' ' + c.summary)).toLowerCase();
    if (q && !haystack.includes(q)) return '';
    count++;
    const category = library === 'originals' ? c.category : (c.reference ? '专题进阶 · 按需查阅' : '核心主线');
    let label = '';
    if (category !== lastCategory) { lastCategory = category; label = '<div class="category">' + E(category) + '</div>'; }
    return label + '<button data-chapter="' + E(c.id) + '" title="' + E(c.title) + '" class="' + (c.id === chapterId ? 'active' : '') + '" ' + (c.id === chapterId ? 'aria-current="page"' : '') + '><span class="chapter-number">' + (library === 'curriculum' ? String(i + 1).padStart(2, '0') : '文') + '</span><span>' + E(c.nav || c.title) + '</span>' + (read.has(c.id) ? '<span class="check" aria-label="已读">✓</span>' : '') + '</button>';
  }).join('') || '<p class="empty">没有找到相关内容，试试问题或函数名。</p>';
  $('chapterList').setAttribute('aria-label', (q ? '搜索结果 ' + count + ' 篇：' : '') + (library === 'curriculum' ? '学习目录' : '实测与复盘目录'));
  $('tabCurriculum').setAttribute('aria-pressed', String(library === 'curriculum'));
  $('tabOriginals').setAttribute('aria-pressed', String(library === 'originals'));
  $('libraryHint').hidden = library !== 'originals';
}

function preservePosition() {
  if (current === 'learn' && bookMounted) {
    positions[chapterId + '|' + readerDepth] = $('bookScroll').scrollTop;
    storage.set('positions', positions);
  }
}

function sourceButtons(c) {
  return c.sources?.length ? '<section class="source-list"><h2>本章源码索引</h2><p>点击正文中的“源码对照”按钮可在侧栏就近阅读核心实现；下方汇总了本章涉及的全部源码快照与行号索引。</p>' + c.sources.map((s, i) => '<button data-source="' + i + '"><strong>' + E(s.path) + (s.symbol ? ' · ' + E(s.symbol) : '') + '</strong><small>' + E(s.reason) + '</small></button>').join('') + '</section>' : '';
}

function introBody(c) {
  if (!c.lesson) return c.html;
  let prerequisite = E(c.lesson.prerequisite);
  for (const chapter of manifest.chapters) {
    prerequisite = prerequisite.replace(new RegExp('\\b' + chapter.id + '\\b', 'g'), '<button data-chapter="' + chapter.id + '">' + E(chapter.nav) + '</button>');
  }
  const guide = '<section class="lesson-orientation"><p><strong>前置章节：</strong>' + prerequisite + '</p><p><strong>核心问题：</strong>' + E(c.lesson.goal) + '</p><p><strong>学完自测：</strong>' + E(c.lesson.deliverable) + '</p><p class="case-transition">' + E(c.lesson.caseNote) + '</p></section>';
  let content = c.lesson.html;
  const first = content.indexOf('</p>');
  content = first >= 0 ? content.slice(0, first + 4) + guide + content.slice(first + 4) : guide + content;
  return content + '<section class="recall-card"><h2>动手思考与自测</h2><p>' + E(c.lesson.question.q) + '</p><details><summary>查看思路提示</summary><p>' + E(c.lesson.question.hint) + '</p></details><details class="exercise-answer"><summary>展开参考解析与源码依据</summary><p>' + E(c.lesson.question.answer) + '</p><button data-chapter="' + E(c.lesson.question.returnTo || c.id) + '" data-deep-link="true">深入源码核查实现</button></details></section><p class="depth-invitation">以上是本章的通俗主线导读。如需剖析底层状态机、并发边界、完整源码与交互沙盒，请切换至“深入源码”模式。</p><button class="open-deep">进入深入源码与交互推演</button>';
}

async function openChapter(id, anchor, fromClick = false) {
  if (Object.hasOwn(manifest.chapterAliases, id)) { id = manifest.chapterAliases[id]; anchor = null; }
  const validChap = manifest.chapters.some(x => x.id === id);
  const validOrig = manifest.originals.some(x => x.id === id);
  if (!validChap && !validOrig) id = 'start';
  if (current === 'learn') preservePosition();
  closeSourcePanel(false);
  chapterId = id;
  library = validOrig ? 'originals' : 'curriculum';
  const ownTicket = ++ticket;
  pauseFrames();
  $('resources').hidden = true;
  $('loading').hidden = true;
  $('learning').hidden = false;
  remember('learn');
  storage.set('chapter', id);
  list();
  progress();
  $('depthMode').value = readerDepth;
  $('depthMode').disabled = library === 'originals';

  if (!chaptersCache.has(id) && !originalsCache.has(id)) {
    $('chapterArticle').innerHTML = '<p style="color:#687c75;padding:32px 0;">正在按需加载本章节内容…</p>';
  }
  const c = await ensureChapter(id);
  if (ownTicket !== ticket) return;

  const idx = manifest.chapters.findIndex(x => x.id === c.id);
  const intro = readerDepth === 'intro' && c.lesson;
  let body = intro ? introBody(c) : (c.lesson ? '<p class="case-transition deep-case-note"><strong>本章场景主线：</strong>' + E(c.lesson.caseNote) + '</p>' : '') + c.html;
  if (c.discussion) {
    body += '<section class="recall-card"><h2>面试追问</h2>' + c.discussion.map(item =>
      '<details><summary>' + E(item.question) + '</summary><p>' + E(item.answer) + '</p></details>'
    ).join('') + '</section>';
  }
  const plain = body.replace(/<[^>]*>/g, '').length, mins = Math.max(1, Math.round(plain / 420));
  $('chapterPosition').textContent = idx >= 0 ? (c.reference ? '专题进阶' : '核心主线') + ' · ' + (intro ? '通俗导读' : '深入源码') : '实测与复盘 · ' + c.category;
  $('chapterArticle').innerHTML = '<header><div class="lesson-label"><span>' + (idx >= 0 ? 'AgentHub 架构精读' : '专题记录') + '</span><span>约 ' + mins + ' 分钟阅读</span></div><h1>' + E(intro ? c.lesson.title : c.title) + '</h1><p class="chapter-summary">' + E(intro ? c.lesson.summary : c.summary) + '</p></header>' + body + (intro ? '' : sourceButtons(c));

  const art = $('chapterArticle');
  art.querySelectorAll('img[data-asset]').forEach(img => {
    const file = manifest.assetFiles[img.dataset.asset];
    if (file) { img.loading = 'lazy'; img.src = window.archiveMedia?.[file] || './assets/media/' + file; }
  });
  art.querySelectorAll('table').forEach(table => {
    if (table.parentElement.classList.contains('table-wrap')) return;
    const wrap = document.createElement('div');
    wrap.className = 'table-wrap';
    table.before(wrap);
    wrap.append(table);
  });

  if (c.id === 'start' && !intro) mountTrace();
  await mountLearningLabs();
  if (ownTicket !== ticket) return;
  mountStorageRouter();
  mountErrorRouter();
  mountBusinessLanes();
  mountMastery();
  await enhanceLearningContent(art);
  if (ownTicket !== ticket) return;

  const hs = [...art.querySelectorAll('h2,h3')].filter(h => !h.closest('.lab-mount') && !h.closest('details.exercise-answer'));
  hs.forEach((h, i) => { if (!h.id) h.id = 'section-' + i; });
  $('chapterToc').innerHTML = '<strong>本章' + (intro ? '导读' : '目录') + '</strong>' + hs.map(h => '<a class="' + (h.tagName === 'H3' ? 'toc-sub' : '') + '" href="#' + E(h.id) + '" data-section="' + E(h.id) + '">' + E(h.textContent) + '</a>').join('');
  art.querySelectorAll('.open-deep').forEach(b => b.onclick = () => setDepth('deep'));
  tocObserver?.disconnect();
  tocObserver = new IntersectionObserver(entries => {
    for (const e of entries) if (e.isIntersecting) $('chapterToc').querySelectorAll('a').forEach(a => a.classList.toggle('active', a.dataset.section === e.target.id));
  }, { root: $('bookScroll'), rootMargin: '-8% 0px -72% 0px' });
  hs.forEach(h => tocObserver.observe(h));

  $('prevChapter').disabled = idx <= 0;
  $('nextChapter').disabled = idx < 0 || idx >= manifest.chapters.length - 1;
  $('prevChapter').onclick = () => openChapter(manifest.chapters[idx - 1].id, null, true);
  $('nextChapter').onclick = () => openChapter(manifest.chapters[idx + 1].id, null, true);
  $('bookScroll').scrollTop = fromClick ? 0 : (positions[c.id + '|' + readerDepth] || 0);
  bookMounted = true;
  if (anchor) jumpSection(anchor, false);
  if (fromClick) {
    $('learning').classList.remove('menu-open');
    $('toggleBookMenu').setAttribute('aria-expanded', 'false');
    $('bookScroll').focus({ preventScroll: true });
  }
  resize();
}

function setDepth(depth) {
  if (depth === readerDepth) return;
  preservePosition();
  readerDepth = depth;
  storage.set('depth', depth);
  bookMounted = false;
  openChapter(chapterId);
  updateReaderUrl(depth === 'intro' ? { depth, section: null, lab: null, scene: null, step: null } : { depth, section: null }, false);
}

function jumpSection(id, push = true) {
  const target = $('chapterArticle').querySelector('#' + CSS.escape(id));
  if (!target) return;
  target.scrollIntoView({ block: 'start' });
  readerSection = id;
  const lab = target.closest('[data-learning-lab]');
  updateReaderUrl({ section: id, lab: lab?.dataset.learningLab || null, scene: lab?.dataset.scenario || null, step: lab?.dataset.step ?? null }, push);
}

async function sourceView(key, lines = 20, offset = 0) {
  const s = await ensureSource(key);
  if (!s) return;
  for (const stop of labTimers.values()) stop();
  sourceReturnFocus = document.activeElement;
  const anchor = sourceReturnFocus && $('bookScroll').contains(sourceReturnFocus) ? sourceReturnFocus : null, oldY = anchor?.getBoundingClientRect().top;
  const wide = innerWidth >= 1400;
  const title = s.path + (s.symbol ? ' · ' + s.symbol : '');
  const text = s.text.split('\n'), slice = text.slice(offset, offset + lines).join('\n');
  if (wide) {
    $('sourcePanelTitle').textContent = title;
    $('sourcePanelMeta').textContent = '本地源码快照 · SHA-256 ' + s.sha256 + (s.truncated ? ' · 节选核心片段，可点击下方按钮展开完整快照' : '');
    $('sourcePanelCode').textContent = slice;
    $('sourcePanel').hidden = false;
    document.querySelector('.reading-area').classList.add('source-open');
    if (anchor) $('bookScroll').scrollTop += anchor.getBoundingClientRect().top - oldY;
    $('sourceExpand').textContent = '查看完整摘录';
    $('sourceExpand').onclick = () => { $('sourcePanelCode').textContent = s.text; $('sourceExpand').disabled = true; };
    $('sourceExpand').disabled = false;
    $('sourcePanelClose').focus({ preventScroll: true });
  } else {
    $('sourceTitle').textContent = title;
    $('sourceMeta').textContent = s.kind + '；SHA-256 ' + s.sha256 + (s.truncated ? '；带行号源码节选' : '');
    $('sourceCode').textContent = s.text;
    $('sourceDialog').showModal();
  }
}

function showSource(index) {
  const c = chaptersCache.get(chapterId) || originalsCache.get(chapterId);
  const ref = c?.sources?.[index];
  if (ref) sourceView(ref.key, 20, ref.inlineOffset || 0);
}

function closeSourcePanel(returnFocus = true) {
  if (!$('sourcePanel') || $('sourcePanel').hidden) return;
  const anchor = sourceReturnFocus?.isConnected ? sourceReturnFocus : null, oldY = anchor?.getBoundingClientRect().top;
  $('sourcePanel').hidden = true;
  document.querySelector('.reading-area').classList.remove('source-open');
  if (anchor && returnFocus) $('bookScroll').scrollTop += anchor.getBoundingClientRect().top - oldY;
  if (returnFocus && anchor) anchor.focus({ preventScroll: true });
}

function mountMastery() {
  const host = document.getElementById('masteryChecklist'); if (!host) return;
  const saved = storage.get('mastery', {});
  host.innerHTML = '<h2>核心主线掌握度自查清单</h2><p>勾选你已能独立讲清的架构环节（进度自动保存在本地浏览器），遇到模糊处可一键跳回对应章节复盘。</p>' + manifest.chapters.filter(c => !c.reference).map(c => '<label><input type="checkbox" data-mastery="' + E(c.id) + '" ' + (saved[c.id] ? 'checked' : '') + '><span>' + E(c.deliverable || c.summary) + ' <button data-chapter="' + E(c.id) + '">回到本章</button></span></label>').join('');
  host.onchange = e => { if (e.target.dataset.mastery) { saved[e.target.dataset.mastery] = e.target.checked; storage.set('mastery', saved); } };
}

function mountBusinessLanes() {
  const host = document.getElementById('businessLanes'); if (!host || !manifest.businessLanes) return;
  host.innerHTML = '<h2>三条并列业务闭环，各司其职</h2><p>一次会话执行结束后，结果归档、数据集迭代与人工坐席接管是三条彼此独立的业务链路，按需触发且互不篡改原 Run 记录：</p>' + manifest.businessLanes.lanes.map(l => '<section class="business-lane"><h3>' + E(l.title) + '</h3><ol>' + l.steps.map(s => '<li>' + E(s) + '</li>').join('') + '</ol><p>' + E(l.explain) + '</p></section>').join('') + '<h3>人工接管案件 (HandoffCase) 的认领与流转</h3><div class="handoff-links">' + manifest.businessLanes.handoff.edges.map(e => '<p><strong>' + E(e.from) + ' → ' + E(e.to) + '</strong><span>' + E(e.label) + '</span></p>').join('') + '</div><p>注：关闭人工案件仅代表线下协同流程办结，不会将原 Run 中结果未知的外部写操作（UNKNOWN_OUTCOME）自动改写为成功。</p>';
}

async function setupReader() {
  const q = new URLSearchParams(location.hash.slice(1));
  readerDepth = q.get('depth') || storage.get('depth', 'intro');
  if (q.has('lab')) readerDepth = 'deep';
  if (!['intro', 'deep'].includes(readerDepth)) readerDepth = 'intro';
  document.body.classList.toggle('large-type', storage.get('large', false));
  $('fontSize').setAttribute('aria-pressed', String(storage.get('large', false)));
  $('fontSize').textContent = storage.get('large', false) ? '标准字号' : '大字阅读';
  $('depthMode').onchange = e => setDepth(e.target.value);
  $('readingLayout').value = storage.get('layout', 'wide');
  document.body.classList.toggle('compact-reading', $('readingLayout').value === 'compact');
  $('readingLayout').onchange = e => { document.body.classList.toggle('compact-reading', e.target.value === 'compact'); storage.set('layout', e.target.value); };
  $('sourcePanelClose').onclick = () => closeSourcePanel();
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('sourcePanel').hidden) { e.preventDefault(); closeSourcePanel(); } });
  document.addEventListener('click', e => {
    const inline = e.target.closest('[data-source-key]');
    if (inline) { e.preventDefault(); e.stopImmediatePropagation(); sourceView(inline.dataset.sourceKey, 20, Number(inline.dataset.sourceOffset || 0)); return; }
    const snap = e.target.closest('a[data-snapshot]');
    if (snap) { e.preventDefault(); e.stopImmediatePropagation(); sourceView(snap.dataset.snapshot); return; }
    const sect = e.target.closest('a[data-section]');
    if (sect) { e.preventDefault(); e.stopImmediatePropagation(); jumpSection(sect.dataset.section, true); return; }
    const deep = e.target.closest('[data-deep-link]');
    if (deep) { e.preventDefault(); e.stopImmediatePropagation(); readerDepth = 'deep'; storage.set('depth', 'deep'); openChapter(deep.dataset.chapter, null, true); }
  }, true);
  window.addEventListener('popstate', async () => {
    const pq = new URLSearchParams(location.hash.slice(1));
    readerRestoring = true; readerDepth = pq.get('depth') || 'intro';
    if ((pq.get('view') || 'learn') === 'learn') {
      await openChapter(pq.get('chapter') || 'start', pq.get('section'));
      restoreLinkedLab(pq);
    } else await window.archiveNavigate(pq.get('view'), pq.get('scope') || 'all');
    readerRestoring = false;
  });
  chapterId = q.get('chapter') || storage.get('chapter', 'start');
  resize();
  if (q.get('view') && q.get('view') !== 'learn') await window.archiveNavigate(q.get('view'), q.get('scope') || 'all');
  else {
    await openChapter(chapterId, q.get('section'));
    restoreLinkedLab(q);
  }
  readerBoot = false;
}

function restoreLinkedLab(q) {
  const id = q.get('lab'); if (!id) return;
  const host = document.querySelector('[data-learning-lab="' + CSS.escape(id) + '"]');
  if (!host) return;
  host.__restore?.(q.get('scene'), Number(q.get('step') || 0));
  updateReaderUrl({ lab: id, scene: host.dataset.scenario, step: host.dataset.step });
  host.scrollIntoView({ block: 'start' });
}

let diagramInstance = 0;
function fitLearningLabLabels(graphic) {
  for (const node of graphic.querySelectorAll('.flow-node')) {
    const available = Number(node.querySelector('rect')?.getAttribute('width') || 158) - 16;
    for (const line of node.querySelectorAll('text:not(:has(tspan)), text tspan')) {
      if (line.getComputedTextLength() > available) {
        line.setAttribute('textLength', available);
        line.setAttribute('lengthAdjust', 'spacingAndGlyphs');
      }
    }
  }
}

const highlightedSources = new WeakMap();
const languageNames = { python: 'Python', py: 'Python', javascript: 'JavaScript', js: 'JavaScript', typescript: 'TypeScript', ts: 'TypeScript', json: 'JSON', sql: 'SQL', bash: 'Shell', sh: 'Shell', shell: 'Shell', powershell: 'PowerShell', ps1: 'PowerShell', yaml: 'YAML', yml: 'YAML', html: 'HTML', xml: 'XML', css: 'CSS', dockerfile: 'Dockerfile', text: '文本', plaintext: '文本', http: 'HTTP', toml: 'TOML', ini: '配置' };

function copyLearningText(text, button) {
  const original = button.textContent;
  const done = () => { button.textContent = '已复制'; setTimeout(() => { if (button.isConnected) button.textContent = original; }, 1500); };
  const fallback = () => {
    const field = document.createElement('textarea'); field.value = text; field.style.cssText = 'position:fixed;opacity:0';
    document.body.append(field); field.select(); let ok = false;
    try { ok = document.execCommand('copy'); } finally { field.remove(); button.focus({ preventScroll: true }); }
    if (ok) done(); else button.textContent = '复制失败，请选择文字复制';
  };
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(done, fallback); else fallback();
}

function inferCodeLanguage(text) {
  if (/^\s*(?:async\s+def |def |from \w+ import |import (?:asyncio|json|uuid)|class \w+.*:)/m.test(text)) return 'python';
  if (/^\s*(?:SELECT |CREATE TABLE |INSERT INTO |UPDATE \w+ SET)/mi.test(text)) return 'sql';
  if (/^\s*(?:curl |pip |python |npm |docker |\$ )/m.test(text)) return 'bash';
  if (/^\s*[\[{][\s\S]*[\]}]\s*$/.test(text)) { try { JSON.parse(text); return 'json'; } catch {} }
  return 'plaintext';
}

function highlightLearningCode(code, language) {
  const raw = code.textContent, hl = window.learningHighlighter;
  const lang = hl?.getLanguage(language) ? language : 'plaintext';
  code.classList.add('hljs'); code.dataset.codeLanguage = lang;
  code.innerHTML = lang === 'plaintext' ? E(raw) : hl.highlight(raw, { language: lang, ignoreIllegals: true }).value;
  return raw;
}

async function enhanceLearningContent(root) {
  for (const pre of root.querySelectorAll('pre:not(.mermaid)')) {
    if (!pre.querySelector('code')) { const code = document.createElement('code'); code.textContent = pre.textContent; pre.replaceChildren(code); }
  }
  const hasMermaid = root.querySelector('pre.mermaid');
  const diagrams = hasMermaid ? await ensureDiagrams() : null;
  for (const code of root.querySelectorAll('pre > code,pre.mermaid')) {
    const pre = code.matches('pre') ? code : code.parentElement;
    if (pre.dataset.learningEnhanced) continue;
    const raw = code.textContent, match = (code.className + ' ' + pre.className).match(/(?:language-|lang-)([\w+-]+)/);
    const lang = pre.classList.contains('mermaid') ? 'mermaid' : match?.[1]?.toLowerCase() || inferCodeLanguage(raw);
    pre.dataset.learningEnhanced = 'true';
    if (lang === 'mermaid') {
      const entry = diagrams?.[raw.trim()];
      if (!entry?.svg) { pre.dataset.renderError = 'missing'; continue; }
      const figure = document.createElement('figure'); figure.className = 'learning-diagram'; figure.setAttribute('aria-label', '可放大的流程图');
      const header = document.createElement('figcaption'); header.className = 'diagram-toolbar'; header.innerHTML = '<span>流程图</span><button type="button" class="diagram-open">放大查看</button>';
      const canvas = document.createElement('div'); canvas.className = 'diagram-preview'; canvas.innerHTML = entry.svg.replaceAll(entry.prefix, entry.prefix + '-instance' + (++diagramInstance));
      canvas.querySelector('svg')?.setAttribute('role', 'img');
      canvas.querySelector('svg')?.setAttribute('aria-label', '流程图，完整文字说明可在图源码中查看');
      const details = document.createElement('details'); details.className = 'diagram-source'; details.innerHTML = '<summary>查看图源码</summary><pre><code></code></pre>';
      details.querySelector('code').textContent = raw;
      header.querySelector('button').onclick = () => openLearningDiagram(entry, raw);
      figure.append(header, canvas, details); pre.replaceWith(figure); continue;
    }
    if (code.matches('pre')) continue;
    const text = highlightLearningCode(code, lang);
    const wrap = document.createElement('div'); wrap.className = 'learning-code-block';
    const header = document.createElement('div'); header.className = 'code-toolbar';
    const label = document.createElement('span'); label.textContent = languageNames[lang] || lang;
    const copy = document.createElement('button'); copy.type = 'button'; copy.textContent = '复制代码';
    copy.onclick = () => copyLearningText(text, copy);
    header.append(label, copy); pre.before(wrap); wrap.append(header, pre);
  }
}

function highlightLearningSource(pre) {
  if (!pre || pre.hidden) return;
  const text = pre.textContent;
  const title = (pre.id === 'sourcePanelCode' ? $('sourcePanelTitle') : $('sourceTitle'))?.textContent || '';
  const ext = title.split(' · ')[0].split('.').pop().toLowerCase();
  const language = ({ py: 'python', js: 'javascript', cjs: 'javascript', mjs: 'javascript', tsx: 'typescript', ts: 'typescript', json: 'json', sql: 'sql', yaml: 'yaml', yml: 'yaml', ps1: 'powershell', sh: 'bash', html: 'xml', css: 'css', toml: 'ini' })[ext] || 'plaintext';
  const key = language + '\n' + text;
  if (highlightedSources.get(pre) === key) return;
  highlightedSources.set(pre, key);
  const code = document.createElement('code'); code.textContent = text;
  highlightLearningCode(code, language); pre.replaceChildren(code); pre.dataset.codeLanguage = language;
}

function openLearningDiagram(entry, raw) {
  for (const stop of labTimers.values()) stop();
  let dialog = $('learningDiagramDialog');
  if (!dialog) {
    dialog = document.createElement('dialog'); dialog.id = 'learningDiagramDialog'; dialog.className = 'diagram-dialog';
    dialog.innerHTML = '<header><strong>流程图 · 放大查看</strong><button type="button" class="diagram-close">关闭</button></header><div class="diagram-dialog-controls"><button type="button" data-zoom="out" aria-label="缩小流程图">−</button><output>100%</output><button type="button" data-zoom="in" aria-label="放大流程图">＋</button><button type="button" data-zoom="fit">适应窗口</button><button type="button" class="diagram-copy">复制图源码</button></div><div class="diagram-dialog-scroll" tabindex="0" aria-label="流程图画布，可滚动查看"><div class="diagram-dialog-canvas"></div></div>';
    document.body.append(dialog);
    dialog.querySelector('.diagram-close').onclick = () => dialog.close();
    dialog.onclick = e => { if (e.target === dialog) dialog.close(); };
  }
  const canvas = dialog.querySelector('.diagram-dialog-canvas');
  canvas.innerHTML = entry.svg.replaceAll(entry.prefix, entry.prefix + '-zoom' + (++diagramInstance));
  const svg = canvas.querySelector('svg'); svg.removeAttribute('style'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', '放大流程图');
  let scale = 1;
  const draw = () => {
    const view = svg.viewBox.baseVal, viewport = dialog.querySelector('.diagram-dialog-scroll');
    const fit = Math.min((viewport.clientWidth - 64) / view.width, (viewport.clientHeight - 64) / view.height, 1.5);
    const base = view.width * Math.max(0.05, fit);
    svg.style.width = Math.round(base * scale) + 'px'; svg.style.maxWidth = 'none'; svg.style.height = 'auto';
    dialog.querySelector('output').textContent = Math.round(scale * 100) + '%';
  };
  dialog.querySelectorAll('[data-zoom]').forEach(b => b.onclick = () => { scale = b.dataset.zoom === 'fit' ? 1 : Math.min(4, Math.max(0.5, scale * (b.dataset.zoom === 'in' ? 1.25 : 0.8))); draw(); });
  dialog.querySelector('.diagram-copy').onclick = e => copyLearningText(raw, e.currentTarget);
  dialog.showModal(); draw(); dialog.querySelector('.diagram-dialog-scroll').scrollTo(0, 0);
}

function installLearningRenderers() {
  for (const id of ['sourcePanelCode', 'sourceCode']) {
    const pre = $(id);
    new MutationObserver(() => highlightLearningSource(pre)).observe(pre, { childList: true, subtree: true, characterData: true });
  }
}

async function bootArchive() {
  try {
    manifest = await fetchJson('./data/manifest.json');
    $('resourceSelect').innerHTML = manifest.noteKeys.map(key => '<option value="' + E(key) + '">' + E(key) + '</option>').join('');
    installLearningRenderers();
    await setupReader();
    window.bookApp = {
      open: openChapter,
      chapters: manifest.chapters.map(c => ({ id: c.id, title: c.title })),
      originals: manifest.originals.map(c => ({ id: c.id, path: c.path })),
      audit: manifest.audit
    };
  } catch (err) {
    $('learning').hidden = true;
    $('loading').hidden = false;
    $('loading').innerHTML = location.protocol === 'file:' && !document.getElementById('./data/manifest.json')
      ? '<div style="max-width:560px;padding:24px;line-height:1.8;text-align:center;"><strong>按需分片版需要通过 HTTP 服务打开</strong><p>检测到当前使用 <code>file://</code> 本地文件协议，浏览器会拦截 <code>fetch(./data/...)</code>。请在 <code>site</code> 目录执行 <code>python -m http.server 8080</code> 后访问 <code>http://localhost:8080</code>，或直接部署至静态网站/CDN；若需无服务器离线打开，请使用上一级目录的单文件 <code>index.html</code>。</p></div>'
      : '<div style="max-width:560px;padding:24px;line-height:1.8;text-align:center;"><strong>加载档案索引失败</strong><p>' + E(err?.message || String(err)) + '</p></div>';
  }
}

bootArchive();

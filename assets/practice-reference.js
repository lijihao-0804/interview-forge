(function () {
  'use strict';

  var CONTEXT_PREFIX = 'interviewforge.practice.context:';
  var DRAFT_PREFIX = 'interviewforge.practice.draft:';
  var TEMPLATE_KEY = 'interviewforge.practice.template';
  var THEME_KEY = 'forge-theme';
  var templates = window.InterviewForgeAcmTemplates;

  var editor = null;
  var context = readContext();
  var currentLanguage = initialLanguage();
  var currentTemplate = 'array';
  try {
    var savedTemplate = localStorage.getItem(TEMPLATE_KEY);
    if (Object.hasOwn(templates, savedTemplate)) currentTemplate = savedTemplate;
  } catch (_) {}
  var currentSampleIndex = 0;
  var saveTimer = null;
  var running = false;
  var suiteController = null;
  var suiteCancelled = false;

  function $(id) { return document.getElementById(id); }
  function waitForAuthClient() {
    if (window.InterviewForgeAuth && window.InterviewForgeAuth.ready) return Promise.resolve(window.InterviewForgeAuth);
    return new Promise(function (resolve, reject) {
      var timer = window.setTimeout(function () {
        document.removeEventListener('interviewforge:auth-ready', ready);
        reject(new Error('登录状态确认超时，请刷新页面后重试'));
      }, 12000);
      function ready() {
        window.clearTimeout(timer);
        document.removeEventListener('interviewforge:auth-ready', ready);
        if (window.InterviewForgeAuth) resolve(window.InterviewForgeAuth);
        else reject(new Error('登录状态暂时不可用，请刷新页面后重试'));
      }
      document.addEventListener('interviewforge:auth-ready', ready, { once: true });
    });
  }
  async function requireRunUser(feature) {
    var auth = await waitForAuthClient();
    return auth.requireUser(feature);
  }
  async function protectedPracticeFetch(options, feature) {
    var auth = await waitForAuthClient();
    return auth.fetchProtected('/api/practice/run', Object.assign({ credentials: 'same-origin' }, options || {}), feature);
  }
  function valueOf(id) { var el = $(id); return el ? el.value : ''; }
  function initialLanguage() {
    try {
      var params = new URLSearchParams(location.search);
      var lang = params.get('lang') || params.get('language');
      if (lang === 'java' || lang === 'python') return lang;
    } catch (_) {}
    return context && context.language === 'java' ? 'java' : 'python';
  }
  function queryId() {
    try { return new URLSearchParams(location.search).get('id') || ''; } catch (_) { return ''; }
  }
  function readContext() {
    var id = queryId();
    if (!id) return null;
    try {
      var stored = JSON.parse(localStorage.getItem(CONTEXT_PREFIX + id)) ||
        JSON.parse(sessionStorage.getItem('interviewforge.practice.context'));
      return stored && stored.id === id ? stored : null;
    } catch (_) { return null; }
  }
  async function refreshContext() {
    var id = queryId() || (context && context.id);
    if (!id) return;
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, 8000);
    try {
      var response = await fetch('/books/ai-exam/practice-meta.json', { credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new Error('用例更新失败');
      var items = await response.json();
      var fresh = Array.isArray(items) && items.find(function (item) { return item.id === id; });
      if (fresh) context = fresh;
      else if (queryId()) context = null;
    } catch (_) { /* Offline use can still open previously carried public cases. */ }
    finally { clearTimeout(timer); }
    if (context && !context.suite_version) context.checker = { mode: 'manual', reason: '未能更新用例，请联网刷新后再评测' };
  }
  function checkOutput(actual, expected, input) {
    var checker = window.InterviewForgePracticeChecker;
    return checker ? checker.check(actual, expected, context && context.checker, input)
      : { verdict: 'review', message: '输出校验组件不可用，请刷新页面' };
  }
  function renderSuiteInfo() {
    var items = sampleList();
    var info = $('suite-info');
    if (context) {
      var statement = items.filter(function (s) { return s.source !== 'supplemental'; }).length;
      info.textContent = '本题共 ' + items.length + ' 组公开用例，含 ' + statement + ' 组题面样例和 ' + (items.length - statement) + ' 组站内补充。';
      if (context.checker && context.checker.mode === 'manual') info.textContent += '本题输出需人工核对。';
      if (context.case_note) info.textContent += ' ' + context.case_note;
    } else {
      info.textContent = '「' + templates[currentTemplate].title + '」共有 ' + items.length + ' 组模板样例。';
    }
    $('sample-prompt').textContent = context ? '' : templates[currentTemplate].prompt;
    $('sample-prompt').hidden = Boolean(context);
    $('problem-suite-notice').hidden = !context;
    $('judge-all-btn').textContent = '运行全部用例（' + items.length + '）';
    $('judge-all-btn').disabled = !items.length;
  }
  function setBusy(busy) {
    ['run-btn', 'judge-all-btn', 'language-select', 'template-select', 'reset-btn', 'initial-code-btn', 'format-btn', 'sample-select', 'clear-input-btn'].forEach(function (id) {
      var needsSample = id === 'judge-all-btn' || id === 'reset-btn';
      if ($(id)) $(id).disabled = busy || (needsSample && !sampleList().length);
    });
    $('stdin-area').readOnly = busy;
    $('expected-area').readOnly = busy;
    $('code-editor').readOnly = busy;
    if (editor) editor.setOption('readOnly', busy);
  }
  function initialCode(language) {
    return context ? (context.codes[language] || '') : templates[currentTemplate].codes[language];
  }
  function sampleList() {
    return context ? (context.samples || []) : templates[currentTemplate].samples;
  }
  function currentSample() {
    var items = sampleList();
    if (!items.length) return { input: '', expected: '' };
    return items[currentSampleIndex];
  }
  function renderSampleSelect() {
    var select = $('sample-select');
    if (!select) return;
    var items = sampleList();
    select.replaceChildren();
    if (!items.length) {
      select.hidden = true;
      return;
    }
    items.forEach(function (item, index) {
      var option = document.createElement('option');
      option.value = String(index);
      var label = context ? (item.source === 'supplemental' ? '站内补充' : '题面样例') : '模板样例';
      option.textContent = (index + 1) + '/' + items.length + ' · ' + (item.name || label);
      option.title = label;
      select.appendChild(option);
    });
    select.hidden = false;
    select.value = String(currentSampleIndex);
  }
  function draftKey(language, field, scope) {
    return DRAFT_PREFIX + (scope || (context ? context.id : 'template:' + currentTemplate)) + ':' + language + ':' + field;
  }
  function getDraft(language, field, scope) {
    try { return localStorage.getItem(draftKey(language, field, scope)); } catch (_) { return null; }
  }
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 220);
  }
  function saveDraft() {
    clearTimeout(saveTimer);
    try {
      localStorage.setItem(draftKey(currentLanguage, 'code'), getCode());
      localStorage.setItem(draftKey(currentLanguage, 'stdin'), valueOf('stdin-area'));
      localStorage.setItem(draftKey(currentLanguage, 'expected'), valueOf('expected-area'));
      localStorage.setItem(draftKey(currentLanguage, 'sample'), String(currentSampleIndex));
    } catch (_) {}
  }
  function getCode() { return editor ? editor.getValue() : valueOf('code-editor'); }
  function setCode(code) {
    if (editor) editor.setValue(code);
    else $('code-editor').value = code;
  }
  function formatJava(source) {
    // Text blocks and Unicode escapes are interpreted before ordinary Java tokens.
    if (source.includes('"""') || /\\u+[0-9a-f]{4}/i.test(source)) return source;
    var out = [], line = '', indent = 0, paren = 0;
    var inString = false, inChar = false, inLineComment = false, inBlockComment = false, escape = false;
    function emit() {
      var trimmed = line.trim();
      if (trimmed) out.push('    '.repeat(indent) + trimmed);
      line = '';
    }
    for (var i = 0; i < source.length; i += 1) {
      var c = source[i];
      var next = source[i + 1];
      if (inLineComment) {
        if (c === '\n' || c === '\r') { inLineComment = false; emit(); }
        else line += c;
        continue;
      }
      if (inBlockComment) {
        line += c;
        if (c === '*' && next === '/') { line += '/'; i += 1; inBlockComment = false; }
        continue;
      }
      if (inString || inChar) {
        line += c;
        if (escape) escape = false;
        else if (c === '\\') escape = true;
        else if (inString && c === '"') inString = false;
        else if (inChar && c === "'") inChar = false;
        continue;
      }
      if (c === '/' && next === '/') { inLineComment = true; line += '//'; i += 1; continue; }
      if (c === '/' && next === '*') { inBlockComment = true; line += '/*'; i += 1; continue; }
      if (c === '"') { inString = true; line += c; continue; }
      if (c === "'") { inChar = true; line += c; continue; }
      if (c === '(') paren += 1;
      if (c === ')') paren = Math.max(0, paren - 1);
      if (c === '{' && paren === 0) { line += c; emit(); indent += 1; continue; }
      if (c === '}' && paren === 0) {
        emit();
        indent = Math.max(0, indent - 1);
        line = '}';
        continue;
      }
      if (c === ';' && paren === 0) { line += c; emit(); continue; }
      if (c === '\n' || c === '\r') { if (line.trim()) emit(); continue; }
      line += c;
    }
    emit();
    return out.join('\n');
  }
  function formatPython(source) {
    if (source.indexOf('\n') >= 0 || source.indexOf(';') < 0) return source;
    // Splitting an inline suite, a comment, or an indented line can change execution.
    if (/^\s|[:#]/.test(source)) return source;
    var out = [], current = '', quote = '', escaped = false;
    for (var i = 0; i < source.length; i += 1) {
      var c = source[i];
      if (quote) {
        current += c;
        if (escaped) escaped = false;
        else if (c === '\\') escaped = true;
        else if (c === quote) quote = '';
      } else if (c === '"' || c === "'") {
        quote = c;
        current += c;
      } else if (c === ';') {
        out.push(current.trim());
        current = '';
      } else {
        current += c;
      }
    }
    if (current.trim()) out.push(current.trim());
    return out.join('\n');
  }
  function formatCode() {
    var source = getCode();
    var formatted = currentLanguage === 'java' ? formatJava(source) : formatPython(source);
    if (source.trimEnd() === formatted.trimEnd()) {
      $('status-info').textContent = '代码格式无变化';
      return;
    }
    setCode(formatted);
    scheduleSave();
    clearResult(true);
    setRuntimeStatus(languageLabel() + ' · 已格式化', 'ready');
    $('status-info').textContent = '代码已格式化';
  }
  function restoreInitialCode() {
    setCode(initialCode(currentLanguage));
    scheduleSave();
    clearResult(true);
    setRuntimeStatus(languageLabel() + ' · 已恢复初始代码', 'ready');
    $('status-info').textContent = '已恢复初始代码';
  }
  function setEditorLanguage(language) {
    if (editor) editor.setOption('mode', language === 'java' ? 'text/x-java' : 'python');
  }
  function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem(THEME_KEY, theme); } catch (_) {}
    if (editor) editor.setOption('theme', theme === 'light' ? 'eclipse' : 'material-darker');
  }
  function initTheme() {
    var button = $('theme-toggle');
    if (!button) return;
    if (!document.documentElement.getAttribute('data-theme')) {
      setTheme(window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    }
    button.addEventListener('click', function () {
      setTheme(document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light');
    });
  }
  function setRuntimeStatus(text, state) {
    var status = $('runtime-status');
    if (!status) return;
    status.textContent = text;
    status.className = 'runtime-status ' + (state || 'ready');
  }
  function languageLabel() { return currentLanguage === 'java' ? 'Java 17' : 'Python 3'; }
  function updateLanguageUi() {
    $('language-select').value = currentLanguage;
    $('language-hint').textContent = languageLabel();
    setEditorLanguage(currentLanguage);
    setRuntimeStatus(languageLabel() + ' 就绪', 'ready');
  }
  function loadLanguage(language) {
    currentLanguage = language === 'java' ? 'java' : 'python';
    // Before templates had their own workspaces, all standalone drafts shared "scratch".
    var scope = !context && currentTemplate === 'array' && getDraft(currentLanguage, 'code') == null ? 'scratch' : null;
    var codeDraft = getDraft(currentLanguage, 'code', scope);
    var stdinDraft = getDraft(currentLanguage, 'stdin', scope);
    var expectedDraft = getDraft(currentLanguage, 'expected', scope);
    var items = sampleList();
    var storedIndex = getDraft(currentLanguage, 'sample', scope);
    var index = storedIndex == null ? items.findIndex(function (s) {
      return s.input === stdinDraft && s.expected === expectedDraft;
    }) : Number(storedIndex);
    if (index >= 0 && index < items.length && Number.isInteger(index)) currentSampleIndex = index;
    var sample = currentSample();
    setCode(codeDraft != null ? codeDraft : initialCode(currentLanguage));
    $('stdin-area').value = stdinDraft != null ? stdinDraft : sample.input;
    $('expected-area').value = expectedDraft != null ? expectedDraft : sample.expected;
    updateLanguageUi();
    renderSampleSelect();
    clearResult(true);
    updateCaseLabel();
  }
  function updateCaseLabel() {
    var sample = currentSample();
    var input = valueOf('stdin-area'), expected = valueOf('expected-area');
    var custom = sampleList().length && (input !== sample.input || expected !== sample.expected);
    $('case-state').textContent = custom ? '自定义输入 / 期望输出' : '';
    $('stdin-area').placeholder = input === '' && sampleList().length && sample.input === '' ? '此样例的标准输入为空' : '输入标准输入文本';
    $('expected-area').placeholder = sampleList().length && expected === '' && input === sample.input && sample.expected === '' ?
      '此样例应无输出' : '可填写期望输出，与运行结果对比';
  }
  function clearResult(clearSuite) {
    var output = $('stdout-area');
    if (output) {
      output.textContent = '点击「运行当前输入」或按 Ctrl+Enter 执行代码';
      output.className = 'io-output placeholder-text';
    }
    var runStatus = $('run-status');
    if (runStatus) { runStatus.textContent = ''; runStatus.className = 'run-status'; }
    var diff = $('diff-result');
    if (diff) { diff.textContent = ''; diff.className = 'diff-result'; }
    if ($('status-info')) $('status-info').textContent = '就绪';
    if ($('status-time')) $('status-time').textContent = '';
    if (clearSuite) {
      $('suite-summary').textContent = '';
      $('suite-results').replaceChildren();
    }
  }
  function compare(actual, expected, input) {
    var box = $('diff-result');
    // An explicitly empty expected stream is part of EOF / zero-group samples.
    var sample = currentSample();
    if (expected === '' && !(sampleList().length && sample.input === input && sample.expected === '')) {
      box.textContent = '未填写期望输出';
      box.className = 'diff-result';
      return;
    }
    var result = checkOutput(actual, expected, input);
    if (result.verdict === 'pass') {
      box.textContent = '输出符合期望';
      box.className = 'diff-result match';
    } else if (result.verdict === 'fail') {
      box.textContent = '输出不符';
      box.className = 'diff-result mismatch';
    } else {
      box.textContent = '待人工核对';
      box.className = 'diff-result';
    }
  }
  function showOutput(text, isError) {
    var output = $('stdout-area');
    output.textContent = text || '（无输出）';
    output.className = 'io-output' + (isError ? ' has-error' : '');
  }
  async function authorizeRun(feature) {
    running = true;
    setBusy(true);
    clearResult();
    $('status-info').textContent = '正在确认登录状态…';
    try {
      await requireRunUser(feature);
      return true;
    } catch (error) {
      var denied = error && error.code === 'AUTH_REQUIRED';
      var message = denied ? '请登录后运行代码。' : '暂时无法确认登录状态，请刷新后重试。';
      $('run-status').textContent = denied ? '需要登录' : '连接失败';
      $('status-info').textContent = message;
      showOutput(message, true);
      running = false;
      setBusy(false);
      return false;
    }
  }
  async function runCode() {
    if (running) return;
    if (!await authorizeRun('运行代码')) return;
    var input = valueOf('stdin-area'), expected = valueOf('expected-area');
    var controller = new AbortController();
    var timeout = setTimeout(function () { controller.abort(); }, 30000);
    setRuntimeStatus(languageLabel() + ' · 运行中…', 'loading');
    $('run-status').textContent = '运行中';
    $('run-status').className = 'run-status running';
    $('status-info').textContent = '运行中…';
    try {
      var response = await protectedPracticeFetch({
        method: 'POST',
        signal: controller.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          language: currentLanguage,
          code: getCode(),
          stdin: input
        })
      }, '运行或提交代码');
      var payload = {};
      try { payload = await response.json(); } catch (_) {}
      if (response.status === 401) {
        showOutput('登录后才能运行代码。', true);
        $('run-status').textContent = '未登录';
        $('run-status').className = 'run-status error';
        setRuntimeStatus(languageLabel() + ' · 需要登录', 'error');
        $('status-info').textContent = '请登录后重试';
        return;
      }
      if (response.status === 429) {
        showOutput('已有一次执行正在进行，请稍后重试。', true);
        $('run-status').textContent = '繁忙';
        $('run-status').className = 'run-status error';
        setRuntimeStatus(languageLabel() + ' · 执行中', 'error');
        $('status-info').textContent = '执行服务繁忙，请稍后再运行';
        return;
      }
      if (!response.ok) {
        showOutput((payload && payload.error) || '执行服务异常。', true);
        $('run-status').textContent = '服务异常';
        $('run-status').className = 'run-status error';
        setRuntimeStatus(languageLabel() + ' · 服务异常', 'error');
        $('status-info').textContent = '执行服务暂时不可用';
        return;
      }
      var status = payload.status || 'unknown';
      var stderr = payload.stderr || '';
      var stdout = payload.stdout || '';
      var combined = stderr ? (stdout ? stdout.replace(/\s+$/, '') + '\n' + stderr : stderr) : stdout;
      showOutput(combined, status !== 'ok');
      $('run-status').textContent = status === 'ok' ? '完成' : ({
        compile_error: '编译错误',
        runtime_error: '运行错误',
        timeout: '超时',
        output_limit: '输出超限',
        busy: '繁忙'
      }[status] || status);
      $('run-status').className = 'run-status ' + (status === 'ok' ? 'success' : 'error');
      setRuntimeStatus(languageLabel() + ' · 就绪', 'ready');
      $('status-info').textContent = status === 'ok' ? '运行完成' : '执行结束';
      $('status-time').textContent = [
        payload.compile_time_ms ? ('编译 ' + payload.compile_time_ms + ' ms') : '',
        payload.run_time_ms ? ('运行 ' + payload.run_time_ms + ' ms') : '',
        payload.timed_out ? '超时' : '',
        payload.output_truncated ? '输出截断' : ''
      ].filter(Boolean).join(' · ');
      if (status === 'ok') compare(stdout, expected, input);
      else { $('diff-result').textContent = '未比较输出'; $('diff-result').className = 'diff-result'; }
    } catch (error) {
      var authExpired = error && error.code === 'AUTH_REQUIRED';
      var message = authExpired ? '登录已失效，请登录后重试。' :
        (controller.signal.aborted ? '等待执行服务响应超时，请重试。' : '无法连接执行服务，请重试。');
      showOutput(message, true);
      $('status-info').textContent = message;
      $('run-status').textContent = authExpired ? '请先登录' : '连接失败';
      $('run-status').className = 'run-status error';
      setRuntimeStatus(languageLabel() + ' · 服务不可用', 'error');
    } finally {
      clearTimeout(timeout);
      running = false;
      setBusy(false);
    }
  }
  var CASE_LABELS = { pass: '通过', fail: '输出不符', review: '待人工核对', runtime_error: '运行错误',
    compile_error: '编译错误', timeout: '超时', output_limit: '输出超限', service_error: '服务不可用', not_run: '未执行' };
  function renderCases(results, total, finished) {
    var passed = results.filter(function (r) { return r.verdict === 'pass'; }).length;
    var failed = results.filter(function (r) { return ['fail', 'runtime_error', 'compile_error', 'timeout', 'output_limit'].indexOf(r.verdict) >= 0; }).length;
    var review = results.filter(function (r) { return r.verdict === 'review'; }).length;
    var uncertain = results.filter(function (r) { return r.verdict === 'service_error'; }).length;
    var executed = results.filter(function (r) { return r.verdict !== 'not_run'; }).length;
    var summary = '通过 ' + passed + '/' + total + ' · 未通过 ' + failed + ' · 待核对 ' + review + ' · 服务异常 ' + uncertain + ' · 未执行 ' + (total - executed);
    if ($('suite-summary')) $('suite-summary').textContent = summary + (finished ? '' : ' · 评测中…');
    var host = $('suite-results');
    if (host) {
      host.replaceChildren();
      results.forEach(function (r, index) {
        var sample = sampleList()[index];
        var details = document.createElement('details');
        details.className = 'suite-case';
        details.setAttribute('data-verdict', r.verdict);
        var title = document.createElement('summary');
        title.textContent = (index + 1) + '/' + total + ' · ' + (sample.name || (sample.source === 'supplemental' ? '补充用例' : '题面样例')) + ' · ' + CASE_LABELS[r.verdict];
        details.appendChild(title);
        [['输入', sample.input], ['期望输出', sample.expected], ['实际输出', r.stdout || ''], ['说明', r.message || ''], ['stderr', r.stderr || '']].forEach(function (field) {
          if (!field[1] && field[0] === 'stderr') return;
          var label = document.createElement('strong');
          label.textContent = field[0];
          var pre = document.createElement('pre');
          pre.textContent = field[1] || '（空）';
          details.appendChild(label); details.appendChild(pre);
        });
        host.appendChild(details);
      });
    }
    return { passed: passed, failed: failed, review: review, uncertain: uncertain, executed: executed, summary: summary };
  }
  async function judgeAll() {
    if (running || !sampleList().length) return;
    if (!await authorizeRun('评测全部用例')) return;
    // Snapshot code, language and cases: every case tests the same submitted program.
    var items = sampleList().slice(), language = currentLanguage, code = getCode();
    var results = [], compileMs = 0, runMs = 0;
    suiteCancelled = false;
    suiteController = new AbortController();
    if ($('cancel-judge-btn')) $('cancel-judge-btn').hidden = false;
    $('run-status').textContent = '评测中';
    $('run-status').className = 'run-status running';
    try {
      renderCases(results, items.length, false);
      for (var index = 0; index < items.length; index += 1) {
        if (suiteCancelled) break;
        setRuntimeStatus(languageLabel() + ' · 用例 ' + (index + 1) + '/' + items.length, 'loading');
        var response, payload, failure = '';
        for (var attempt = 0; attempt < 3; attempt += 1) {
          var timer = setTimeout(function () { if (suiteController) suiteController.abort(); }, 30000);
          try {
            response = await protectedPracticeFetch({ method: 'POST', headers: { 'Content-Type': 'application/json' },
              signal: suiteController.signal, body: JSON.stringify({ language: language, code: code, stdin: items[index].input }) }, '评测全部用例');
            payload = await response.json();
          } catch (error) {
            failure = suiteCancelled ? '已停止，当前请求结果未知' :
              (error && error.code === 'AUTH_REQUIRED' ? '登录已失效，请登录后重试' : '连接中断或执行服务未响应');
          }
          finally { clearTimeout(timer); }
          if (failure || !response || response.status !== 429 || attempt === 2) break;
          // Bounded retry for the runner's single execution slot; no parallel fan-out.
          await new Promise(function (resolve) { setTimeout(resolve, 1200); });
          if (suiteCancelled) break;
        }
        if (suiteCancelled) break;
        if (failure || !response || !response.ok || !payload || typeof payload.status !== 'string') {
          results.push({ verdict: 'service_error', message: failure || (response && response.status === 401 ? '登录已失效，请登录后重试' : '执行服务繁忙或返回异常，请稍后重试') });
          break;
        }
        compileMs += Number(payload.compile_time_ms) || 0;
        runMs += Number(payload.run_time_ms) || 0;
        var result = payload.status === 'ok' ? checkOutput(payload.stdout || '', items[index].expected, items[index].input)
          : { verdict: CASE_LABELS[payload.status] ? payload.status : 'service_error', message: payload.status };
        result.stdout = payload.stdout || ''; result.stderr = payload.stderr || '';
        results.push(result);
        renderCases(results, items.length, false);
        if (result.verdict === 'compile_error' || result.verdict === 'service_error') break;
      }
    } finally {
      while (results.length < items.length) results.push({ verdict: 'not_run', message: suiteCancelled ? '用户停止评测' : '评测中断，请重试' });
      var state = renderCases(results, items.length, true);
      var allPassed = state.passed === items.length;
      showOutput(state.summary, state.failed > 0);
      $('run-status').textContent = suiteCancelled ? '已停止' : (allPassed ? '全部用例通过' : (state.failed ? '存在未通过用例' : '评测未完成 / 待核对'));
      $('run-status').className = 'run-status ' + (allPassed ? 'success' : (state.failed ? 'error' : ''));
      $('diff-result').textContent = ''; $('diff-result').className = 'diff-result';
      $('status-info').textContent = state.summary;
      $('status-time').textContent = '编译合计 ' + compileMs + ' ms · 运行合计 ' + runMs + ' ms';
      setRuntimeStatus(languageLabel() + ' · 就绪', 'ready');
      suiteController = null; running = false; setBusy(false);
      if ($('cancel-judge-btn')) $('cancel-judge-btn').hidden = true;
    }
  }
  function setSample(index) {
    currentSampleIndex = Number(index);
    $('sample-select').value = String(currentSampleIndex);
    var sample = currentSample();
    $('stdin-area').value = sample.input;
    $('expected-area').value = sample.expected;
    clearResult();
    updateCaseLabel();
    $('status-info').textContent = '已载入样例 ' + (currentSampleIndex + 1) + '/' + sampleList().length;
    setRuntimeStatus(languageLabel() + ' 就绪', 'ready');
    saveDraft();
  }
  function codeChanged() {
    clearResult(true);
    setRuntimeStatus(languageLabel() + ' 就绪', 'ready');
    scheduleSave();
  }
  function caseChanged() {
    clearResult();
    updateCaseLabel();
    scheduleSave();
  }
  function initEditor() {
    if (window.CodeMirror) {
      editor = CodeMirror.fromTextArea($('code-editor'), {
        mode: 'python',
        screenReaderLabel: '代码编辑器',
        theme: document.documentElement.getAttribute('data-theme') === 'light' ? 'eclipse' : 'material-darker',
        lineNumbers: true,
        indentUnit: 4,
        tabSize: 4,
        lineWrapping: true,
        styleActiveLine: true,
        extraKeys: {
          'Ctrl-Enter': runCode,
          'Cmd-Enter': runCode
        }
      });
      editor.on('change', codeChanged);
    } else {
      var fallback = $('code-editor');
      fallback.style.display = 'block';
      fallback.style.width = '100%';
      fallback.style.height = '100%';
      fallback.style.background = 'transparent';
      fallback.style.color = 'inherit';
      fallback.style.border = '0';
      fallback.style.padding = '12px';
    }
  }
  function initContext() {
    var select = $('template-select');
    select.hidden = Boolean(context);
    $('template-link').hidden = !context;
    if (!context) {
      Object.keys(templates).forEach(function (key) {
        var option = document.createElement('option');
        option.value = key;
        option.textContent = templates[key].title;
        select.appendChild(option);
      });
      select.value = currentTemplate;
      if (queryId()) {
        $('context-notice').textContent = '未能加载这道题的公开用例。可以刷新重试，或练习下方输入模板。';
        $('context-notice').hidden = false;
      }
      return;
    }
    var chip = $('problem-context');
    if (chip) {
      chip.textContent = context.title;
      chip.hidden = false;
      chip.title = context.title;
    }
    document.title = context.title + ' · ACM 模拟';
  }
  async function init() {
    running = true;
    setBusy(true);
    await refreshContext();
    initTheme();
    initEditor();
    initContext();
    renderSuiteInfo();
    $('language-select').addEventListener('change', function () {
      saveDraft();
      var url;
      try {
        url = new URL(location.href);
        url.searchParams.set('lang', this.value);
        history.replaceState(null, '', url.toString());
      } catch (_) {}
      loadLanguage(this.value);
    });
    $('template-select').addEventListener('change', function () {
      if (context || !Object.hasOwn(templates, this.value)) return;
      saveDraft();
      currentTemplate = this.value;
      currentSampleIndex = 0;
      try { localStorage.setItem(TEMPLATE_KEY, currentTemplate); } catch (_) {}
      renderSuiteInfo();
      loadLanguage(currentLanguage);
      $('status-info').textContent = '已载入「' + templates[currentTemplate].title + '」';
    });
    $('run-btn').addEventListener('click', runCode);
    if ($('judge-all-btn')) $('judge-all-btn').addEventListener('click', judgeAll);
    if ($('cancel-judge-btn')) $('cancel-judge-btn').addEventListener('click', function () {
      suiteCancelled = true; if (suiteController) suiteController.abort();
    });
    if ($('format-btn')) $('format-btn').addEventListener('click', formatCode);
    if ($('initial-code-btn')) $('initial-code-btn').addEventListener('click', restoreInitialCode);
    if ($('sample-select')) {
      $('sample-select').addEventListener('change', function () {
        setSample(this.value);
      });
    }
    $('reset-btn').addEventListener('click', function () { setSample(currentSampleIndex); });
    $('save-code-btn').addEventListener('click', function () {
      var code = getCode();
      var blob = new Blob([code], { type: 'text/plain;charset=utf-8' });
      var link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      var className = /\bpublic\s+(?:(?:final|abstract|sealed)\s+)*class\s+([A-Za-z_$][\w$]*)/.exec(code);
      link.download = currentLanguage === 'java' ? (className ? className[1] : 'Main') + '.java' : 'solution.py';
      document.body.appendChild(link);
      link.click();
      $('status-info').textContent = '已开始下载 ' + link.download;
      setTimeout(function () { URL.revokeObjectURL(link.href); link.remove(); }, 0);
    });
    $('clear-input-btn').addEventListener('click', function () {
      $('stdin-area').value = '';
      caseChanged();
      $('status-info').textContent = '已清空当前输入';
      $('stdin-area').focus();
    });
    $('stdin-area').addEventListener('input', caseChanged);
    $('expected-area').addEventListener('input', caseChanged);
    $('code-editor').addEventListener('input', codeChanged);
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.defaultPrevented && !event.isComposing) {
        event.preventDefault();
        runCode();
      }
    });
    var navToggle = $('nav-toggle');
    if (navToggle) {
      navToggle.addEventListener('click', function () {
        var open = document.querySelector('.nav-menu').classList.toggle('active');
        navToggle.setAttribute('aria-expanded', String(open));
      });
    }
    loadLanguage(currentLanguage);
    running = false;
    setBusy(false);
    window.addEventListener('beforeunload', saveDraft);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

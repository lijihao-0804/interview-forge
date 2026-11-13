(function () {
  'use strict';

  var CONTEXT_KEY = 'interviewforge.practice.context';
  var CONTEXT_PREFIX = 'interviewforge.practice.context:';
  var DRAFT_PREFIX = 'interviewforge.practice.draft:';
  var THEME_KEY = 'forge-theme';
  var DEFAULT_CODE = {
    python: '# ACM 模式：使用 input() 读取输入，print() 输出结果\n# 在右侧「输入」区粘贴测试数据，点击运行即可\n\nn = int(input())\narr = list(map(int, input().split()))\narr.sort()\nprint(" ".join(map(str, arr)))\n',
    java: 'import java.io.*;\nimport java.util.*;\n\npublic class Main {\n    public static void main(String[] args) throws Exception {\n        Scanner sc = new Scanner(System.in);\n        int n = sc.nextInt();\n        int[] arr = new int[n];\n        for (int i = 0; i < n; i++) arr[i] = sc.nextInt();\n        Arrays.sort(arr);\n        StringBuilder out = new StringBuilder();\n        for (int i = 0; i < n; i++) {\n            if (i > 0) out.append(" ");\n            out.append(arr[i]);\n        }\n        System.out.println(out);\n    }\n}\n'
  };
  var TEMPLATES = {
    single: {
      python: 'n = int(input())\nprint(n)\n',
      java: 'import java.util.*;\npublic class Main { public static void main(String[] args) { Scanner sc = new Scanner(System.in); int n = sc.nextInt(); System.out.println(n); } }\n'
    },
    two: {
      python: 'a, b = map(int, input().split())\nprint(a + b)\n',
      java: 'import java.util.*;\npublic class Main { public static void main(String[] args) { Scanner sc = new Scanner(System.in); long a = sc.nextLong(), b = sc.nextLong(); System.out.println(a + b); } }\n'
    },
    array: {
      python: 'n = int(input())\narr = list(map(int, input().split()))\nprint(arr)\n',
      java: 'import java.util.*;\npublic class Main { public static void main(String[] args) { Scanner sc = new Scanner(System.in); int n = sc.nextInt(); int[] a = new int[n]; for (int i = 0; i < n; i++) a[i] = sc.nextInt(); System.out.println(Arrays.toString(a)); } }\n'
    },
    matrix: {
      python: 'n, m = map(int, input().split())\ngrid = [list(map(int, input().split())) for _ in range(n)]\nprint(grid)\n',
      java: 'import java.util.*;\npublic class Main { public static void main(String[] args) { Scanner sc = new Scanner(System.in); int n = sc.nextInt(), m = sc.nextInt(); for (int i = 0; i < n; i++) for (int j = 0; j < m; j++) sc.nextInt(); System.out.println("ok"); } }\n'
    },
    multi: {
      python: 'import sys\nfor line in sys.stdin:\n    if line.strip():\n        print(line.strip())\n',
      java: 'import java.util.*;\npublic class Main { public static void main(String[] args) { Scanner sc = new Scanner(System.in); while (sc.hasNextLine()) System.out.println(sc.nextLine()); } }\n'
    },
    string: {
      python: 's = input()\nprint(s)\n',
      java: 'import java.util.*;\npublic class Main { public static void main(String[] args) { Scanner sc = new Scanner(System.in); System.out.println(sc.nextLine()); } }\n'
    },
    graph: {
      python: 'n, m = map(int, input().split())\ng = [[] for _ in range(n)]\nfor _ in range(m):\n    u, v = map(int, input().split())\n    g[u].append(v)\n    g[v].append(u)\nprint(g)\n',
      java: 'import java.util.*;\npublic class Main { public static void main(String[] args) { Scanner sc = new Scanner(System.in); int n = sc.nextInt(), m = sc.nextInt(); for (int i = 0; i < m; i++) { sc.nextInt(); sc.nextInt(); } System.out.println("ok"); } }\n'
    }
  };

  var editor = null;
  var context = readContext();
  var currentLanguage = initialLanguage();
  var currentTemplate = 'array';
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
    try {
      var id = queryId();
      if (id) {
        var scoped = localStorage.getItem(CONTEXT_PREFIX + id);
        if (scoped) return JSON.parse(scoped);
        return null;
      }
      var raw = sessionStorage.getItem(CONTEXT_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (_) { return null; }
  }
  function contextCode(language) {
    return context && context.codes && typeof context.codes[language] === 'string'
      ? context.codes[language] : DEFAULT_CODE[language];
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
    var statement = items.filter(function (s) { return !s.source || s.source === 'statement'; }).length;
    var info = $('suite-info');
    if (info) info.textContent = items.length ? ('共 ' + items.length + ' 组用例：题面 ' + statement + ' 组，站内补充 ' + (items.length - statement) + ' 组。' +
      (context.checker && context.checker.mode === 'manual' ? '本题输出需人工核对。' : '')) : '从题目页打开，可一次评测该题全部用例。';
    if (info && context && context.case_note) info.textContent += ' ' + context.case_note;
    if ($('judge-all-btn')) $('judge-all-btn').disabled = !items.length;
  }
  function setBusy(busy) {
    ['run-btn', 'judge-all-btn', 'language-select', 'template-select', 'reset-btn', 'initial-code-btn', 'format-btn', 'sample-select', 'clear-input-btn'].forEach(function (id) {
      if ($(id)) $(id).disabled = busy || (id === 'judge-all-btn' && !sampleList().length);
    });
  }
  function templateSource(language, template) {
    var item = TEMPLATES[template] || TEMPLATES.array;
    var source = item && item[language] ? item[language] : DEFAULT_CODE[language];
    return language === 'java' ? formatJava(source) : formatPython(source);
  }
  function initialCode(language) {
    return templateSource(language, currentTemplate);
  }
  function sampleList() {
    return context && Array.isArray(context.samples) ? context.samples : [];
  }
  function currentSample() {
    var items = sampleList();
    if (!items.length) return { input: '', expected: '' };
    if (currentSampleIndex >= items.length) currentSampleIndex = items.length - 1;
    return items[currentSampleIndex];
  }
  function renderSampleSelect() {
    var select = $('sample-select');
    if (!select) return;
    var items = sampleList();
    select.innerHTML = '';
    if (items.length <= 1) {
      select.hidden = true;
      return;
    }
    items.forEach(function (item, index) {
      var option = document.createElement('option');
      option.value = String(index);
      option.textContent = (index + 1) + '/' + items.length + ' · ' + (item.source === 'supplemental' ? '补充' : '题面') + (item.name ? ' · ' + item.name : '');
      select.appendChild(option);
    });
    select.hidden = false;
    select.value = String(currentSampleIndex);
  }
  function draftKey(language, field) {
    return DRAFT_PREFIX + (context && context.id ? context.id : 'scratch') + ':' + language + ':' + field;
  }
  function getDraft(language, field) {
    try { return localStorage.getItem(draftKey(language, field)); } catch (_) { return null; }
  }
  function setDraft(language, field, value) {
    try { localStorage.setItem(draftKey(language, field), value); } catch (_) {}
  }
  function clearDraft(language) {
    ['code', 'stdin', 'expected'].forEach(function (field) {
      try { localStorage.removeItem(draftKey(language, field)); } catch (_) {}
    });
  }
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 220);
  }
  function saveDraft() {
    setDraft(currentLanguage, 'code', getCode());
    setDraft(currentLanguage, 'stdin', valueOf('stdin-area'));
    setDraft(currentLanguage, 'expected', valueOf('expected-area'));
  }
  function getCode() { return editor ? editor.getValue() : valueOf('code-editor'); }
  function setCode(code) {
    if (editor) editor.setValue(code);
    else $('code-editor').value = code;
  }
  function formatJava(source) {
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
    var formatted = currentLanguage === 'java' ? formatJava(getCode()) : formatPython(getCode());
    setCode(formatted);
    scheduleSave();
    clearResult();
    setRuntimeStatus(languageLabel() + ' · 已格式化', 'ready');
    $('status-info').textContent = '代码已格式化';
  }
  function restoreInitialCode() {
    setCode(initialCode(currentLanguage));
    scheduleSave();
    clearResult();
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
    $('language-hint').textContent = languageLabel() + ' · ACM 模式';
    setEditorLanguage(currentLanguage);
    setRuntimeStatus(languageLabel() + ' 就绪', 'ready');
  }
  function loadLanguage(language, preserveDraft) {
    currentLanguage = language === 'java' ? 'java' : 'python';
    var codeDraft = preserveDraft ? getDraft(currentLanguage, 'code') : null;
    var stdinDraft = preserveDraft ? getDraft(currentLanguage, 'stdin') : null;
    var expectedDraft = preserveDraft ? getDraft(currentLanguage, 'expected') : null;
    var sample = currentSample();
    setCode(codeDraft != null ? codeDraft : initialCode(currentLanguage));
    $('stdin-area').value = stdinDraft != null ? stdinDraft : sample.input;
    $('expected-area').value = expectedDraft != null ? expectedDraft : sample.expected;
    updateLanguageUi();
    renderSampleSelect();
    clearResult();
  }
  function clearResult() {
    var output = $('stdout-area');
    if (output) {
      output.textContent = '点击「运行」或按 Ctrl+Enter 执行代码';
      output.className = 'io-output placeholder-text';
    }
    var runStatus = $('run-status');
    if (runStatus) { runStatus.textContent = ''; runStatus.className = 'run-status'; }
    var diff = $('diff-result');
    if (diff) { diff.textContent = ''; diff.className = 'diff-result'; }
    if ($('status-info')) $('status-info').textContent = '就绪';
    if ($('status-time')) $('status-time').textContent = '';
  }
  function compare(actual) {
    var expected = valueOf('expected-area');
    var box = $('diff-result');
    if (!expected.trim()) { box.textContent = ''; box.className = 'diff-result'; return; }
    var result = checkOutput(actual, expected, valueOf('stdin-area'));
    if (result.verdict === 'pass') {
      box.textContent = '样例通过';
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
  async function runCode() {
    if (running) return;
    try { await requireRunUser('运行或提交代码'); }
    catch (_) { return; }
    if (running) return;
    running = true;
    setBusy(true);
    setRuntimeStatus(languageLabel() + ' · 运行中…', 'loading');
    $('run-status').textContent = '运行中';
    $('run-status').className = 'run-status running';
    $('status-info').textContent = '运行中…';
    try {
      var response = await protectedPracticeFetch({
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          language: currentLanguage,
          code: getCode(),
          stdin: valueOf('stdin-area')
        })
      }, '运行或提交代码');
      var payload = {};
      try { payload = await response.json(); } catch (_) {}
      if (response.status === 401) {
        showOutput('登录后才能运行代码。', true);
        $('run-status').textContent = '未登录';
        $('run-status').className = 'run-status error';
        setRuntimeStatus(languageLabel() + ' · 需要登录', 'error');
        return;
      }
      if (response.status === 429) {
        showOutput('已有一次执行正在进行，请稍后重试。', true);
        $('run-status').textContent = '繁忙';
        $('run-status').className = 'run-status error';
        setRuntimeStatus(languageLabel() + ' · 执行中', 'error');
        return;
      }
      if (!response.ok) {
        showOutput((payload && payload.error) || '执行服务异常。', true);
        $('run-status').textContent = '服务异常';
        $('run-status').className = 'run-status error';
        setRuntimeStatus(languageLabel() + ' · 服务异常', 'error');
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
      if (status === 'ok') compare(stdout);
      else { $('diff-result').textContent = '未比较输出'; $('diff-result').className = 'diff-result'; }
    } catch (error) {
      var authExpired = error && error.code === 'AUTH_REQUIRED';
      showOutput(authExpired ? '登录已失效，请登录后重试。' : '无法连接执行服务。', true);
      $('run-status').textContent = authExpired ? '请先登录' : '连接失败';
      $('run-status').className = 'run-status error';
      setRuntimeStatus(languageLabel() + ' · 服务不可用', 'error');
    } finally {
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
    try { await requireRunUser('评测全部用例'); }
    catch (_) { return; }
    if (running) return;
    // Snapshot code, language and cases: every case tests the same submitted program.
    var items = sampleList().slice(), language = currentLanguage, code = getCode();
    var results = [], compileMs = 0, runMs = 0;
    running = true; suiteCancelled = false;
    suiteController = new AbortController();
    setBusy(true);
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
      showOutput(state.summary + (allPassed ? '\n通过站内全部用例，不保证原平台完整评测通过。' : ''), state.failed > 0);
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
    currentSampleIndex = Number(index) || 0;
    renderSampleSelect();
    var sample = currentSample();
    $('stdin-area').value = sample.input || '';
    $('expected-area').value = sample.expected || '';
    clearResult();
    scheduleSave();
  }
  function resetCode() {
    clearDraft(currentLanguage);
    var sample = currentSample();
    setCode(initialCode(currentLanguage));
    $('stdin-area').value = sample.input;
    $('expected-area').value = sample.expected;
    clearResult();
    saveDraft();
  }
  function initEditor() {
    if (window.CodeMirror) {
      editor = CodeMirror.fromTextArea($('code-editor'), {
        mode: 'python',
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
      editor.on('change', scheduleSave);
    } else {
      var fallback = $('code-editor');
      fallback.style.display = 'block';
      fallback.style.width = '100%';
      fallback.style.height = '100%';
      fallback.style.background = 'transparent';
      fallback.style.color = 'inherit';
      fallback.style.border = '0';
      fallback.style.padding = '12px';
      fallback.addEventListener('input', scheduleSave);
    }
  }
  function initContext() {
    if (!context || !context.title) return;
    var chip = $('problem-context');
    if (chip) {
      chip.textContent = context.title;
      chip.hidden = false;
      chip.title = context.title;
    }
    document.title = context.title + ' · ACM 模拟';
  }
  async function init() {
    setBusy(true);
    await refreshContext();
    setBusy(false);
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
      loadLanguage(this.value, true);
    });
    $('template-select').addEventListener('change', function () {
      currentTemplate = this.value || 'array';
      this.value = currentTemplate;
      setCode(templateSource(currentLanguage, currentTemplate));
      scheduleSave();
      clearResult();
      setRuntimeStatus(languageLabel() + ' · 已载入模板', 'ready');
      $('status-info').textContent = '已载入输入模板';
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
        saveDraft();
        setSample(this.value);
      });
    }
    $('reset-btn').addEventListener('click', resetCode);
    $('save-code-btn').addEventListener('click', function () {
      var blob = new Blob([getCode()], { type: 'text/plain;charset=utf-8' });
      var link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'solution.' + (currentLanguage === 'java' ? 'java' : 'py');
      document.body.appendChild(link);
      link.click();
      setTimeout(function () { URL.revokeObjectURL(link.href); link.remove(); }, 0);
    });
    $('clear-input-btn').addEventListener('click', function () {
      $('stdin-area').value = '';
      scheduleSave();
      $('stdin-area').focus();
    });
    $('stdin-area').addEventListener('input', scheduleSave);
    $('expected-area').addEventListener('input', scheduleSave);
    $('code-editor').addEventListener('input', scheduleSave);
    var navToggle = $('nav-toggle');
    if (navToggle) {
      navToggle.addEventListener('click', function () {
        var open = document.querySelector('.nav-menu').classList.toggle('active');
        navToggle.setAttribute('aria-expanded', String(open));
      });
    }
    if ($('template-select')) $('template-select').value = currentTemplate;
    loadLanguage(currentLanguage, true);
    window.addEventListener('beforeunload', saveDraft);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

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
  var currentSampleIndex = 0;
  var saveTimer = null;
  var running = false;

  function $(id) { return document.getElementById(id); }
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
      }
      var raw = sessionStorage.getItem(CONTEXT_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (_) { return null; }
  }
  function contextCode(language) {
    return context && context.codes && typeof context.codes[language] === 'string'
      ? context.codes[language] : DEFAULT_CODE[language];
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
      option.textContent = '样例 ' + (index + 1) + ' / ' + items.length;
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
    setCode(codeDraft != null ? codeDraft : contextCode(currentLanguage));
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
  function normalizeOutput(value) {
    return String(value == null ? '' : value).replace(/\r\n/g, '\n').replace(/\r/g, '\n')
      .split('\n').map(function (line) { return line.replace(/[ \t]+$/g, ''); })
      .join('\n').replace(/\n+$/g, '');
  }
  function compare(actual) {
    var expected = valueOf('expected-area');
    var box = $('diff-result');
    if (!expected.trim()) { box.textContent = ''; box.className = 'diff-result'; return; }
    if (normalizeOutput(actual) === normalizeOutput(expected)) {
      box.textContent = 'ACCEPTED';
      box.className = 'diff-result match';
    } else {
      box.textContent = 'WRONG ANSWER';
      box.className = 'diff-result mismatch';
    }
  }
  function showOutput(text, isError) {
    var output = $('stdout-area');
    output.textContent = text || '（无输出）';
    output.className = 'io-output' + (isError ? ' has-error' : '');
  }
  async function runCode() {
    if (running) return;
    running = true;
    $('run-btn').disabled = true;
    setRuntimeStatus(languageLabel() + ' · 运行中…', 'loading');
    $('run-status').textContent = '运行中';
    $('run-status').className = 'run-status running';
    $('status-info').textContent = '运行中…';
    try {
      var response = await fetch('/api/practice/run', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          language: currentLanguage,
          code: getCode(),
          stdin: valueOf('stdin-area')
        })
      });
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
      compare(stdout);
    } catch (_) {
      showOutput('无法连接执行服务。', true);
      $('run-status').textContent = '连接失败';
      $('run-status').className = 'run-status error';
      setRuntimeStatus(languageLabel() + ' · 服务不可用', 'error');
    } finally {
      running = false;
      $('run-btn').disabled = false;
    }
  }
  async function judgeAll() {
    if (running) return;
    var items = sampleList();
    if (!items.length) {
      await runCode();
      return;
    }
    running = true;
    var runBtn = $('run-btn');
    var judgeBtn = $('judge-all-btn');
    var code = getCode();
    var passed = 0;
    var total = items.length;
    var totalCompileMs = 0;
    var totalRunMs = 0;
    var lines = [];
    if (runBtn) runBtn.disabled = true;
    if (judgeBtn) judgeBtn.disabled = true;
    $('run-status').textContent = '评测中';
    $('run-status').className = 'run-status running';
    $('status-info').textContent = '评测全部样例…';
    try {
      for (var index = 0; index < items.length; index += 1) {
        var sample = items[index];
        setRuntimeStatus(languageLabel() + ' · 样例 ' + (index + 1) + '/' + total, 'loading');
        var response = await fetch('/api/practice/run', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            language: currentLanguage,
            code: code,
            stdin: sample.input || ''
          })
        });
        var payload = {};
        try { payload = await response.json(); } catch (_) {}
        var status = payload.status || 'unknown';
        var actual = payload.stdout || '';
        var expected = sample.expected || '';
        var caseOk = response.ok && status === 'ok' && normalizeOutput(actual) === normalizeOutput(expected);
        if (caseOk) passed += 1;
        totalCompileMs += Number(payload.compile_time_ms) || 0;
        totalRunMs += Number(payload.run_time_ms) || 0;
        lines.push('Case ' + (index + 1) + '/' + total + ': ' + (caseOk ? 'ACCEPTED' : ({
          ok: 'WRONG ANSWER',
          compile_error: 'COMPILE ERROR',
          runtime_error: 'RUNTIME ERROR',
          timeout: 'TIME LIMIT EXCEEDED',
          output_limit: 'OUTPUT LIMIT EXCEEDED',
          busy: 'BUSY'
        }[status] || (response.status === 401 ? 'UNAUTHORIZED' : 'ERROR'))));
        if (!caseOk && payload.stderr) {
          lines.push('  ' + String(payload.stderr).split('\n')[0].slice(0, 180));
        }
        if (response.status === 401) break;
      }
      var allPassed = passed === total;
      lines.push('');
      lines.push(allPassed ? '全部样例通过（' + passed + '/' + total + '）' : '样例通过 ' + passed + '/' + total);
      showOutput(lines.join('\n'), !allPassed);
      $('run-status').textContent = allPassed ? ('ACCEPTED ' + passed + '/' + total) : ('FAILED ' + passed + '/' + total);
      $('run-status').className = 'run-status ' + (allPassed ? 'success' : 'error');
      $('diff-result').textContent = allPassed ? 'ACCEPTED' : 'WRONG ANSWER';
      $('diff-result').className = 'diff-result ' + (allPassed ? 'match' : 'mismatch');
      setRuntimeStatus(languageLabel() + ' · 就绪', 'ready');
      $('status-info').textContent = allPassed ? '全部样例通过' : '样例未全部通过';
      $('status-time').textContent = [
        totalCompileMs ? ('编译合计 ' + totalCompileMs + ' ms') : '',
        totalRunMs ? ('运行合计 ' + totalRunMs + ' ms') : ''
      ].filter(Boolean).join(' · ');
    } catch (_) {
      showOutput('无法连接执行服务。', true);
      $('run-status').textContent = '连接失败';
      $('run-status').className = 'run-status error';
      setRuntimeStatus(languageLabel() + ' · 服务不可用', 'error');
    } finally {
      running = false;
      if (runBtn) runBtn.disabled = false;
      if (judgeBtn) judgeBtn.disabled = false;
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
    setCode(contextCode(currentLanguage));
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
        lineWrapping: false,
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
  function init() {
    initTheme();
    initEditor();
    initContext();
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
      var template = this.value;
      if (!template || !TEMPLATES[template]) return;
      setCode(TEMPLATES[template][currentLanguage]);
      scheduleSave();
      this.value = '';
    });
    $('run-btn').addEventListener('click', runCode);
    if ($('judge-all-btn')) $('judge-all-btn').addEventListener('click', judgeAll);
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
    loadLanguage(currentLanguage, true);
    window.addEventListener('beforeunload', saveDraft);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

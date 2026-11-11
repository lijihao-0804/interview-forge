(function () {
  'use strict';

  var CONTEXT_KEY = 'interviewforge.practice.context';
  var CONTEXT_PREFIX = 'interviewforge.practice.context:';
  var DRAFT_PREFIX = 'interviewforge.practice.draft:';
  var THEME_KEY = 'forge-theme';
  var THEME_MODES = [
    { v: 'system', icon: '◐', label: '跟随系统' },
    { v: 'light', icon: '☀', label: '浅色' },
    { v: 'dark', icon: '☾', label: '深色' }
  ];
  var DEFAULT_CODE = {
    python: 'import sys\n\n\ndef solve():\n    data = sys.stdin.read().split()\n    if not data:\n        return\n    print(sum(int(x) for x in data))\n\n\nif __name__ == "__main__":\n    solve()\n',
    java: 'import java.io.*;\nimport java.util.*;\n\npublic class Main {\n    public static void main(String[] args) throws Exception {\n        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));\n        String line;\n        long sum = 0;\n        while ((line = br.readLine()) != null) {\n            for (String part : line.trim().split("\\\\s+")) {\n                if (!part.isEmpty()) sum += Long.parseLong(part);\n            }\n        }\n        System.out.println(sum);\n    }\n}\n'
  };

  var editor = null;
  var context = readContext();
  var currentLanguage = queryLanguage() || (context && context.language) || 'python';
  var saveTimer = null;
  var running = false;

  function $(id) { return document.getElementById(id); }
  function text(value) { return value == null ? '' : String(value); }
  function queryLanguage() {
    try { return new URLSearchParams(location.search).get('lang') || ''; } catch (_) { return ''; }
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
  function contextCode(lang) {
    return context && context.codes && typeof context.codes[lang] === 'string'
      ? context.codes[lang] : DEFAULT_CODE[lang];
  }
  function contextSample() {
    var samples = context && context.samples;
    return Array.isArray(samples) && samples.length ? samples[0] : { input: '', expected: '' };
  }
  function draftKey(lang, field) { return DRAFT_PREFIX + (context && context.id ? context.id : 'scratch') + ':' + lang + ':' + field; }
  function getDraft(lang, field) {
    try { return localStorage.getItem(draftKey(lang, field)); } catch (_) { return null; }
  }
  function setDraft(lang, field, value) {
    try { localStorage.setItem(draftKey(lang, field), value); } catch (_) {}
  }
  function clearDraft(lang) {
    ['code', 'stdin', 'expected'].forEach(function (field) {
      try { localStorage.removeItem(draftKey(lang, field)); } catch (_) {}
    });
  }
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 250);
  }
  function saveDraft() {
    setDraft(currentLanguage, 'code', getCode());
    setDraft(currentLanguage, 'stdin', $('stdinArea').value);
    setDraft(currentLanguage, 'expected', $('expectedArea').value);
  }
  function getCode() { return editor ? editor.getValue() : $('editorFallback').value; }
  function setCode(value) {
    if (editor) editor.setValue(value);
    else $('editorFallback').value = value;
  }
  function setEditorMode(lang) {
    if (!editor) return;
    editor.setOption('mode', lang === 'java' ? 'text/x-java' : 'python');
  }
  function updateLanguageUi() {
    $('language').value = currentLanguage;
    $('languageHint').textContent = currentLanguage === 'java' ? 'Java 17 · ACM 模式' : 'Python 3 · ACM 模式';
    setEditorMode(currentLanguage);
  }
  function loadLanguage(lang, preserveDraft) {
    currentLanguage = lang;
    var codeDraft = preserveDraft ? getDraft(lang, 'code') : null;
    var stdinDraft = preserveDraft ? getDraft(lang, 'stdin') : null;
    var expectedDraft = preserveDraft ? getDraft(lang, 'expected') : null;
    var sample = contextSample();
    setCode(codeDraft != null ? codeDraft : contextCode(lang));
    $('stdinArea').value = stdinDraft != null ? stdinDraft : sample.input;
    $('expectedArea').value = expectedDraft != null ? expectedDraft : sample.expected;
    $('diffResult').textContent = '';
    $('diffResult').className = 'practice-diff';
    updateLanguageUi();
    setRuntime('就绪', 'idle');
  }
  function setRuntime(message, state) {
    var el = $('runtimeStatus');
    el.textContent = message;
    el.className = 'practice-runtime ' + (state || '');
  }
  function getThemeMode() {
    try {
      var value = localStorage.getItem(THEME_KEY);
      return THEME_MODES.some(function (item) { return item.v === value; }) ? value : 'system';
    } catch (_) { return 'system'; }
  }
  function paintTheme(mode) {
    var item = THEME_MODES.filter(function (candidate) { return candidate.v === mode; })[0] || THEME_MODES[0];
    if ($('practiceThemeIcon')) $('practiceThemeIcon').textContent = item.icon;
    if ($('practiceThemeLabel')) $('practiceThemeLabel').textContent = item.label;
    if ($('practiceThemeBtn')) $('practiceThemeBtn').title = '主题：' + item.label;
  }
  function applyTheme(mode, persist) {
    var root = document.documentElement;
    if (mode === 'light' || mode === 'dark') root.setAttribute('data-theme', mode);
    else root.removeAttribute('data-theme');
    if (persist !== false) {
      try { localStorage.setItem(THEME_KEY, mode); } catch (_) {}
    }
    paintTheme(mode);
  }
  function initTheme() {
    var button = $('practiceThemeBtn');
    if (!button) return;
    var mode = getThemeMode();
    applyTheme(mode, false);
    button.addEventListener('click', function () {
      var next = THEME_MODES[(THEME_MODES.findIndex(function (item) { return item.v === getThemeMode(); }) + 1) % THEME_MODES.length];
      applyTheme(next.v);
    });
    window.addEventListener('storage', function (event) {
      if (event.key === THEME_KEY) applyTheme(event.newValue || 'system', false);
    });
  }
  function normalizeOutput(value) {
    return text(value).replace(/\r\n/g, '\n').replace(/\r/g, '\n')
      .split('\n').map(function (line) { return line.replace(/[ \t]+$/g, ''); })
      .join('\n').replace(/\n+$/g, '');
  }
  function setOutput(stdout, stderr) {
    $('stdoutArea').textContent = stdout || '（无输出）';
    $('stderrArea').textContent = stderr || '';
    $('stderrArea').className = 'stderr';
  }
  function compare(actual) {
    var expected = $('expectedArea').value;
    var box = $('diffResult');
    if (!expected.trim()) { box.textContent = ''; box.className = 'practice-diff'; return; }
    if (normalizeOutput(actual) === normalizeOutput(expected)) {
      box.textContent = 'ACCEPTED';
      box.className = 'practice-diff ok';
    } else {
      box.textContent = 'WRONG ANSWER';
      box.className = 'practice-diff bad';
    }
  }
  function showResult(result) {
    var status = result.status || 'unknown';
    var labels = {
      ok: '运行完成',
      compile_error: 'COMPILE ERROR / 编译错误',
      runtime_error: 'RUNTIME ERROR / 运行错误',
      timeout: 'TIME LIMIT EXCEEDED / 超时',
      output_limit: 'OUTPUT LIMIT EXCEEDED / 输出超限',
      invalid_language: '语言不支持',
      busy: '当前已有一次执行',
      internal_error: '执行服务异常'
    };
    setOutput(result.stdout, result.stderr);
    setRuntime(labels[status] || status, status === 'ok' ? 'ok' : 'bad');
    $('runMeta').textContent = [
      result.compile_time_ms ? ('编译 ' + result.compile_time_ms + ' ms') : '',
      result.run_time_ms ? ('运行 ' + result.run_time_ms + ' ms') : '',
      result.timed_out ? '超时' : '',
      result.output_truncated ? '输出已截断' : ''
    ].filter(Boolean).join(' · ');
    compare(result.stdout || '');
  }
  async function runCode() {
    if (running) return;
    running = true;
    $('runBtn').disabled = true;
    setRuntime('运行中…', 'loading');
    $('stderrArea').textContent = '';
    try {
      var response = await fetch('/api/practice/run', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: currentLanguage, code: getCode(), stdin: $('stdinArea').value })
      });
      var payload = {};
      try { payload = await response.json(); } catch (_) {}
      if (response.status === 401) {
        setRuntime('请先登录', 'bad');
        $('stdoutArea').textContent = '登录后才能运行代码。';
        return;
      }
      if (response.status === 429) {
        setRuntime('已有一次执行正在进行，请稍后重试', 'bad');
        return;
      }
      if (!response.ok) {
        setRuntime((payload && payload.error) || '执行失败', 'bad');
        return;
      }
      showResult(payload);
    } catch (_) {
      setRuntime('无法连接执行服务', 'bad');
    } finally {
      running = false;
      $('runBtn').disabled = false;
    }
  }
  function resetCode() {
    clearDraft(currentLanguage);
    var sample = contextSample();
    setCode(contextCode(currentLanguage));
    $('stdinArea').value = sample.input;
    $('expectedArea').value = sample.expected;
    $('diffResult').textContent = '';
    $('diffResult').className = 'practice-diff';
    setRuntime('已重置', 'idle');
    saveDraft();
  }
  function initEditor() {
    if (window.CodeMirror) {
      editor = CodeMirror.fromTextArea($('editorFallback'), {
        lineNumbers: true,
        mode: 'python',
        indentUnit: 4,
        tabSize: 4,
        lineWrapping: false,
        extraKeys: { 'Ctrl-Enter': runCode, 'Cmd-Enter': runCode }
      });
      editor.on('change', scheduleSave);
    } else {
      $('editorFallback').style.display = 'block';
      $('editorFallback').addEventListener('input', scheduleSave);
    }
  }
  function init() {
    initTheme();
    initEditor();
    var sampleHint = $('sampleHint');
    if (context && context.title) {
      if ($('contextTitle')) $('contextTitle').textContent = context.title;
      if ($('practiceContext')) $('practiceContext').hidden = false;
      if ($('contextMeta')) {
        var meta = [];
        if (context.url) meta.push(context.url);
        if (Array.isArray(context.samples) && context.samples.length) meta.push(context.samples.length + ' 组样例');
        $('contextMeta').textContent = meta.join(' · ');
      }
      document.title = context.title + ' · ACM 模拟';
      $('sourceNote').textContent = context.url ? ('来源：' + context.url) : '';
    } else {
      $('sourceNote').textContent = '未从题目页带入上下文，可直接粘贴代码运行。';
    }
    if (sampleHint) {
      sampleHint.textContent = context && Array.isArray(context.samples) && context.samples.length
        ? ('已载入 ' + context.samples.length + ' 组样例 · 可直接运行')
        : '希望这里有一组样例';
    }
    $('language').addEventListener('change', function () {
      saveDraft();
      try {
        var url = new URL(location.href);
        url.searchParams.set('lang', this.value);
        history.replaceState(null, '', url.toString());
      } catch (_) {}
      loadLanguage(this.value, true);
    });
    $('runBtn').addEventListener('click', runCode);
    $('resetBtn').addEventListener('click', resetCode);
    $('clearOutput').addEventListener('click', function () {
      setOutput('', '');
      $('diffResult').textContent = '';
      $('diffResult').className = 'practice-diff';
      setRuntime('就绪', 'idle');
    });
    $('stdinArea').addEventListener('input', scheduleSave);
    $('expectedArea').addEventListener('input', scheduleSave);
    $('editorFallback').addEventListener('input', scheduleSave);
    loadLanguage(currentLanguage, true);
    window.addEventListener('beforeunload', saveDraft);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

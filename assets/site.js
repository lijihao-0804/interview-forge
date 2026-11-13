function fallbackCopy(text) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  let copied = false;
  try { copied = document.execCommand('copy'); } catch (_) { copied = false; }
  textarea.remove();
  return copied;
}

document.querySelectorAll('.markdown-body table').forEach((table) => {
  if (table.parentElement?.classList.contains('table-wrap')) return;
  const wrapper = document.createElement('div');
  wrapper.className = 'table-wrap';
  wrapper.setAttribute('role', 'region');
  wrapper.setAttribute('aria-label', '数据表，可横向滚动');
  table.parentNode.insertBefore(wrapper, table);
  wrapper.appendChild(table);
});

document.querySelectorAll('.markdown-body pre').forEach((pre) => {
  if (pre.parentElement?.classList.contains('code-block')) return;
  const wrapper = document.createElement('div');
  wrapper.className = 'code-block';
  const toolbar = document.createElement('div');
  toolbar.className = 'code-toolbar';
  const code = pre.querySelector('code');
  const languageClass = [...(code?.classList || [])].find((item) => item.startsWith('language-'));
  const language = languageClass ? languageClass.replace('language-', '') : 'code';
  const label = document.createElement('span');
  label.textContent = language.toUpperCase();
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'copy-code';
  button.textContent = '复制代码';
  button.setAttribute('aria-label', `复制${language === 'code' ? '' : language + ' '}代码`);
  button.addEventListener('click', async () => {
    const text = code?.innerText || pre.innerText;
    let copied = false;
    if (navigator.clipboard?.writeText) {
      try { await navigator.clipboard.writeText(text); copied = true; } catch (_) { copied = false; }
    }
    if (!copied) copied = fallbackCopy(text);
    button.textContent = copied ? '已复制' : '请手动复制';
    setTimeout(() => button.textContent = '复制代码', 1400);
  });
  const wrapButton = document.createElement('button');
  wrapButton.type = 'button';
  wrapButton.className = 'copy-code';
  wrapButton.textContent = '换行';
  wrapButton.setAttribute('aria-pressed', 'false');
  wrapButton.setAttribute('aria-label', '切换代码长行自动换行');
  wrapButton.addEventListener('click', () => {
    const nowrap = pre.classList.toggle('code-nowrap');
    const wrapped = pre.classList.toggle('code-wrap', !nowrap);
    wrapButton.setAttribute('aria-pressed', String(wrapped));
    wrapButton.textContent = wrapped ? '原样' : '换行';
  });
  toolbar.append(label, button, wrapButton);
  pre.parentNode.insertBefore(wrapper, pre);
  wrapper.append(toolbar, pre);
});

const readerVisualFrames = [...document.querySelectorAll('iframe.reader-visual-frame')];
const pendingVisualHeights = new Map();
let visualHeightFrame = 0;
const flushVisualHeights = () => {
  visualHeightFrame = 0;
  pendingVisualHeights.forEach((nextHeight, frame) => {
    if (Math.abs(frame.getBoundingClientRect().height - nextHeight) > 2) {
      frame.style.height = `${nextHeight}px`;
    }
  });
  pendingVisualHeights.clear();
};
window.addEventListener('message', (event) => {
  if (event.data?.type !== 'hot100:visual-height') return;
  const frame = readerVisualFrames.find((item) => item.contentWindow === event.source);
  const height = Math.ceil(Number(event.data.height));
  if (!frame || !Number.isFinite(height) || height < 240) return;
  const nextHeight = height + 2;
  pendingVisualHeights.set(frame, nextHeight);
  if (!visualHeightFrame) visualHeightFrame = requestAnimationFrame(flushVisualHeights);
});
readerVisualFrames.forEach((frame) => {
  frame.addEventListener('load', () => {
    frame.contentWindow?.postMessage({ type: 'hot100:measure' }, '*');
  });
});

/* ===== 阅读进度条 + 表格溢出遮罩 ===== */
(function () {
  const main = document.querySelector('.markdown-body');
  if (!main) return;
  const bar = document.createElement('div');
  bar.className = 'read-progress';
  document.body.appendChild(bar);
  const update = () => {
    const rect = main.getBoundingClientRect();
    const total = Math.max(rect.height - window.innerHeight, 1);
    const passed = Math.min(Math.max(-rect.top, 0), total);
    bar.style.width = Math.round((passed / total) * 100) + '%';
  };
  update();
  let progressFrame = 0;
  const scheduleUpdate = () => {
    if (progressFrame) return;
    progressFrame = requestAnimationFrame(() => {
      progressFrame = 0;
      update();
    });
  };
  window.addEventListener('scroll', scheduleUpdate, { passive: true });
  window.addEventListener('resize', scheduleUpdate);
  document.querySelectorAll('.table-wrap').forEach((wrap) => {
    const check = () => wrap.classList.toggle('has-overflow', wrap.scrollWidth > wrap.clientWidth + 4);
    check();
    wrap.addEventListener('scroll', () => {
      wrap.classList.toggle('has-overflow', wrap.scrollWidth - wrap.scrollLeft > wrap.clientWidth + 4);
    }, { passive: true });
  });
})();

/* ===== 多语言题解：语言偏好、切换条与可见面板 ===== */
(function () {
  const LANG_NAMES = { java: 'Java', cpp: 'C++', python: 'Python', go: 'Go', c: 'C' };
  const SUPPORTED = new Set(Object.keys(LANG_NAMES));

  function getLang() {
    try {
      const value = localStorage.getItem('forge-lang') || 'java';
      return SUPPORTED.has(value) ? value : 'java';
    } catch (_) { return 'java'; }
  }

  function syncServerPreference(lang) {
    function sync(auth) {
      // 游客只在本地保存偏好；没有 authenticated 状态时绝不写 profile。
      auth.ready.then((session) => {
        if (!session || session.status !== 'authenticated') return;
        fetch('/api/profile', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lang })
        }).catch(() => {});
      }).catch(() => {});
    }
    if (window.InterviewForgeAuth && window.InterviewForgeAuth.ready) sync(window.InterviewForgeAuth);
    else document.addEventListener('interviewforge:auth-ready', () => {
      if (window.InterviewForgeAuth && window.InterviewForgeAuth.ready) sync(window.InterviewForgeAuth);
    }, { once: true });
  }

  function setLang(lang, syncServer = true) {
    if (!SUPPORTED.has(lang)) lang = 'java';
    try { localStorage.setItem('forge-lang', lang); } catch (_) { }
    applyLang(lang);
    document.dispatchEvent(new CustomEvent('forge-lang-change', { detail: { lang } }));
    if (syncServer) syncServerPreference(lang);
  }

  function applyLang(lang) {
    const main = document.querySelector('.markdown-body.hot100-solution, .markdown-body');
    if (!main) return;
    const blocks = [...main.querySelectorAll(
      '.language-panel[data-lang], .lang-section[data-lang], ' +
      '[data-lang-scope][data-lang], .codehilite[data-lang]'
    )].filter((block) => Object.prototype.hasOwnProperty.call(LANG_NAMES, block.dataset.lang));
    if (!blocks.length) return;
    const available = new Set(blocks.map((block) => block.dataset.lang));
    const requested = SUPPORTED.has(lang) ? lang : 'java';
    const effectiveLang = available.has(requested)
      ? requested
      : (available.has('java') ? 'java' : (available.values().next().value || 'java'));
    document.documentElement.dataset.codeLanguage = effectiveLang;
    main.dataset.activeLanguage = effectiveLang;
    blocks.forEach((block) => { block.style.display = (block.dataset.lang === effectiveLang) ? '' : 'none'; });
    const bar = buildBar();
    bar.dataset.lang = effectiveLang;
    bar.querySelectorAll('.forge-lang-chip').forEach((chip) => {
      const availableForChip = available.has(chip.dataset.lang);
      chip.classList.toggle('active', chip.dataset.lang === effectiveLang);
      chip.classList.toggle('unavailable', !availableForChip);
      chip.disabled = !availableForChip;
    });
    main.querySelectorAll('iframe').forEach((frame) => {
      try { frame.contentWindow?.postMessage({ type: 'forge-lang', lang: effectiveLang }, '*'); } catch (_) { }
    });
  }

  function buildBar() {
    let bar = document.getElementById('forge-lang-bar');
    if (bar) return bar;
    bar = document.createElement('div');
    bar.id = 'forge-lang-bar';
    bar.className = 'forge-lang-bar';
    const label = document.createElement('span');
    label.className = 'flb-label';
    label.textContent = '题解语言';
    bar.appendChild(label);
    Object.keys(LANG_NAMES).forEach((lang) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'forge-lang-chip';
      chip.dataset.lang = lang;
      chip.textContent = LANG_NAMES[lang];
      chip.addEventListener('click', () => setLang(lang, true));
      bar.appendChild(chip);
    });
    const main = document.querySelector('.markdown-body');
    if (main && main.parentNode) main.parentNode.insertBefore(bar, main);
    return bar;
  }

  window.InterviewForgeLanguage = Object.freeze({ get: getLang, set: setLang });
  document.addEventListener('forge-lang-change', (event) => applyLang(event.detail.lang));
  window.addEventListener('storage', (event) => {
    if (!event || event.key === null || event.key === 'forge-lang') applyLang(getLang());
  });
  window.addEventListener('message', (event) => {
    if (event && event.data && event.data.type === 'forge-lang' && event.data.lang && event.data.lang !== getLang()) {
      setLang(event.data.lang, true);
    }
  });
  document.querySelector('.markdown-body')?.querySelectorAll('iframe').forEach((frame) => {
    frame.addEventListener('load', () => {
      try {
        frame.contentWindow?.postMessage({
          type: 'forge-lang',
          lang: document.documentElement.dataset.codeLanguage || getLang()
        }, '*');
      } catch (_) { }
    });
  });
  applyLang(getLang());

  function applyAccountLanguage(session) {
    const me = session && session.user;
    if (!session || session.status !== 'authenticated' || !me || !SUPPORTED.has(me.lang)) return;
    try { localStorage.setItem('forge-lang', me.lang); } catch (_) { }
    applyLang(me.lang);
  }
  const auth = window.InterviewForgeAuth;
  if (auth && auth.getState) applyAccountLanguage(auth.getState());
  if (auth && auth.ready) auth.ready.then(applyAccountLanguage).catch(() => {});
  else document.addEventListener('interviewforge:auth-ready', (event) => applyAccountLanguage(event.detail), { once: true });
})();

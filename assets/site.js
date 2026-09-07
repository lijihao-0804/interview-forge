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
window.addEventListener('message', (event) => {
  if (event.data?.type !== 'hot100:visual-height') return;
  const frame = readerVisualFrames.find((item) => item.contentWindow === event.source);
  const height = Math.ceil(Number(event.data.height));
  if (!frame || !Number.isFinite(height) || height < 240) return;
  const nextHeight = height + 2;
  if (Math.abs(frame.getBoundingClientRect().height - nextHeight) > 2) frame.style.height = `${nextHeight}px`;
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
  window.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update);
  document.querySelectorAll('.table-wrap').forEach((wrap) => {
    const check = () => wrap.classList.toggle('has-overflow', wrap.scrollWidth > wrap.clientWidth + 4);
    check();
    wrap.addEventListener('scroll', () => {
      wrap.classList.toggle('has-overflow', wrap.scrollWidth - wrap.scrollLeft > wrap.clientWidth + 4);
    }, { passive: true });
  });
})();

/* ===== 多语言题解：语言偏好应用 + 切换条 ===== */
(function () {
  const LANG_NAMES = { java: 'Java', cpp: 'C++', python: 'Python', go: 'Go', c: 'C' };
  function getLang() {
    try { return localStorage.getItem('forge-lang') || 'java'; } catch (e) { return 'java'; }
  }
  function setLang(lang, syncServer) {
    try { localStorage.setItem('forge-lang', lang); } catch (e) { }
    applyLang(lang);
    if (syncServer) {
      fetch('/api/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lang })
      });
    }
    document.dispatchEvent(new CustomEvent('forge-lang-change', { detail: { lang } }));
  }
  function applyLang(lang) {
    const main = document.querySelector('.markdown-body');
    if (!main) return;
    if (!main.querySelector('.codehilite[data-lang], .lang-section')) return;
    const blocks = [...document.querySelectorAll('.markdown-body .lang-section[data-lang], .markdown-body .codehilite[data-lang]')];
    const available = new Set(blocks.map((block) => block.dataset.lang));
    const effectiveLang = available.has(lang) ? lang : (available.has('java') ? 'java' : (available.values().next().value || lang));
    blocks.forEach((block) => { block.style.display = (block.dataset.lang === effectiveLang) ? '' : 'none'; });
    const bar = buildBar();
    bar.dataset.lang = effectiveLang;
    bar.querySelectorAll('.forge-lang-chip').forEach((chip) => {
      const l = chip.dataset.lang;
      chip.classList.toggle('active', l === effectiveLang);
      chip.classList.toggle('unavailable', l !== 'java' && !available.has(l));
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
    Object.keys(LANG_NAMES).forEach((l) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'forge-lang-chip';
      chip.dataset.lang = l;
      chip.textContent = LANG_NAMES[l];
      chip.onclick = () => setLang(l, true);
      bar.appendChild(chip);
    });
    const main = document.querySelector('.markdown-body');
    if (main && main.parentNode) main.parentNode.insertBefore(bar, main);
    return bar;
  }
  document.addEventListener('forge-lang-change', (e) => applyLang(e.detail.lang));
  fetch('/api/me', { cache: 'no-store' })
    .then((r) => (r.ok ? r.json() : null))
    .then((me) => {
      let lang = getLang();
      if (me && me.lang) {
        lang = me.lang;
        try { localStorage.setItem('forge-lang', me.lang); } catch (e) { }
      }
      applyLang(lang);
    })
    .catch(() => applyLang(getLang()));
})();

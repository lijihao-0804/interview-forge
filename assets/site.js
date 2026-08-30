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
  toolbar.append(label, button);
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

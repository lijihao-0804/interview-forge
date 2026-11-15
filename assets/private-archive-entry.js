/* The public shelf holds no private metadata. Every refresh authorizes on server. */
(() => {
  const host = document.getElementById('privateTeachingShelf');
  if (!host) return;
  let generation = 0;
  let pending;
  function clear() {
    generation++;
    if (pending) pending.abort();
    pending = null;
    host.hidden = true;
    host.style.display = 'none';
    host.replaceChildren();
    host.removeAttribute('aria-label');
  }
  async function refresh() {
    clear();
    if (document.visibilityState === 'hidden') return;
    const version = generation;
    const controller = new AbortController();
    pending = controller;
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch('/api/private-archive-status', {
        credentials: 'same-origin', cache: 'no-store', signal: controller.signal
      });
      if (!response.ok) return;
      const status = await response.json();
      const entry = status.entry;
      if (version !== generation || status.available !== true || !entry ||
          entry.url !== '/api/private-archive/index.html' ||
          typeof entry.title !== 'string' || typeof entry.description !== 'string') return;
      const card = document.createElement('article');
      card.className = 'module-card';
      const head = document.createElement('div');
      head.className = 'card-head';
      const icon = document.createElement('span');
      icon.className = 'module-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = '◇';
      icon.style.cssText = 'color:var(--brand);background:var(--brand-soft)';
      const title = document.createElement('h2');
      const link = document.createElement('a');
      link.href = entry.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = entry.title;
      title.append(link);
      head.append(icon, title);
      const description = document.createElement('p');
      description.className = 'module-meta';
      description.textContent = entry.description;
      const action = link.cloneNode(false);
      action.className = 'module-link';
      action.textContent = '进入学习 →';
      card.append(head, description, action);
      host.append(card);
      host.setAttribute('aria-label', entry.title);
      host.hidden = false;
      host.style.display = 'grid';
    } catch (_) {
      // Errors and missing configuration leave no private card or metadata.
    } finally {
      clearTimeout(timeout);
      if (pending === controller) pending = null;
    }
  }
  document.addEventListener('interviewforge:auth-change', event => {
    clear();
    if (event.detail && event.detail.status === 'authenticated') refresh();
  });
  addEventListener('storage', refresh);
  addEventListener('focus', refresh);
  addEventListener('pagehide', clear);
  addEventListener('pageshow', refresh);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') clear(); else refresh();
  });
  setInterval(refresh, 30000);
  refresh();
})();

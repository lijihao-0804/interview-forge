/* The public shelf holds no private metadata. Every refresh authorizes on server. */
(() => {
  const host = document.getElementById('privateTeachingShelf');
  const track = document.getElementById('projectNotesTrack');
  if (!host || !track) return;
  let generation = 0;
  let pending;
  let snapshot;
  function clear() {
    generation++;
    if (pending) pending.abort();
    pending = null;
    snapshot = null;
    track.hidden = true;
    track.style.display = 'none';
    host.hidden = true;
    host.style.display = 'none';
    host.replaceChildren();
    host.removeAttribute('aria-label');
  }
  function makeCard(entry) {
    const card = document.createElement('article');
    card.className = 'module-card';
    card.dataset.search = (entry.title + ' ' + entry.description).toLowerCase();
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
    return card;
  }
  async function refresh(background) {
    if (background === true && pending) return;
    if (background !== true) clear();
    if (document.visibilityState === 'hidden') return;
    const version = generation;
    const controller = new AbortController();
    pending = controller;
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch('/api/private-archive-status', {
        credentials: 'same-origin', cache: 'no-store', signal: controller.signal
      });
      if (!response.ok) throw new Error();
      const status = await response.json();
      if (version !== generation) return;
      const entries = Array.isArray(status.entries) ? status.entries : (status.available ? [status.entry] : []);
      const permitted = new Set(['/api/private-archive/index.html', '/library/development-history/index.html',
        '/library/voltedu-study/index.html']);
      const books = entries.filter(entry => entry && permitted.delete(entry.url) &&
        typeof entry.title === 'string' && typeof entry.description === 'string');
      if (!books.length) throw new Error();
      const next = JSON.stringify(books);
      if (snapshot === next) return;
      snapshot = next;
      host.replaceChildren(...books.map(makeCard));
      host.setAttribute('aria-label', '项目学习笔记');
      track.hidden = false;
      track.style.display = '';
      document.dispatchEvent(new CustomEvent('shelf-books-change'));
    } catch (_) {
      if (version !== generation) return;
      clear();
      document.dispatchEvent(new CustomEvent('shelf-books-change', {detail: 'unavailable'}));
    } finally {
      clearTimeout(timeout);
      if (pending === controller) pending = null;
    }
  }
  document.addEventListener('interviewforge:auth-change', event => {
    clear();
    if (event.detail && event.detail.status === 'authenticated') refresh();
    else if (event.detail && event.detail.status === 'guest') {
      document.dispatchEvent(new CustomEvent('shelf-books-change', {detail: 'unavailable'}));
    }
  });
  addEventListener('storage', refresh);
  addEventListener('focus', refresh);
  addEventListener('pagehide', clear);
  addEventListener('pageshow', refresh);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') clear(); else refresh();
  });
  setInterval(() => refresh(true), 30000);
  refresh();
})();

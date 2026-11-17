/* Integration chrome only. The supplied archive scripts and animations are untouched. */
(() => {
  const assistant = window.InterviewForgeAI;
  if (assistant?.getPageContext) {
    const baseContext = assistant.getPageContext;
    assistant.getPageContext = () => {
      const context = baseContext();
      const isAgentHub = location.pathname.startsWith('/api/private-archive/');
      const view = new URLSearchParams(location.hash.slice(1)).get('view');
      let root = document.querySelector('main article, main');
      let title = document.title;
      if (isAgentHub) {
        const frame = document.querySelector('#archiveWorkspace > iframe:not([hidden])');
        root = document.querySelector('#resources:not([hidden]) #resourceText, #learning:not([hidden]) #chapterArticle, #recentHistory:not([hidden]) #recentArticle');
        if (!root && frame) {
          root = frame.contentDocument?.body;
          title += ' · ' + (document.querySelector('#historyView option:checked')?.textContent || frame.title);
        }
        const chapter = root?.querySelector('h1')?.textContent;
        if (chapter) title += ' · ' + chapter.trim();
      } else {
        root = root?.querySelector('article') || root;
      }
      context.path = (location.pathname + location.hash).slice(0, 512);
      context.page_type = 'library/chapter';
      context.title = title.slice(0, 200);
      if (!root) return context;
      const doc = root.ownerDocument;
      const panel = root.closest('#bookScroll, #recentHistory');
      const top = Math.max(0, panel?.getBoundingClientRect().top || 0);
      const bottom = Math.min(doc.defaultView.innerHeight, panel?.getBoundingClientRect().bottom ?? Infinity);
      const inView = el => {
        const rect = el.getBoundingClientRect();
        return rect.height > 0 && rect.width > 0 && rect.bottom > top && rect.top < bottom;
      };
      const headings = [...root.querySelectorAll('h1,h2,h3')];
      context.heading = (headings.find(inView)?.textContent || headings.filter(h => {
        const rect = h.getBoundingClientRect();
        return rect.height && rect.bottom <= top;
      }).pop()?.textContent || headings[0]?.textContent || view || title).trim().slice(0, 300);
      const fragments = [];
      let length = 0;
      for (const el of root.matches('pre') ? [root] : root.querySelectorAll('p,li,pre,figcaption,td')) {
        if (!inView(el)) continue;
        const value = el.innerText?.trim();
        if (value) { fragments.push(value); length += value.length; }
        if (length >= 1200) break;
      }
      if (fragments.length) context.chapter_excerpt = fragments.join(' ').replace(/\s+/g, ' ').slice(0, 1200);
      if (doc !== document) {
        const selection = String(doc.getSelection() || '').trim();
        if (selection) context.selected_text = selection.slice(0, 2000);
      }
      return context;
    };
  }
  // Some imported originals mark Mermaid on <code>, while the reader only
  // loads its SVG index when the enclosing <pre> has that class.
  const enhance = window.enhanceLearningContent;
  if (enhance) window.enhanceLearningContent = async root => {
    root.querySelectorAll('pre > code.language-mermaid,pre > code.lang-mermaid')
      .forEach(code => code.parentElement.classList.add('mermaid'));
    return enhance(root);
  };
  const actions = document.querySelector('.mast nav, .bar nav, .archive-actions');
  if (actions) {
    const back = document.createElement('a');
    back.href = '/library/index.html'; back.className = 'forge-archive-back'; back.textContent = '← 学习书架';
    actions.prepend(back);
  }
  // A restored history entry must reauthorize instead of showing a logged-out snapshot.
  addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
  const check = () => fetch('/api/private-archive-status', {credentials:'same-origin', cache:'no-store'})
    .then(response => {
      if (response.status === 401 || response.status === 403) {
        document.body.replaceChildren();
        location.replace('/pages/login.html?next=' + encodeURIComponent(location.pathname + location.search + location.hash));
      }
    }).catch(() => {});
  addEventListener('focus', check);
  setInterval(check, 60000);
})();

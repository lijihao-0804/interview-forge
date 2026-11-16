/* Integration chrome only. The supplied archive scripts and animations are untouched. */
(() => {
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

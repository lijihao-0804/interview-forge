(() => {
  const publicCards = [...document.querySelectorAll('#moduleGrid .module-card')];
  const tracks = [...document.querySelectorAll('[data-track-filter]')];
  const categories = [...document.querySelectorAll('[data-cat-filter]')];
  const groups = [...document.querySelectorAll('[data-track-group]')];
  const notes = document.getElementById('privateTeachingShelf');
  const notesTrack = document.getElementById('projectNotesTrack');
  const search = document.getElementById('shelfSearch');
  const scopeToggle = document.getElementById('shelfScope');
  const result = document.getElementById('shelfResult');
  const hits = document.getElementById('chapterHits');
  const params = new URLSearchParams(location.search);
  let track = params.get('track') || '';
  if (track === '面经与实战') track = '面经与项目实战';
  let category = params.get('cat') || '';
  let timer, indexPromise, generation = 0;

  function loadIndex() {
    if (!indexPromise) {
      indexPromise = fetch('search-index.json').then(response => {
        if (!response.ok) throw new Error();
        return response.json();
      }).catch(error => {
        indexPromise = null;
        throw error;
      });
    }
    return indexPromise;
  }

  function score(entry, query) {
    const at = entry.text.toLowerCase().indexOf(query);
    return (entry.title.toLowerCase().includes(query) ? 60 : 0) +
      (entry.module_title.toLowerCase().includes(query) ? 20 : 0) +
      (at < 0 ? 0 : 30 + Math.max(0, 10 - Math.floor(at / 200)));
  }

  function highlight(node, text, query) {
    const at = text.toLowerCase().indexOf(query);
    if (at < 0) { node.textContent = text; return; }
    const mark = document.createElement('mark');
    mark.textContent = text.slice(at, at + query.length);
    node.append(text.slice(0, at), mark, text.slice(at + query.length));
  }

  function showGroup(name, entries, query) {
    if (!entries.length) return;
    const group = document.createElement('div');
    group.className = 'hit-group';
    const heading = document.createElement('h2');
    heading.textContent = name + ' · ' + entries.length +
      (entries.length > 30 ? '（显示前 30 条）' : '');
    group.append(heading);
    for (const entry of entries.slice(0, 30)) {
      const link = document.createElement('a');
      link.href = entry.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.className = 'hit-item';
      const title = document.createElement('span');
      title.className = 'hit-title';
      highlight(title, entry.title, query);
      const detail = document.createElement('span');
      detail.className = 'hit-snip';
      const at = entry.text.toLowerCase().indexOf(query);
      const snippet = at < 0 ? '' : ' · ' + (at > 40 ? '…' : '') +
        entry.text.slice(Math.max(0, at - 40), at + query.length + 70);
      highlight(detail, entry.module_title + snippet, query);
      link.append(title, detail);
      group.append(link);
    }
    hits.append(group);
  }

  async function showContent(query, modules, version, scope, books) {
    try {
      const index = await loadIndex();
      if (version !== generation) return;
      const matches = index.filter(entry => modules.has(entry.module_id))
        .map(entry => ({entry, score: score(entry, query)}))
        .filter(match => match.score > 0).sort((a, b) => b.score - a.score);
      const chapters = [], questions = [];
      for (const {entry} of matches) {
        (entry.kind === 'question' ? questions : chapters).push(entry);
      }
      showGroup('章节', chapters, query);
      showGroup('题目', questions, query);
      hits.hidden = !matches.length;
      result.textContent = scope + ' · ' + (books || matches.length
        ? '书籍 ' + books + ' 本，章节 ' + chapters.length + ' 篇，题目 ' + questions.length + ' 道'
        : '没有匹配的书籍、章节或题目');
    } catch (_) {
      if (version !== generation) return;
      result.textContent = scope + ' · 匹配书籍 ' + books + ' 本，章节与题目索引加载失败。';
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.textContent = '重试';
      retry.addEventListener('click', apply);
      result.append(retry);
    }
  }

  function apply() {
    const version = ++generation;
    clearTimeout(timer);
    hits.replaceChildren();
    hits.hidden = true;
    const inNotes = track === notesTrack.dataset.trackFilter;
    const query = search.value.trim().toLowerCase();
    const selected = [track, category].filter(Boolean).join(' · ');
    if (!query || !selected) scopeToggle.checked = false;
    document.getElementById('shelfScopeLabel').hidden = !query || !selected;
    const globalSearch = !!query && !scopeToggle.checked;
    const modules = new Set();
    let books = 0, noteCount = 0;
    for (const card of publicCards) {
      const inScope = globalSearch || ((!track || card.dataset.track === track) &&
        (!category || card.dataset.category === category));
      if (inScope) {
        for (const id of (card.dataset.searchModules || card.dataset.moduleId || '').split(/\s+/)) {
          if (id) modules.add(id);
        }
      }
      card.hidden = !inScope || !card.dataset.search.includes(query);
      if (!card.hidden) books++;
    }
    for (const card of notes.children) {
      card.hidden = !(inNotes || globalSearch) || !card.dataset.search.includes(query);
      if (!card.hidden) noteCount++;
    }
    notes.hidden = !noteCount;
    notes.style.display = notes.hidden ? 'none' : 'grid';
    books += noteCount;
    document.getElementById('shelfBookHeading').hidden = !query || !books;
    for (const button of [...tracks, ...categories]) {
      const active = button.hasAttribute('data-track-filter')
        ? button.dataset.trackFilter === track : button.dataset.catFilter === category;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    }
    groups.forEach(group => { group.hidden = group.dataset.trackGroup !== track; });
    document.getElementById('chipRow').hidden = !track || inNotes;
    document.getElementById('chipAllCount').textContent = publicCards.filter(card => card.dataset.track === track).length;
    if (query) {
      const scope = globalSearch ? '全书架搜索' : '当前分类 · ' + selected;
      result.textContent = scope + ' · 匹配书籍 ' + books + ' 本';
      if (modules.size) {
        result.textContent += '，正在搜索章节和题目…';
        timer = setTimeout(() => showContent(query, modules, version, scope, books), 180);
      }
    } else {
      result.textContent = (selected || '全书架') + ' · ' + books + ' 本';
    }
    window.__shelfState = { track, cat: category };
    document.dispatchEvent(new Event('shelf-filter-change'));
  }

  tracks.forEach(button => button.addEventListener('click', () => {
    track = track === button.dataset.trackFilter ? '' : button.dataset.trackFilter;
    category = '';
    apply();
  }));
  categories.forEach(button => button.addEventListener('click', () => {
    category = button.dataset.catFilter;
    apply();
  }));
  search.addEventListener('input', apply);
  scopeToggle.addEventListener('change', apply);
  search.addEventListener('keydown', event => {
    if (event.key === 'Escape') { search.value = ''; apply(); }
  });
  document.addEventListener('shelf-books-change', event => {
    if (event.detail === 'unavailable' && track === notesTrack.dataset.trackFilter) {
      track = '';
      category = '';
    }
    apply();
  });
  apply();
})();

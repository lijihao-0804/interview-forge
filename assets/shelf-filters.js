(() => {
  const publicCards = [...document.querySelectorAll('#moduleGrid .module-card')];
  const tracks = [...document.querySelectorAll('[data-track-filter]')];
  const categories = [...document.querySelectorAll('[data-cat-filter]')];
  const groups = [...document.querySelectorAll('[data-track-group]')];
  const notes = document.getElementById('privateTeachingShelf');
  const notesTrack = document.getElementById('projectNotesTrack');
  const search = document.getElementById('shelfSearch');
  const params = new URLSearchParams(location.search);
  let track = params.get('track') || '';
  let category = params.get('cat') || '';

  function apply() {
    const inNotes = track === notesTrack.dataset.trackFilter;
    const query = search.value.trim().toLowerCase();
    let count = 0;
    const matches = card => !query || card.dataset.search.includes(query);
    for (const card of publicCards) {
      const visible = (!track || card.dataset.track === track) &&
        (!category || card.dataset.category === category) && matches(card);
      card.hidden = !visible;
      if (visible) count++;
    }
    for (const card of notes.children) {
      card.hidden = !inNotes || !matches(card);
      if (!card.hidden) count++;
    }
    notes.hidden = !inNotes || !count;
    notes.style.display = notes.hidden ? 'none' : 'grid';
    tracks.forEach(button => button.classList.toggle('active', button.dataset.trackFilter === track));
    categories.forEach(button => button.classList.toggle('active', button.dataset.catFilter === category));
    groups.forEach(group => { group.hidden = !!query || group.dataset.trackGroup !== track; });
    document.getElementById('chipRow').hidden = !track || inNotes || !!query;
    document.getElementById('chipAllCount').textContent = publicCards.filter(card => card.dataset.track === track).length;
    const scope = [track, category].filter(Boolean).join(' · ');
    const result = document.getElementById('shelfResult');
    if (inNotes) {
      result.textContent = query && !count ? '没有匹配的项目笔记' : '项目学习笔记 · ' + count + ' 本';
    } else if (!count) {
      result.textContent = query ? '当前范围没有匹配「' + query + '」的课程名' : '当前范围没有课程';
    } else if (query) {
      result.textContent = (scope ? '在「' + scope + '」内搜索' : '全局搜索') + '「' + query + '」：匹配 ' + count + ' 个课程';
    } else {
      result.textContent = scope ? scope + '：' + count + ' 个模块' : '共 ' + count + ' 个模块 · 点上方学习形态可按类型收窄';
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

document.addEventListener('DOMContentLoaded', () => {
  const sections = [...document.querySelectorAll('.admin-main > section')];
  const links = [...document.querySelectorAll('.admin-topic-nav a')];
  const fallback = document.getElementById('admin-feedback');
  const picker = document.getElementById('admin-section-select');
  let group;
  for (const item of document.querySelector('.admin-topic-nav').children) {
    if (item.matches('.nav-group')) {
      group = document.createElement('optgroup');
      group.label = item.textContent;
      picker.append(group);
    } else {
      group.append(new Option(item.textContent, item.hash));
    }
  }
  picker.addEventListener('change', () => { location.hash = picker.value; });
  let selecting = false;

  function renderRoute() {
    const target = document.getElementById(location.hash.slice(1)) || fallback;
    const section = target.closest('.admin-main > section') || fallback;
    sections.forEach(item => { item.hidden = item !== section; });
    for (const link of links) {
      const destination = document.getElementById(link.hash.slice(1));
      if (destination.closest('section') === section) {
        link.setAttribute('aria-current', 'page');
        picker.value = link.hash;
      }
      else link.removeAttribute('aria-current');
    }
    const panel = target.closest('[data-admin-panel], [data-ops-panel]');
    const tab = panel?.dataset.adminPanel || panel?.dataset.opsPanel;
    const button = tab
      ? section.querySelector('[data-admin-tab="' + tab + '"], [data-ops-tab="' + tab + '"]')
      : section.querySelector('[data-admin-tab].active, [data-ops-tab].active');
    if (button) {
      selecting = true;
      try { button.click(); } finally { selecting = false; }
    }
  }

  // Keep a bookmarkable address for the selected monitoring or operations tab.
  document.querySelector('.admin-main').addEventListener('click', event => {
    const button = event.target.closest('[data-admin-tab], [data-ops-tab]');
    if (!button || selecting) return;
    const panel = button.closest('section').querySelector('[data-admin-panel].active, [data-ops-panel].active');
    if (panel?.id && location.hash !== '#' + panel.id) history.pushState(null, '', '#' + panel.id);
  });
  window.addEventListener('hashchange', renderRoute);
  renderRoute();
});

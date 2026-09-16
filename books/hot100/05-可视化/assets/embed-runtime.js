(() => {
  // 可视化中心的演示卡片由页面脚本动态生成；只处理卡片容器，不拦截全站点击。
  const ensureVisualCardLinks = () => document.querySelectorAll('#grid a.card').forEach((link) => {
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
  });
  const visualCardGrid = document.getElementById('grid');
  if (visualCardGrid) {
    ensureVisualCardLinks();
    new MutationObserver(ensureVisualCardLinks).observe(visualCardGrid, { childList: true, subtree: true });
  }
  const tabLike = document.querySelectorAll('.sort-tab, .ds-tab, .code-tab, .preset-btn');
  const syncState = (item) => item.setAttribute('aria-pressed', item.classList.contains('active') ? 'true' : 'false');
  tabLike.forEach((item) => {
    if (!item.hasAttribute('role')) item.setAttribute('role', 'button');
    if (!item.hasAttribute('tabindex')) item.setAttribute('tabindex', '0');
    syncState(item);
    item.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); item.click(); }
    });
    new MutationObserver(() => syncState(item)).observe(item, { attributes: true, attributeFilter: ['class'] });
  });
  document.querySelectorAll('button').forEach((button) => { if (!button.type) button.type = 'button'; });
  document.querySelectorAll('input, select, textarea').forEach((control) => {
    if (control.matches('[aria-label], [aria-labelledby]')) return;
    if (control.id && document.querySelector(`label[for="${CSS.escape(control.id)}"]`)) return;
    if (control.closest('label')) return;
    const fallback = control.getAttribute('placeholder') || control.getAttribute('name') || control.id || (control.type === 'range' ? '播放速度' : '参数');
    control.setAttribute('aria-label', fallback);
  });
  document.querySelectorAll('canvas').forEach((canvas) => {
    if (!canvas.hasAttribute('role')) canvas.setAttribute('role', 'img');
    if (!canvas.hasAttribute('aria-label')) {
      const heading = canvas.closest('.panel')?.querySelector('h2, h3')?.textContent?.trim();
      canvas.setAttribute('aria-label', `${heading || document.title} 的算法状态图`);
    }
    canvas.parentElement?.classList.add('hot100-native-canvas');
  });
  document.querySelectorAll('.vis-canvas-wrap').forEach((stage) => {
    if (stage.querySelector('.bar-wrapper')) stage.classList.add('hot100-bar-stage');
  });
  document.querySelectorAll('.log, .status, .vis-msg, .desc').forEach((node) => {
    if (!node.hasAttribute('aria-live')) node.setAttribute('aria-live', 'polite');
  });
  const embedParams = new URLSearchParams(location.search);
  if (embedParams.get('embed') === '1') {
    const panelIndex = embedParams.get('panel');
    if (panelIndex !== null) {
      const panelTab = [...document.querySelectorAll('.sort-tab, .ds-tab')]
        .find((item) => item.dataset.idx === panelIndex);
      panelTab?.click();
    }
    const mode = embedParams.get('mode');
    const modeSelect = document.getElementById('mode');
    if (mode && modeSelect && [...modeSelect.options].some((option) => option.value === mode)) {
      modeSelect.value = mode;
      modeSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }
    // 高度计算：可见子元素最大 bottom（子元素盒子即使被 iframe 裁切，
    // 其 rect 仍反映真实布局高度；不要用 body.scrollHeight —— 它不会小于
    // iframe 视口高度，会把"虚高"锁死导致收缩永远上报不出去）。
    const computeHeight = () => {
      const bottoms = [...document.body.children]
        .filter((item) => getComputedStyle(item).display !== 'none')
        .map((item) => item.getBoundingClientRect().bottom);
      return Math.max(320, Math.ceil(Math.max(0, ...bottoms) + 12));
    };
    // 单帧合并测量：同一时段的多个触发只保留一次布局读取。
    let lastReported = -1;
    let measureFrame = 0;
    let resizeTimer = 0;
    const measure = (reason) => {
      measureFrame = 0;
      const height = computeHeight();
      if (Math.abs(height - lastReported) <= 2) return;
      lastReported = height;
      parent.postMessage({ type: 'hot100:visual-height', height, reason }, '*');
    };
    const scheduleEmbeddedMeasure = (reason = 'structure') => {
      if (measureFrame) return;
      measureFrame = requestAnimationFrame(() => measure(reason));
    };
    window.__hot100ScheduleEmbeddedMeasure = scheduleEmbeddedMeasure;
    window.addEventListener('message', (event) => {
      if (event.data?.type === 'hot100:measure') scheduleEmbeddedMeasure('parent-request');
    });
    window.addEventListener('load', () => scheduleEmbeddedMeasure('load'), { once: true });
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => scheduleEmbeddedMeasure('resize'), 100);
    }, { passive: true });
    document.fonts?.ready.then(() => scheduleEmbeddedMeasure('fonts'));
    window.addEventListener('hot100:demo-rebuilt', () => scheduleEmbeddedMeasure('demo-rebuild'));
    document.querySelectorAll('.sort-tab, .ds-tab').forEach((item) => {
      item.addEventListener('click', () => setTimeout(() => scheduleEmbeddedMeasure('panel-change'), 0));
    });
    modeSelect?.addEventListener('change', () => setTimeout(() => scheduleEmbeddedMeasure('mode-change'), 0));
    scheduleEmbeddedMeasure('initial');
  }
})();

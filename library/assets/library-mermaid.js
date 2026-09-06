(async () => {
  const diagrams = [...document.querySelectorAll('.mermaid-diagram .mermaid')];
  if (!diagrams.length) return;
  const markFailed = (node) => {
    const figure = node.closest('.mermaid-diagram');
    if (figure) figure.classList.add('is-error');
  };
  if (!window.mermaid) {
    diagrams.forEach(markFailed);
    return;
  }
  // 缓存原始源码：mermaid 渲染会把节点内容替换成 svg+样式，切换主题重渲染前需还原
  diagrams.forEach((node) => { if (!node.dataset.origSrc) node.dataset.origSrc = node.textContent; });

  // 配色跟随站内主题：实时读取 library.css 的 --diagram-* 令牌（浅/深两套齐全），
  // 不再写死浅色调色板 —— 否则深色模式下节点/标签的黑色文字在深色底上不可见。
  const token = (name, fallback) => {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  };
  const palette = () => ({
    background: token('--diagram-surface', '#fbfcff'),
    primaryColor: token('--diagram-node', '#f1f2ff'),
    primaryTextColor: token('--diagram-node-text', '#344056'),
    primaryBorderColor: token('--diagram-node-border', '#7775dc'),
    secondaryColor: token('--diagram-cluster', '#f7f9fd'),
    tertiaryColor: token('--diagram-label-bg', '#fbfcff'),
    lineColor: token('--diagram-line', '#8490a3'),
    textColor: token('--diagram-node-text', '#344056'),
    mainBkg: token('--diagram-node', '#f1f2ff'),
    nodeBorder: token('--diagram-node-border', '#7775dc'),
    clusterBkg: token('--diagram-cluster', '#f7f9fd'),
    clusterBorder: token('--diagram-cluster-border', '#d4dbe7'),
    edgeLabelBackground: token('--diagram-label-bg', '#fbfcff'),
    actorBkg: token('--diagram-node', '#f1f2ff'),
    actorBorder: token('--diagram-node-border', '#7775dc'),
    actorTextColor: token('--diagram-node-text', '#344056'),
    actorLineColor: token('--diagram-line', '#8490a3'),
    signalColor: token('--diagram-line', '#8490a3'),
    signalTextColor: token('--diagram-node-text', '#344056'),
    labelBoxBkgColor: token('--diagram-cluster', '#f7f9fd'),
    labelBoxBorderColor: token('--diagram-line', '#8490a3'),
    labelTextColor: token('--diagram-node-text', '#344056'),
    activationBkgColor: token('--diagram-decision', '#fff7e8'),
    activationBorderColor: token('--diagram-decision-border', '#dfa34c'),
    sequenceNumberColor: '#ffffff'
  });

  const renderAll = async () => {
    const narrow = window.innerWidth < 640;
    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: 'base',
      themeVariables: { ...palette(), fontSize: '15px' },
      fontFamily: 'system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif',
      flowchart: { htmlLabels: true, useMaxWidth: true, curve: 'basis', nodeSpacing: narrow ? 18 : 34, rankSpacing: narrow ? 26 : 44, padding: narrow ? 10 : 14 },
      sequence: { useMaxWidth: true, wrap: true, actorMargin: narrow ? 34 : 46, messageMargin: narrow ? 24 : 32, diagramMarginX: narrow ? 12 : 24, diagramMarginY: narrow ? 12 : 18 },
      mindmap: { useMaxWidth: true }
    });
    // 逐图、按顺序渲染：某一张图语法异常时只标记该图，不阻断同页其他图；
    // 同时避免并发生成 Mermaid 临时 ID 时发生冲突。
    for (const node of diagrams) {
      const figure = node.closest('.mermaid-diagram');
      figure?.classList.remove('is-error', 'is-rendered');
      try {
        node.textContent = node.dataset.origSrc || node.textContent;
        delete node.dataset.processed;
        await window.mermaid.run({ nodes: [node], suppressErrors: false });
        if (!node.querySelector('svg')) throw new Error('Mermaid did not create SVG');
        figure?.classList.add('is-rendered');
      } catch (e) {
        console.error('[mermaid] render failed:', e);
        window.__mermaidErr = String(e && (e.message || e));
        markFailed(node);
      }
    }
  };

  await renderAll();

  // 主题切换（手动 data-theme 属性或系统深浅切换）后按新配色防抖重渲染
  let rerenderTimer = null;
  const scheduleRerender = () => {
    clearTimeout(rerenderTimer);
    rerenderTimer = setTimeout(renderAll, 200);
  };
  new MutationObserver(scheduleRerender).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', scheduleRerender);
  window.addEventListener('storage', (e) => { if (!e || e.key === 'forge-theme') scheduleRerender(); });
})();

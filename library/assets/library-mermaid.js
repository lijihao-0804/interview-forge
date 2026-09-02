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
  const palette = {
    background: '#fbfcff', primaryColor: '#f1f2ff', primaryTextColor: '#344056',
    primaryBorderColor: '#7775dc', secondaryColor: '#edf9f8', tertiaryColor: '#f7f9fd',
    lineColor: '#8490a3', textColor: '#344056', mainBkg: '#f1f2ff', nodeBorder: '#7775dc',
    clusterBkg: '#f7f9fd', clusterBorder: '#d4dbe7', edgeLabelBackground: '#fbfcff',
    actorBkg: '#f1f2ff', actorBorder: '#7775dc', actorTextColor: '#344056',
    actorLineColor: '#b5becc', signalColor: '#758196', signalTextColor: '#344056',
    labelBoxBkgColor: '#edf9f8', labelBoxBorderColor: '#79b8ba', labelTextColor: '#344056',
    activationBkgColor: '#fff7e8', activationBorderColor: '#dfa34c', sequenceNumberColor: '#ffffff'
  };
  const narrow = window.innerWidth < 640;
  window.mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme: 'base',
    themeVariables: { ...palette, fontSize: '15px' },
    fontFamily: 'system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif',
    flowchart: { htmlLabels: true, useMaxWidth: true, curve: 'basis', nodeSpacing: narrow ? 18 : 34, rankSpacing: narrow ? 26 : 44, padding: narrow ? 10 : 14 },
    sequence: { useMaxWidth: true, wrap: true, actorMargin: narrow ? 34 : 46, messageMargin: narrow ? 24 : 32, diagramMarginX: narrow ? 12 : 24, diagramMarginY: narrow ? 12 : 18 },
    mindmap: { useMaxWidth: true }
  });
  // 逐图、按顺序渲染：某一张图语法异常时不会阻断同页其他图，
  // 同时避免并发生成 Mermaid 临时 ID 时发生冲突。
  for (const node of diagrams) {
    const figure = node.closest('.mermaid-diagram');
    figure?.classList.remove('is-error', 'is-rendered');
    try {
      await window.mermaid.run({ nodes: [node], suppressErrors: false });
      if (!node.querySelector('svg')) throw new Error('Mermaid did not create SVG');
      figure?.classList.add('is-rendered');
    } catch (_) {
      markFailed(node);
    }
  }
})();

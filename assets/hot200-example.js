(() => {
  const example = JSON.parse(document.getElementById("problemExample").textContent);
  const kit = window.DemoKit;

  kit.mount({
    no: example.no,
    title: example.title,
    tag: example.tag,
    example: example.example,
    build(ctx) {
      example.frames.forEach((frame, index) => {
        ctx.step(frame.why, frame, {phase: index === example.frames.length - 1 ? "done" : "update"});
      });
    },
    render(frame, stage) {
      stage.appendChild(kit.el("h2", "dk-head", frame.label));
      const cells = kit.el("div", "dk-cells");
      const occurrences = new Map();
      frame.cells.forEach(value => {
        const count = occurrences.get(value) || 0;
        occurrences.set(value, count + 1);
        cells.appendChild(kit.keyed("span", value + ":" + count, "dk-cell", value));
      });
      stage.append(cells, kit.el("p", "dk-log", frame.state));
    }
  });

  function reportHeight() {
    if (parent !== window) {
      parent.postMessage({type: "hot100:visual-height", height: document.body.offsetHeight}, "*");
    }
  }
  new ResizeObserver(reportHeight).observe(document.body);
  window.addEventListener("message", event => {
    if (event.source === parent && event.data?.type === "hot100:measure") reportHeight();
  });
})();

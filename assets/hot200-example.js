(() => {
  const source = document.getElementById("problemExample");
  const example = source ? JSON.parse(source.textContent) : null;
  const kit = window.DemoKit;
  const execution = window.Hot200Execution;
  document.body.classList.add("dk-trace-player");
  const text = value => JSON.stringify(value);
  const cases = example ? [{label: "思路推演"}, ...execution.cases] : execution.cases;

  function explain(line, returning, method) {
    if (returning) return method + " 本次调用结束，返回值见变量栏。";
    if (/^(if|elif|while)\b/.test(line)) return "用当前变量判断条件 " + line.replace(/^(if|elif|while)\s+|:$/g, "");
    if (/^for\b/.test(line)) return "按当前顺序遍历 " + line.slice(4).replace(/:$/, "");
    if (/^return\b/.test(line)) return "用当前状态求出返回表达式 " + line.slice(6).trim();
    return "即将执行 " + line;
  }

  function showValue(value) {
    if (value && Array.isArray(value.$set) && typeof value.$size === "number") {
      const contents = value.$set.map(text).join(", ") + (value.$size > value.$set.length ? ", …" : "");
      return kit.el("span", null, "{" + contents + "}");
    }
    if (Array.isArray(value)) {
      if (value.length && value.every(row => Array.isArray(row))) {
        const table = kit.el("table", "dk-trace-grid");
        value.forEach(row => {
          const tr = kit.el("tr");
          row.forEach(cell => tr.appendChild(kit.el("td", null, text(cell))));
          table.appendChild(tr);
        });
        return table;
      }
      const strip = kit.el("ol", "dk-trace-strip");
      value.forEach((item, i) => {
        const cell = kit.el("li");
        cell.append(kit.el("small", null, String(i)), kit.el("span", null, text(item)));
        strip.appendChild(cell);
      });
      if (!value.length) strip.appendChild(kit.el("li", null, "[]"));
      return strip;
    }
    if (value && typeof value === "object" && Object.keys(value).length) {
      const pairs = kit.el("dl", "dk-trace-map");
      Object.entries(value).forEach(([key, item]) => {
        const cell = kit.el("dd");
        cell.appendChild(showValue(item));
        pairs.append(kit.el("dt", null, key), cell);
      });
      return pairs;
    }
    return kit.el("span", null, text(value));
  }

  kit.mount({
    no: execution.id,
    title: execution.title,
    tag: example ? example.tag : "Python 用例回放",
    sizes: cases,
    sizeLabel: "演示输入",
    build(ctx, selected) {
      selected = selected || cases[0];
      if (selected.steps) {
        ctx.step("按顺序读入各行参数，再调用题解中的 Python 实现。", {input: selected.input});
        let previous = null;
        selected.steps.forEach(([position, lineNo, method, locals, returning]) => {
          const line = execution.lines[lineNo];
          const changed = previous && previous.method === method ? Object.keys(locals).filter(
            key => text(previous.locals[key]) !== text(locals[key])) : [];
          const why = Object.hasOwn(locals, "产出") ? method + " 产出一个值，保留游标供下次继续。" :
            explain(line, returning, method);
          ctx.step(why, {
            position, count: selected.count, method, lineNo, line, locals, changed
          }, {phase: returning ? "recursive_return" : "visit"});
          previous = {method, locals};
        });
        ctx.step("此输入运行结束，输出与该用例的预期值一致。", {output: selected.output}, {phase: "done"});
        return;
      }
      example.frames.forEach((frame, index) => {
        ctx.step(frame.why, {...frame, example: example.example}, {phase: index === example.frames.length - 1 ? "done" : "update"});
      });
    },
    render(frame, stage) {
      if ("input" in frame || "output" in frame) {
        const input = "input" in frame;
        stage.append(kit.el("h2", "dk-head", input ? "输入参数" : (example ? "实际输出" : "判题结果")),
                     kit.el("pre", "dk-trace-code", input ? frame.input : text(frame.output)));
        return;
      }
      if (frame.locals) {
        stage.append(kit.el("h2", "dk-head", frame.method + " · 第 " + frame.lineNo + " 行"),
                     kit.el("pre", "dk-trace-code", frame.line),
                     kit.el("p", "dk-note", "执行位置 " + frame.position + " / " + frame.count +
                       (frame.count > 20 ? "（选取 20 个位置）" : "")));
        const variables = kit.el("dl", "dk-trace-vars");
        Object.entries(frame.locals).forEach(([name, value]) => {
          const label = kit.el("dt", null, name);
          if (frame.changed.includes(name)) label.appendChild(kit.el("small", "dk-trace-change", "已变"));
          const cell = kit.el("dd");
          cell.appendChild(showValue(value));
          variables.append(label, cell);
        });
        stage.appendChild(variables);
        return;
      }
      stage.appendChild(kit.el("p", "dk-note", frame.example));
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

  const statePanel = document.querySelector(".dk-stage");
  statePanel.tabIndex = 0;
  statePanel.setAttribute("role", "region");
  statePanel.setAttribute("aria-label", "当前步骤的算法状态");

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

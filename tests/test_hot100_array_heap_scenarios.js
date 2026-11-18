"use strict";

const assert = require("node:assert/strict");

function values(step, name) {
  const row = step.view.rows.find((item) => item.name === name);
  assert.ok(row, "缺少图解行 " + name);
  return Array.from(row.vals || row.cells, (cell) =>
    typeof cell === "object" ? cell.v : cell
  );
}

function marked(step, name, mark) {
  const row = step.view.rows.find((item) => item.name === name);
  return Object.keys(row.st).filter((key) => row.st[key] === mark).map(Number);
}

function productExceptSelf(cfg, collect) {
  const steps = collect(cfg);
  const input = values(steps[0], "nums");
  const expected = input.map((_, skip) =>
    input.reduce((product, number, i) => i === skip ? product : product * number, 1)
  );
  const answer = Array(input.length).fill("·");
  answer[0] = 1;
  assert.deepEqual(values(steps[0], "answer"), answer);
  const forward = steps.filter((step) => step.opts.line === 3);
  assert.equal(forward.length, input.length - 1);
  forward.forEach((step, n) => {
    const i = n + 1;
    answer[i] = answer[i - 1] * input[i - 1];
    assert.deepEqual(marked(step, "nums", "hot"), [i - 1]);
    assert.deepEqual(marked(step, "answer", "write"), [i]);
    assert.deepEqual(values(step, "answer"), answer);
  });
  let suffix = 1;
  const initSuffix = steps.find((step) => step.opts.line === 4);
  assert.deepEqual(values(initSuffix, "suf"), [suffix]);
  const backward = steps.filter((step) => step.opts.line === 6).slice(0, -1);
  assert.equal(backward.length, input.length);
  backward.forEach((step, n) => {
    const i = input.length - 1 - n;
    answer[i] *= suffix;
    suffix *= input[i];
    assert.deepEqual(marked(step, "answer", "write"), [i]);
    assert.deepEqual(values(step, "answer"), answer);
    assert.deepEqual(values(step, "suf"), [suffix]);
  });
  const final = steps.at(-1);
  assert.deepEqual(values(final, "answer"), expected);
  assert.ok(final.desc.includes(JSON.stringify(expected)), "终态讲解须包含整个输出数组");
}

function frequentElements(cfg, collect) {
  const steps = collect(cfg);
  const input = values(steps[0], "nums");
  const count = new Map();
  const counting = steps.filter((step) => step.opts.line === 2);
  assert.equal(counting.length, input.length);
  counting.forEach((step, i) => {
    const value = input[i];
    count.set(value, (count.get(value) || 0) + 1);
    assert.deepEqual(marked(step, "nums", "hot"), [i]);
    assert.ok(step.view.note.includes(JSON.stringify(Object.fromEntries(count))));
  });
  const collecting = steps.filter((step) => step.opts.line === 7);
  const ranked = [...count.keys()].sort((a, b) => count.get(b) - count.get(a));
  const expected = ranked.slice(0, 2);
  const selectedFrequencies = [...new Set(expected.map((v) => count.get(v)))];
  assert.equal(collecting.length, selectedFrequencies.length);
  collecting.forEach((step, i) => {
    const numbers = values(step, "数字");
    const frequencies = values(step, "频率");
    assert.deepEqual(frequencies, numbers.map((v) => count.get(v)));
    const indices = numbers.flatMap((v, index) => count.get(v) === selectedFrequencies[i] ? [index] : []);
    assert.deepEqual(marked(step, "数字", "hot"), indices);
    assert.deepEqual(marked(step, "频率", "hot"), indices);
  });
  const final = steps.at(-1);
  assert.deepEqual(values(final, "结果"), expected);
  assert.ok(final.desc.includes(JSON.stringify(expected)));
  assert.match(final.desc, /额外空间 O\(n\)/);
  assert.match(final.view.note, /候选堆占 O\(k\) 空间/);
}

function streamMedian(cfg, collect) {
  const sizes = [...cfg.sizes, {s: [0, -10, 1, 7, -3, 4, -2, 7, -11, -11]}, {s: []}];
  let sawLeftTransfer = false, sawRightTransfer = false, sawUnsortedHeap = false;
  for (const size of sizes) {
    const source = Array.from(size.s);
    const steps = collect(cfg, size);
    for (const step of steps) {
      const low = values(step, "左｜大顶堆"), high = values(step, "右｜小顶堆");
      const vars = Object.fromEntries(step.view.vars);
      const count = low.length + high.length;
      assert.equal(vars["已入堆"], count);
      const expected = source.slice(0, count).sort((a, b) => a - b);
      assert.deepEqual([...low, ...high].sort((a, b) => a - b), expected);
      for (let i = 1; i < low.length; i++) assert.ok(low[(i - 1) >> 1] >= low[i]);
      for (let i = 1; i < high.length; i++) assert.ok(high[(i - 1) >> 1] <= high[i]);
      if (low.length && high.length) assert.ok(low[0] <= high[0]);
      if (low.some((v, i) => i && v > low[i - 1]) || high.some((v, i) => i && v < high[i - 1])) {
        sawUnsortedHeap = true;
      }
      const diff = low.length - high.length;
      const balanced = diff === 0 || diff === 1;
      assert.equal(step.view.settled, balanced);
      assert.ok(diff >= -1 && diff <= 2);
      if (!balanced) {
        assert.equal(vars["中位数"], "待平衡");
      } else if (!count) {
        assert.equal(vars["中位数"], "—");
      } else {
        const mid = (expected[(count - 1) >> 1] + expected[count >> 1]) / 2;
        assert.equal(vars["中位数"], mid);
        if (step.view.phase === "done") assert.ok(step.desc.includes("最终中位数为 " + mid + "。"));
      }
      if (step.view.phase === "swap_move") {
        if (step.opts.line === 5) sawLeftTransfer = true;
        if (step.opts.line === 6) sawRightTransfer = true;
        if (source.every((v, i) => i === 0 || v > source[i - 1])) assert.equal(step.opts.line, 6);
      }
    }
    assert.equal(steps.filter((step) => step.view.phase === "enqueue").length, source.length);
    assert.equal(Object.fromEntries(steps.at(-1).view.vars)["已入堆"], source.length);
  }
  assert.ok(sawLeftTransfer && sawRightTransfer && sawUnsortedHeap);
}

const checks = {238: productExceptSelf, 347: frequentElements, 295: streamMedian};
module.exports = function checkArrayHeapScenario(cfg, collect) {
  if (checks[cfg.no]) checks[cfg.no](cfg, collect);
};

/* Production scheduler smoke/performance test; run with: node tests/test_ai_assistant_streaming.js */
const fs = require("fs");
const vm = require("vm");
const { performance } = require("perf_hooks");

const source = fs.readFileSync("assets/ai-assistant.js", "utf8");
const markdownStart = source.indexOf("  function esc");
const markdownEnd = source.indexOf("  async function api", markdownStart);
const start = source.indexOf("  function updateAutoFollow");
const end = source.indexOf("  function actionHost", start);
if (markdownStart < 0 || markdownEnd < 0 || start < 0 || end < 0) throw new Error("stream test blocks not found");

const state = {
  autoFollow: true,
  scrollFrame: null,
  streamDiagnostics: { delta_count: 0, render_count: 0, max_render_ms: 0 },
};
const messages = { scrollHeight: 2000, scrollTop: 1800, clientHeight: 200 };
const context = {
  state,
  messages,
  STREAM_RENDER_INTERVAL: 100,
  AUTO_FOLLOW_THRESHOLD: 120,
  performance,
  console,
  Date,
  window: {
    setTimeout,
    clearTimeout,
    requestAnimationFrame: (callback) => setTimeout(callback, 0),
  },
};
vm.runInNewContext(source.slice(markdownStart, markdownEnd), context, { filename: "assets/ai-assistant.js" });
vm.runInNewContext(source.slice(start, end), context, { filename: "assets/ai-assistant.js" });

const bubble = {
  _rawText: "",
  _streamRenderTimer: null,
  _lastStreamRenderAt: 0,
  textContent: "",
  innerHTML: "",
  classList: { removed: false, remove(name) { if (name === "streaming") this.removed = true; } },
};

for (let i = 0; i < 1000; i += 1) {
  bubble._rawText += i % 5 === 0
    ? "| key | value |\n| --- | --- |\n| item | **text** |\n"
    : i % 7 === 0
      ? "```js\nconst value = 1;\n```\n"
      : "- ordinary text\n";
  state.streamDiagnostics.delta_count += 1;
  context.scheduleStreamRender(bubble);
}

setTimeout(() => {
  if (state.streamDiagnostics.delta_count !== 1000) throw new Error("delta count mismatch");
  if (state.streamDiagnostics.render_count > 150) throw new Error("too many stream renders: " + state.streamDiagnostics.render_count);
  context.finalizeAssistant(bubble);
  if (!bubble.classList.removed) throw new Error("streaming class was not removed");
  for (const marker of ["<table>", "<pre><code", "<ul>", "<strong>text</strong>"]) {
    if (!bubble.innerHTML.includes(marker)) throw new Error("final markdown missing: " + marker);
  }

  const before = messages.scrollTop;
  state.autoFollow = false;
  context.scheduleScrollBottom();
  setTimeout(() => {
    if (messages.scrollTop !== before) throw new Error("user scroll position was overridden");
    console.log(JSON.stringify({ delta_count: state.streamDiagnostics.delta_count,
      render_count: state.streamDiagnostics.render_count,
      max_render_ms: state.streamDiagnostics.max_render_ms }));
  }, 10);
}, 120);

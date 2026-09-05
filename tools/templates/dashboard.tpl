<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Interview Forge</title>
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#5755d4">
<link rel="stylesheet" href="assets/uplot.min.css?v=__ASSET_VERSION__">
<style>
@font-face{font-family:"Inter";src:url("assets/fonts/Inter-Variable.woff2") format("woff2");font-weight:100 900;font-style:normal;font-display:swap;unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD}
@font-face{font-family:"JetBrains Mono";src:url("assets/fonts/JetBrainsMono-Variable.woff2") format("woff2");font-weight:100 800;font-style:normal;font-display:swap;unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD}

:root{
  color-scheme:light dark;
  --font-sans:"Inter","PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,-apple-system,"Segoe UI",sans-serif;
  --font-mono:"JetBrains Mono","Cascadia Code",Consolas,"Microsoft YaHei",monospace;
  --bg:#f3f5fa;--panel:#fff;--panel-soft:#f7f8fc;--text:#172033;--muted:#647188;
  --line:#dce2ec;--brand:#5755d4;--brand-strong:#4543bd;--brand-soft:#eeedff;
  --success:#13764b;--success-soft:#e7f6ee;--warning:#a45a00;--danger:#c1363e;
  --hot-hm-1:#9be9a8;--hot-hm-2:#40c463;--hot-hm-3:#30a14e;--hot-hm-4:#216e39;
  --shadow:0 14px 38px rgba(31,42,68,.075)
}
@media(prefers-color-scheme:dark){:root{
  --bg:#0f131b;--panel:#181e29;--panel-soft:#141a24;--text:#edf2fb;--muted:#a7b2c4;
  --line:#313b4c;--brand:#b2b0ff;--brand-strong:#cbc9ff;--brand-soft:#292955;
  --success:#79d8a8;--success-soft:#17382b;--warning:#ffc474;--danger:#ff969d;
  --hot-hm-1:#6fc98c;--hot-hm-2:#3db863;--hot-hm-3:#23944b;--hot-hm-4:#136b33;
  --shadow:0 18px 46px rgba(0,0,0,.22)
}}
*{box-sizing:border-box}
*{scrollbar-width:thin;scrollbar-color:color-mix(in srgb,var(--muted) 45%,transparent) transparent}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:color-mix(in srgb,var(--muted) 45%,transparent);border-radius:8px;border:2px solid transparent;background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:color-mix(in srgb,var(--muted) 72%,transparent);border:2px solid transparent;background-clip:padding-box}
html{background:var(--bg);scroll-behavior:smooth}
body{margin:0;min-width:0;overflow-x:hidden;color:var(--text);background:radial-gradient(circle at 12% 0%,color-mix(in srgb,var(--brand) 10%,transparent),transparent 35rem),var(--bg);font:15px/1.65 var(--font-sans)}
a{color:var(--brand);text-decoration:none}a:hover{text-decoration:underline}
button,input,select{font:inherit}button{color:inherit}
:focus-visible{outline:3px solid color-mix(in srgb,var(--brand) 48%,transparent);outline-offset:3px}
.skip-link{position:absolute;left:12px;top:-60px;z-index:10;padding:8px 12px;border:1px solid var(--line);border-radius:8px;color:var(--text);background:var(--panel)}
.skip-link:focus{top:12px}
.shell{width:calc(100% - 36px);margin:auto;padding:30px 0 56px}
.hero{display:flex;align-items:flex-end;justify-content:space-between;gap:22px;flex-wrap:wrap}
h1{margin:0;font-size:clamp(30px,4vw,46px);line-height:1.15;letter-spacing:-.025em}
.sub{margin-top:8px;color:var(--muted);font-size:16px}
.connection{display:inline-flex;align-items:center;gap:7px;margin-top:10px;color:var(--muted);font-size:13px}
.connection::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--warning)}
.connection.online::before{background:var(--success)}
.stats{display:grid;grid-template-columns:repeat(4,minmax(105px,1fr));gap:9px}
.stat{min-width:0;padding:10px 13px;border:1px solid var(--line);border-radius:13px;background:var(--panel);box-shadow:0 5px 18px rgba(31,42,68,.035)}
.stat span{color:var(--muted);font-size:12px}.stat strong{display:block;margin-top:1px;font-size:23px;line-height:1.25;font-variant-numeric:tabular-nums}
.stat .goal-line{display:flex;align-items:center;gap:6px;margin-top:2px}
.stat .goal-line input{width:52px;padding:2px 5px;border:1px solid var(--line);border-radius:6px;color:var(--text);background:var(--panel-soft);font-size:12px}
.stat .goal-hint{font-size:11px;color:var(--muted)}
.dashboard-nav{display:flex;gap:8px;flex-wrap:wrap;margin:22px 0 17px}
.dashboard-nav a{padding:7px 11px;border:1px solid var(--line);border-radius:9px;color:var(--text);background:var(--panel)}
.dashboard-nav a:hover{border-color:color-mix(in srgb,var(--brand) 28%,var(--line));color:var(--brand);background:var(--brand-soft);text-decoration:none}
.dashboard-nav a.lc-button{background:var(--brand);border-color:var(--brand);color:#fff;font-weight:650}
.dashboard-nav a.lc-button:hover{background:var(--brand-strong);border-color:var(--brand-strong);color:#fff}
.notice{margin:0 0 18px;padding:12px 14px;border:1px solid color-mix(in srgb,var(--warning) 35%,var(--line));border-radius:12px;background:color-mix(in srgb,var(--warning) 7%,var(--panel));color:var(--text)}
.notice code{padding:.12em .34em;border-radius:4px;background:var(--panel-soft);color:var(--brand)}
.progress-section{margin:0 0 22px}
.progress-head{display:flex;justify-content:space-between;gap:12px;margin-bottom:7px;color:var(--muted);font-size:13px}.progress-head strong{color:var(--text)}
.bar{height:9px;overflow:hidden;border-radius:999px;background:var(--line)}.bar>div{width:0;height:100%;background:linear-gradient(90deg,var(--brand),var(--success));transition:width .22s ease}
.workspace{display:block}
.controls{display:grid;grid-template-columns:minmax(220px,2fr) repeat(2,minmax(145px,1fr));gap:12px;margin:0 0 18px;padding:14px;border:1px solid var(--line);border-radius:15px;background:var(--panel);box-shadow:var(--shadow)}
.field{display:grid;gap:6px;min-width:0}.field label{color:var(--muted);font-size:13px;font-weight:650}
.field input,.field select{width:100%;min-width:0;padding:9px 10px;border:1px solid var(--line);border-radius:9px;color:var(--text);background:var(--panel-soft)}
.field input::placeholder{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(270px,100%),1fr));gap:13px}
.card{min-width:0;padding:15px;border:1px solid var(--line);border-radius:14px;background:var(--panel);box-shadow:0 7px 22px rgba(31,42,68,.04);transition:border-color .18s,transform .18s,box-shadow .18s}
.card:hover{border-color:color-mix(in srgb,var(--brand) 38%,var(--line));transform:translateY(-1px);box-shadow:0 11px 27px rgba(31,42,68,.075)}
.card.studied{box-shadow:inset 4px 0 var(--success),0 7px 22px rgba(31,42,68,.04)}
.card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.card h2{min-width:0;margin:0;font-size:16px;line-height:1.45}.card h2 a{color:var(--text)}.card h2 a:hover{color:var(--brand)}
.round-count{flex:0 0 auto;padding:2px 7px;border-radius:999px;color:var(--success);background:var(--success-soft);font-size:12px;font-variant-numeric:tabular-nums}
.meta{display:flex;gap:7px;flex-wrap:wrap;margin:8px 0;color:var(--muted);font-size:13px}.pill{padding:2px 8px;border-radius:999px;color:var(--brand);background:var(--brand-soft)}
.difficulty-简单{color:var(--success)}.difficulty-中等{color:var(--warning)}.difficulty-困难{color:var(--danger)}
.method{min-height:46px;color:var(--muted);overflow-wrap:anywhere}
.card-actions{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:12px;padding-top:11px;border-top:1px solid var(--line);flex-wrap:wrap}
.last-study{min-width:0;width:100%;color:var(--muted);font-size:12px;line-height:1.5;white-space:normal;overflow-wrap:anywhere}
.card-buttons{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-left:auto}
.round-button{flex:0 0 auto;padding:6px 9px;border:1px solid color-mix(in srgb,var(--brand) 34%,var(--line));border-radius:8px;color:var(--brand);background:var(--brand-soft);cursor:pointer}
.round-button:hover:not(:disabled){border-color:var(--brand);color:var(--brand-strong)}.round-button:disabled{cursor:not-allowed;opacity:.52}
.history{min-width:0;padding:16px;border:1px solid var(--line);border-radius:15px;background:var(--panel);box-shadow:var(--shadow)}
.history h2{margin:0 0 12px;font-size:18px}.history h3{margin:19px 0 8px;font-size:14px;color:var(--muted)}
.day-list,.event-list{list-style:none;margin:0;padding:0}.day-list li,.event-list li{display:grid;gap:2px;padding:8px 0;border-bottom:1px solid var(--line)}.day-list li:last-child,.event-list li:last-child{border-bottom:0}
.day-row{display:flex;justify-content:space-between;gap:10px}.day-row strong{font-variant-numeric:tabular-nums}.day-row span,.event-time{color:var(--muted);font-size:12px}
.event-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.history-empty{padding:12px 0;color:var(--muted)}
.empty{padding:42px 18px;border:1px dashed var(--line);border-radius:14px;color:var(--muted);text-align:center}
.toast{min-height:24px;margin:14px 0 0;color:var(--success);text-align:center}
.review-section{margin:0 0 22px;padding:16px;border:1px solid var(--line);border-radius:15px;background:var(--panel);box-shadow:var(--shadow)}
.review-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:10px}
.review-head h2{margin:0;font-size:18px}
.review-summary{color:var(--muted);font-size:13px}
.review-summary strong{color:var(--warning)}
.review-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(300px,100%),1fr));gap:9px}
.review-item{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 11px;border:1px solid var(--line);border-radius:10px;background:var(--panel-soft)}
.review-item a{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text)}
.review-item a:hover{color:var(--brand);text-decoration:underline}
.review-item .due-badge{flex:0 0 auto;padding:2px 8px;border-radius:999px;font-size:12px;color:var(--success);background:var(--success-soft)}
/* 移动端防溢出：网格/弹性子项允许收缩，长标题不再撑宽 1fr 轨道把整页顶破 */
.quick-cards>*,.review-list>*,.shelf-due-list>*,.review-item,.plan-item,.mock-item,.weak-list li{min-width:0;max-width:100%}
.review-item.due-overdue .due-badge{color:var(--danger);background:color-mix(in srgb,var(--danger) 12%,var(--panel))}
.review-empty{padding:14px 4px;color:var(--muted);font-size:13px}
.due-pill{flex:0 0 auto;padding:2px 7px;border-radius:999px;font-size:12px;color:var(--warning);background:color-mix(in srgb,var(--warning) 14%,var(--panel))}
.due-pill.overdue{color:var(--danger);background:color-mix(in srgb,var(--danger) 12%,var(--panel))}
.ac-pill{flex:0 0 auto;padding:2px 7px;border-radius:999px;font-size:12px;color:var(--success);background:var(--success-soft)}
.mark-pill{flex:0 0 auto;padding:2px 7px;border-radius:999px;font-size:12px}
.mark-pill.weak{color:var(--danger);background:color-mix(in srgb,var(--danger) 12%,var(--panel))}
.mark-pill.reviewing{color:var(--warning);background:color-mix(in srgb,var(--warning) 14%,var(--panel))}
.mark-pill.mastered{color:var(--success);background:var(--success-soft)}
.card.due{box-shadow:inset 3px 0 var(--warning),0 7px 22px rgba(31,42,68,.04)}
.card.due.overdue{box-shadow:inset 3px 0 var(--danger),0 7px 22px rgba(31,42,68,.04)}
.pick-card{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:11px 13px;border:1px solid var(--line);border-radius:11px;background:var(--panel-soft)}
.pick-card a{font-weight:650;color:var(--text)}
.pick-card a:hover{color:var(--brand)}
.pick-meta{display:flex;gap:8px;flex-wrap:wrap;color:var(--muted);font-size:13px}
.export-buttons{display:flex;gap:7px;flex-wrap:wrap}
.weak-list{list-style:none;margin:0;padding:0}
.weak-list li{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px solid var(--line)}
.weak-list li:last-child{border-bottom:0}
.weak-list a{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text)}
.weak-list a:hover{color:var(--brand)}
.weak-clear{border:1px solid var(--line);border-radius:7px;padding:3px 8px;color:var(--muted);background:transparent;cursor:pointer;font-size:12px}
.mark-select{border:1px solid var(--line);border-radius:7px;padding:3px 6px;color:var(--muted);background:var(--panel-soft);font-size:12px}
.plan-item{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 11px;border:1px solid var(--line);border-radius:10px;background:var(--panel-soft)}
.plan-item a{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text);font-weight:650}
.plan-item .pick-meta{flex:0 0 150px;align-items:center;justify-content:flex-start}
.plan-item a:hover{color:var(--brand)}
.plan-reason{flex:0 0 auto;padding:2px 8px;border-radius:999px;font-size:12px}
.plan-reason.due{color:var(--warning);background:color-mix(in srgb,var(--warning) 14%,var(--panel))}
.plan-reason.weak{color:var(--danger);background:color-mix(in srgb,var(--danger) 12%,var(--panel))}
.plan-reason.new{color:var(--brand);background:var(--brand-soft)}
.mock-setup{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:12px}
.mock-timer{font-variant-numeric:tabular-nums;font-weight:750;color:var(--brand);font-size:18px}
.mock-list{display:grid;gap:9px;margin-top:14px}
.mock-item{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--panel-soft)}
.mock-item a{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text);font-weight:650}
.mock-item a:hover{color:var(--brand)}
.mock-actions{display:flex;gap:7px;flex:0 0 auto}
.mock-btn{border:1px solid var(--line);border-radius:8px;padding:4px 9px;color:var(--brand);background:var(--brand-soft);cursor:pointer;font-size:12px}
.mock-btn.skip{color:var(--muted);background:transparent}
.mock-report{line-height:1.9;margin-top:12px;padding:12px 14px;border:1px solid var(--line);border-radius:11px;background:var(--panel-soft)}
@media(max-width:760px){.mock-setup{grid-template-columns:repeat(2,1fr)}}
@media(max-width:520px){.mock-setup{grid-template-columns:1fr}}
.track-section{margin:22px 0 0;padding:16px;border:1px solid var(--line);border-radius:15px;background:var(--panel);box-shadow:var(--shadow)}
.track-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.track-head h2{margin:0;font-size:18px}
.track-sub{color:var(--muted);font-size:13px}
.heatmap{display:grid;grid-template-columns:repeat(53,minmax(9px,1fr));gap:3px;overflow-x:auto;padding-bottom:4px}
.hm-cell{aspect-ratio:1;border-radius:2px;background:var(--panel-soft);border:1px solid var(--line)}
.hm-label{display:flex;align-items:center;justify-content:center;min-width:14px;font-size:10px;color:var(--muted);white-space:nowrap}
.hm-cell.level-1{background:var(--hot-hm-1);border-color:transparent}
.hm-cell.level-2{background:var(--hot-hm-2);border-color:transparent}
.hm-cell.level-3{background:var(--hot-hm-3);border-color:transparent}
.hm-cell.level-4{background:var(--hot-hm-4);border-color:transparent}
.hm-legend{display:flex;align-items:center;gap:6px;margin-top:8px;font-size:11px;color:var(--muted)}
.hm-legend i{width:11px;height:11px;border-radius:2px;display:inline-block}
.hm-legend{display:flex;align-items:center;gap:5px;margin-top:10px;color:var(--muted);font-size:12px;flex-wrap:wrap}
#heatmapDetail{min-height:20px;margin-top:8px;color:var(--muted);font-size:13px}
.trend-chart{margin-top:18px;max-width:100%}
.trend-chart .u-title{font-size:14px;color:var(--muted)}
#trend,#trend .uplot,#trend .u-wrap,.history{min-width:0}
#trend .uplot,#trend .u-wrap{width:100%;max-width:100%}
.quick-cards{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px;align-items:start;margin:0 0 22px}
.quick-cards .review-section{margin:0}
.quick-cards .review-list{display:grid;grid-template-columns:1fr;align-content:start;gap:8px;max-height:156px;overflow-y:auto;overscroll-behavior:contain;padding-right:4px}
#reviewList,#pickCard{scrollbar-width:thin}
#reviewList::-webkit-scrollbar,#pickCard::-webkit-scrollbar{width:6px}
.more-section{margin:22px 0 0;display:grid;grid-template-columns:minmax(0,1fr);gap:18px}
.mock-check{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--muted);margin-top:10px}
.shelf-due-fold{margin-top:12px;border:1px solid var(--line);border-radius:11px;background:var(--panel-soft)}
.shelf-due-fold summary{cursor:pointer;padding:9px 12px;font-weight:650;color:var(--text);list-style:none}
.shelf-due-fold summary::-webkit-details-marker{display:none}
.shelf-due-fold summary::before{content:"▸ ";color:var(--brand)}
.shelf-due-fold[open] summary::before{content:"▾ "}
.shelf-due-list{display:grid;gap:7px;padding:0 12px 12px}
.shelf-due-list{max-height:220px;overflow-y:auto;overscroll-behavior:contain}
.shelf-due-link{flex:0 0 auto;color:var(--brand);font-size:13px;text-decoration:none;white-space:nowrap}
.shelf-due-link:hover{text-decoration:underline}
@media(max-width:980px){.quick-cards{grid-template-columns:minmax(0,1fr)}}
footer{margin-top:25px;color:var(--muted);text-align:center;font-size:13px}
@media(max-width:980px){.workspace{grid-template-columns:1fr}.history{order:-1}.history-columns{display:grid;grid-template-columns:1fr 1fr;gap:22px}.history h3{margin-top:0}}
@media(max-width:760px){.shell{width:min(100% - 18px,1240px);padding:18px 0 38px}.hero{align-items:flex-start}.stats{width:100%;grid-template-columns:repeat(2,1fr)}.controls{grid-template-columns:1fr;padding:12px}.method{min-height:0}.card{padding:14px}}
@media(max-width:520px){.history-columns{grid-template-columns:1fr;gap:0}.card-actions{align-items:flex-end}.last-study{white-space:normal}.dashboard-nav{gap:6px}.dashboard-nav a{padding:6px 8px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
/* 手动主题切换（theme-toggle.js 写入 data-theme） */
html[data-theme="dark"]{color-scheme:dark;
  --bg:#0f131b;--panel:#181e29;--panel-soft:#141a24;--text:#edf2fb;--muted:#a7b2c4;
  --line:#313b4c;--brand:#b2b0ff;--brand-strong:#cbc9ff;--brand-soft:#292955;
  --success:#79d8a8;--success-soft:#17382b;--warning:#ffc474;--danger:#ff969d;
  --hot-hm-1:#6fc98c;--hot-hm-2:#3db863;--hot-hm-3:#23944b;--hot-hm-4:#136b33;
  --shadow:0 18px 46px rgba(0,0,0,.22)
}
html[data-theme="light"]{color-scheme:light;--bg:#f3f5fa;--panel:#fff;--panel-soft:#f7f8fc;--text:#172033;--muted:#647188;--line:#dce2ec;--brand:#5755d4;--brand-strong:#4543bd;--brand-soft:#eeedff;--success:#13764b;--success-soft:#e7f6ee;--warning:#a45a00;--danger:#c1363e;--hot-hm-1:#9be9a8;--hot-hm-2:#40c463;--hot-hm-3:#30a14e;--hot-hm-4:#216e39;--shadow:0 14px 38px rgba(31,42,68,.075)}
  /* P2-2 骨架屏 */
  .skeleton{position:relative;overflow:hidden;background:var(--panel-soft);border-radius:9px;min-height:42px}
  .skeleton::after{content:"";position:absolute;inset:0;transform:translateX(-100%);
  background:linear-gradient(90deg,transparent,color-mix(in srgb,var(--muted) 14%,transparent),transparent);
  animation:skel 1.4s infinite}
  @keyframes skel{100%{transform:translateX(100%)}}
  @media(prefers-reduced-motion:reduce){.skeleton::after{animation:none}}
</style>
</head>
<body>
<a class="skip-link" href="#problemGrid">跳到题目列表</a>
<main class="shell">
  <header class="hero">
    <div><h1>Interview Forge</h1><div class="sub">__PROBLEM_COUNT__ 道高频算法题，覆盖 __TOPIC_COUNT__ 个专题；每一次打开与每一轮完成，都会留下可回看的学习轨迹</div><div id="connection" class="connection">正在连接本地数据库</div></div>
    <div class="stats" aria-live="polite">
      <div class="stat"><span>今天看题</span><strong id="todayViewed">0</strong></div>
      <div class="stat"><span>今天完成</span><strong id="todayRounds">0</strong></div>
      <div class="stat"><span>已刷题目</span><strong id="completedCount">0</strong></div>
      <div class="stat"><span>累计轮次</span><strong id="totalRounds">0</strong></div>
      <div class="stat"><span>日 AC / 提交</span><strong id="acTodayText">0 / 0</strong></div>
  <div class="stat"><span>累计 AC / 已解决</span><strong id="acTotalText">0 / 0</strong></div>
  <div class="stat"><span>连续学习</span><strong id="streakCount">0</strong></div>
      <div class="stat"><span>今日目标</span><strong id="goalText">0 / 0</strong><div class="goal-line"><span class="goal-hint">每日轮次</span><input id="goalInput" type="number" min="1" max="50" value="3" aria-label="每日目标轮次"></div></div>
    </div>
  </header>
  <nav class="dashboard-nav" aria-label="学习入口"><a href="library/index.html">学习书架</a><a href="books/hot100/00-总览/01-学习路线.html">学习路线</a><a href="books/hot100/00-总览/02-算法模式地图.html">模式地图</a><a href="books/hot100/00-总览/03-复习清单.html">复习清单</a><a href="books/hot100/04-模板/01-Hot100算法模板.html">算法模板</a><a href="pages/history.html">学习记录</a><a class="lc-button" href="pages/leetcode-connect.html">力扣连接</a></nav>
  <div id="serverNotice" class="notice" hidden>学习服务暂时不可用，请稍后刷新页面重试；若持续失败请联系管理员。</div>
  <section class="progress-section" aria-labelledby="progressLabel"><div class="progress-head"><span id="progressLabel">至少完成一轮的题目</span><strong id="progressText">0 / 100</strong></div><div id="progressBar" class="bar" role="progressbar" aria-label="至少完成一轮的题目" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><div id="progress"></div></div></section>
  <div class="quick-cards">
  <section class="review-section" aria-labelledby="reviewTitle">
    <div class="review-head"><h2 id="reviewTitle">今日待复习</h2><span id="reviewSummary" class="review-summary">正在读取…</span><a id="shelfDueLink" class="shelf-due-link" href="library/index.html" title="去书架查看各模块待复习章节">书架待复习 0 项 →</a><button id="remindButton" class="round-button" type="button">开启复习提醒</button></div>
    <div id="reviewList" class="review-list"><div class="skeleton" style="flex:1"></div><div class="skeleton" style="flex:1"></div></div></div>
  </section>
  <section class="review-section" aria-labelledby="pickTitle">
    <div class="review-head"><h2 id="pickTitle">今日计划</h2><button id="pickAgain" class="round-button" type="button">换一组</button></div>
    <div id="pickCard" class="review-list">正在读取…</div>
  </section>
  </div>
  <div class="workspace">
  <section aria-label="题目学习区">
    <section class="controls" aria-label="筛选题目">
      <div class="field"><label for="search">搜索</label><input id="search" type="search" placeholder="题号、题名或核心方法" autocomplete="off"></div>
      <div class="field"><label for="category">专题</label><select id="category"><option value="">全部专题</option></select></div>
      <div class="field"><label for="status">学习轮次</label><select id="status"><option value="">全部轮次</option><option value="due">待复习</option><option value="weak">薄弱</option><option value="new">尚未完成</option><option value="once">完成 1 轮</option><option value="repeat">完成 2 轮以上</option></select></div>
    </section>
    <section id="problemGrid" aria-label="Hot 100 题目"><div id="grid" class="grid"></div><div id="empty" class="empty" hidden>没有匹配的题目，请调整搜索词或筛选条件。</div></section>
  </section>
  </div>
  <div class="more-section">
  <section class="review-section" aria-labelledby="weakTitle">
    <div class="review-head"><h2 id="weakTitle">薄弱清单</h2><a class="review-summary" href="books/hot100/00-总览/05-错题本.html">错题本页 →</a>
      <div class="export-buttons">
        <button class="round-button" type="button" data-export="weak">导出薄弱清单</button>
        <button class="round-button" type="button" data-export="anki">导出 Anki CSV</button>
        <button class="round-button" type="button" data-export="records">导出记录 JSON</button>
        <button class="round-button" type="button" data-export="db">备份数据库</button>
        <button class="round-button" type="button" data-export="weekly">导出周报</button>
      </div>
    </div>
    <ul id="weakList" class="weak-list"></ul>
  </section>
  <section class="review-section" aria-labelledby="mockTitle">
    <div class="review-head"><h2 id="mockTitle">限时模拟</h2><span id="mockStatus" class="review-summary">随机组卷，模拟考试节奏</span></div>
    <div class="mock-setup">
      <div class="field"><label for="mockCount">题目数</label><select id="mockCount"><option value="5">5 题</option><option value="10" selected>10 题</option><option value="20">20 题</option></select></div>
      <div class="field"><label for="mockMinutes">时长（分钟）</label><select id="mockMinutes"><option value="10">10</option><option value="20" selected>20</option><option value="30">30</option></select></div>
      <div class="field"><label for="mockCategory">专题</label><select id="mockCategory"><option value="">全部专题</option></select></div>
      <div class="field"><label for="mockDifficulty">难度</label><select id="mockDifficulty"><option value="">全部难度</option><option value="简单">简单</option><option value="中等">中等</option><option value="困难">困难</option></select></div>
    </div>
    <div style="margin-top:12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap"><button id="mockStart" class="round-button" type="button">开始模拟</button><span id="mockTimer" class="mock-timer"></span></div>
    <div id="mockList" class="mock-list"></div>
    <div id="mockReport"></div>
  </section>
  <section class="track-section" aria-labelledby="trackTitle">
    <div class="track-head"><h2 id="trackTitle">学习轨迹</h2><span id="heatmapDetail" class="track-sub">近 365 天活跃热力图，点击格子看当日明细</span></div>
    <div id="heatmap" class="heatmap" role="img" aria-label="近 365 天学习活跃热力图"></div>
<div class="hm-legend" aria-hidden="true"><span>低</span><i class="hm-cell level-1"></i><i class="hm-cell level-2"></i><i class="hm-cell level-3"></i><i class="hm-cell level-4"></i><span>高</span><span style="margin-left:8px">绿色深浅 = 当日力扣提交次数（0 / 1 / 2–4 / 5–9 / 10+）</span></div>
    <div class="track-head" style="margin-top:20px"><h3 id="trendTitle">近 14 天趋势</h3><span class="track-sub">每日看题与完成轮次</span></div>
    <div id="trend" class="trend-chart"></div>
  </section>
  </div>
  <div id="toast" class="toast" aria-live="polite"></div>
<footer><a href="guide.html">完整使用指南</a> · <a href="pages/leetcode-connect.html">力扣连接</a> · <span id="lcStatus" class="muted">力扣：检测中…</span> · 你的学习数据保存在服务端，仅自己可见</footer>
</main>
<script src="assets/uplot.min.js?v=__ASSET_VERSION__"></script>
<script>
const problems=__HOT100_PROBLEMS__;
const state={online:false,data:{summary:{today_viewed:0,today_rounds:0,completed_problems:0,total_rounds:0,active_days:0},problems:{},days:[],recent:[]},daily:{summary:{due:0,overdue:0,problems:0,overdue_problems:0,contents:0,overdue_contents:0},problems:[],contents:[]},settings:{}};
const grid=document.getElementById('grid');
const empty=document.getElementById('empty');
const search=document.getElementById('search');
const category=document.getElementById('category');
const status=document.getElementById('status');
const toast=document.getElementById('toast');
const reviewList=document.getElementById('reviewList');
const reviewSummary=document.getElementById('reviewSummary');
const pickCard=document.getElementById('pickCard');
const weakList=document.getElementById('weakList');

[...new Set(problems.map(problem=>problem.category))].forEach(name=>{const option=document.createElement('option');option.value=name;option.textContent=name;category.appendChild(option)});
function esc(value){return String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))}
function infoFor(id){return state.data.problems[String(id)]||{rounds:0,last_viewed_at:null,last_completed_at:null,last_activity_at:null}}
function localTime(value){if(!value)return '尚无记录';const date=new Date(value);return `${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')} ${String(date.getHours()).padStart(2,'0')}:${String(date.getMinutes()).padStart(2,'0')}`}
function updateSummary(){
  const summary=state.data.summary;
  document.getElementById('todayViewed').textContent=summary.today_viewed;
  document.getElementById('todayRounds').textContent=summary.today_rounds;
  document.getElementById('completedCount').textContent=summary.completed_problems;
  document.getElementById('totalRounds').textContent=summary.total_rounds;
  const subs=(state.data.submissions||{}).summary||{};
  document.getElementById('acTodayText').textContent=`${subs.today_ac||0} / ${subs.today_submits||0}`;
  document.getElementById('acTotalText').textContent=`${subs.total_ac||0} / ${subs.solved_ac||0}`;
  document.getElementById('streakCount').textContent=summary.streak||0;
  document.getElementById('goalText').textContent=`${summary.today_rounds||0} / ${summary.daily_goal||3}`;
  document.getElementById('goalInput').value=summary.daily_goal||3;
  const completed=summary.completed_problems;
  const percent=problems.length?Math.round(completed/problems.length*100):0;
  document.getElementById('progress').style.width=`${percent}%`;
  document.getElementById('progressText').textContent=`${completed} / ${problems.length}`;
  document.getElementById('progressBar').setAttribute('aria-valuenow',String(completed));
}
function renderReview(){
  const daily=state.daily;
  const items=daily.problems.map(item=>({href:item.note,title:`${item.id}. ${item.title}`,meta:`${item.difficulty||item.category||''} · 已 ${item.rounds} 轮`,due:item.due_date,overdue:item.due_date<daily.today}));
  reviewSummary.textContent=`${daily.summary.problems} 题待复习${daily.summary.overdue_problems?`（逾期 ${daily.summary.overdue_problems}）`:''}`;
  const shelfLink=document.getElementById('shelfDueLink');
  if(shelfLink) shelfLink.textContent=`书架待复习 ${daily.summary.contents||0} 项 →`;
  let contentsBlock='';
  if(state.settings&&state.settings.review_include_contents==='1'&&daily.contents.length){
    contentsBlock=`<details class="shelf-due-fold" open><summary>书架章节 ${daily.contents.length} 项（逾期 ${daily.summary.overdue_contents||0}）</summary><div class="shelf-due-list">${daily.contents.map(item=>`<div class="review-item ${item.due_date<daily.today?'due-overdue':''}"><a href="${esc(item.url)}" title="${esc(item.title)}">${esc(item.module_title)} · ${esc(item.title)}</a><span class="due-badge">${item.due_date<daily.today?`逾期 ${esc(item.due_date)}`:`今日 ${esc(item.due_date)}`}</span></div>`).join('')}</div></details>`;
  }
  reviewList.innerHTML=(items.length?items.map(item=>`<div class="review-item ${item.overdue?'due-overdue':''}"><a href="${esc(item.href)}" title="${esc(item.title)}">${esc(item.title)}</a><span class="due-badge">${item.overdue?`逾期 ${esc(item.due)}`:`今日 ${esc(item.due)}`}</span></div>`).join(''):'<div class="review-empty">今日没有到期的题目，可以学新题或复习其他内容。</div>')+contentsBlock;
}
async function loadPick(randomize){
  try{
    const response=await fetch(`/api/plan${randomize?'?count=3&random=1':''}`,{cache:'no-store'});
    if(!response.ok)throw new Error('pick failed');
    const plan=await response.json();
    const reasonLabels={due:'待复习',weak:'薄弱',new:'新题'};
    pickCard.innerHTML=plan.items.length?plan.items.map(item=>`<div class="plan-item"><a href="${esc(item.note)}" title="${esc(item.title)}">${item.id}. ${esc(item.title)}</a><span class="pick-meta"><span class="pill">${esc(item.category)}</span><span class="difficulty-${item.difficulty}">${item.difficulty}</span></span><span class="plan-reason ${item.reason}">${reasonLabels[item.reason]||item.reason}</span></div>`).join(''):'<div class="review-empty">暂无计划项，先完成几轮复习吧。</div>';
  }catch(_){
    pickCard.innerHTML='<div class="review-empty">计划加载失败，请稍后刷新重试</div>';
  }
}
const markLabels={weak:'薄弱',reviewing:'复习中',mastered:'已掌握'};
function renderWeak(){
  const marks=state.data.marks||{};
  const autoWeak=(state.data.submissions||{}).auto_weak||{};
  const items=problems.filter(p=>marks[String(p.id)]==='weak'||autoWeak[String(p.id)]);
  weakList.innerHTML=items.length?items.map(p=>{
    const manual=marks[String(p.id)]==='weak';
    const auto=!!autoWeak[String(p.id)];
    return `<li><a href="${esc(p.note)}">${p.id}. ${esc(p.title)}</a><span class="muted">${manual?'手动标记':auto?'AC 通过率低于 50%':''}</span>${manual?`<button class="weak-clear" type="button" data-clear="${p.id}">清除标记</button>`:''}</li>`;
  }).join(''):'<li class="history-empty">还没有薄弱题：提交多次后 AC 通过率低于 50% 会自动进入。</li>';
  weakList.querySelectorAll('[data-clear]').forEach(button=>button.addEventListener('click',()=>setMark(Number(button.dataset.clear),'')));
}
function renderHeatmap(){
  const el=document.getElementById('heatmap');
  const days=state.data.activity||[];
  if(!days.length){el.innerHTML='';return}
  const first=new Date(`${days[0].date}T00:00:00`);
  const leading=(first.getDay()+6)%7;
  const cells=[...Array.from({length:leading},()=>null),...days];
  const weeks=[];
  for(let i=0;i<cells.length;i+=7)weeks.push(cells.slice(i,i+7));
  while(weeks[weeks.length-1].length<7)weeks[weeks.length-1].push(null);
  el.style.gridTemplateColumns=`auto repeat(${weeks.length},minmax(9px,1fr))`;
  const monthRow=['<span class="hm-label"></span>'];
  let prevMonth='';
  for(const week of weeks){
    const day=week.find(Boolean);
    const month=day?String(day.date).slice(0,7):'';
    monthRow.push(month&&month!==prevMonth?`<span class="hm-label hm-month">${Number(month.slice(5))}月</span>`:'<span class="hm-label"></span>');
    if(month)prevMonth=month;
  }
  const weekLabels=['一','','三','','五','',''];
  const rows=weeks[0].map((_,row)=>`<span class="hm-label hm-week">${weekLabels[row]||''}</span>`+weeks.map(week=>{
    const day=week[row];
    if(!day)return '<span class="hm-cell"></span>';
    const submits=Number(day.submits||0);
    const level=submits===0?0:submits===1?1:submits<=4?2:submits<=9?3:4;
    const detail=`提交 ${submits} 次${Number(day.viewed||0)?` · 看 ${day.viewed} 题`:''}${Number(day.rounds||0)?` · 完成 ${day.rounds} 轮`:''}`;
    return `<span class="hm-cell level-${level}" data-date="${esc(day.date)}" data-viewed="${esc(day.viewed)}" data-rounds="${esc(day.rounds)}" data-submits="${esc(submits)}" title="${esc(day.date)}：${esc(detail)}" tabindex="0" role="gridcell" aria-label="${esc(day.date)} ${esc(detail)}"></span>`;
  }).join('')).join('');
  el.innerHTML=monthRow.join('')+rows;
  el.querySelectorAll('.hm-cell[data-date]').forEach(cell=>{
    const show=()=>{document.getElementById('heatmapDetail').textContent=`${cell.dataset.date}：看 ${cell.dataset.viewed} 题 · 完成 ${cell.dataset.rounds} 轮${Number(cell.dataset.submits)?` · 提交 ${cell.dataset.submits} 次`:''}`};
    cell.addEventListener('click',show);
    cell.addEventListener('focus',show);
    cell.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();show()}});
  });
}
let trendChart=null;
function renderTrend(){
  const days=(state.data.activity||[]).slice(-14);
  const el=document.getElementById('trend');
  if(!el)return;
  if(!window.uPlot){el.innerHTML='<div class="history-empty">趋势图组件未加载</div>';return}
  if(!days.length){el.innerHTML='<div class="history-empty">还没有学习记录，完成几轮后这里会显示趋势。</div>';return}
  try{
    const width=Math.max(240,el.clientWidth||320);
    const cssv=name=>getComputedStyle(document.documentElement).getPropertyValue(name).trim()||'#647188';
      const opts={
      width,height:210,
      legend:{show:true,isolate:false},
      scales:{x:{time:false},y:{min:0}},
      series:[
        {label:'日期'},
        {label:'看题',stroke:cssv('--brand'),width:2,points:{show:false},value:(_u,v)=>v==null?'–':`${v} 题`},
        {label:'完成轮次',stroke:cssv('--success'),width:2,strokeDash:[6,4],points:{show:false},value:(_u,v)=>v==null?'–':`${v} 轮`},
        {label:'提交',stroke:cssv('--danger'),width:2,strokeDash:[2,3],points:{show:false},value:(_u,v)=>v==null?'–':`${v} 次`}
      ],
      axes:[
        {stroke:cssv('--muted'),grid:{stroke:cssv('--line')},values:(_u,vals)=>vals.map(v=>{const d=days[Math.round(v)];return d?d.date.slice(5):''})},
        {stroke:cssv('--muted'),grid:{stroke:cssv('--line')}}
      ],
      cursor:{x:true,y:true}
    };
    const data=[days.map((_,i)=>i),days.map(d=>Number(d.viewed||0)),days.map(d=>Number(d.rounds||0)),days.map(d=>Number(d.submits||0))];
    if(trendChart){
      trendChart.setData(data);
    }else{
      trendChart=new uPlot(opts,data,el);
      requestAnimationFrame(()=>{if(trendChart)trendChart.redraw()});
    }
  }catch(error){
    el.innerHTML=`<div class="history-empty">趋势图渲染失败：${esc(error.message)}</div>`;
  }
}
function renderCards(){
  const query=search.value.trim().toLowerCase();
  const dueIds=new Set(state.daily.problems.map(item=>String(item.id)));
  const dueOverdue=new Set(state.daily.problems.filter(item=>item.due_date<state.daily.today).map(item=>String(item.id)));
  const marks=state.data.marks||{};
  const autoWeak=(state.data.submissions||{}).auto_weak||{};
  const list=problems.filter(problem=>{
    const rounds=Number(infoFor(problem.id).rounds||0);
    const matchesText=!query||`${problem.id} ${problem.title} ${problem.method}`.toLowerCase().includes(query);
    const matchesCategory=!category.value||problem.category===category.value;
    const isDue=dueIds.has(String(problem.id));
    const mark=marks[String(problem.id)]||(autoWeak[String(problem.id)]?'weak':'');
    const matchesStatus=!status.value||(status.value==='due'&&isDue)||(status.value==='weak'&&mark==='weak')||(status.value==='new'&&rounds===0)||(status.value==='once'&&rounds===1)||(status.value==='repeat'&&rounds>=2);
    return matchesText&&matchesCategory&&matchesStatus;
  });
  grid.innerHTML=list.map(problem=>{
    const info=infoFor(problem.id);const rounds=Number(info.rounds||0);const last=info.last_activity_at;
    const isDue=dueIds.has(String(problem.id));
    const overdue=dueOverdue.has(String(problem.id));
    const manualMark=marks[String(problem.id)]||'';
    const autoWeakFlag=!!autoWeak[String(problem.id)];
    const mark=manualMark||(autoWeakFlag?'weak':'');
    const everAc=((state.data.submissions||{}).ever_ac||{})[String(problem.id)];
    const badge=isDue?`<span class="due-pill ${overdue?'overdue':''}">待复习</span>`:'';
    const acBadge=everAc?`<span class="ac-pill">已 AC</span>`:'';
    const markBadge=mark?`<span class="mark-pill ${mark}">${markLabels[mark]}</span>`:'';
    const submissionLine=info.submits?`提交：AC ${info.ac_submits||0} / ${info.submits}（${Math.round((info.pass_rate||0)*100)}%） · 最近：${localTime(info.last_submitted_at)}`:`最近：${localTime(last)}`;
    const nextDue=info.next_due?` · 下次 ${String(info.next_due).slice(5)}`:'';
    return `<article class="card ${rounds?'studied':''} ${isDue?'due':''} ${overdue?'overdue':''}"><div class="card-head"><h2><a href="${problem.note}">${problem.id}. ${esc(problem.title)}</a></h2><span class="round-count">${rounds} 轮</span>${acBadge}${badge}${markBadge}</div><div class="meta"><span class="pill">${esc(problem.category)}</span><span class="difficulty-${problem.difficulty}">${problem.difficulty}</span></div><div class="method">${esc(problem.method)}</div><div class="card-actions"><span class="last-study">${submissionLine}${nextDue}</span><div class="card-buttons"><select class="mark-select" data-mark="${problem.id}" aria-label="标记薄弱"><option value="">标记</option><option value="mastered" ${manualMark==='mastered'?'selected':''}>已掌握</option><option value="reviewing" ${manualMark==='reviewing'?'selected':''}>复习中</option><option value="weak" ${manualMark==='weak'?'selected':''}>薄弱</option><option value="">清除</option></select></div></div></article>`;
  }).join('');
  empty.hidden=list.length!==0;
  grid.querySelectorAll('[data-mark]').forEach(select=>select.addEventListener('change',()=>setMark(Number(select.dataset.mark),select.value)));
}
async function setMark(problemId,mark){
  try{
    const response=await fetch('/api/mark',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target_type:'problem',target_id:String(problemId),mark})});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'标记失败');
    await refresh();
  }catch(error){toast.textContent=`标记失败：${error.message}`}
}
function downloadText(filename,text,mime){
  const blob=new Blob([text],{type:mime});
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');
  link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();
  URL.revokeObjectURL(url);
}
async function exportData(kind){
  try{
    const response=await fetch(`/api/export?kind=${kind}`,{cache:'no-store'});
    if(!response.ok)throw new Error('导出失败');
    const disposition=response.headers.get('Content-Disposition')||'';
    const star=disposition.match(/filename\*=UTF-8''([^;]+)/i);
    const filename=star?decodeURIComponent(star[1]):(disposition.match(/filename="([^"]+)"/)?.[1]||`hot100-${kind}.txt`);
    if(kind==='db'){
      const blob=await response.blob();
      const url=URL.createObjectURL(blob);
      const link=document.createElement('a');link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();
      URL.revokeObjectURL(url);
    }else{
      downloadText(filename,await response.text(),response.headers.get('Content-Type')||'text/plain');
    }
    toast.textContent=`已导出 ${filename}`;
  }catch(error){toast.textContent=`导出失败：${error.message}`}
}
async function saveGoal(){
  const value=String(Math.max(1,Math.min(50,Number(document.getElementById('goalInput').value)||3)));
  try{
    const response=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'daily_goal_rounds',value})});
    if(!response.ok)throw new Error('保存失败');
    await refresh();
    toast.textContent=`每日目标已设为 ${value} 轮`;
  }catch(error){toast.textContent=`保存失败：${error.message}`}
}
function render(){updateSummary();renderReview();renderWeak();renderHeatmap();renderTrend();renderCards()}
document.getElementById('pickAgain').addEventListener('click',()=>loadPick(true));
document.querySelectorAll('[data-export]').forEach(button=>button.addEventListener('click',()=>exportData(button.dataset.export)));
document.getElementById('goalInput').addEventListener('change',saveGoal);
let mockState=null;let mockTimerId=null;
function mockTick(){
  if(!mockState)return;
  const left=mockState.deadline-Date.now();
  if(left<=0){clearInterval(mockTimerId);mockState.finished=true;mockFinish(true);return}
  const s=Math.max(0,Math.floor(left/1000));
  document.getElementById('mockTimer').textContent=`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;
}
async function mockStart(){
  if(mockState&&!mockState.finished){mockState.finished=true;clearInterval(mockTimerId)}
  const count=Number(document.getElementById('mockCount').value);
  const minutes=Number(document.getElementById('mockMinutes').value);
  const category=document.getElementById('mockCategory').value;
  const difficulty=document.getElementById('mockDifficulty').value;
  document.getElementById('mockStatus').textContent='组卷中…';
  try{
    const response=await fetch(`/api/mock?count=${count}&category=${encodeURIComponent(category)}&difficulty=${encodeURIComponent(difficulty)}`,{cache:'no-store'});
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||'组卷失败');
    mockState={problems:data.problems,index:0,done:[],skip:[],startedAt:Date.now(),deadline:Date.now()+minutes*60000,finished:false};
    document.getElementById('mockStatus').textContent=`${data.count} 题 · ${minutes} 分钟`;
    document.getElementById('mockReport').innerHTML='';
    mockTimerId=setInterval(mockTick,1000);mockTick();mockRender();
  }catch(error){document.getElementById('mockStatus').textContent=`组卷失败：${error.message}`}
}
function mockRender(){
  if(!mockState)return;
  const list=document.getElementById('mockList');
  const current=mockState.problems[mockState.index];
  list.innerHTML=`<div class="mock-item"><a href="${esc(current.note)}" target="_blank" rel="noopener">${current.id}. ${esc(current.title)}</a><span class="pick-meta"><span class="pill">${esc(current.category)}</span><span class="difficulty-${current.difficulty}">${current.difficulty}</span></span><div class="mock-actions"><button class="mock-btn skip" type="button" data-mock="skip">跳过</button><button class="mock-btn" type="button" data-mock="done">完成</button></div></div><p class="review-empty">第 ${mockState.index+1} / ${mockState.problems.length} 题，点击完成或跳过进入下一题。</p>`;
  list.querySelector('[data-mock="done"]').addEventListener('click',()=>{mockState.done.push(current.id);mockNext()});
  list.querySelector('[data-mock="skip"]').addEventListener('click',()=>{mockState.skip.push(current.id);mockNext()});
}
function mockNext(){
  if(!mockState)return;
  mockState.index+=1;
  if(mockState.index>=mockState.problems.length){clearInterval(mockTimerId);mockState.finished=true;mockFinish(false)}else{mockRender()}
}
async function mockFinish(timeout){
  if(!mockState)return;
  const used=Math.round((Date.now()-mockState.startedAt)/1000);
  const report=document.getElementById('mockReport');
  report.innerHTML=`<div class="mock-report"><strong>模拟结束</strong><br>完成 ${mockState.done.length} 题 · 跳过 ${mockState.skip.length} 题 · 用时 ${Math.floor(used/60)} 分 ${used%60} 秒${timeout?'（时间到）':''}</div>`;
  document.getElementById('mockList').innerHTML='';
  document.getElementById('mockTimer').textContent='';
  document.getElementById('mockStatus').textContent=`完成 ${mockState.done.length} / ${mockState.problems.length}`;
  if(mockState.done.length){
    toast.textContent=`模拟完成 ${mockState.done.length} 题；真实 AC 会自动计入轮次`;
  }
  mockState=null;
}
document.getElementById('mockStart').addEventListener('click',mockStart);
[...new Set(problems.map(problem=>problem.category))].forEach(name=>{const option=document.createElement('option');option.value=name;option.textContent=name;document.getElementById('mockCategory').appendChild(option)});
window.addEventListener('resize',()=>{
  if(!trendChart||!state.data.activity)return;
  const el=document.getElementById('trend');
  const width=Math.max(240,el.clientWidth||320);
  if(Math.abs(width-trendChart.width)>60)renderTrend();
});
async function updateLcStatus(){
  const el=document.getElementById('lcStatus');
  if(!el)return;
  try{
    const response=await fetch('/api/leetcode/status',{cache:'no-store'});
    const data=await response.json();
    if(!response.ok)throw new Error();
    if(data.credentials_saved){
      if(data.connected){el.textContent=`力扣：已连接 ${data.user_name}`;}
      else{el.innerHTML='力扣：<a href="pages/leetcode-connect.html" style="color:var(--danger)">会话已失效，点击重新获取</a>';}
    }else{
      el.innerHTML='力扣：<a href="pages/leetcode-connect.html">未连接</a>';
    }
  }catch(error){
    el.textContent='力扣：检测失败';
  }
}
async function refresh(){
  try{
    const [dashboardResponse,dailyResponse,settingsResponse]=await Promise.all([
      fetch('/api/dashboard',{cache:'no-store'}),
      fetch('/api/daily',{cache:'no-store'}),
      fetch('/api/settings',{cache:'no-store'})
    ]);
    if(!dashboardResponse.ok||!dailyResponse.ok||!settingsResponse.ok)throw new Error('database unavailable');
    state.data=await dashboardResponse.json();
    state.daily=await dailyResponse.json();
    state.settings=await settingsResponse.json();
    state.online=true;
    document.getElementById('connection').classList.add('online');
    document.getElementById('connection').textContent='SQLite 数据库已连接';
    document.getElementById('serverNotice').hidden=true;
  }catch(error){
    state.online=false;
    document.getElementById('connection').classList.remove('online');
    document.getElementById('connection').textContent='当前是静态浏览模式';
    document.getElementById('serverNotice').hidden=false;
  }
  updateLcStatus();
  render();
  maybeNotify();
}
if('serviceWorker' in navigator&&location.protocol.startsWith('http')){
  window.addEventListener('load',()=>navigator.serviceWorker.register('service-worker.js').catch(()=>{}));
}
let lastNotifyDate='';
function maybeNotify(){
  if(!('Notification' in window)||Notification.permission!=='granted'||!state.online)return;
  const daily=state.daily||{summary:{due:0,overdue:0}};
  if(!daily.summary.due||lastNotifyDate===daily.today)return;
  lastNotifyDate=daily.today;
  try{new Notification('Interview Forge',{body:`今日待复习 ${daily.summary.due} 项${daily.summary.overdue?`（逾期 ${daily.summary.overdue}）`:''}，去复习吧`})}catch(_){}
}
document.getElementById('remindButton').addEventListener('click',async()=>{
  if(!('Notification' in window)){toast.textContent='当前浏览器不支持通知';return}
  const permission=await Notification.requestPermission();
  document.getElementById('remindButton').textContent=permission==='granted'?'复习提醒已开启':'提醒被拒绝';
  if(permission==='granted'){toast.textContent='复习提醒已开启，刷新页面后会通知待复习项';maybeNotify()}
});
search.addEventListener('input',renderCards);
[category,status].forEach(control=>control.addEventListener('change',renderCards));
refresh();
loadPick(false);
</script>
</body>
</html>

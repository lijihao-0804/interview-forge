/* Keep a chapter index aligned with the article's own scroll container. */
(() => {
  "use strict";

  function reveal(rail, link) {
    if (!link || !rail.clientHeight || rail.scrollHeight <= rail.clientHeight) return;
    const bounds = rail.getBoundingClientRect();
    const item = link.getBoundingClientRect();
    const margin = Math.min(40, rail.clientHeight / 6);
    if (item.height && (item.top < bounds.top + margin || item.bottom > bounds.bottom - margin)) {
      rail.scrollTop += item.top - bounds.top - (rail.clientHeight - item.height) / 2;
    }
  }

  document.querySelectorAll(".shelf-topic-links").forEach(rail => {
    reveal(rail, rail.querySelector(".shelf-topic-link.current"));
  });

  function track(rail) {
    const scroller = rail.closest("#bookScroll");
    const scrollTarget = scroller || window;
    const mobileLinks = document.querySelectorAll(".mobile-toc a[href^='#'], .mobiletoc a[href^='#']");
    let sections = [];
    let frame = 0;
    let activeId = "";
    let clicked = null;

    function schedule() {
      if (!frame) frame = requestAnimationFrame(update);
    }

    function rebuild() {
      sections = [];
      for (const link of rail.querySelectorAll("a[href^='#']")) {
        let id = link.hash.slice(1);
        try { id = decodeURIComponent(id); } catch (_) {}
        const heading = document.getElementById(id);
        if (heading) sections.push({ link, heading });
      }
      activeId = "";
      clicked = null;
      schedule();
    }

    function update() {
      frame = 0;
      if (!sections.length) return;
      const top = scroller ? scroller.getBoundingClientRect().top : 0;
      const height = scroller ? scroller.clientHeight : window.innerHeight;
      const position = scroller ? scroller.scrollTop : window.scrollY;
      const limit = (scroller || document.scrollingElement).scrollHeight - height;
      const line = top + Math.min(100, height * 0.18);
      let current = null;
      for (const section of sections) {
        const rect = section.heading.getBoundingClientRect();
        if (!rect.height) continue;
        if (!current || rect.top <= line || (limit > 0 && position >= limit - 2)) current = section;
      }
      if (clicked && clicked.position === position) current = clicked.section;
      else clicked = null;
      if (!current) return;
      const id = current.heading.id;
      const changed = activeId !== id;
      activeId = id;
      for (const {link, heading} of sections) {
        const active = heading.id === id;
        // Generated chapters also update this class from an intersection observer.
        if (link.classList.contains("active") !== active) link.classList.toggle("active", active);
        if (changed) {
          if (active) link.setAttribute("aria-current", "location");
          else link.removeAttribute("aria-current");
        }
      }
      if (changed) {
        for (const link of mobileLinks) {
          if (link.hash === current.link.hash) link.setAttribute("aria-current", "location");
          else link.removeAttribute("aria-current");
        }
        reveal(rail, current.link);
      }
    }

    rail.addEventListener("click", event => {
      const link = event.target.closest("a");
      const section = sections.find(entry => entry.link === link);
      if (!section || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      requestAnimationFrame(() => {
        if (!section.heading.isConnected) return;
        clicked = {section, position: scroller ? scroller.scrollTop : window.scrollY};
        schedule();
      });
    });
    new MutationObserver(changes => {
      // AgentHub replaces its outline on chapter and reading-mode changes.
      if (changes.some(change => change.type === "childList")) rebuild();
      else schedule();
    }).observe(rail, {childList: true, subtree: true, attributes: true, attributeFilter: ["class"]});
    scrollTarget.addEventListener("scroll", schedule, {passive: true});
    window.addEventListener("resize", () => { activeId = ""; schedule(); });
    window.addEventListener("pageshow", schedule);
    window.addEventListener("hashchange", schedule);
    const article = document.querySelector("#chapterArticle,main article,article.markdown-body");
    if (article && window.ResizeObserver) new ResizeObserver(schedule).observe(article);
    rebuild();
  }

  document.querySelectorAll("#chapterToc, main.reading > .toc, main.reading > .contents, .sol-rail-right:has(.toc), .sol-rail-left:has(.toc)").forEach(track);
})();

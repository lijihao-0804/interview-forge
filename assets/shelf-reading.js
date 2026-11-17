/* The library API is scoped to the signed-in account. Keep its resume link in
 * memory only and discard responses from a superseded session. */
(() => {
  const auth = window.InterviewForgeGuestAuth;
  const section = document.getElementById("shelfResume");
  const book = section.querySelector("[data-resume-book]");
  const chapter = section.querySelector("[data-resume-chapter]");
  const start = section.querySelector("[data-resume-open]");
  let account = null;
  let generation = 0;

  function clearResume() {
    section.hidden = true;
    book.textContent = chapter.textContent = "";
    book.removeAttribute("href");
    start.removeAttribute("href");
  }

  function paintProgress(modules) {
    document.querySelectorAll("[data-module-progress]").forEach(bar => {
      const id = bar.dataset.moduleProgress;
      const info = modules[id];
      const pct = info && info.total ? Math.round(info.completed / info.total * 100) : 0;
      bar.style.width = pct + "%";
      const label = document.querySelector('[data-module-pct="' + CSS.escape(id) + '"]');
      if (label) label.textContent = pct + "%";
    });
  }

  async function load(session, refresh = false) {
    const key = session?.status === "authenticated" && session.user
      ? String(session.user.id ?? session.user.username) : null;
    if (!refresh && key === account) return;
    const token = ++generation;
    if (key !== account) {
      clearResume();
      paintProgress({});
    }
    account = key;
    if (key === null) return;
    try {
      const response = await auth.request("/api/library", {cache: "no-store"});
      if (!response.ok) throw new Error("library unavailable");
      const data = await response.json();
      if (token !== generation) return;
      paintProgress(data.modules || {});
      clearResume();
      if (!data.resume) return;
      book.textContent = data.resume.book_title;
      book.href = data.resume.book_url;
      chapter.textContent = data.resume.chapter_title;
      start.href = data.resume.chapter_url;
      section.hidden = false;
    } catch (_) {
      if (token === generation) clearResume();
    }
  }

  document.addEventListener("interviewforge:auth-change", event => load(event.detail));
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") load(auth.getState(), true);
  });
  window.addEventListener("pageshow", event => {
    if (event.persisted) load(auth.getState(), true);
  });
  auth.ready().then(() => load(auth.getState()));
})();

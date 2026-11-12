/* Keep the current item visible in every library TOC rail.
 * The chapter pages already highlight the current section; this only handles
 * scrolling the rail so the active item sits near the vertical center. */
(function () {
  'use strict';

  function centerRail(rail, selector) {
    if (!rail || !rail.clientHeight) return;
    var current = null;
    // A direct #section URL is the most precise target; prefer it over the
    // IntersectionObserver's active item, which may still be one heading behind
    // while the browser finishes scrolling.
    if (location.hash) {
      try {
        current = rail.querySelector('.toc a[href="' + location.hash + '"]');
        if (current) {
          rail.querySelectorAll('.toc a.active').forEach(function (old) { old.classList.remove('active'); });
          current.classList.add('active');
        }
      } catch (_) {}
    }
    if (!current) current = rail.querySelector(selector);
    if (!current && rail.querySelector('.toc')) {
      // No active class yet: pick the last heading whose top is above the
      // reading midpoint, so the rail has a sensible current item immediately.
      var links = rail.querySelectorAll('.toc a[href^="#"]');
      var best = null;
      var midpoint = window.innerHeight * 0.4;
      Array.prototype.forEach.call(links, function (link) {
        var id = (link.getAttribute('href') || '').slice(1);
        var heading = id && document.getElementById(id);
        if (!heading) return;
        var top = heading.getBoundingClientRect().top;
        if (top <= midpoint) best = link;
      });
      current = best;
    }
    if (!current) return;
    var railRect = rail.getBoundingClientRect();
    var currentRect = current.getBoundingClientRect();
    if (currentRect.height === 0 && currentRect.width === 0) return;
    var target = rail.scrollTop + (currentRect.top - railRect.top)
      - rail.clientHeight / 2 + currentRect.height / 2;
    rail.scrollTop = Math.max(0, target);
  }

  function centerAll() {
    document.querySelectorAll('.shelf-topic-links').forEach(function (rail) {
      centerRail(rail, '.shelf-topic-link.current');
    });
    document.querySelectorAll('.sol-rail-right, .sol-rail-left').forEach(function (rail) {
      centerRail(rail, '.toc a.active');
    });
  }

  function schedule() {
    setTimeout(centerAll, 0);
    setTimeout(centerAll, 80);
    setTimeout(centerAll, 300);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', schedule);
  } else {
    schedule();
  }
  window.addEventListener('load', schedule);
  window.addEventListener('hashchange', schedule);

  // IntersectionObserver in chapter pages changes `active` while reading.
  if (window.MutationObserver) {
    var observer = new MutationObserver(centerAll);
    document.querySelectorAll('.shelf-topic-links, .sol-rail-right, .sol-rail-left').forEach(function (rail) {
      observer.observe(rail, { subtree: true, attributes: true, attributeFilter: ['class'] });
    });
  }
})();

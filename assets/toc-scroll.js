/* Keep the current item visible in every library TOC rail.
 * The chapter pages already highlight the current section; this only handles
 * scrolling the rail so the active item sits near the vertical center. */
(function () {
  'use strict';

  function centerRail(rail, selector) {
    if (!rail || !rail.clientHeight) return;
    var current = rail.querySelector(selector);
    if (!current && location.hash && rail.querySelector('.toc')) {
      try {
        current = rail.querySelector('.toc a[href="' + location.hash + '"]');
      } catch (_) {}
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

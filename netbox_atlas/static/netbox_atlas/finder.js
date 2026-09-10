/*
 * Finding one thing among hundreds, and narrowing the drawing to a handful of them.
 *
 * The same behaviour wherever a list is too long to read: a button, a search box under it, and
 * rows you tick. Written once, the way `legend.js` is, and it knows nothing about sites,
 * circuits or cables.
 *
 * A finder declares the group it narrows with `data-atlas-finder`, and which data attribute
 * carries identity on the things it narrows with `data-atlas-finder-key`. Anything on the page
 * carrying `data-atlas-filterable="<that group>"` and that attribute joins in, and recedes when
 * it is not among the picks. Empty means all of them, never none.
 *
 * It composes with the legends rather than competing with them: this owns `is-unfocused`, the
 * legend owns `is-filtered`, and a thing has to survive both to stay lit. Pages that draw
 * somewhere a class cannot reach, such as the map's own canvas layers, listen for
 * `atlas:finder` instead, which carries the same decision.
 */
(function () {
  'use strict';

  const finders = document.querySelectorAll('[data-atlas-finder]');
  if (!finders.length) return;

  // group -> Set of picked ids, as strings. Empty means "all of them", never "none".
  const picked = new Map();

  /* node -> the Set of finder groups that currently leave it out.
   *
   * A rack can be narrowed by several finders at once: by Tags and by a custom field. It is out
   * of focus while any one of them excludes it, so each finder records its own verdict here
   * rather than setting the shared class, which the next finder would overwrite. */
  const excludedBy = new WeakMap();

  function setExcluded(node, group, excluded) {
    let groups = excludedBy.get(node);
    if (!groups) {
      groups = new Set();
      excludedBy.set(node, groups);
    }
    if (excluded) groups.add(group);
    else groups.delete(group);
    node.classList.toggle('is-unfocused', groups.size > 0);
  }

  function rowsOf(finder) {
    return finder.querySelectorAll('[data-atlas-pick]');
  }

  function apply(group) {
    const finder = document.querySelector(`[data-atlas-finder="${group}"]`);
    const chosen = picked.get(group);
    const key = finder.dataset.atlasFinderKey;

    // An element can belong to several groups (`~=`), and can carry several ids separated by
    // spaces, as a rack carries its tags. It stays in focus if any of its ids is picked.
    document.querySelectorAll(`[data-atlas-filterable~="${group}"]`).forEach(function (node) {
      const ids = String(node.dataset.atlasPick || (key ? node.dataset[key] : '') || '')
        .split(/\s+/)
        .filter(Boolean);
      setExcluded(node, group, Boolean(chosen.size) && !ids.some((id) => chosen.has(id)));
    });

    rowsOf(finder).forEach(function (row) {
      row.setAttribute('aria-checked', String(chosen.has(row.dataset.atlasPick)));
    });
    finder.classList.toggle('is-picking', Boolean(chosen.size));

    const total = rowsOf(finder).length;
    // The button says how far the drawing is narrowed while its panel is shut: "2/28" once two
    // rows are ticked, and the plain total when none is.
    const count = finder.querySelector('[data-atlas-finder-count]');
    if (count) {
      count.textContent = chosen.size ? `${chosen.size}/${total}` : String(total);
      count.classList.toggle('text-bg-primary', Boolean(chosen.size));
      count.classList.toggle('text-bg-secondary', !chosen.size);
    }
    const noun = finder.dataset.atlasFinderNoun || 'row';
    finder.querySelector('[data-atlas-finder-summary]').textContent = chosen.size
      ? `${chosen.size} of ${total} picked`
      : `${total} ${noun}${total === 1 ? '' : 's'}`;
    finder.querySelector('[data-atlas-finder-clear]').hidden = !chosen.size;

    if (window.atlasState) window.atlasState.set(`pick-${group}`, [...chosen]);

    document.dispatchEvent(
      new CustomEvent('atlas:finder', {
        detail: { group: group, picked: [...chosen] },
      })
    );
  }

  function filterRows(finder, term) {
    const needle = term.trim().toLowerCase();
    let shown = 0;
    rowsOf(finder).forEach(function (row) {
      const hit = !needle || (row.dataset.atlasName || '').toLowerCase().includes(needle);
      row.classList.toggle('is-hidden', !hit);
      if (hit) shown += 1;
    });
    finder.querySelector('[data-atlas-finder-empty]').hidden = shown > 0;
  }

  function closeFinders(except) {
    finders.forEach(function (finder) {
      if (finder === except) return;
      finder.querySelector('[data-atlas-finder-panel]').hidden = true;
      finder.querySelector('[data-atlas-finder-toggle]').setAttribute('aria-expanded', 'false');
    });
  }

  finders.forEach(function (finder) {
    const group = finder.dataset.atlasFinder;
    const toggle = finder.querySelector('[data-atlas-finder-toggle]');
    const panel = finder.querySelector('[data-atlas-finder-panel]');
    const search = finder.querySelector('[data-atlas-finder-search]');
    picked.set(group, new Set());

    toggle.addEventListener('click', function () {
      const open = panel.hidden;
      closeFinders(finder);
      panel.hidden = !open;
      toggle.setAttribute('aria-expanded', String(open));
      // A panel opened to find something should be ready to be typed into.
      if (open) search.focus();
      // Right-aligned if opening it left would run off the edge of the card.
      const box = panel.getBoundingClientRect();
      finder.classList.toggle('atlas-finder--right', !open ? false : box.right > window.innerWidth - 8);
    });

    search.addEventListener('input', () => filterRows(finder, search.value));

    finder.addEventListener('click', function (event) {
      if (event.target.closest('.atlas-cable__open')) return; // a real link; let it navigate
      const row = event.target.closest('[data-atlas-pick]');
      if (!row) return;
      const id = row.dataset.atlasPick;
      const chosen = picked.get(group);
      if (chosen.has(id)) chosen.delete(id);
      else chosen.add(id);
      apply(group);
    });

    finder.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const row = event.target.closest('[data-atlas-pick]');
      if (!row) return;
      event.preventDefault();
      row.click();
    });

    finder.querySelector('[data-atlas-finder-clear]').addEventListener('click', function () {
      picked.get(group).clear();
      apply(group);
    });
  });

  // Clicking away puts the lists back. They are a way to reach the drawing, not a place to stay.
  document.addEventListener('click', function (event) {
    if (!event.target.closest('[data-atlas-finder]')) closeFinders(null);
  });

  // Escape clears here as it does everywhere else in the atlas: the lists close and every tick
  // goes, so the drawing is whole again.
  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    closeFinders(null);
    picked.forEach(function (chosen, group) {
      if (!chosen.size) return;
      chosen.clear();
      apply(group);
    });
  });

  /* Ticks carried in the URL, applied once every script on the page is listening, for the
   * same reason the legend waits (see `legend.js`). Only ids that are still rows are kept. */
  document.addEventListener('DOMContentLoaded', function () {
    if (!window.atlasState) return;
    finders.forEach(function (finder) {
      const group = finder.dataset.atlasFinder;
      const rows = new Set([...rowsOf(finder)].map((row) => row.dataset.atlasPick));
      const wanted = window.atlasState.get(`pick-${group}`).filter((id) => rows.has(id));
      if (!wanted.length) return;
      wanted.forEach((id) => picked.get(group).add(id));
      apply(group);
    });
  });

  // Read by the pages that compose a narrowing of their own with this one.
  window.atlasFinder = {
    picked: (group) => picked.get(group) || new Set(),
    inFocus: function (group, id) {
      const chosen = picked.get(group);
      return !chosen || !chosen.size || chosen.has(String(id));
    },
  };
})();

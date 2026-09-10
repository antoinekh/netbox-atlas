/*
 * Picking bands out of a legend.
 *
 * The same behaviour on all three levels, so it is written once. A legend declares the group of
 * things it colours with `data-atlas-filter`; anything on the page carrying
 * `data-atlas-filterable="<that group>"` and a `data-band` joins in. Nothing here knows what a
 * rack, a device or a site is.
 *
 * A legend row is a toggle, like a tick in a finder: click a band to add it to the picked set,
 * click it again to take it out. Nothing picked means everything shows. So "the racks at 75% and
 * over" is two clicks, on the two top bands.
 *
 * A band is a key the server hands out, not a colour: two roles can wear one colour, and matched
 * on the colour they were picked together.
 *
 * It uses its own class, `is-filtered`, and never touches `is-dimmed`. Two of these pages
 * already have a selection model of their own that owns `is-dimmed` and clears it wholesale on
 * every click; sharing the class would have made picking a band and selecting a device cancel
 * each other out at random. Kept apart, they compose: pick the bands of racks that are nearly
 * full, then click one of them to trace it.
 *
 * A renderer that is not the DOM, such as the map's own layers on its canvas, cannot be reached
 * by a class. Those listen for the `atlas:filter` event instead, which carries the same decision.
 *
 * The picked bands are kept in the URL hash (see `state.js`), so a reload or a shared link keeps
 * them.
 */
(function () {
  'use strict';

  const legends = document.querySelectorAll('[data-atlas-filter]');
  if (!legends.length) return;

  // group -> Map of band -> { label, count }. Empty means all of them, never none.
  const picked = new Map();

  function buttonsOf(group) {
    return document.querySelectorAll(`[data-atlas-filter="${group}"] [data-atlas-band]`);
  }

  function describe(button) {
    return {
      label: (button.querySelector('.atlas-legend__label') || button).textContent.trim(),
      count: Number((button.querySelector('.atlas-legend__count') || {}).textContent) || 0,
    };
  }

  function apply(group) {
    const bands = picked.get(group);

    // `~=`: an element can belong to several groups, such as a rack in the legend's `racks` and
    // in the Tags finder's `rack-tags`.
    document.querySelectorAll(`[data-atlas-filterable~="${group}"]`).forEach(function (node) {
      node.classList.toggle('is-filtered', bands.size > 0 && !bands.has(node.dataset.band));
    });

    buttonsOf(group).forEach(function (button) {
      const on = bands.has(button.dataset.atlasBand);
      button.classList.toggle('is-picked', on);
      button.setAttribute('aria-pressed', String(on));
    });

    // Marks the page while a group is narrowed, so a stylesheet can say so without the script
    // knowing which element carries the message.
    document.body.classList.toggle(`atlas-filtering-${group}`, bands.size > 0);

    if (window.atlasState) window.atlasState.set(`band-${group}`, [...bands.keys()]);

    // The labels and the tally come from the legend rather than from counting what is lit: one
    // site is both a marker on the map and a row in the list beside it, so the elements wearing
    // a band are not the things the reader is counting.
    const picks = [...bands.values()];
    document.dispatchEvent(
      new CustomEvent('atlas:filter', {
        detail: {
          group: group,
          bands: [...bands.keys()],
          label: picks.map((pick) => pick.label).join(', '),
          count: picks.reduce((total, pick) => total + pick.count, 0),
        },
      })
    );
  }

  legends.forEach(function (legend) {
    const group = legend.dataset.atlasFilter;
    picked.set(group, new Map());
    legend.addEventListener('click', function (event) {
      const button = event.target.closest('[data-atlas-band]');
      if (!button || button.disabled) return;
      const bands = picked.get(group);
      const band = button.dataset.atlasBand;
      if (bands.has(band)) bands.delete(band);
      else bands.set(band, describe(button));
      apply(group);
    });
  });

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    picked.forEach(function (bands, group) {
      if (!bands.size) return;
      bands.clear();
      apply(group);
    });
  });

  /* Bands carried in the URL, applied once every script on the page is listening. Deferred
   * scripts run before DOMContentLoaded, so by then the page's own handlers for `atlas:filter`
   * are in place and a restored band reaches them like a clicked one. */
  document.addEventListener('DOMContentLoaded', function () {
    if (!window.atlasState) return;
    picked.forEach(function (bands, group) {
      const wanted = new Set(window.atlasState.get(`band-${group}`));
      if (!wanted.size) return;
      buttonsOf(group).forEach(function (button) {
        if (!button.disabled && wanted.has(button.dataset.atlasBand)) {
          bands.set(button.dataset.atlasBand, describe(button));
        }
      });
      apply(group);
    });
  });

  // Read by the pages that need to compose a filter of their own with this one.
  window.atlasLegendFilter = {
    bands: (group) => [...(picked.get(group) || new Map()).keys()],
  };
})();

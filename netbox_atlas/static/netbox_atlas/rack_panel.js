/*
 * The column beside the rack drawing, and the find box above it.
 *
 * The drawing (`rack3d.js`) owns the scene and the selection; this owns what a selection shows
 * beside it: the port allocation narrowed to one device, that device's cabling, the reservation
 * card, the path of a traced port, and the cable count. The drawing tells it what is selected
 * with `show`, and hears about a click on a cabling row through `onPick`. Kept apart from the
 * drawing because none of it needs Three.js, and all of it has to work when the drawing cannot
 * be loaded.
 *
 * The page already holds every state the column can be in, so a selection costs no request. The
 * one exception is a trace, which is fetched once per port and cached.
 */
(function () {
  'use strict';

  const config = document.getElementById('atlas-rack-config');
  if (!config) return;

  const scopeLabel = document.querySelector('[data-atlas-scope]');
  const allocBlocks = document.querySelectorAll('[data-atlas-alloc]');
  const cablingBlocks = document.querySelectorAll('[data-atlas-cabling]');
  const reservationPanels = document.querySelectorAll('[data-atlas-reservation]');
  const traceCard = document.querySelector('[data-atlas-trace-card]');
  const traceBody = document.querySelector('[data-atlas-trace]');
  const traceSummary = document.querySelector('[data-atlas-trace-summary]');
  const traceUrlTemplate = JSON.parse(config.textContent).traceUrl;

  const traceCache = new Map();
  // Only the newest request may write to the panel. Clicking along a row of ports fires
  // several, and without this the slowest one wins and the panel shows the wrong path.
  let traceToken = 0;

  const pickHandlers = [];
  const searchHandlers = [];

  function prefersReducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  /* ----------------------------------------------------------------------
   * What a selection shows
   * ------------------------------------------------------------------- */

  /* The Cabling badge counts what is currently lit, not what the rack holds.
   *
   * Dimming alone was too quiet to notice: the list still looked like nineteen rows. Saying
   * "2 of 19" is what makes the selection legible without hiding the rest of the rack, which
   * is still worth seeing as context. */
  function showCableCount(shown) {
    const badge = document.querySelector('[data-atlas-cable-count]');
    if (!badge) return;
    const total = badge.dataset.atlasCableCount;
    badge.textContent = shown === null ? total : `${shown} of ${total}`;
    badge.classList.toggle('text-bg-primary', shown !== null);
    badge.classList.toggle('text-bg-secondary', shown === null);
  }

  /* Which cabling block is on screen: one device's, or the whole rack's.
   *
   * Narrowing rather than dimming, because a faded list of nineteen rows still reads as
   * nineteen rows. A device with no block of its own falls back to the rack. */
  function showCabling(key) {
    const target = document.querySelector(`[data-atlas-cabling="${key}"]`) ? key : 'rack';
    cablingBlocks.forEach(function (block) {
      block.hidden = block.dataset.atlasCabling !== target;
    });
  }

  function showReservation(id) {
    reservationPanels.forEach(function (panel) {
      panel.hidden = panel.dataset.atlasReservation !== String(id);
    });
  }

  function showAlloc(key, label) {
    // A device with no ports has no block of its own, so fall back rather than showing
    // an empty panel.
    const target = document.querySelector(`[data-atlas-alloc="${key}"]`) ? key : 'rack';
    allocBlocks.forEach(function (block) {
      block.hidden = block.dataset.atlasAlloc !== target;
    });
    if (scopeLabel) scopeLabel.textContent = target === 'rack' ? 'whole rack' : label;
  }

  /* The cabling rows of the selection lit, the rest dimmed.
   *
   * A row matches on its cable alone. It used to also match when either of its ends was among
   * the devices lit by the selection, which includes the far end of every cable the selection
   * touches. In a top-of-rack layout that set holds the switch and the PDU, and every row in
   * the rack terminates on one of those, so selecting any server lit up the whole list. */
  function markRows(selection, cableIds) {
    document.querySelectorAll('.atlas-cable').forEach(function (row) {
      row.classList.remove('is-selected', 'is-related', 'is-dimmed');
      if (!selection) return;
      const cableId = row.dataset.cableId;
      if (!cableIds || !cableIds.has(cableId)) {
        row.classList.add('is-dimmed');
        return;
      }
      const primary = selection.type === 'cable' && selection.id === cableId;
      row.classList.add(primary ? 'is-selected' : 'is-related');
    });
  }

  /* Show a selection beside the drawing.
   *
   * `selection` is null, or { type: 'device' | 'cable' | 'reservation', id }. `cableIds` is the
   * set of cables the drawing lit for it, and `label` names a selected device in the
   * allocation card's header. */
  function show(selection, { cableIds = null, label = 'device' } = {}) {
    document.body.classList.toggle('atlas-has-selection', Boolean(selection));
    showReservation(selection && selection.type === 'reservation' ? selection.id : null);
    markRows(selection, cableIds);

    if (selection && selection.type === 'device') {
      showAlloc(selection.id, label);
      showCabling(selection.id);
    } else {
      showAlloc('rack', 'whole rack');
      showCabling('rack');
    }
    showCableCount(selection && selection.type !== 'reservation' && cableIds ? cableIds.size : null);
  }

  /* ----------------------------------------------------------------------
   * Tracing
   * ------------------------------------------------------------------- */

  function traceUrl(termination) {
    const [type, id] = termination.split('/');
    return traceUrlTemplate.replace('APP.MODEL', type).replace(/\/0\/$/, `/${id}/`);
  }

  function hideTrace() {
    traceToken += 1;
    traceCard.hidden = true;
    traceBody.innerHTML = '';
    traceSummary.textContent = '';
  }

  /* Bring the path into view when it opens off screen.
   *
   * The card sits above the cabling card, so a cable picked from the bottom of that list opened
   * its path somewhere above the fold and the click appeared to do nothing. Scrolled only as far
   * as needed, so a trace started from the drawing does not move the page at all. */
  function revealTrace() {
    const box = traceCard.getBoundingClientRect();
    if (box.top >= 0 && box.top < window.innerHeight - 80) return;
    traceCard.scrollIntoView({ block: 'nearest', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  }

  function escape(value) {
    const node = document.createElement('span');
    node.textContent = value == null ? '' : String(value);
    return node.innerHTML;
  }

  function renderTrace(data) {
    traceCard.hidden = false;
    traceSummary.textContent = data.complete ? `reaches ${data.reaches}` : 'path is incomplete';
    traceSummary.classList.toggle('text-warning', !data.complete);

    if (!data.hops.length) {
      traceBody.innerHTML = '<p class="text-muted mb-0">Nothing is cabled to this port.</p>';
      return;
    }

    const rows = data.hops.map(function (hop) {
      // The rack is named only when the hop leaves this one, so an in-rack path is not
      // repeated on every line.
      const rack = hop.rack ? `<span class="badge text-bg-secondary">${escape(hop.rack)}</span>` : '';
      const from = hop.from.device
        ? `${escape(hop.from.device)} · ${escape(hop.from.label)}`
        : escape(hop.from.label);
      const to = hop.to.device ? `${escape(hop.to.device)} · ${escape(hop.to.label)}` : escape(hop.to.label);
      return (
        `<li class="atlas-hop atlas-hop--${escape(hop.kind)}">` +
        `<span class="atlas-hop__index">${hop.index}</span>` +
        `<span class="atlas-hop__from">${from}</span>` +
        '<i class="mdi mdi-arrow-right text-muted"></i>' +
        `<span class="atlas-hop__to">${to} ${rack}</span>` +
        '</li>'
      );
    });

    traceBody.innerHTML =
      `<p class="text-muted small mb-2">From ${escape(data.origin.device)} · ` +
      `${escape(data.origin.label)}</p><ol class="atlas-hops">${rows.join('')}</ol>` +
      (data.complete
        ? ''
        : '<p class="text-muted small mb-0 mt-2">The path stops at an uncabled ' +
          'pass-through port, so where it goes next is not recorded.</p>');
  }

  async function showTrace(termination) {
    if (!termination || termination.endsWith('/None')) return hideTrace();

    const token = ++traceToken;
    if (traceCache.has(termination)) {
      renderTrace(traceCache.get(termination));
      return revealTrace();
    }

    traceCard.hidden = false;
    traceSummary.textContent = 'tracing...';
    traceBody.innerHTML = '';
    revealTrace();
    try {
      const response = await fetch(traceUrl(termination), { credentials: 'same-origin' });
      if (!response.ok) throw new Error(response.status);
      const data = await response.json();
      traceCache.set(termination, data);
      if (token === traceToken) renderTrace(data);
    } catch (error) {
      if (token !== traceToken) return;
      traceCard.hidden = false;
      traceSummary.textContent = '';
      traceBody.innerHTML = '<p class="text-muted mb-0">The path could not be read. See the console.</p>';
      console.error('netbox-atlas could not trace:', error);
    }
  }

  /* ----------------------------------------------------------------------
   * Clicks on the column
   * ------------------------------------------------------------------- */

  function pick(row) {
    pickHandlers.forEach((handler) => handler('cable', row.dataset.cableId, row.dataset.termination));
  }

  document.addEventListener('click', function (event) {
    const row = event.target.closest('.atlas-cable');
    if (row) pick(row);
  });

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const row = event.target.closest('.atlas-cable');
    if (!row) return;
    event.preventDefault();
    pick(row);
  });

  /* Whether a click landed on the column or on a legend, rather than on empty page.
   *
   * `.atlas-legend` is here because picking a band is an act on the drawing, not a click on
   * empty space beside it: left out, choosing a band cleared whatever was selected. */
  function ownsClick(target) {
    return Boolean(target.closest('.atlas-cables, .atlas-alloc, .atlas-legend, [data-atlas-reservation]'));
  }

  /* ----------------------------------------------------------------------
   * The find box
   *
   * The floor's box, over the same problem one zoom in: reading a name off a 48U cabinet by
   * eye is what hunting a cabinet in a room of fifty is out there. The drawing fades rather than
   * hides, so a device keeps its position in the rack, and it composes with the legend band
   * and the selection instead of replacing either.
   * ------------------------------------------------------------------- */

  const find = document.querySelector('[data-atlas-find]');
  // The box, not the input inside it: the stylesheet draws the warning on the bordered label.
  const findBox = find ? find.closest('.atlas-find') : null;
  // A term carried in the URL, from a reload or a shared link.
  let term = ((window.atlasState && window.atlasState.get('find')[0]) || '').trim().toLowerCase();
  if (find) find.value = term;

  function setTerm(value) {
    term = value;
    if (window.atlasState) window.atlasState.set('find', term ? [term] : []);
    searchHandlers.forEach((handler) => handler(term));
  }

  if (find) {
    find.addEventListener('input', () => setTerm(find.value.trim().toLowerCase()));
  }

  window.atlasRackPanel = {
    show: show,
    showTrace: showTrace,
    hideTrace: hideTrace,
    ownsClick: ownsClick,
    prefersReducedMotion: prefersReducedMotion,
    // fn('cable', cableId, termination) when a cabling row is clicked.
    onPick: (handler) => pickHandlers.push(handler),

    searchTerm: () => term,
    onSearch: (handler) => searchHandlers.push(handler),
    clearSearch: function () {
      if (find) find.value = '';
      setTerm('');
    },
    // A name or an asset tag: the label on the device, or the sticker on its front.
    matchesSearch: (name, assetTag) =>
      !term || (name || '').toLowerCase().includes(term) || (assetTag || '').toLowerCase().includes(term),
    /* Whether anything is left after every filter.
     *
     * Counted over all of them together rather than over the search alone: with a band picked
     * and a name typed, a search matching only devices in another band leaves the cabinet empty,
     * and the box has to say so or it looks like a drawing that failed to load. */
    reportShown: function (shown) {
      if (findBox) findBox.classList.toggle('is-empty', Boolean(term) && shown === 0);
    },
  };
})();

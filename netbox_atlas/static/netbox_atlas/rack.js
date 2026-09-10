/*
 * Rack view: tracing.
 *
 * One selection model drives everything. Selecting a device highlights its cables, the devices
 * at their far ends and its rows in the list, and narrows the allocation panel to it.
 * Selecting a cable highlights the line, both devices it joins, and its row.
 *
 * The page already holds every state it can be in, so a selection costs no request. All this
 * does is add and remove classes and toggle which allocation block is visible.
 */
(function () {
  'use strict';

  const root = document.querySelector('.atlas-elevation');
  if (!root) return;

  const scopeLabel = document.querySelector('[data-atlas-scope]');
  const allocBlocks = document.querySelectorAll('[data-atlas-alloc]');
  const cablingBlocks = document.querySelectorAll('[data-atlas-cabling]');
  const reservationPanels = document.querySelectorAll('[data-atlas-reservation]');
  const traceCard = document.querySelector('[data-atlas-trace-card]');
  const traceBody = document.querySelector('[data-atlas-trace]');
  const traceSummary = document.querySelector('[data-atlas-trace-summary]');
  const traceUrlTemplate = JSON.parse(
    document.getElementById('atlas-rack-config').textContent
  ).traceUrl;

  const traceCache = new Map();
  // Only the newest request may write to the panel. Clicking along a row of ports fires
  // several, and without this the slowest one wins and the panel shows the wrong path.
  let traceToken = 0;

  // { type: 'device' | 'cable', id: string } or null
  let selection = null;

  /* ----------------------------------------------------------------------
   * Finding a device
   *
   * The floor's box, over the same problem one zoom in: reading a name off a 48U cabinet by
   * eye is what hunting a cabinet in a room of fifty is out there. It dims rather than hides,
   * so a device keeps its position in the rack, and it composes with the legend band and the
   * selection instead of replacing either.
   * ------------------------------------------------------------------- */

  const find = document.querySelector('[data-atlas-find]');
  // The box, not the input inside it: the stylesheet draws the warning on the bordered label.
  const findBox = find ? find.closest('.atlas-find') : null;
  const devices = Array.from(document.querySelectorAll('.atlas-device'));

  let term = '';

  function applySearch() {
    devices.forEach(function (device) {
      // A name or an asset tag: the label on the device, or the sticker on its front.
      const hit =
        (device.dataset.name || '').toLowerCase().includes(term) ||
        (device.dataset.assetTag || '').toLowerCase().includes(term);
      device.classList.toggle('is-searched-out', Boolean(term) && !hit);
    });
    if (window.atlasState) window.atlasState.set('find', term ? [term] : []);
    report();
  }

  /* Whether anything is left after both filters.
   *
   * Counted over the two classes together rather than over the search alone: with a band picked
   * and a name typed, a search matching only devices in another band leaves the cabinet empty,
   * and the box has to say so or it looks like a drawing that failed to load. */
  function report() {
    if (!findBox) return;
    const shown = document.querySelectorAll(
      '.atlas-device:not(.is-filtered):not(.is-searched-out):not(.is-unfocused)'
    ).length;
    findBox.classList.toggle('is-empty', Boolean(term) && shown === 0);
  }

  if (find) {
    find.addEventListener('input', function () {
      term = find.value.trim().toLowerCase();
      applySearch();
    });
    // A term carried in the URL, from a reload or a shared link.
    term = ((window.atlasState && window.atlasState.get('find')[0]) || '').trim().toLowerCase();
    find.value = term;
  }

  // A band was picked or cleared, so the "nothing matches" message may have changed even though
  // the term did not.
  document.addEventListener('atlas:filter', function (event) {
    if (event.detail.group === 'devices') report();
  });

  // Tags, a custom field, or the cabling finder: report whether anything is still lit.
  document.addEventListener('atlas:finder', report);

  function clearClasses() {
    document
      .querySelectorAll('.is-selected, .is-related, .is-dimmed')
      .forEach((n) => n.classList.remove('is-selected', 'is-related', 'is-dimmed'));
  }

  function endsOf(run) {
    return [run.dataset.deviceId, run.dataset.peerDeviceId].filter(Boolean);
  }

  function apply() {
    clearClasses();
    document.body.classList.toggle('atlas-has-selection', Boolean(selection));

    showReservation(null);

    if (!selection) {
      showAlloc('rack', 'whole rack');
      showCabling('rack');
      showCableCount(null);
      return;
    }

    const { type, id } = selection;

    if (type === 'reservation') {
      // Reserved space is not wired to anything, so there is nothing to trace from it. The
      // rest of the rack dims to put the claim in front of you, and its panel says the rest.
      document.querySelectorAll('.atlas-run, .atlas-cable').forEach((n) => n.classList.add('is-dimmed'));
      document
        .querySelectorAll(`.atlas-reserved[data-reservation-id="${id}"]`)
        .forEach((n) => n.classList.add('is-selected'));
      showAlloc('rack', 'whole rack');
      showCabling('rack');
      showCableCount(null);
      showReservation(id);
      return;
    }

    const cableIds = new Set();
    const deviceIds = new Set();

    document.querySelectorAll('.atlas-run').forEach(function (run) {
      const ends = endsOf(run);
      const hit = type === 'device' ? ends.includes(id) : run.dataset.cableId === id;
      if (!hit) return;
      cableIds.add(run.dataset.cableId);
      // The far end too, so selecting a switch shows what it actually reaches.
      ends.forEach((d) => deviceIds.add(d));
    });
    if (type === 'device') deviceIds.add(id);

    document.querySelectorAll('.atlas-run, .atlas-cable, .atlas-device, .atlas-port').forEach(function (node) {
      const cableId = node.dataset.cableId;
      const isDevice = node.classList.contains('atlas-device') && deviceIds.has(node.dataset.deviceId);
      // A row matches on its cable alone. It used to also match when either of its ends was
      // in deviceIds, which is the set of devices to highlight and therefore includes the far
      // end of every cable the selection touches. In a top-of-rack layout that set holds the
      // switch and the PDU, and every row in the rack terminates on one of those, so selecting
      // any server lit up the whole list and nothing appeared to change.
      const isRow = node.classList.contains('atlas-cable') && cableIds.has(cableId);
      const isLine = node.classList.contains('atlas-run') && cableIds.has(cableId);
      const isPort = node.classList.contains('atlas-port') && cableIds.has(cableId);

      if (!isDevice && !isRow && !isLine && !isPort) {
        // Only the things that carry meaning are dimmed. Dimming a free port would hide
        // exactly what the allocation panel is asking you to look at.
        if (node.classList.contains('atlas-run') || node.classList.contains('atlas-cable')) {
          node.classList.add('is-dimmed');
        }
        return;
      }

      const isPrimary =
        type === 'device' ? isDevice && node.dataset.deviceId === id : cableId === id;
      node.classList.add(isPrimary ? 'is-selected' : 'is-related');
    });

    showCableCount(cableIds.size);

    if (type === 'device') {
      const device = document.querySelector(`.atlas-device[data-device-id="${id}"]`);
      showAlloc(id, device ? device.querySelector('.atlas-device__label').textContent : 'device');
      showCabling(id);
      scrollTo(device);
    } else {
      showAlloc('rack', 'whole rack');
      showCabling('rack');
      // Scroll to the first end of the cable, so tracing from the list moves the drawing to
      // the run you picked rather than leaving you looking at an unrelated part of the rack.
      scrollTo(document.querySelector(`.atlas-device.is-selected, .atlas-device.is-related`));
    }
  }

  /* Bring a highlighted device into view.
   *
   * A 48U rack is taller than the window, so selecting a device from the cable list often lit
   * up something off screen and the click looked like it had done nothing.
   *
   * The drawing used to sit in its own scrolling frame and only that frame was moved. The
   * frame is gone, because a scrollbar inside a card on a page that already scrolls is two
   * scrollbars for one drawing; so this scrolls the page, and only when the device is actually
   * out of view, which keeps a click on a row that was already on screen from moving anything.
   */
  function scrollTo(node) {
    if (!node) return;
    const box = node.getBoundingClientRect();
    const margin = 80;
    if (box.top >= margin && box.bottom <= window.innerHeight - margin) return;
    node.scrollIntoView({ block: 'center', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  }

  function prefersReducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

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
    return target;
  }

  /* Which reservation panel is on screen, if any. */
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
    scopeLabel.textContent = target === 'rack' ? 'whole rack' : label;
  }

  /* ----------------------------------------------------------------------
   * Tracing
   * ------------------------------------------------------------------- */

  function traceUrl(termination) {
    const [type, id] = termination.split('/');
    return traceUrlTemplate.replace('APP.MODEL', type).replace(/\/0\/$/, `/${id}/`);
  }

  function hideTrace() {
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

  function renderTrace(data) {
    traceCard.hidden = false;
    traceSummary.textContent = data.complete
      ? `reaches ${data.reaches}`
      : 'path is incomplete';
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
      const to = hop.to.device
        ? `${escape(hop.to.device)} · ${escape(hop.to.label)}`
        : escape(hop.to.label);
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

  function escape(value) {
    const node = document.createElement('span');
    node.textContent = value == null ? '' : String(value);
    return node.innerHTML;
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
      traceBody.innerHTML =
        '<p class="text-muted mb-0">The path could not be read. See the console.</p>';
      console.error('netbox-atlas could not trace:', error);
    }
  }

  function select(type, id) {
    // Clicking the current selection clears it, so there is always a way out without
    // hunting for empty space.
    selection = selection && selection.type === type && selection.id === id ? null : { type, id };
    apply();
  }

  document.addEventListener('click', function (event) {
    const reserved = event.target.closest('.atlas-reserved');
    if (reserved) {
      select('reservation', reserved.dataset.reservationId);
      return hideTrace();
    }

    const port = event.target.closest('.atlas-port[data-cable-id]');
    if (port) {
      select('cable', port.dataset.cableId);
      // Traced from the port that was clicked, not from the cable: a cable has two ends,
      // and the path you want is the one leaving the port under the cursor.
      return selection ? showTrace(port.dataset.termination) : hideTrace();
    }

    const run = event.target.closest('.atlas-run, .atlas-cable');
    if (run) {
      select('cable', run.dataset.cableId);
      return selection ? showTrace(run.dataset.termination) : hideTrace();
    }

    const device = event.target.closest('.atlas-device');
    if (device) {
      select('device', device.dataset.deviceId);
      // A device has many paths, so there is no single one to show.
      return hideTrace();
    }

    // `.atlas-legend` is in this list because picking a band is an act on the drawing, not a click
    // on empty space beside it: left out, choosing a band cleared whatever was selected.
    if (
      !event.target.closest(
        '.atlas-elevation, .atlas-cables, .atlas-alloc, .atlas-legend, [data-atlas-reservation]'
      )
    ) {
      selection = null;
      hideTrace();
      apply();
    }
  });

  /* A device opens on a double click, so a single click keeps its more useful meaning of
     "show me what this connects to". */
  document.addEventListener('dblclick', function (event) {
    const device = event.target.closest('.atlas-device[data-device-url]');
    if (device) window.location.href = device.dataset.deviceUrl;
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && (selection || term)) {
      // One key, both narrowings: a reader pressing Escape wants the whole rack back, not to
      // press it twice and wonder which half it undid the first time.
      selection = null;
      term = '';
      if (find) find.value = '';
      applySearch();
      hideTrace();
      return apply();
    }
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const node = event.target.closest('.atlas-device, .atlas-run, .atlas-cable, .atlas-reserved');
    if (!node) return;
    event.preventDefault();
    if (node.classList.contains('atlas-reserved')) select('reservation', node.dataset.reservationId);
    else if (node.classList.contains('atlas-device')) select('device', node.dataset.deviceId);
    else select('cable', node.dataset.cableId);
  });

  apply();
  applySearch();
})();

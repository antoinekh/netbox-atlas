/*
 * The rack in 3D.
 *
 * Drawn from the scene the server built (`scene.py`): device boxes wearing their device type
 * images, the cabinet around them, and every cable along the path the server routed through the
 * cable managers. Nothing here decides where anything goes. It draws on the stage `stage3d.js`
 * sets up, and keeps the selection, telling `rack_panel.js` what is selected so the column
 * beside the drawing can follow it.
 */

import { PICK_LAYER, isDark, openStage, textOn } from 'atlas/stage3d';

const panel = window.atlasRackPanel;
const element = document.querySelector('[data-atlas-3d]');
const configNode = document.getElementById('atlas-rack3d-config');

// Opacity of a device or cable that is out of focus: left out by a filter, or not part of the
// selection. A filter hides harder than a selection, which only puts the rest behind glass.
const FILTERED_OPACITY = 0.08;
const DIMMED_DEVICE_OPACITY = 0.2;
const RELATED_DEVICE_OPACITY = 0.5;
const DIMMED_CABLE_OPACITY = 0.1;
// A cable is thin and hard to hit, so it is picked by an invisible tube this much fatter.
const PICK_RADIUS = 11;
const CABLE_RADIUS = { power: 4.2, default: 3.2 };
// How far a cable's corners are rounded, in millimetres, where the segments are long enough.
const CORNER_RADIUS = 18;
// The names of the cables leaving the rack, stacked this far apart over the roof.
const END_LABEL_STEP = 70;

const VIEWS = {
  front: [0, 0.05, 1],
  rear: [0, 0.05, -1],
  side: [1, 0.05, 0],
  angle: [0.85, 0.42, 1.1],
};

function build(stage, config) {
  const { THREE, scene } = stage;
  const { rack, devices, cables, reservations, free } = config.scene;
  const colours = config.colours;
  const controlsBar = element.querySelector('[data-atlas-3d-controls]');

  /* ----------------------------------------------------------------------
   * The cabinet
   * ------------------------------------------------------------------- */

  const frameMaterial = new THREE.MeshStandardMaterial({ color: 0x3b424c, metalness: 0.7, roughness: 0.34 });
  const railMaterial = new THREE.MeshStandardMaterial({ color: 0x5b6472, metalness: 0.8, roughness: 0.32 });
  const glassMaterial = new THREE.MeshStandardMaterial({
    color: 0xa9bccf,
    metalness: 0.1,
    roughness: 0.1,
    transparent: true,
    opacity: 0.035,
    depthWrite: false,
    side: THREE.DoubleSide,
  });

  function block(material, w, h, d, x, y, z, { shadow = true } = {}) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
    mesh.position.set(x, y, z);
    mesh.castShadow = shadow;
    mesh.receiveShadow = shadow;
    scene.add(mesh);
    return mesh;
  }

  const interiorTop = rack.plinth + rack.units.length * rack.unitHeight;
  const interior = interiorTop - rack.plinth;
  const post = 26;
  const halfW = rack.width / 2;
  const halfD = rack.depth / 2;

  // Plinth, posts and the roof frame. The roof is a frame and not a lid, so the cables leaving
  // through it stay visible from above.
  block(frameMaterial, rack.width, rack.plinth - 20, rack.depth, 0, (rack.plinth - 20) / 2 + 20, 0);
  [-1, 1].forEach(function (sx) {
    [-1, 1].forEach(function (sz) {
      block(frameMaterial, post, rack.height - 20, post, sx * (halfW - post / 2), (rack.height + 20) / 2, sz * (halfD - post / 2));
      // Feet.
      block(frameMaterial, 50, 20, 50, sx * (halfW - 45), 10, sz * (halfD - 45));
    });
    block(frameMaterial, post, post, rack.depth, sx * (halfW - post / 2), rack.height - post / 2, 0);
  });
  [-1, 1].forEach(function (sz) {
    block(frameMaterial, rack.width, post, post, 0, rack.height - post / 2, sz * (halfD - post / 2));
  });

  // Glass side panels, so the inside is always in view.
  [-1, 1].forEach(function (sx) {
    const side = new THREE.Mesh(new THREE.PlaneGeometry(rack.depth - post * 2, rack.height - rack.plinth - post), glassMaterial);
    side.rotation.y = Math.PI / 2;
    side.position.set(sx * (halfW - 2), (rack.height + rack.plinth - post) / 2, 0);
    side.renderOrder = 2;
    scene.add(side);
  });

  // Mounting rails, front and rear.
  const railX = rack.faceplate / 2 - 11;
  [rack.frontRailZ + 1.5, rack.rearRailZ - 1.5].forEach(function (z) {
    [-1, 1].forEach(function (sx) {
      block(railMaterial, 18, interior, 3, sx * railX, rack.plinth + interior / 2, z, { shadow: false });
    });
  });

  /* The unit numbers, on a strip beside the front rail and another beside the rear one. Drawn
     into a texture rather than as page elements, so they turn with the rack and stay where
     they are fixed. Redrawn when the theme changes. */
  function rulerTexture() {
    const units = rack.units.length;
    const perUnit = Math.max(16, Math.min(48, Math.floor(8192 / units)));
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = perUnit * units;
    const context = canvas.getContext('2d');
    context.fillStyle = isDark() ? 'rgba(229, 231, 235, .85)' : 'rgba(33, 37, 41, .8)';
    context.strokeStyle = isDark() ? 'rgba(229, 231, 235, .25)' : 'rgba(33, 37, 41, .22)';
    context.font = `600 ${Math.round(perUnit * 0.48)}px ui-monospace, SFMono-Regular, Menlo, monospace`;
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    rack.units.forEach(function ([unit, y]) {
      const row = ((interiorTop - y) / rack.unitHeight - 0.5) * perUnit;
      context.fillText(String(unit), 32, row + perUnit / 2);
      context.beginPath();
      context.moveTo(8, row);
      context.lineTo(56, row);
      context.stroke();
    });
    return stage.finishTexture(new THREE.CanvasTexture(canvas));
  }

  const rulerMaterials = [
    { z: rack.frontRailZ + 2, x: -(rack.faceplate / 2 + 14), turn: 0 },
    { z: rack.rearRailZ - 2, x: rack.faceplate / 2 + 14, turn: Math.PI },
  ].map(function ({ x, z, turn }) {
    const material = new THREE.MeshBasicMaterial({ map: rulerTexture(), transparent: true, depthWrite: false });
    const strip = new THREE.Mesh(new THREE.PlaneGeometry(22, interior), material);
    strip.position.set(x, rack.plinth + interior / 2, z);
    strip.rotation.y = turn;
    scene.add(strip);
    return material;
  });

  stage.onThemeChange(function () {
    rulerMaterials.forEach(function (material) {
      material.map.dispose();
      material.map = rulerTexture();
    });
    applyHighlightColour();
  });

  // The cable managers, as the outline of the space the lanes run in.
  const managerDepth = rack.rearRailZ - (-halfD + post);
  Object.values(rack.managers).forEach(function ([x, width]) {
    const outline = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(width, interior, managerDepth)),
      new THREE.LineBasicMaterial({ color: 0x8a94a3, transparent: true, opacity: 0.28 })
    );
    outline.position.set(x, rack.plinth + interior / 2, rack.rearRailZ - managerDepth / 2);
    scene.add(outline);
  });

  /* ----------------------------------------------------------------------
   * Devices
   * ------------------------------------------------------------------- */

  let mode = window.atlasState && window.atlasState.get('mode')[0] === 'colour' ? 'colour' : 'images';

  const highlight = new THREE.Color();
  function applyHighlightColour() {
    highlight.set(isDark() ? colours.highlightDark : colours.highlight);
    deviceViews.forEach((view) => view.outline.material.color.copy(highlight));
  }

  /* A face with no image: the colouring, and the device's name on it, drawn on a canvas at the
     proportions of the face so the letters are not stretched. */
  function nameTexture(text, colour, width, height) {
    const canvasWidth = 1024;
    const canvasHeight = Math.max(64, Math.round((canvasWidth * height) / width));
    const canvas = document.createElement('canvas');
    canvas.width = canvasWidth;
    canvas.height = canvasHeight;
    const context = canvas.getContext('2d');

    const gradient = context.createLinearGradient(0, 0, 0, canvasHeight);
    gradient.addColorStop(0, colour);
    gradient.addColorStop(1, stage.shade(colour, -0.18));
    context.fillStyle = gradient;
    context.fillRect(0, 0, canvasWidth, canvasHeight);

    // The ears, darker, so a colour face still reads as something bolted to rails.
    const ear = Math.round((22 / width) * canvasWidth);
    context.fillStyle = 'rgba(0, 0, 0, .22)';
    context.fillRect(0, 0, ear, canvasHeight);
    context.fillRect(canvasWidth - ear, 0, ear, canvasHeight);

    const size = Math.min(44, canvasHeight * 0.5);
    context.font = `600 ${size}px system-ui, -apple-system, "Segoe UI", sans-serif`;
    context.fillStyle = textOn(colour);
    context.textBaseline = 'middle';
    context.fillText(text, ear + 24, canvasHeight / 2, canvasWidth - 2 * ear - 48);

    return stage.finishTexture(new THREE.CanvasTexture(canvas));
  }

  const bodyColour = new THREE.Color(0x454c57);

  function deviceView(device) {
    const [x, y, z, w, h, d] = device.box;
    const faces = {
      front: new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.15 }),
      rear: new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.15 }),
    };
    const body = new THREE.MeshStandardMaterial({ color: bodyColour, metalness: 0.6, roughness: 0.42 });
    // BoxGeometry's groups run +x, -x, +y, -y, +z, -z. A device mounted on the rear shows its
    // own front at the back of the cabinet.
    const plusZ = device.facing === 'rear' ? faces.rear : faces.front;
    const minusZ = device.facing === 'rear' ? faces.front : faces.rear;
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), [body, body, body, body, plusZ, minusZ]);
    mesh.position.set(x, y, z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.layers.enable(PICK_LAYER);
    scene.add(mesh);

    const outline = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(w + 2, h + 2, d + 2)),
      new THREE.LineBasicMaterial({ transparent: true, opacity: 0, depthTest: false })
    );
    outline.position.copy(mesh.position);
    outline.renderOrder = 5;
    scene.add(outline);

    // The colouring, as a tag down the left ear of whichever face you are looking at, so it is
    // there in Images mode without painting over the photograph.
    const tagMaterial = new THREE.MeshBasicMaterial({ color: new THREE.Color(device.colour) });
    const tags = [
      [z + d / 2 + 0.6, -w / 2 + 5, 0],
      [z - d / 2 - 0.6, w / 2 - 5, Math.PI],
    ].map(function ([tagZ, tagX, turn]) {
      const tag = new THREE.Mesh(new THREE.PlaneGeometry(6, Math.max(4, h - 6)), tagMaterial);
      tag.position.set(x + tagX, y, tagZ);
      tag.rotation.y = turn;
      scene.add(tag);
      return tag;
    });

    const name = stage.label(device.label, 'atlas-3d__name');
    const facingZ = device.facing === 'rear' ? z - d / 2 - 1 : z + d / 2 + 1;
    const facingX = device.facing === 'rear' ? w / 2 - 36 : -w / 2 + 36;
    name.position.set(x + facingX, y, facingZ);
    name.center.set(device.facing === 'rear' ? 1 : 0, 0.5);
    scene.add(name);

    // The name belongs to the face it is written on, so it is only shown while that face is
    // turned towards the camera; from the other side it would float over the wrong device.
    const normal = new THREE.Vector3(0, 0, device.facing === 'rear' ? -1 : 1);
    const view = { device, mesh, faces, body, outline, tags, tagMaterial, name, normal, textures: {} };
    view.textures.colour = nameTexture(device.label, device.colour, w, h);
    mesh.userData.device = view;
    return view;
  }

  const deviceViews = devices.map(deviceView);
  const deviceById = new Map(deviceViews.map((view) => [String(view.device.id), view]));

  function paintFaces(view) {
    ['front', 'rear'].forEach(function (side) {
      const image = mode === 'images' ? view.textures[side] : null;
      const material = view.faces[side];
      material.map = image || view.textures.colour;
      material.color.set(0xffffff);
      material.needsUpdate = true;
    });
    view.tags.forEach((tag) => (tag.visible = mode === 'images' && Boolean(view.textures.front || view.textures.rear)));
  }

  deviceViews.forEach(function (view) {
    paintFaces(view);
    ['front', 'rear'].forEach(function (side) {
      const url = view.device.images[side];
      if (!url) return;
      stage.imageTexture(url).then(function (texture) {
        view.textures[side] = texture;
        paintFaces(view);
        stage.requestRender();
      });
    });
  });

  const toCamera = new THREE.Vector3();
  stage.beforeLabels(function () {
    deviceViews.forEach(function (view) {
      toCamera.subVectors(stage.camera.position, view.name.position);
      view.name.visible = Boolean(view.name.userData.wanted) && toCamera.dot(view.normal) > 0;
    });
  });

  /* ----------------------------------------------------------------------
   * Reserved and free units
   * ------------------------------------------------------------------- */

  const reservedColour = new THREE.Color(colours.reserved);
  const reservationViews = reservations.map(function (band) {
    const [x, y, z, w, h, d] = band.box;
    const material = new THREE.MeshStandardMaterial({
      color: reservedColour,
      transparent: true,
      opacity: 0.22,
      depthWrite: false,
      roughness: 0.8,
    });
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
    mesh.position.set(x, y, z);
    mesh.layers.enable(PICK_LAYER);
    scene.add(mesh);
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(mesh.geometry),
      new THREE.LineBasicMaterial({ color: reservedColour, transparent: true, opacity: 0.8 })
    );
    edges.position.copy(mesh.position);
    scene.add(edges);
    const view = { band, mesh, material, edges };
    mesh.userData.reservation = view;
    return view;
  });

  const freeLabels = free.map(function (band) {
    const [x, y, z, w, , d] = band.box;
    const node = stage.label(band.label, 'atlas-3d__free');
    node.position.set(x + w / 2 - 30, y, z + d / 2 + 1);
    node.center.set(1, 0.5);
    scene.add(node);
    return node;
  });

  /* ----------------------------------------------------------------------
   * Cables
   * ------------------------------------------------------------------- */

  const pickMaterial = new THREE.MeshBasicMaterial();

  const cableViews = cables.map(function (cable) {
    const path = stage.roundedPath(cable.points, CORNER_RADIUS);
    const segments = Math.max(24, Math.round(path.getLength() / 12));
    const radius = CABLE_RADIUS[cable.kind] || CABLE_RADIUS.default;
    const material = new THREE.MeshStandardMaterial({
      color: new THREE.Color(cable.colour),
      roughness: 0.5,
      metalness: 0.05,
      emissive: new THREE.Color(cable.colour),
      emissiveIntensity: 0,
    });
    scene.add(new THREE.Mesh(new THREE.TubeGeometry(path, segments, radius, 8, false), material));

    const pick = new THREE.Mesh(new THREE.TubeGeometry(path, Math.ceil(segments / 3), PICK_RADIUS, 5, false), pickMaterial);
    pick.layers.set(PICK_LAYER);
    scene.add(pick);

    let marker = null;
    let end = null;
    if (!cable.internal) {
      const last = cable.points[cable.points.length - 1];
      marker = new THREE.Mesh(new THREE.SphereGeometry(radius * 2.6, 20, 14), material);
      marker.position.set(last[0], last[1], last[2]);
      scene.add(marker);
      end = stage.label(cable.endLabel, 'atlas-3d__end');
      end.center.set(0.5, 1);
      scene.add(end);
    }
    const view = { cable, pick, material, marker, end };
    pick.userData.cable = view;
    return view;
  });

  /* The names of the cables leaving the rack that are on show, one above the other over the
     roof. Their markers end at one height, so the names would otherwise print over each other;
     stacked in the order the lanes run, each name sits above the marker nearest it. */
  const roofY = rack.height + 60;

  function stackEndLabels() {
    const shown = cableViews.filter((view) => view.end && view.end.visible);
    shown.sort((a, b) => a.marker.position.x - b.marker.position.x || a.marker.position.z - b.marker.position.z);
    shown.forEach(function (view, index) {
      const marker = view.marker.position;
      view.end.position.set(marker.x, Math.max(roofY, marker.y) + 30 + index * END_LABEL_STEP, marker.z);
    });
  }

  /* ----------------------------------------------------------------------
   * Selection and filters
   * ------------------------------------------------------------------- */

  // { type: 'device' | 'cable' | 'reservation', id: string } or null
  let selection = null;

  function legendBands(group) {
    return new Set(window.atlasLegendFilter ? window.atlasLegendFilter.bands(group) : []);
  }

  function finderKeeps(group, ids) {
    if (!window.atlasFinder) return true;
    const picked = window.atlasFinder.picked(group);
    return !picked.size || ids.some((id) => picked.has(id));
  }

  /* Whether a device survives every narrowing: the colouring's legend, each finder that carries
     ids for it, and the find box. The drawing is a canvas, so it reads the picks from the legend
     and the finders rather than from the classes they set on the page. */
  function deviceInFocus(device, bands) {
    if (bands.size && !bands.has(device.band)) return false;
    const keptByFinders = Object.entries(device.filters).every(([group, ids]) =>
      finderKeeps(group, String(ids).split(/\s+/).filter(Boolean))
    );
    return keptByFinders && panel.matchesSearch(device.label, device.assetTag);
  }

  function cableInFocus(cable, bands) {
    return (!bands.size || bands.has(cable.colour)) && finderKeeps('cables', [String(cable.id)]);
  }

  function apply() {
    const deviceBands = legendBands('devices');
    const cableBands = legendBands('cables');
    const hovered = stage.hovered();
    const showNames = stage.showNames();

    const litCables = new Set();
    const litDevices = new Set();
    if (selection && selection.type !== 'reservation') {
      cableViews.forEach(function ({ cable }) {
        const ends = [String(cable.deviceId), cable.peerDeviceId ? String(cable.peerDeviceId) : null];
        const hit = selection.type === 'device' ? ends.includes(selection.id) : String(cable.id) === selection.id;
        if (!hit) return;
        litCables.add(String(cable.id));
        ends.filter(Boolean).forEach((id) => litDevices.add(id));
      });
      if (selection.type === 'device') litDevices.add(selection.id);
    }

    let shown = 0;
    deviceViews.forEach(function (view) {
      const id = String(view.device.id);
      const inFocus = deviceInFocus(view.device, deviceBands);
      if (inFocus) shown += 1;
      const primary = selection && selection.type === 'device' && selection.id === id;
      const related = litDevices.has(id) && !primary;
      // A cable's two ends are what a cable selection is about, so they stay solid. Around a
      // selected device everything else turns to glass, the devices it reaches less so, which
      // is what lets its cables be followed through the cabinet behind them.
      const solid = !selection || primary || (selection.type === 'cable' && related);

      let opacity = 1;
      if (!inFocus) opacity = FILTERED_OPACITY;
      else if (!solid) opacity = related ? RELATED_DEVICE_OPACITY : DIMMED_DEVICE_OPACITY;
      [view.faces.front, view.faces.rear, view.body, view.tagMaterial].forEach((m) => stage.setOpacity(m, opacity));
      view.mesh.castShadow = opacity === 1;

      const glow = primary ? 0.16 : related ? 0.1 : 0;
      [view.faces.front, view.faces.rear].forEach(function (material) {
        material.emissive.copy(highlight);
        material.emissiveIntensity = glow;
      });

      // Drawn over everything for the one selected device, so it can be found from any side;
      // the hovered one is outlined where it is visible, and nothing else is outlined at all.
      const outline = view.outline.material;
      outline.opacity = primary ? 1 : hovered === view ? 0.6 : 0;
      outline.depthTest = !primary;

      // On a colour face the name is already painted on, so the label is only added for the
      // device under the pointer or the one selected.
      view.name.userData.wanted = inFocus && ((showNames && mode === 'images') || primary || hovered === view);
    });

    cableViews.forEach(function (view) {
      const id = String(view.cable.id);
      const inFocus = cableInFocus(view.cable, cableBands);
      const lit = litCables.has(id);
      stage.setOpacity(view.material, !inFocus ? FILTERED_OPACITY : selection && !lit ? DIMMED_CABLE_OPACITY : 1);
      const primary = lit && selection.type === 'cable' && selection.id === id;
      view.material.emissiveIntensity = primary ? 0.75 : lit || hovered === view ? 0.35 : 0;
      // Only for the cables in hand: every uplink of a switch ends at the same roof, and their
      // names all at once are a pile of overlapping boxes.
      if (view.end) view.end.visible = inFocus && (lit || hovered === view);
    });
    stackEndLabels();

    reservationViews.forEach(function (view) {
      const inFocus = !deviceBands.size || deviceBands.has('reserved');
      const primary = selection && selection.type === 'reservation' && selection.id === String(view.band.id);
      view.material.opacity = !inFocus ? 0.04 : primary ? 0.45 : 0.22;
      view.edges.material.opacity = inFocus ? 0.8 : 0.1;
    });

    freeLabels.forEach((node) => (node.visible = showNames && !selection));

    panel.reportShown(shown);
    const selected = selection && selection.type === 'device' ? deviceById.get(selection.id) : null;
    panel.show(selection, { cableIds: litCables, label: selected ? selected.device.label : 'device' });
    stage.requestRender();
  }

  function select(type, id) {
    // Choosing the current selection again clears it, so there is always a way out.
    selection = selection && selection.type === type && selection.id === id ? null : { type, id };
    apply();
  }

  function clearSelection() {
    selection = null;
    panel.hideTrace();
    apply();
  }

  panel.onPick(function (type, id, termination) {
    select(type, id);
    return selection ? panel.showTrace(termination) : panel.hideTrace();
  });
  panel.onSearch(apply);
  stage.onNames(apply);
  document.addEventListener('atlas:filter', apply);
  document.addEventListener('atlas:finder', apply);

  /* ----------------------------------------------------------------------
   * The pointer
   * ------------------------------------------------------------------- */

  const pickable = [
    ...deviceViews.map((v) => v.mesh),
    ...reservationViews.map((v) => v.mesh),
    ...cableViews.map((v) => v.pick),
  ];

  stage.setPicking({
    objects: () => pickable,
    choose(hits) {
      const first = hits[0];
      if (!first) return null;
      // A cable in front of a device is what the pointer means, even where the device's box is
      // nearer: cables run behind the devices and would otherwise only be picked from the back.
      const cableHit = hits.find((hit) => hit.object.userData.cable);
      if (cableHit && cableHit.distance - first.distance < 40) return cableHit.object.userData.cable;
      const data = first.object.userData;
      return data.device || data.reservation || data.cable || null;
    },
    describe(target) {
      if (target.device) return { title: target.device.label, lines: target.device.facts };
      if (target.cable) {
        const lines = target.cable.endLabel ? [`leaves the rack to ${target.cable.endLabel}`] : [];
        return { title: target.cable.label, lines };
      }
      return { title: target.band.label };
    },
    hover: apply,
    click(target) {
      if (!target) return clearSelection();
      if (target.device) {
        select('device', String(target.device.id));
        return panel.hideTrace();
      }
      if (target.cable) {
        select('cable', String(target.cable.id));
        return selection ? panel.showTrace(target.cable.termination) : panel.hideTrace();
      }
      select('reservation', String(target.band.id));
      return panel.hideTrace();
    },
    // A device opens on a double click, so a single click keeps its more useful meaning of
    // "show me what this connects to".
    open(target) {
      if (target && target.device) window.location.href = target.device.url;
    },
  });

  document.addEventListener('click', function (event) {
    if (element.contains(event.target) || event.target.closest('.atlas-cable') || panel.ownsClick(event.target)) return;
    if (selection) clearSelection();
  });

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape' || (!selection && !panel.searchTerm())) return;
    // One key, both narrowings: a reader pressing Escape wants the whole rack back, not to press
    // it twice and wonder which half it undid the first time.
    selection = null;
    panel.clearSearch();
    panel.hideTrace();
    apply();
  });

  /* ----------------------------------------------------------------------
   * Faces, and the first frame
   * ------------------------------------------------------------------- */

  function markMode() {
    controlsBar.querySelectorAll('[data-atlas-mode]').forEach(function (button) {
      const on = button.dataset.atlasMode === mode;
      button.classList.toggle('active', on);
      button.setAttribute('aria-pressed', String(on));
    });
  }

  controlsBar.addEventListener('click', function (event) {
    const modeButton = event.target.closest('[data-atlas-mode]');
    if (!modeButton) return;
    mode = modeButton.dataset.atlasMode;
    if (window.atlasState) window.atlasState.set('mode', mode === 'colour' ? ['colour'] : []);
    deviceViews.forEach(paintFaces);
    markMode();
    apply();
  });

  // The rack with the cables rising out of its roof: what the camera frames.
  const top = cables.reduce((high, cable) => Math.max(high, ...cable.points.map((p) => p[1])), rack.height) + 60;
  stage.setBounds([-halfW, 0, -halfD], [halfW, top, halfD]);
  // A little below the horizon, to look up at the underside of a device, and no further: from
  // under the floor the rack is upside down and the shadow is gone.
  stage.controls.maxPolarAngle = Math.PI * 0.56;

  applyHighlightColour();
  markMode();
  apply();
  stage.start(VIEWS, 'angle');
}

if (element && panel && configNode) {
  const config = JSON.parse(configNode.textContent);
  openStage(element, config, 'rack', (stage) => build(stage, config));
}

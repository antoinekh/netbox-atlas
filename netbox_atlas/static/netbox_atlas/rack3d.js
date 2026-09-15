/*
 * The rack in 3D.
 *
 * A Three.js scene drawn from the one the server built (`scene.py`): device boxes wearing their
 * device type images, the cabinet around them, and every cable along the path the server routed
 * through the cable managers. Nothing here decides where anything goes. It draws, it answers the
 * pointer, and it keeps the selection, telling `rack_panel.js` what is selected so the column
 * beside the drawing can follow it.
 *
 * Loaded as a module, and Three.js through the page's import map, so a deployment can serve its
 * own copy. Everything that can fail to load is awaited before the stage is uncovered, and a
 * failure leaves the reason on the stage rather than a blank box.
 *
 * It draws on demand. A rack that is not moving costs nothing: a frame is rendered when the
 * camera moves, a texture arrives, or the selection changes, and not otherwise.
 */

const panel = window.atlasRackPanel;
const stage = document.querySelector('[data-atlas-rack3d]');
const configNode = document.getElementById('atlas-rack3d-config');

// How long a camera move takes, in milliseconds.
const CAMERA_MOVE = 650;
// A press that moves further than this, in pixels, is a drag of the camera and not a click.
const CLICK_TOLERANCE = 5;
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
// The layer the pointer is tested against. Only pickable meshes are on it, and the camera does
// not draw it, so the fat pick tubes are never seen.
const PICK_LAYER = 1;

class ReaderError extends Error {}

function readerError(message) {
  return new ReaderError(message);
}

function showMessage(message, isError) {
  const node = stage.querySelector('[data-atlas-rack3d-message]');
  node.textContent = message;
  node.classList.toggle('is-error', Boolean(isError));
  node.hidden = false;
}

function hasWebGL() {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'));
  } catch (error) {
    return false;
  }
}

function isDark() {
  return document.documentElement.getAttribute('data-bs-theme') === 'dark';
}

/* Whether white or near-black text reads better on a colour, by its relative luminance. */
function textOn(hex) {
  const value = parseInt(hex.replace('#', ''), 16);
  const channel = (shift) => {
    const c = ((value >> shift) & 255) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const luminance = 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0);
  return luminance > 0.36 ? '#111827' : '#ffffff';
}

async function loadThree(config) {
  if (!config.enabled) {
    throw readerError('The rack drawing is turned off: the three_base setting is empty.');
  }
  if (!hasWebGL()) {
    throw readerError(
      'The rack view needs WebGL, and this browser has none. Turn on hardware acceleration, or use another browser.'
    );
  }
  try {
    const [THREE, controls, labels, environment] = await Promise.all([
      import('three'),
      import('three/addons/controls/OrbitControls.js'),
      import('three/addons/renderers/CSS2DRenderer.js'),
      import('three/addons/environments/RoomEnvironment.js'),
    ]);
    return { THREE, ...controls, ...labels, ...environment };
  } catch (error) {
    console.warn('netbox-atlas:', error);
    throw readerError(
      `The rack view could not load Three.js from ${config.threeBase}. Point the three_base setting at a copy this browser can reach.`
    );
  }
}

function build(lib, config) {
  const { THREE, OrbitControls, CSS2DRenderer, CSS2DObject, RoomEnvironment } = lib;
  const { rack, devices, cables, reservations, free } = config.scene;
  const colours = config.colours;

  const host = stage.querySelector('[data-atlas-rack3d-canvas]');
  const tip = stage.querySelector('[data-atlas-rack3d-tip]');
  const controlsBar = stage.querySelector('[data-atlas-rack3d-controls]');

  /* ----------------------------------------------------------------------
   * Renderer, camera, light
   * ------------------------------------------------------------------- */

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  // Neutral rather than filmic: the device images are photographs of real faceplates, and a
  // filmic curve shifts their colours away from what is printed on the hardware.
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  host.appendChild(renderer.domElement);

  const labelRenderer = new CSS2DRenderer();
  labelRenderer.domElement.classList.add('atlas-rack3d__labels');
  host.appendChild(labelRenderer.domElement);

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.55;

  const centre = new THREE.Vector3(0, rack.height / 2, 0);
  const camera = new THREE.PerspectiveCamera(32, 1, 10, 40000);
  camera.layers.enable(0);

  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(rack.width * 2.2, rack.height * 3, rack.depth * 2.4);
  key.target.position.copy(centre);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.radius = 6;
  key.shadow.bias = -0.0004;
  const reach = Math.max(rack.width, rack.depth, rack.height) * 1.4;
  Object.assign(key.shadow.camera, { left: -reach, right: reach, top: reach, bottom: -reach, near: 10, far: reach * 6 });
  scene.add(key, key.target);
  scene.add(new THREE.HemisphereLight(0xdfe8f5, 0x3a3f47, 0.7));

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.09;
  controls.screenSpacePanning = true;
  controls.minDistance = 250;
  controls.maxDistance = 16000;
  // A little below the horizon, to look up at the underside of a device, and no further: from
  // under the floor the rack is upside down and the shadow is gone.
  controls.maxPolarAngle = Math.PI * 0.56;
  controls.target.copy(centre);

  /* ----------------------------------------------------------------------
   * Drawing on demand
   * ------------------------------------------------------------------- */

  let frame = 0;
  let tween = null;

  function requestRender() {
    if (!frame) frame = requestAnimationFrame(render);
  }

  function render(now) {
    frame = 0;
    if (tween) stepTween(now);
    const moving = controls.update();
    renderer.render(scene, camera);
    faceNamesToCamera();
    labelRenderer.render(scene, camera);
    if (moving || tween) requestRender();
  }

  controls.addEventListener('change', requestRender);

  const toCamera = new THREE.Vector3();

  function faceNamesToCamera() {
    deviceViews.forEach(function (view) {
      toCamera.subVectors(camera.position, view.name.position);
      view.name.visible = Boolean(view.name.userData.wanted) && toCamera.dot(view.normal) > 0;
    });
  }

  /* ----------------------------------------------------------------------
   * Textures
   * ------------------------------------------------------------------- */

  const anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  const loader = new THREE.TextureLoader();
  const imageTextures = new Map();

  function finishTexture(texture) {
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = anisotropy;
    return texture;
  }

  /* One texture per image URL, shared by every device of that type. Resolves to null when the
     image cannot be loaded, so the face falls back to its colour. */
  function imageTexture(url) {
    if (!imageTextures.has(url)) {
      imageTextures.set(
        url,
        new Promise(function (resolve) {
          loader.load(
            url,
            (texture) => resolve(finishTexture(texture)),
            undefined,
            function () {
              console.warn(`netbox-atlas: could not load ${url}`);
              resolve(null);
            }
          );
        })
      );
    }
    return imageTextures.get(url);
  }

  /* A face with no image: the colouring, and the device's name on it, drawn on a canvas at the
     proportions of the face so the letters are not stretched. */
  function nameTexture(label, colour, width, height) {
    const canvasWidth = 1024;
    const canvasHeight = Math.max(64, Math.round((canvasWidth * height) / width));
    const canvas = document.createElement('canvas');
    canvas.width = canvasWidth;
    canvas.height = canvasHeight;
    const context = canvas.getContext('2d');

    const gradient = context.createLinearGradient(0, 0, 0, canvasHeight);
    gradient.addColorStop(0, colour);
    gradient.addColorStop(1, shade(colour, -0.18));
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
    context.fillText(label, ear + 24, canvasHeight / 2, canvasWidth - 2 * ear - 48);

    return finishTexture(new THREE.CanvasTexture(canvas));
  }

  function shade(hex, amount) {
    const colour = new THREE.Color(hex);
    colour.offsetHSL(0, 0, amount);
    return `#${colour.getHexString()}`;
  }

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
  const post = 26;
  const halfW = rack.width / 2;
  const halfD = rack.depth / 2;

  // Plinth, posts and the roof frame. The roof is a frame and not a lid, so the cables leaving
  // through it stay visible from above.
  block(frameMaterial, rack.width, rack.plinth - 20, rack.depth, 0, (rack.plinth - 20) / 2 + 20, 0);
  [-1, 1].forEach(function (sx) {
    [-1, 1].forEach(function (sz) {
      block(frameMaterial, post, rack.height - 20, post, sx * (halfW - post / 2), (rack.height + 20) / 2, sz * (halfD - post / 2));
    });
    block(frameMaterial, post, post, rack.depth, sx * (halfW - post / 2), rack.height - post / 2, 0);
  });
  [-1, 1].forEach(function (sz) {
    block(frameMaterial, rack.width, post, post, 0, rack.height - post / 2, sz * (halfD - post / 2));
  });
  // Feet.
  [-1, 1].forEach(function (sx) {
    [-1, 1].forEach(function (sz) {
      block(frameMaterial, 50, 20, 50, sx * (halfW - 45), 10, sz * (halfD - 45));
    });
  });

  // Glass side panels and roof, so the inside is always in view.
  [-1, 1].forEach(function (sx) {
    const side = new THREE.Mesh(new THREE.PlaneGeometry(rack.depth - post * 2, rack.height - rack.plinth - post), glassMaterial);
    side.rotation.y = Math.PI / 2;
    side.position.set(sx * (halfW - 2), (rack.height + rack.plinth - post) / 2, 0);
    side.renderOrder = 2;
    scene.add(side);
  });

  // Mounting rails, front and rear.
  const railX = rack.faceplate / 2 - 11;
  const interior = interiorTop - rack.plinth;
  [rack.frontRailZ + 1.5, rack.rearRailZ - 1.5].forEach(function (z) {
    [-1, 1].forEach(function (sx) {
      block(railMaterial, 18, interior, 3, sx * railX, rack.plinth + interior / 2, z, { shadow: false });
    });
  });

  // The floor: nothing but the rack's shadow on it.
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(rack.width * 12, rack.depth * 12),
    new THREE.ShadowMaterial({ opacity: 0.2 })
  );
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);

  /* The unit numbers, on a strip beside the front rail and another beside the rear one. Drawn
     into a texture rather than as page elements, so they turn with the rack and stay where
     they are fixed. Redrawn when the theme changes. */
  const rulerMaterials = [];

  function rulerTexture() {
    const units = rack.units.length;
    const perUnit = Math.max(16, Math.min(48, Math.floor(8192 / units)));
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = perUnit * units;
    const context = canvas.getContext('2d');
    const ink = isDark() ? 'rgba(229, 231, 235, .85)' : 'rgba(33, 37, 41, .8)';
    context.fillStyle = ink;
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
    return finishTexture(new THREE.CanvasTexture(canvas));
  }

  [
    { z: rack.frontRailZ + 2, x: -(rack.faceplate / 2 + 14), turn: 0 },
    { z: rack.rearRailZ - 2, x: rack.faceplate / 2 + 14, turn: Math.PI },
  ].forEach(function ({ x, z, turn }) {
    const material = new THREE.MeshBasicMaterial({ map: rulerTexture(), transparent: true, depthWrite: false });
    rulerMaterials.push(material);
    const strip = new THREE.Mesh(new THREE.PlaneGeometry(22, interior), material);
    strip.position.set(x, rack.plinth + interior / 2, z);
    strip.rotation.y = turn;
    scene.add(strip);
  });

  new MutationObserver(function () {
    rulerMaterials.forEach(function (material) {
      material.map.dispose();
      material.map = rulerTexture();
    });
    applyHighlightColour();
    requestRender();
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-bs-theme'] });

  // The cable managers, as the outline of the space the lanes run in.
  const managerDepth = rack.rearRailZ - (-halfD + post);
  Object.values(rack.managers).forEach(function ([x, width]) {
    const box = new THREE.BoxGeometry(width, interior, managerDepth);
    const outline = new THREE.LineSegments(
      new THREE.EdgesGeometry(box),
      new THREE.LineBasicMaterial({ color: 0x8a94a3, transparent: true, opacity: 0.28 })
    );
    outline.position.set(x, rack.plinth + interior / 2, rack.rearRailZ - managerDepth / 2);
    scene.add(outline);
  });

  /* ----------------------------------------------------------------------
   * Devices
   * ------------------------------------------------------------------- */

  let mode = window.atlasState && window.atlasState.get('mode')[0] === 'colour' ? 'colour' : 'images';
  let showNames = Boolean(window.atlasState && window.atlasState.get('names')[0]);

  const highlight = new THREE.Color();
  function applyHighlightColour() {
    highlight.set(isDark() ? colours.highlightDark : colours.highlight);
    deviceViews.forEach((view) => view.outline.material.color.copy(highlight));
  }

  function label(text, className) {
    const node = document.createElement('div');
    node.className = className;
    node.textContent = text;
    return new CSS2DObject(node);
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

    const name = label(device.label, 'atlas-rack3d__name');
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
      imageTexture(url).then(function (texture) {
        view.textures[side] = texture;
        paintFaces(view);
        requestRender();
      });
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
    return { band, mesh, material, edges };
  });
  const reservationById = new Map(reservationViews.map((view) => [String(view.band.id), view]));

  const freeLabels = free.map(function (band) {
    const [x, y, z, w, , d] = band.box;
    const node = label(band.label, 'atlas-rack3d__free');
    node.position.set(x + w / 2 - 30, y, z + d / 2 + 1);
    node.center.set(1, 0.5);
    scene.add(node);
    return node;
  });

  /* ----------------------------------------------------------------------
   * Cables
   * ------------------------------------------------------------------- */

  /* The server's polyline, with its corners rounded. Each corner is cut back along both of its
     segments, never by more than half of either, and bridged with a quadratic curve. */
  function cablePath(points) {
    const vectors = points.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
    const path = new THREE.CurvePath();
    let from = vectors[0];
    for (let i = 1; i < vectors.length - 1; i += 1) {
      const corner = vectors[i];
      const before = vectors[i - 1];
      const after = vectors[i + 1];
      const cut = Math.min(CORNER_RADIUS, corner.distanceTo(before) / 2, corner.distanceTo(after) / 2);
      const entry = corner.clone().lerp(before, cut / Math.max(corner.distanceTo(before), 1e-6));
      const exit = corner.clone().lerp(after, cut / Math.max(corner.distanceTo(after), 1e-6));
      if (from.distanceTo(entry) > 0.01) path.add(new THREE.LineCurve3(from, entry));
      if (cut > 0.01) path.add(new THREE.QuadraticBezierCurve3(entry, corner, exit));
      from = exit;
    }
    path.add(new THREE.LineCurve3(from, vectors[vectors.length - 1]));
    return path;
  }

  const pickMaterial = new THREE.MeshBasicMaterial();

  const cableViews = cables.map(function (cable) {
    const path = cablePath(cable.points);
    const segments = Math.max(24, Math.round(path.getLength() / 12));
    const radius = CABLE_RADIUS[cable.kind] || CABLE_RADIUS.default;
    const material = new THREE.MeshStandardMaterial({
      color: new THREE.Color(cable.colour),
      roughness: 0.5,
      metalness: 0.05,
      emissive: new THREE.Color(cable.colour),
      emissiveIntensity: 0,
      transparent: true,
    });
    const tube = new THREE.Mesh(new THREE.TubeGeometry(path, segments, radius, 8, false), material);
    scene.add(tube);

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
      end = label(cable.endLabel, 'atlas-rack3d__end');
      end.center.set(0.5, 1);
      scene.add(end);
    }
    const view = { cable, tube, pick, material, marker, end };
    pick.userData.cable = view;
    return view;
  });

  /* The names of the cables leaving the rack that are on show, one above the other over the
     roof. Their markers end at one height, so the names would otherwise print over each other;
     stacked in the order the lanes run, each name sits above the marker nearest it. */
  const END_LABEL_STEP = 70;
  const roofY = rack.height + 60;

  function stackEndLabels() {
    const shown = cableViews.filter((view) => view.end && view.end.visible);
    shown.sort((a, b) => a.marker.position.x - b.marker.position.x || a.marker.position.z - b.marker.position.z);
    shown.forEach(function (view, index) {
      const marker = view.marker.position;
      view.end.position.set(marker.x, Math.max(roofY, marker.y) + 30 + index * END_LABEL_STEP, marker.z);
    });
  }

  deviceViews.forEach((view) => (view.mesh.userData.device = view));
  reservationViews.forEach((view) => (view.mesh.userData.reservation = view));

  /* ----------------------------------------------------------------------
   * Selection and filters
   * ------------------------------------------------------------------- */

  // { type: 'device' | 'cable' | 'reservation', id: string } or null
  let selection = null;
  let hovered = null;

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

  function setOpacity(material, opacity) {
    const transparent = opacity < 1;
    // Blending is part of the compiled material, so a change of `transparent` has to recompile
    // it; a change of the opacity alone does not.
    if (material.transparent !== transparent) material.needsUpdate = true;
    material.transparent = transparent;
    material.opacity = opacity;
    material.depthWrite = !transparent;
  }

  function apply() {
    const deviceBands = legendBands('devices');
    const cableBands = legendBands('cables');

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
      [view.faces.front, view.faces.rear, view.body, view.tagMaterial].forEach((m) => setOpacity(m, opacity));
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
      const opacity = !inFocus ? FILTERED_OPACITY : selection && !lit ? DIMMED_CABLE_OPACITY : 1;
      setOpacity(view.material, opacity);
      view.material.emissiveIntensity = lit ? (selection.type === 'cable' && selection.id === id ? 0.75 : 0.35) : hovered === view ? 0.35 : 0;
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
    requestRender();
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
  document.addEventListener('atlas:filter', apply);
  document.addEventListener('atlas:finder', apply);

  /* ----------------------------------------------------------------------
   * The pointer
   * ------------------------------------------------------------------- */

  const raycaster = new THREE.Raycaster();
  raycaster.layers.set(PICK_LAYER);
  const pointer = new THREE.Vector2();
  let pendingMove = null;
  let pressed = null;

  function hitAt(clientX, clientY) {
    const box = renderer.domElement.getBoundingClientRect();
    pointer.set(((clientX - box.left) / box.width) * 2 - 1, -((clientY - box.top) / box.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const pickable = [
      ...deviceViews.map((v) => v.mesh),
      ...reservationViews.map((v) => v.mesh),
      ...cableViews.map((v) => v.pick),
    ];
    const hits = raycaster.intersectObjects(pickable, false);
    // A cable in front of a device is what the pointer means, even where the device's box is
    // nearer: cables run behind the devices and would otherwise only be picked from the back.
    const cableHit = hits.find((hit) => hit.object.userData.cable);
    const first = hits[0];
    if (!first) return null;
    if (cableHit && cableHit.distance - first.distance < 40) return cableHit.object.userData.cable;
    const data = first.object.userData;
    return data.device || data.reservation || data.cable || null;
  }

  function showTip(target, clientX, clientY) {
    if (!target) {
      tip.hidden = true;
      return;
    }
    tip.replaceChildren();
    const title = document.createElement('strong');
    const lines = [];
    if (target.device) {
      title.textContent = target.device.label;
      lines.push(...target.device.facts);
    } else if (target.cable) {
      title.textContent = target.cable.label;
      if (target.cable.endLabel) lines.push(`leaves the rack to ${target.cable.endLabel}`);
    } else {
      title.textContent = target.band.label;
    }
    tip.appendChild(title);
    lines.forEach(function (line) {
      const row = document.createElement('div');
      row.textContent = line;
      tip.appendChild(row);
    });
    tip.hidden = false;
    const box = stage.getBoundingClientRect();
    const left = clientX - box.left + 14;
    const top = clientY - box.top + 14;
    tip.style.left = `${Math.min(left, box.width - tip.offsetWidth - 8)}px`;
    tip.style.top = `${Math.min(top, box.height - tip.offsetHeight - 8)}px`;
  }

  renderer.domElement.addEventListener('pointermove', function (event) {
    if (pressed) return;
    const first = !pendingMove;
    pendingMove = event;
    if (!first) return;
    requestAnimationFrame(function () {
      const { clientX, clientY } = pendingMove;
      pendingMove = null;
      const target = hitAt(clientX, clientY);
      renderer.domElement.style.cursor = target ? 'pointer' : 'grab';
      showTip(target, clientX, clientY);
      if (target !== hovered) {
        hovered = target;
        apply();
      }
    });
  });

  renderer.domElement.addEventListener('pointerleave', function () {
    tip.hidden = true;
    if (hovered) {
      hovered = null;
      apply();
    }
  });

  renderer.domElement.addEventListener('pointerdown', function (event) {
    pressed = { x: event.clientX, y: event.clientY, button: event.button };
    tip.hidden = true;
  });

  renderer.domElement.addEventListener('pointerup', function (event) {
    const press = pressed;
    pressed = null;
    if (!press || press.button !== 0) return;
    if (Math.hypot(event.clientX - press.x, event.clientY - press.y) > CLICK_TOLERANCE) return;
    const target = hitAt(event.clientX, event.clientY);
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
  });

  /* A device opens on a double click, so a single click keeps its more useful meaning of "show
     me what this connects to". */
  renderer.domElement.addEventListener('dblclick', function (event) {
    const target = hitAt(event.clientX, event.clientY);
    if (target && target.device) window.location.href = target.device.url;
  });

  document.addEventListener('click', function (event) {
    if (stage.contains(event.target) || event.target.closest('.atlas-cable') || panel.ownsClick(event.target)) return;
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
   * The camera
   * ------------------------------------------------------------------- */

  const VIEWS = {
    front: new THREE.Vector3(0, 0.05, 1),
    rear: new THREE.Vector3(0, 0.05, -1),
    side: new THREE.Vector3(1, 0.05, 0),
    angle: new THREE.Vector3(0.85, 0.42, 1.1),
  };

  // The rack with the cables rising out of its roof: what the camera frames.
  const top = cables.reduce((high, cable) => Math.max(high, ...cable.points.map((p) => p[1])), rack.height) + 60;
  const corners = [];
  [-halfW, halfW].forEach(function (x) {
    [0, top].forEach(function (y) {
      [-halfD, halfD].forEach((z) => corners.push(new THREE.Vector3(x, y, z)));
    });
  });
  const boundsCentre = new THREE.Vector3(0, top / 2, 0);

  /* Where the camera stands to fit the whole rack when looking along `direction`.
   *
   * Fitted to the box rather than to a sphere round it: a sphere is the rack's diagonal in every
   * direction, which left a front view of a tall narrow cabinet with most of the stage empty.
   * Each corner needs the camera far enough back that it falls inside both halves of the view,
   * counting how much nearer to the camera the corner already is. */
  function framing(direction) {
    const forward = direction.clone().normalize();
    const right = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), forward).normalize();
    const up = new THREE.Vector3().crossVectors(forward, right);
    const tanV = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
    const tanH = tanV * camera.aspect;
    let distance = 0;
    corners.forEach(function (corner) {
      const offset = corner.clone().sub(boundsCentre);
      const towards = offset.dot(forward);
      distance = Math.max(
        distance,
        Math.abs(offset.dot(right)) / tanH + towards,
        Math.abs(offset.dot(up)) / tanV + towards
      );
    });
    return {
      position: boundsCentre.clone().add(forward.multiplyScalar(distance * 1.08)),
      target: boundsCentre.clone(),
    };
  }

  function easeInOut(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
  }

  function stepTween(now) {
    const t = Math.min(1, (now - tween.start) / CAMERA_MOVE);
    const k = easeInOut(t);
    camera.position.lerpVectors(tween.fromPosition, tween.to.position, k);
    controls.target.lerpVectors(tween.fromTarget, tween.to.target, k);
    if (t >= 1) tween = null;
  }

  function lookFrom(name, { animate = true } = {}) {
    const to = framing(VIEWS[name]);
    controlsBar.querySelectorAll('[data-atlas-view]').forEach(function (button) {
      button.classList.toggle('active', button.dataset.atlasView === name);
    });
    if (!animate || panel.prefersReducedMotion()) {
      tween = null;
      camera.position.copy(to.position);
      controls.target.copy(to.target);
      controls.update();
      return requestRender();
    }
    tween = {
      start: performance.now(),
      fromPosition: camera.position.clone(),
      fromTarget: controls.target.clone(),
      to: to,
    };
    requestRender();
  }

  // A drag of the camera leaves every preset: none of them describes the view any more.
  controls.addEventListener('start', function () {
    tween = null;
    controlsBar.querySelectorAll('[data-atlas-view]').forEach((button) => button.classList.remove('active'));
  });

  /* ----------------------------------------------------------------------
   * The controls on the stage
   * ------------------------------------------------------------------- */

  function markMode() {
    controlsBar.querySelectorAll('[data-atlas-mode]').forEach(function (button) {
      const on = button.dataset.atlasMode === mode;
      button.classList.toggle('active', on);
      button.setAttribute('aria-pressed', String(on));
    });
    const names = controlsBar.querySelector('[data-atlas-labels]');
    names.classList.toggle('active', showNames);
    names.setAttribute('aria-pressed', String(showNames));
  }

  controlsBar.addEventListener('click', function (event) {
    const view = event.target.closest('[data-atlas-view]');
    if (view) return lookFrom(view.dataset.atlasView);

    const modeButton = event.target.closest('[data-atlas-mode]');
    if (modeButton) {
      mode = modeButton.dataset.atlasMode;
      if (window.atlasState) window.atlasState.set('mode', mode === 'colour' ? ['colour'] : []);
      deviceViews.forEach(paintFaces);
      markMode();
      return apply();
    }

    if (event.target.closest('[data-atlas-labels]')) {
      showNames = !showNames;
      if (window.atlasState) window.atlasState.set('names', showNames ? ['on'] : []);
      markMode();
      return apply();
    }

    if (event.target.closest('[data-atlas-fullscreen]')) {
      if (document.fullscreenElement) document.exitFullscreen();
      else if (stage.requestFullscreen) stage.requestFullscreen();
    }
  });

  document.addEventListener('fullscreenchange', function () {
    const icon = controlsBar.querySelector('[data-atlas-fullscreen] .mdi');
    icon.classList.toggle('mdi-fullscreen', !document.fullscreenElement);
    icon.classList.toggle('mdi-fullscreen-exit', Boolean(document.fullscreenElement));
  });

  /* ----------------------------------------------------------------------
   * Size
   * ------------------------------------------------------------------- */

  let framed = false;

  function resize() {
    const width = host.clientWidth;
    const height = host.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    labelRenderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    if (!framed) {
      framed = true;
      lookFrom('angle', { animate: false });
    }
    requestRender();
  }

  new ResizeObserver(resize).observe(host);

  applyHighlightColour();
  markMode();
  controlsBar.hidden = false;
  resize();
  apply();
}

async function main() {
  const config = JSON.parse(configNode.textContent);
  try {
    const lib = await loadThree(config);
    build(lib, config);
    stage.querySelector('[data-atlas-rack3d-message]').hidden = true;
  } catch (error) {
    if (error instanceof ReaderError) {
      showMessage(error.message, true);
      return;
    }
    showMessage('The rack view could not draw this rack. The browser console has the detail.', true);
    console.warn('netbox-atlas could not draw the rack:', error);
  }
}

if (stage && panel && configNode) main();

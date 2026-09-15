# Gotchas

Things about NetBox and about this stack that cost time to find out. Each one is here because it was learned the hard way.

## NetBox

- **NetBox sets `CSRF_COOKIE_HTTPONLY`**, so JavaScript cannot read the CSRF cookie. Read the token from the hidden input Django renders.
- **NetBox sends `Referrer-Policy: same-origin`**, so a request to another origin carries no `Referer`. OpenStreetMap's tile servers block exactly that ("Referer is required"). The world map page overrides the policy with a `<meta name="referrer">` tag.
- **`Rack.get_utilization()` is U-space, not power.** Power is `get_power_utilization()`, and it returns 0 both for an idle rack and one with no feeds. The two are different questions and one of them has no answer.
- **Rack units are counted in halves.** A 48U rack has 96 of them.
- **`CableTermination` denormalises `_rack_id`**, which is what makes the floor's cable runs one query rather than one per cable.
- **Cables built by creating `CableTermination` rows get no `CablePath`** and cannot be traced. The link exists, the drawing shows it, and `trace()` returns nothing. Use `a_terminations` / `b_terminations`.
- **`PowerPort.get_power_draw()` walks the tree below each port**, so calling it per port costs a handful of queries per PDU. `power.py` resolves the whole rack a level at a time instead.
- **A power port with both `allocated_draw` and `maximum_draw` blank is in aggregating mode**, and reports what is plugged into it. One with either value set reports that value. Only both being blank puts it in the first case.

## This stack

- **A plugin on `PYTHONPATH` is not collected by the entrypoint.** Run `make static` after touching anything under `static/`.
- **A template change needs `make reload`, not `make static`.** Django caches the loaded templates.
- **A browser with no GPU has no WebGL**, and the rack view and the world map then show their "needs WebGL" message. The DevTools browser under WSL is one. For a headless check, start Chrome with `--use-angle=swiftshader --enable-unsafe-swiftshader`.
- **The demo SQL dump inserts explicit ids without advancing the sequences**, so the first row NetBox writes afterwards collides. `manage.py sqlsequencereset` for the affected apps fixes it. The symptom is a worker container that dies on `duplicate key value violates unique constraint "core_job_pkey"`.

## Drawing

- **Overlapping strokes defeat dimming.** Seventeen lines at 14% opacity drawn on the same path composite back to about 94%: the band reads as fully lit while being unclickable. Anything that can be drawn more than once on the same path has to be separated first, which is what the lanes in `scene.py` do for the cables in a rack.
- **In Three.js, changing a material's `transparent` needs `material.needsUpdate = true`.** Changing its `opacity` alone does not. Without it, a cable faded by a filter stays solid.
- **Three.js 0.186 has no `PCFSoftShadowMap`.** It warns and falls back to `PCFShadowMap`.
- **A metallic material under a dim environment renders black, whatever its colour.** Metal shows reflections, not its base colour, and the stage's environment light is dim. The cabinet finish in `stage3d.js` is only half metallic for that reason.
- **A fixed camera near plane breaks at room scale.** With a near plane of a few millimetres, a room ten metres across has too little depth precision to tell a door panel from the cabinet face behind it, and the two show through each other in stripes. `stage3d.js` sets the near plane from the size of what is drawn.
- **A raycaster also hits hidden meshes.** Filter the hits on `object.visible`, or hidden cabling still takes the pointer.
- **`getBoundingClientRect().top` does not tell you whether two SVG elements overlap.** Diagonal paths that share a start point share a bounding-box top. Compare the `d` attribute, or sample pixels.

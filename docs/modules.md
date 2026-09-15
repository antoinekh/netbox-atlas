# Modules

What each part of the plugin holds. The Python modules are under `netbox_atlas/`, the scripts under `netbox_atlas/static/netbox_atlas/`.

| Module | Holds |
|---|---|
| `models` | `Floor`, `RackPlacement` and `FloorLayer`, geometry only |
| `signals` | Removing a background image from storage when no layer uses it any more |
| `layout` / `world` | Turning those into a drawing |
| `elevation` / `scene` | A rack in rack units, then the same rack in millimetres for the 3D drawing, with every cable routed through the cable managers |
| `cabling` / `ports` / `power` / `floor_cabling` | Resolved in bulk, never per object |
| `tracing` | Following a path end to end, and a power chain past the PDU |
| `overlays` / `device_overlays` / `site_overlays` | The colouring registries and their built-ins |
| `palette` | Every colour that carries meaning, in one place |
| `tags` | The tags in use on a floor or in a rack, for the Tags finder |
| `field_filters` | Custom fields offered as filters, the way tags are |
| `geometry` | Footprints, the scale, and the one type size a drawing gets |
| `legend.js` | Picking bands, shared by all three levels |
| `finder.js` | Searching and ticking a long list, shared by the map and the rack |
| `state.js` | What a drawing is narrowed to, kept in the URL hash |
| `zoom.js` | Zooming into a floor plan and moving round it, on the floor page and in the editor |
| `floor.js` | The floor: hovering, selection, tracing, the rack table |
| `stage3d.js` | What every 3D drawing shares: loading Three.js, light and shadow, labels, the hover card and clicks, the camera and its views, and the message shown when it cannot be drawn |
| `rack3d.js` | The rack on a 3D stage: device images, cables and selection |
| `rack_panel.js` | The column beside the rack: port allocation, cabling, reservations and the traced path |
| `world.js` | The MapLibre globe, and the message shown when it cannot be drawn |
| `editor.js` | Dragging and saving a placement |

To add a colouring from another plugin, or to read a floor through the REST API, see [extending.md](extending.md).

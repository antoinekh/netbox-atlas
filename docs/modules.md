# Modules

What each part of the plugin holds. The Python modules are under `netbox_atlas/`, the scripts under `netbox_atlas/static/netbox_atlas/`.

| Module | Holds |
|---|---|
| `models` | `Floor`, `RackPlacement` and `FloorLayer`, geometry only |
| `signals` | Removing a background image from storage when no layer uses it any more |
| `layout` / `elevation` / `world` | Turning those into a drawing |
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
| `floor.js` / `rack.js` | One level each: hovering, selection, tracing, the rack table |
| `world.js` | The MapLibre globe, and the message shown when it cannot be drawn |
| `editor.js` | Dragging and saving a placement |

To add a colouring from another plugin, or to read a floor through the REST API, see [extending.md](extending.md).

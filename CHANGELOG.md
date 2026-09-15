# Changelog

## Unreleased

First version.

### Added

- **World map:** sites on a MapLibre globe, sized by rack count and coloured by group, status, tenant or region, with the circuits between them coloured by provider.
- **Site page:** a tab on NetBox's site page that draws every room in the site as a small plan, and lists the racks that stand on no floor.
- **Floor plans:** racks at their real positions, coloured by power, cooling, space or role, with a gauge on each rack, a background plan (PNG, JPEG, WebP or GIF), cable runs, zoom and a sortable rack table.
- **Floor in 3D:** the floor opens in 3D, each rack a cabinet at its real position, rotation and height, coloured by the floor's colouring with the reading on its doors, and the cable runs as arcs over the racks and to the walls. A Cabinets and Devices switch opens every rack to show its devices with their front and rear images, loaded on demand from `GET /api/plugins/atlas/floors/<id>/devices/`. A 3D and 2D switch keeps the plan one click away, and the floor falls back to 2D when 3D cannot be drawn. The legend, finders, find box and rack table work in both.
- **Layout editor:** drag, rotate and place racks, or lay them out automatically.
- **Rack view:** the rack in 3D with Three.js, with the device type front and rear images, every cable routed through the cable managers, reserved and free units, camera presets, and colouring by role, status, tenant, cabling or power. The `three_base` setting says where Three.js loads from.
- **Tracing:** a network path through patch panels to a provider, and a power chain from socket to feed.
- **Legends and finders that filter:** pick several legend bands, tick rows, find racks and devices by name or asset tag, and narrow them by tag or by a select custom field; what you picked is kept in the URL.

### Fixed

- **World map:** tiles from OpenStreetMap were refused with "Referer is required", because NetBox's `Referrer-Policy` sent no `Referer`. The world map page now sends its origin.

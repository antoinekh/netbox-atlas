# Changelog

## Unreleased

First version.

### Added

- **World map:** sites on a MapLibre globe, sized by rack count and coloured by group, status, tenant or region, with the circuits between them coloured by provider.
- **Site page:** a tab on NetBox's site page that draws every room in the site as a small plan, and lists the racks that stand on no floor.
- **Floor plans:** racks at their real positions, coloured by power, cooling, space or role, with a gauge on each rack, a background plan (PNG, JPEG, WebP or GIF), cable runs, zoom and a sortable rack table.
- **Layout editor:** drag, rotate and place racks, or lay them out automatically.
- **Rack view:** the front and rear faces with ports, cabling, reserved units and free space, coloured by role, status, tenant, cabling or power.
- **Tracing:** a network path through patch panels to a provider, and a power chain from socket to feed.
- **Legends and finders that filter:** pick several legend bands, tick rows, find racks and devices by name or asset tag, and narrow them by tag or by a select custom field; what you picked is kept in the URL.
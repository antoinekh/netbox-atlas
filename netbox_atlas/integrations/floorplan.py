"""
Reading a layout out of netbox-floorplan.

netbox-floorplan stores its plan as a raw Fabric.js canvas in one JSONField. A rack's identity
sits in `custom_meta.object_id` on an object nested inside a group, and its position is that
group's own `left` and `top`. There are no coordinate columns, so the only way to recover a
placement is to walk the tree.

We do that once, on import, and never again. After that the placements are ordinary rows.

This module never imports netbox_floorplan. It is handed a canvas dictionary, so it is
testable against a captured one and works whether or not that plugin is installed, which on
NetBox 4.7 it cannot be.
"""

__all__ = (
    'extract_rack_placements',
    'load_floorplan_canvases',
)


def _walk(objects):
    """
    Yield every object in the canvas, descending into groups.

    Fabric nests a group's members under its own `objects` key, and netbox-floorplan puts the
    rack marker one level down while keeping the position on the group above it. Both levels
    matter, so both are yielded, each with the group that carried it.
    """
    for obj in objects or []:
        yield obj, None
        for child in obj.get('objects') or []:
            yield child, obj


def extract_rack_placements(canvas: dict | None, scale: float = 1.0) -> list[tuple[int, float, float, float]]:
    """
    Every rack in a netbox-floorplan canvas, as (rack_id, x, y, rotation).

    Coordinates come from the group, because that is what Fabric moves when a rack is dragged.
    A marker with no group of its own falls back to its own position, which is what a canvas
    saved before netbox-floorplan grouped its objects looks like.

    `scale` converts the canvas units to centimetres. netbox-floorplan draws in arbitrary
    canvas units and records the room size separately, so the caller works the ratio out from
    the two width figures and passes it in; this function does no guessing.

    Unknown shapes are skipped rather than raising. A canvas is drawn by hand and may hold
    anything: walls, text, a logo somebody pasted in.
    """
    placements = {}
    for obj, group in _walk(canvas.get('objects') if canvas else None):
        meta = obj.get('custom_meta') or {}
        if meta.get('object_type') != 'rack':
            continue
        try:
            rack_id = int(meta['object_id'])
        except (KeyError, TypeError, ValueError):
            continue

        source = group or obj
        try:
            x = float(source.get('left', 0)) * scale
            y = float(source.get('top', 0)) * scale
            rotation = float(source.get('angle', 0)) % 360
        except (TypeError, ValueError):
            continue

        # A rack drawn twice keeps its first placement; a placement is one-to-one, and the
        # first is the one the eye reads as the real one in a stack.
        placements.setdefault(rack_id, (rack_id, x, y, rotation))

    return list(placements.values())


def load_floorplan_canvases() -> list[tuple]:
    """
    Every netbox-floorplan plan, as (site, location, width, height, unit, canvas).

    Returns an empty list when that plugin is not installed, which is the normal case on
    NetBox 4.7: netbox-floorplan 0.9.2 declares a maximum of 4.6.99 and cannot load.
    """
    try:
        from netbox_floorplan.models import Floorplan
    except ImportError:
        return []

    return [
        (fp.site, fp.location, fp.width, fp.height, fp.measurement_unit, fp.canvas) for fp in Floorplan.objects.all()
    ]

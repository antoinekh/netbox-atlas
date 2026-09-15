"""
What colours a device inside a rack.

The floor has overlays; a rack drawing had one hard-coded answer, the device role. Role is a
good default and a poor only option: the question in front of a rack is as often "what is
still being built here", "who owns this", or "what is not cabled yet", and each of those is a
different colouring of the same picture.

Registered the same way rack overlays are, so another plugin can add one, and evaluated in
bulk for the same reason: a rack is a set of devices, not one device asked twelve times.

`RackValue` is reused rather than copied. It carries a colour, a label and whether there was
an answer at all, which is exactly as true of a device as of a rack, and having one type means
the no-data rule cannot be implemented twice and drift.
"""

import logging
from collections.abc import Callable, Sequence

from netbox_spatial_lens.overlays import NO_DATA_COLOUR, UTILISATION_LEGEND, Colouring, LegendEntry, RackValue
from netbox_spatial_lens.palette import (
    COMPLETION,
    NO_ROLE,
    STATUS_COLOURS,
    completion_colour,
    distinct_colours,
    utilisation_colour,
)

__all__ = (
    'DeviceOverlay',
    'get_device_overlay',
    'get_device_overlays',
    'register_builtin_device_overlays',
    'register_device_overlay',
)

logger = logging.getLogger('netbox.plugins.netbox_spatial_lens.device_overlays')

_registry: dict[str, 'DeviceOverlay'] = {}


class DeviceOverlay(Colouring):
    """
    A named way of colouring the devices in a rack.

    `fn` takes the mounted devices and returns a dict of device id to RackValue.
    """

    @staticmethod
    def item_key(item) -> int:
        return item.device.pk


def register_device_overlay(
    name: str,
    label: str,
    fn: Callable,
    description: str = '',
    legend: list[LegendEntry] | None = None,
) -> DeviceOverlay:
    """
    Make a device colouring selectable on every rack.

    `name` is the key used in the URL, so a coloured rack is a link somebody can send. Keep it
    stable and change the label freely.
    """
    if name in _registry:
        logger.warning(f'Device overlay "{name}" is already registered; the later registration wins.')
    _registry[name] = DeviceOverlay(name, label, fn, description, list(legend or []))
    return _registry[name]


def get_device_overlays() -> list[DeviceOverlay]:
    return list(_registry.values())


def get_device_overlay(name: str) -> DeviceOverlay | None:
    return _registry.get(name)


# --------------------------------------------------------------------------------------
# Built-in device overlays
# --------------------------------------------------------------------------------------


def role_overlay(mounted: Sequence) -> dict[int, RackValue]:
    """
    The device role, in its own colour. The default, and what the drawing used to hard-code.
    """
    values = {}
    for m in mounted:
        role = getattr(m.device, 'role', None)
        if role is None:
            continue
        values[m.device.pk] = RackValue(
            colour=f'#{role.color}' if role.color else NO_ROLE,
            label=role.name,
            value=role.name,
        )
    return values


def status_overlay(mounted: Sequence) -> dict[int, RackValue]:
    """
    Lifecycle status: what is live, what is staged, what has failed.

    NetBox already assigns each status a colour, so this reads the same as the device list
    rather than inventing a second scheme for the same fact.
    """
    values = {}
    for m in mounted:
        device = m.device
        if not device.status:
            continue
        values[device.pk] = RackValue(
            colour=STATUS_COLOURS.get(device.get_status_color(), NO_DATA_COLOUR),
            label=device.get_status_display(),
            value=device.status,
        )
    return values


def tenant_overlay(mounted: Sequence) -> dict[int, RackValue]:
    """
    Who owns each device, which is the question in any shared or colocated rack.

    A tenant carries no colour of its own, so one is derived from its name, chosen across the
    whole rack so that two tenants never share a swatch.
    """
    colours = distinct_colours(
        (tenant.name for m in mounted if (tenant := getattr(m.device, 'tenant', None)) is not None),
        reserved=(NO_DATA_COLOUR,),
    )
    values = {}
    for m in mounted:
        tenant = getattr(m.device, 'tenant', None)
        if tenant is None:
            continue
        values[m.device.pk] = RackValue(
            colour=colours[tenant.name],
            label=tenant.name,
            value=tenant.name,
        )
    return values


CABLING_LEGEND = [LegendEntry(colour, label) for _, colour, label in COMPLETION]


def cabling_overlay(mounted: Sequence) -> dict[int, RackValue]:
    """
    How much of each device is actually plugged in.

    The question before a hand-over: a rack can be full of devices and empty of links, and
    that is invisible in every other colouring.
    """
    values = {}
    for m in mounted:
        if not m.port_count:
            continue
        connected = m.connected_count
        percent = connected / m.port_count * 100
        # The count first, because "3 of 48" is what somebody acts on; the percentage is what
        # makes two devices comparable at a glance.
        label = f'{connected} of {m.port_count} cabled ({percent:.0f}%)'
        values[m.device.pk] = RackValue(
            colour=completion_colour(percent),
            label=label,
            value=percent,
        )
    return values


def power_overlay(mounted: Sequence) -> dict[int, RackValue]:
    """
    Allocated draw against what the device declares it can take.

    Both figures are administrative rather than measured, so the label says "allocated": a
    rack full on paper may be idle in practice, and the two are different problems.
    """
    values = {}
    for m in mounted:
        power = getattr(m, 'power', None)
        if power is None or not power.maximum_watts:
            continue
        percent = power.allocated_watts / power.maximum_watts * 100
        values[m.device.pk] = RackValue(
            colour=utilisation_colour(percent),
            label=f'{power.allocated_watts:.0f} W of {power.maximum_watts:.0f} W',
            value=percent,
        )
    return values


BUILTIN_DEVICE_OVERLAYS: dict[str, tuple[str, Callable, str, list]] = {
    'role': ('Role', role_overlay, 'The device role, in its own colour.', []),
    'status': ('Status', status_overlay, 'What is live, staged, failed or planned.', []),
    'tenant': ('Tenant', tenant_overlay, 'Who owns each device.', []),
    'cabling': ('Cabling', cabling_overlay, 'How much of each device is plugged in.', CABLING_LEGEND),
    'power': ('Power', power_overlay, 'Allocated draw against the device maximum.', UTILISATION_LEGEND),
}


def register_builtin_device_overlays(names: list[str] | None = None) -> None:
    """
    Register the built-in device overlays, all of them or the named subset.

    An unrecognised name is logged and skipped rather than raised, so a typo in the plugin
    configuration cannot stop NetBox from booting.
    """
    if names is None:
        names = list(BUILTIN_DEVICE_OVERLAYS)
    for name in names:
        if name not in BUILTIN_DEVICE_OVERLAYS:
            logger.warning(f'Unknown built-in device overlay "{name}"; skipped.')
            continue
        label, fn, description, legend = BUILTIN_DEVICE_OVERLAYS[name]
        register_device_overlay(name, label, fn, description=description, legend=legend)

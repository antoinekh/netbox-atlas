"""
What colours a site on the world map.

The map had one hard-coded answer, the site group. Group is a good default and a poor only
option: at this zoom the question is as often "what is still planned", "who owns this" or
"which region is this in", and each is a different colouring of the same set of points. It
mattered more here than on the floor, because the legend on this map is also its filter, so
the one thing it could colour by was the one thing you could narrow to.

Registered the same way rack and device overlays are, so another plugin can add one, and
evaluated in bulk for the same reason: a map is a set of sites, not one site asked four times.
A categorical colouring has a second reason to see them all at once. Its colours have to be
distinct across the whole set, which cannot be decided one site at a time.

`RackValue` is reused rather than copied, exactly as the device overlays reuse it. It carries
a colour, a label and whether there was an answer at all, which is as true of a site as of a
rack, and one type means the no-data rule cannot be implemented three times and drift.
"""

import logging
from collections.abc import Callable, Sequence

from netbox_spatial_lens.overlays import NO_DATA_COLOUR, Colouring, LegendEntry, RackValue
from netbox_spatial_lens.palette import RESERVED_COLOURS, STATUS_COLOURS, distinct_colours

__all__ = (
    'BUILTIN_SITE_OVERLAYS',
    'RESERVED_COLOURS',
    'SiteOverlay',
    'distinct_colours',
    'get_site_overlay',
    'get_site_overlays',
    'group_overlay',
    'region_overlay',
    'register_builtin_site_overlays',
    'register_site_overlay',
    'status_overlay',
    'tenant_overlay',
)

logger = logging.getLogger('netbox.plugins.netbox_spatial_lens.site_overlays')

_registry: dict[str, 'SiteOverlay'] = {}


class SiteOverlay(Colouring):
    """
    A named way of colouring the sites on the world map.

    `fn` takes the sites and returns a dict of site id to RackValue.
    """


def _by_related(sites: Sequence, attribute: str) -> dict[int, RackValue]:
    """
    Colour each site by the name of a related object, or leave it as no data.

    The colours are chosen across the whole set rather than per site, which is the only place
    the clash between two names hashing alike can be seen and settled.
    """
    sites = list(sites)
    colours = distinct_colours(
        related.name for site in sites if (related := getattr(site, attribute, None)) is not None
    )
    values = {}
    for site in sites:
        related = getattr(site, attribute, None)
        if related is None:
            continue
        values[site.pk] = RackValue(colour=colours[related.name], label=related.name, value=related.name)
    return values


def group_overlay(sites: Sequence) -> dict[int, RackValue]:
    """
    The site group: how an estate is usually organised, and the map's default.

    A map of two dozen identical dots throws that organisation away, and which of these is a
    branch and which is a data centre is exactly the question at this zoom.
    """
    return _by_related(sites, 'group')


def tenant_overlay(sites: Sequence) -> dict[int, RackValue]:
    """
    Who owns each site.
    """
    return _by_related(sites, 'tenant')


def region_overlay(sites: Sequence) -> dict[int, RackValue]:
    """
    Where each site is, by NetBox's own geography rather than by its coordinates.

    The map already places a site by latitude and longitude. This says which region somebody
    filed it under, which is what an estate is actually run by and is not always what the
    coordinates suggest.
    """
    return _by_related(sites, 'region')


def status_overlay(sites: Sequence) -> dict[int, RackValue]:
    """
    Lifecycle status: what is live, what is planned, what is being decommissioned.

    NetBox already assigns each status a colour, so this reads the same as the site list
    rather than inventing a second scheme for the same fact.
    """
    values = {}
    for site in sites:
        if not site.status:
            continue
        values[site.pk] = RackValue(
            colour=STATUS_COLOURS.get(site.get_status_color(), NO_DATA_COLOUR),
            label=site.get_status_display(),
            value=site.status,
        )
    return values


BUILTIN_SITE_OVERLAYS: dict[str, tuple[str, Callable, str]] = {
    'group': ('Group', group_overlay, 'How the estate is organised.'),
    'status': ('Status', status_overlay, 'What is live, planned or being retired.'),
    'tenant': ('Tenant', tenant_overlay, 'Who owns each site.'),
    'region': ('Region', region_overlay, 'The region each site is filed under.'),
}


def register_site_overlay(
    name: str,
    label: str,
    fn: Callable,
    description: str = '',
    legend: list[LegendEntry] | None = None,
) -> 'SiteOverlay':
    """
    Make a colouring selectable on the world map.

    `name` is the key used in the URL, so it survives in a shared link; keep it stable and
    change the label freely.
    """
    if name in _registry:
        logger.warning(f'Site overlay "{name}" is already registered; the later registration wins.')
    _registry[name] = SiteOverlay(
        name=name,
        label=label,
        fn=fn,
        description=description,
        legend=list(legend or []),
    )
    return _registry[name]


def get_site_overlays() -> list['SiteOverlay']:
    """
    Every registered colouring, in registration order.
    """
    return list(_registry.values())


def get_site_overlay(name: str | None) -> 'SiteOverlay | None':
    """
    One colouring by name, or None where nothing answers to it.

    A link carrying a colouring a later release removed must open the map rather than fail, so
    the caller falls back rather than this raising.
    """
    return _registry.get(name) if name else None


def register_builtin_site_overlays(names: list[str] | None = None) -> None:
    """
    Register the built-in site colourings, all of them or the named subset.

    An unrecognised name is logged and skipped rather than raised, so a typo in the plugin
    configuration cannot stop NetBox from booting.
    """
    if names is None:
        names = list(BUILTIN_SITE_OVERLAYS)
    for name in names:
        if name not in BUILTIN_SITE_OVERLAYS:
            logger.warning(f'Unknown built-in site overlay "{name}"; skipped.')
            continue
        label, fn, description = BUILTIN_SITE_OVERLAYS[name]
        register_site_overlay(name, label, fn, description=description)

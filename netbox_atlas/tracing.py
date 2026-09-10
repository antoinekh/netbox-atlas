"""
Following a path end to end.

A cable is one hop. The question a reviewer actually has is where a link ends up: through the
patch panel, across the rack, out to the provider. NetBox already models that as a CablePath
and exposes it as `termination.trace()`, which returns the path as (A terminations, cables, B
terminations) triples and handles pass-through ports, bridges and circuits.

A power chain is the same thing starting from a power port: outlet, PDU, feed, panel. There is
no second mechanism here, which is the point of this module being one file rather than two.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from django.apps import apps

from netbox_atlas.cabling import RESTRICTED_LABEL, kind_of

__all__ = (
    'Hop',
    'Trace',
    'trace_from',
)

# What the far end of a path can be, in the order a reader meets it. Used only to describe a
# hop, never to decide whether to follow it.
ENDPOINT_LABELS = {
    'powerfeed': 'Power feed',
    'powerpanel': 'Power panel',
    'circuittermination': 'Circuit',
    'providernetwork': 'Provider network',
    'frontport': 'Front port',
    'rearport': 'Rear port',
}


@dataclass
class Hop:
    """
    One step along a path: what it leaves, over which cable, and what it reaches.
    """

    index: int
    from_label: str
    from_device: str
    to_label: str
    to_device: str
    cable_label: str
    cable_id: int | None
    device_id: int | None
    rack_id: int | None
    rack_label: str
    kind: str

    @property
    def crosses_rack(self) -> bool:
        return bool(self.rack_label)


@dataclass
class Trace:
    origin_label: str
    origin_device: str
    hops: list
    complete: bool
    reaches: str

    @property
    def length(self) -> int:
        return len(self.hops)


def _always(obj: Any) -> bool:
    return True


def _describe(termination: Any, shown: Callable[[Any], bool] = _always) -> tuple[str, str]:
    """
    A termination as two strings: what it is, and what it is part of.

    Splitting them lets the panel show the device once and the port beside it, rather than
    repeating a long "device / interface" on every line. A termination or a device the reader
    may not see is named `RESTRICTED_LABEL` and nothing more.
    """
    if termination is None:
        return '', ''
    device = getattr(termination, 'device', None)
    if not shown(termination) or (device is not None and not shown(device)):
        return RESTRICTED_LABEL, ''
    if device is not None:
        return str(termination), str(device)

    # Not on a device: a power feed, a circuit termination, a provider network. The model name
    # is the useful half, because the object's own string is often just an identifier.
    model = termination._meta.model_name
    return str(termination), ENDPOINT_LABELS.get(model, termination._meta.verbose_name.title())


def _visibility(objects: Iterable[Any], user) -> Callable[[Any], bool]:
    """
    Whether the reader may see each of `objects`, in one query per model.

    A path crosses other devices, other racks, circuits and power feeds, and none of them is
    the object the reader asked to trace. Each is checked against the reader's own permissions
    so the trace panel names only what the rest of NetBox would show them.
    """
    if user is None:
        return _always

    by_model: dict[type, set[int]] = defaultdict(set)
    for obj in objects:
        if obj is not None:
            by_model[type(obj)].add(obj.pk)

    visible: set[tuple[type, int]] = set()
    for model, pks in by_model.items():
        for pk in model.objects.restrict(user, 'view').filter(pk__in=pks).values_list('pk', flat=True):
            visible.add((model, pk))
    return lambda obj: obj is None or (type(obj), obj.pk) in visible


def trace_from(termination_type: str, termination_id: int, user=None) -> Trace | None:
    """
    The full path leaving one termination.

    `termination_type` is `app_label.modelname`, which is how the page names it, so a caller
    never has to import the model. An unknown type or a missing object returns None rather
    than raising: a stale link should be answered with "nothing to show", not a 500.

    `user` is the reader. The starting termination must be one they may view, or the answer is
    None as for a missing one; every object along the path is then named only if they may view
    it. None reads everything, for a shell or a command where there is no user.

    A path that ends at a pass-through port nobody has cabled onward is reported as incomplete
    rather than as reaching that port. That is the difference between "this run ends at panel
    port 12" and "this run ends, and panel port 12 is where it stops", and only the second is
    honest about an undocumented remainder.
    """
    try:
        model = apps.get_model(termination_type)
    except (LookupError, ValueError):
        return None

    queryset = model.objects.all()
    if user is not None and hasattr(queryset, 'restrict'):
        queryset = queryset.restrict(user, 'view')
    termination = queryset.filter(pk=termination_id).first()
    if termination is None or not hasattr(termination, 'trace'):
        return None

    raw = list(termination.trace())

    # NetBox's own trace stops at a PDU's outlet. Following the outlet's inlet onward, and
    # again for a PDU fed by another PDU, is what turns "this server is plugged into socket 1"
    # into the power chain: socket, PDU, feed, panel. It is the one place this module does
    # more than call NetBox, and it is the reason the module exists.
    raw += _continue_through_pdus(raw)

    steps = []
    for a_terms, cables, b_terms in raw:
        near = a_terms[0] if a_terms else None
        far = b_terms[0] if b_terms else None
        cable = cables[0] if cables else None
        device = getattr(far, 'device', None)
        rack = getattr(device, 'rack', None) if device else None
        steps.append((near, far, cable, device, rack))

    shown = _visibility(
        [termination, getattr(termination, 'device', None)]
        + [obj for step in steps for obj in (*step[:4], getattr(step[0], 'device', None), step[4])],
        user,
    )
    origin_label, origin_device = _describe(termination, shown)

    hops, last_to = [], None
    for index, (near, far, cable, device, rack) in enumerate(steps, start=1):
        from_label, from_device = _describe(near, shown)
        to_label, to_device = _describe(far, shown)
        if not shown(device):
            device = rack = None
        if not shown(rack):
            rack = None
        if not shown(cable):
            cable = None

        hops.append(
            Hop(
                index=index,
                from_label=from_label,
                from_device=from_device,
                to_label=to_label,
                to_device=to_device,
                cable_label=str(cable) if cable else '',
                cable_id=cable.pk if cable else None,
                device_id=device.pk if device else None,
                rack_id=rack.pk if rack else None,
                rack_label=str(rack) if rack else '',
                kind=kind_of(far or near),
            )
        )
        if far is not None:
            last_to = far

    # A trace that produced no far end at all reached nothing: the port is cabled to something
    # NetBox cannot resolve, or the path is a stub.
    complete = last_to is not None and not _is_dead_end(last_to)
    reaches = ''
    if last_to is not None:
        label, owner = _describe(last_to, shown)
        reaches = f'{owner} · {label}' if owner else label

    return Trace(
        origin_label=origin_label,
        origin_device=origin_device,
        hops=hops,
        complete=complete,
        reaches=reaches,
    )


# A PDU chained into a PDU into a PDU is real but shallow. This bounds the walk so a
# mis-recorded outlet pointing back at its own inlet cannot loop for ever.
MAX_POWER_HOPS = 8


def _continue_through_pdus(raw: list) -> list:
    """
    The rest of a power chain, past the outlet NetBox's trace stops at.

    A PowerOutlet records the inlet it draws from as `power_port`. That link is not a cable,
    so a CablePath does not cross it, and a trace from a server therefore ends at the socket.
    Walking it here continues into the PDU, out of its inlet, and on to the feed and panel.

    Returns extra (A, cables, B) triples in the same shape as `trace()`, so the caller cannot
    tell which half came from where.
    """
    if not raw:
        return []

    extra = []
    seen = set()
    _, _, b_terms = raw[-1]
    current = b_terms[0] if b_terms else None

    for _ in range(MAX_POWER_HOPS):
        if current is None or current._meta.model_name != 'poweroutlet':
            break
        inlet = getattr(current, 'power_port', None)
        if inlet is None or inlet.pk in seen:
            break
        seen.add(inlet.pk)

        onward = list(inlet.trace())
        if not onward:
            break
        extra += onward
        _, _, b_terms = onward[-1]
        current = b_terms[0] if b_terms else None

    return extra


def _is_dead_end(termination: Any) -> bool:
    """
    Whether a path simply stops at an uncabled pass-through port.

    A front or rear port with nothing cabled onward is where documentation ran out, not where
    the link ends. Saying so is the difference between a trace you can trust and one that
    quietly presents a patch panel as a destination.
    """
    if termination._meta.model_name not in ('frontport', 'rearport'):
        return False
    return getattr(termination, 'cable_id', None) is None

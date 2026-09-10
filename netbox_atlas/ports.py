"""
The ports on a device, and how many are left.

Split out of the elevation because "what is in this rack" and "what is left in it" are asked
by different parts of the page: the drawing wants a tick per port, the allocation panel wants
a count per kind, and neither needs the other's shape.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from dcim.models import (
    ConsolePort,
    ConsoleServerPort,
    FrontPort,
    Interface,
    PowerOutlet,
    PowerPort,
    RearPort,
)

__all__ = (
    'PORT_MODELS',
    'Port',
    'PortGroup',
    'PortTick',
    'load_ports',
    'rack_allocation',
)


@dataclass
class PortTick:
    """
    One port as drawn: identity plus the rectangle it occupies.
    """

    name: str
    cable_id: int | None
    connected: bool
    colour: str
    x: float
    y: float
    w: float
    termination_type: str = ''
    termination_id: int | None = None


@dataclass
class Port:
    """
    One termination on a device, as drawn.

    `cable_id` is what ties a port tick to a cable line and to a row in the list, so clicking
    any one of the three can highlight the other two.
    """

    name: str
    kind: str
    cable_id: int | None
    termination_type: str = ''
    termination_id: int | None = None

    @property
    def connected(self) -> bool:
        return self.cable_id is not None


@dataclass
class PortGroup:
    """
    A device's ports of one kind, with how many are in use.

    Grouped by kind rather than listed flat because "how many ports are left" is asked per
    kind: free RJ45s do not help when you need an SFP cage.
    """

    kind: str
    label: str
    ports: list

    @property
    def total(self) -> int:
        return len(self.ports)

    @property
    def connected(self) -> int:
        return sum(1 for p in self.ports if p.connected)

    @property
    def free(self) -> int:
        return self.total - self.connected

    @property
    def percent(self) -> float:
        return self.connected / self.total * 100 if self.total else 0


PORT_MODELS = (
    (Interface, 'interface', 'Interfaces'),
    (FrontPort, 'passthrough', 'Front ports'),
    (RearPort, 'passthrough', 'Rear ports'),
    (ConsolePort, 'console', 'Console ports'),
    (ConsoleServerPort, 'console', 'Console server ports'),
    (PowerPort, 'power', 'Power ports'),
    (PowerOutlet, 'power', 'Power outlets'),
)


def load_ports(device_ids: Iterable[int]) -> dict[int, list[PortGroup]]:
    """
    Every port on every device in the rack, in one query per port model.

    Seven queries for a whole rack, rather than seven per device. A rack of twelve switches
    with forty-eight ports each is nearly six hundred ports, and asking per device turned the
    page into a hundred queries for the same answer.
    """
    by_device = {pk: [] for pk in device_ids}
    for model, kind, label in PORT_MODELS:
        label_path = f'{model._meta.app_label}.{model._meta.model_name}'
        rows = model.objects.filter(device_id__in=device_ids).values_list('device_id', 'name', 'cable_id', 'pk')
        grouped = {}
        for device_id, name, cable_id, pk in rows:
            grouped.setdefault(device_id, []).append(
                Port(
                    name=name,
                    kind=kind,
                    cable_id=cable_id,
                    termination_type=label_path,
                    termination_id=pk,
                )
            )
        for device_id, ports in grouped.items():
            by_device[device_id].append(PortGroup(kind=kind, label=label, ports=ports))
    return by_device


def rack_allocation(elevation) -> list[PortGroup]:
    """
    Every port in the rack, added up by kind.

    This is the panel's resting state: "what is left in this room" before anybody has selected
    anything. Selecting a device narrows it to that device, which the page already holds.
    """
    merged = {}
    for mounted in elevation.mounted:
        for group in mounted.port_groups:
            key = (group.kind, group.label)
            merged.setdefault(key, []).extend(group.ports)
    return [PortGroup(kind=kind, label=label, ports=ports) for (kind, label), ports in merged.items()]

"""
The inside of a rack, as a drawing.

NetBox already draws a rack elevation. This one exists because it has to carry the cabling as
well: where each link leaves a device, whether it stays in the rack, and where it goes if it
does not. That is the question the elevation on the rack page cannot answer.

What a device holds and what it draws are not this module's business. Ports live in `ports`,
power in `power`, and cables in `cabling`; this assembles their answers into positions. The
arithmetic that decides where a device sits stays here, and is a pure function, so it tests
without a browser.
"""

from dataclasses import dataclass, field

from dcim.models import Device

from netbox_atlas.cabling import CABLE_KIND_COLOURS, build_runs, fan_exits
from netbox_atlas.palette import NO_ROLE
from netbox_atlas.ports import PortTick, load_ports
from netbox_atlas.power import load_device_power

__all__ = (
    'FreeBand',
    'MountedDevice',
    'RackElevation',
    'build_elevation',
    'rack_summary',
    'unit_y',
)

# rack is RACK_WIDTH wide, so the SVG viewBox is a fixed shape whatever the rack's real size.
# Chosen so the drawing renders at roughly one viewBox unit per pixel in the column it sits
# in. That is what makes it crisp: at any other scale a 1-unit rule lands on a fraction of a
# pixel and is drawn as a two-pixel smudge, and text picks up the same softness. The absolute
# numbers mean nothing on their own; their ratio to the rendered width is the point.
UNIT_HEIGHT = 15
RACK_WIDTH = 150
# The channel down the right-hand side that cables are routed in, as net3d does.
CHANNEL_WIDTH = 90
# Space between the front and rear cabinets, wide enough to read as two objects.
FACE_GAP = 24
# How far into the channel an exit stub leans before it runs straight out. A device's
# cables all start on its own row, so the lean is what separates them; putting the bend
# here rather than at the cabinet edge keeps most of each stub a horizontal line.
EXIT_BEND = 26

NO_ROLE_COLOUR = NO_ROLE

# The strip of port ticks along the bottom of a device, in drawing units.
PORT_STRIP_X = 5
PORT_STRIP_WIDTH = RACK_WIDTH - 10
# Below this a tick cannot be told from its neighbour, so drawing one per port stops being
# information and becomes texture. A 48-port switch clears it; a 300-port chassis does not.
MIN_PORT_WIDTH = 2.0


@dataclass
class MountedDevice:
    """
    One device in the rack, positioned in drawing units.
    """

    device: object
    y: float
    height: float
    colour: str
    face: str
    # Which side this drawing of the device is on. A full-depth device is drawn twice, once
    # per side, and both carry the same device id so selecting either lights up both.
    side: str = 'front'
    # Ports are drawn once, on the side the device is mounted on. NetBox does not record
    # which face an interface is on, so putting the same ports on both sides would be
    # inventing a fact rather than showing one.
    show_ports: bool = True
    port_groups: list = field(default_factory=list)

    @property
    def ports(self) -> list:
        return [p for group in self.port_groups for p in group.ports]

    @property
    def summarised_ports(self) -> bool:
        """
        Whether this device has too many ports to draw one at a time.
        """
        ports = self.ports
        if not ports:
            return False
        return (PORT_STRIP_WIDTH - 0.8 * (len(ports) - 1)) / len(ports) < MIN_PORT_WIDTH

    @property
    def port_layout(self) -> list[PortTick]:
        """
        Where each port tick is drawn, along the bottom edge of the device.

        Computed here rather than in the browser so a port lines up with the cable leaving it
        without the page measuring itself, and so the same numbers serve the API.

        Past the width where ticks stop being distinguishable they are replaced by two bands,
        connected and free, in proportion. That is an honest "too many to show" rather than a
        row of slivers pretending to be countable, and it takes a 575-port rack from as many
        rectangles to a couple of dozen. Tracing an individual port is still available from
        the cabling list, which is where you would look for one by name anyway.
        """
        ports = self.ports
        if not ports:
            return []

        y = self.y + self.height - 4
        if not self.summarised_ports:
            gap = 0.8
            width = (PORT_STRIP_WIDTH - gap * (len(ports) - 1)) / len(ports)
            return [
                PortTick(
                    name=port.name,
                    cable_id=port.cable_id,
                    connected=port.connected,
                    colour=CABLE_KIND_COLOURS[port.kind],
                    x=PORT_STRIP_X + index * (width + gap),
                    y=y,
                    w=width,
                    termination_type=port.termination_type,
                    termination_id=port.termination_id,
                )
                for index, port in enumerate(ports)
            ]

        connected = [p for p in ports if p.connected]
        used = PORT_STRIP_WIDTH * len(connected) / len(ports)
        kind = connected[0].kind if connected else ports[0].kind
        bands = []
        if used:
            bands.append(
                PortTick(
                    name=f'{len(connected)} of {len(ports)} ports connected',
                    cable_id=None,
                    connected=True,
                    colour=CABLE_KIND_COLOURS[kind],
                    x=PORT_STRIP_X,
                    y=y,
                    w=used,
                )
            )
        if used < PORT_STRIP_WIDTH:
            bands.append(
                PortTick(
                    name=f'{len(ports) - len(connected)} free of {len(ports)}',
                    cable_id=None,
                    connected=False,
                    colour='',
                    x=PORT_STRIP_X + used,
                    y=y,
                    w=PORT_STRIP_WIDTH - used,
                )
            )
        return bands

    @property
    def connected_count(self) -> int:
        return sum(g.connected for g in self.port_groups)

    @property
    def port_count(self) -> int:
        return sum(g.total for g in self.port_groups)

    # Power, filled in alongside the ports. A device's draw is the question asked of it
    # second, right after what it is cabled to, and NetBox puts the answer on a different
    # page from the elevation.
    power: object = None
    # What the device colouring said about this device, kept whole so the legend can be built
    # from the distinct answers on this rack.
    value: object = None
    # The legend band this device falls in, as the key the legend picks it by.
    band: str = ''
    # The device's value for each custom field offered as a filter (see `field_filters`).
    field_cells: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.device.name or f'{self.device.device_type} (unnamed)'

    @property
    def centre_y(self) -> float:
        return self.y + self.height / 2


@dataclass
class RackElevation:
    """
    Everything one drawing of a rack needs.
    """

    rack: object
    units: int
    height: float
    width: float = RACK_WIDTH
    channel: float = CHANNEL_WIDTH
    devices: list = field(default_factory=list)
    rear_devices: list = field(default_factory=list)
    reservations: list = field(default_factory=list)
    runs: list = field(default_factory=list)
    unplaced: list = field(default_factory=list)
    # How the rack's units are spoken for: mounted, reserved, or free, counted the way NetBox
    # counts them for its own utilisation figure so the header and that percentage cannot
    # disagree. Filled in by build_elevation, which already has the available units in hand.
    space: dict = field(default_factory=dict)
    # Runs of consecutive free units, as bands. The empty two thirds of a half-filled cabinet
    # used to be drawn as nothing at all, which is the one thing a rack drawing is asked about
    # most: what will fit.
    free: list = field(default_factory=list)

    @property
    def mounted(self) -> list:
        """
        One drawing per mounted device, whichever face it is on.

        `devices` holds the front drawings and `rear_devices` the rear ones, so a full-depth
        device is in both and a half-depth device on the rear is only in the second. Anything
        that counts, colours or lists devices rather than drawing a face reads this, or the
        rear-mounted ones drop out of it.
        """
        front = {m.device.pk for m in self.devices}
        return self.devices + [m for m in self.rear_devices if m.device.pk not in front]

    # Where the rear cabinet and the cable channel start, in drawing units.
    @property
    def rear_x(self) -> float:
        return self.width + FACE_GAP

    @property
    def channel_x(self) -> float:
        return self.rear_x + self.width

    @property
    def exit_bend(self) -> float:
        return EXIT_BEND

    @property
    def total_width(self) -> float:
        return self.channel_x + self.channel

    @property
    def unit_labels(self) -> list[tuple[int, float]]:
        """
        The U number and y position of every unit, for the ruler down the left.
        """
        return [(self.rack.starting_unit + i, self._unit_y(self.rack.starting_unit + i)) for i in range(self.units)]

    def _unit_y(self, unit):
        return unit_y(self.rack, unit, 1)


def unit_y(rack, position: float, u_height: float) -> float:
    """
    The top edge of a device, in drawing units.

    A rack is numbered from the bottom by default, so U1 is drawn last. `desc_units` inverts
    that, which is how some vendors label a cabinet, and getting it wrong silently draws every
    device upside down in the rack.
    """
    offset = position - rack.starting_unit
    if rack.desc_units:
        return offset * UNIT_HEIGHT
    return (rack.u_height - offset - u_height) * UNIT_HEIGHT


def _role_colour(device) -> str:
    role = getattr(device, 'role', None)
    return f'#{role.color}' if role and role.color else NO_ROLE_COLOUR


def _draw_device(rack, device, u_height: float, face: str, side: str) -> 'MountedDevice':
    """
    One drawing of one device, on one side of the cabinet.

    A module-level function rather than a closure inside the loop: a closure would capture the
    loop variables by reference, which is correct only because it happens to be called at once,
    and is the kind of thing that breaks silently the moment the call is deferred.
    """
    return MountedDevice(
        device=device,
        y=unit_y(rack, float(device.position), u_height),
        height=u_height * UNIT_HEIGHT,
        colour=_role_colour(device),
        face=face,
        side=side,
        # Ports go on the side the device is mounted on. NetBox does not record which face an
        # interface is on, so putting the same ports on both sides would invent a fact.
        show_ports=face == side,
    )


@dataclass
class ReservedBand:
    """
    A run of consecutive reserved units, as one band.

    NetBox records a reservation as a list of unit numbers, which would draw as a stack of
    separate stripes for what is really one claim. Merging the consecutive ones back into a
    band is how a reader sees "U20 to U21 is spoken for" rather than counting stripes.
    """

    reservation: object
    y: float
    height: float
    first_unit: int
    last_unit: int

    @property
    def label(self) -> str:
        span = (
            f'U{self.first_unit}' if self.first_unit == self.last_unit else f'U{self.first_unit}\u2013U{self.last_unit}'
        )
        return f'{span} reserved'


def _build_reservations(rack) -> list[ReservedBand]:
    """
    The reserved units of a rack, merged into bands.

    Reserved space is the one thing a rack drawing can be wrong about in a way that costs
    money: a unit that is claimed, or damaged, looks exactly like a free one, and somebody
    plans a device into it. `Rack.get_utilization()` already counts these as used, so leaving
    them out of the drawing made the picture disagree with the number beside it.
    """
    reserved = rack.get_reserved_units()
    if not reserved:
        return []

    bands, run = [], []
    for unit in sorted(reserved):
        if run and unit == run[-1] + 1 and reserved[unit] == reserved[run[-1]]:
            run.append(unit)
            continue
        if run:
            bands.append(run)
        run = [unit]
    if run:
        bands.append(run)

    out = []
    for units in bands:
        first, last = units[0], units[-1]
        # unit_y measures to the top of a device of the given height, which for a band is the
        # whole run, so the same call places it whichever way the rack is numbered.
        out.append(
            ReservedBand(
                reservation=reserved[first],
                y=unit_y(rack, first, len(units)),
                height=len(units) * UNIT_HEIGHT,
                first_unit=first,
                last_unit=last,
            )
        )
    return out


@dataclass
class FreeBand:
    """
    A run of consecutive empty units, as one band.

    Named with its own height, so "will a 4U chassis go in" is answered by reading rather than
    by counting rungs against the ruler. A single free unit is drawn but not labelled: there is
    no room for the text and "1U" beside a 1U gap says nothing the gap has not already said.
    """

    y: float
    height: float
    first_unit: float
    units: float

    @property
    def label(self) -> str:
        return f'{self.units:g}U free' if self.units >= 2 else ''

    @property
    def centre_y(self) -> float:
        return self.y + self.height / 2


def _measure_space(rack, reservations) -> tuple[dict, list['FreeBand']]:
    """
    What is used, what is reserved, what is left, and where the gaps are.

    One walk for both answers. NetBox works in half units: a 48U rack has 96 of them, and a
    device can sit on a half, so counting whole units instead reported 51 free of 48. The
    arithmetic below is NetBox's own from `Rack.get_utilization`, divided back into whole units
    at the end.
    """
    from utilities.data import drange

    # Cast: NetBox returns these as Decimal, and mixing one with the 0.5 step below raises
    # rather than comparing.
    available = {float(unit) for unit in rack.get_available_units(u_height=0.5, ignore_excluded_devices=True)}
    reserved_halves = set()
    for band in reservations:
        for unit in range(band.first_unit, band.last_unit + 1):
            for half in drange(unit, unit + 1, 0.5):
                half = float(half)
                if half in available:
                    available.discard(half)
                    reserved_halves.add(half)

    total_halves = len(list(rack.units))
    space = {
        'total': rack.u_height,
        'free': len(available) / 2,
        'reserved': len(reserved_halves) / 2,
        'used': (total_halves - len(available) - len(reserved_halves)) / 2,
    }

    # Consecutive free halves, merged into bands. Sorted low to high whichever way the cabinet
    # is numbered; `unit_y` places each band correctly from its first unit and its height.
    bands, run = [], []
    for half in sorted(available):
        if run and abs(half - run[-1] - 0.5) < 1e-6:
            run.append(half)
            continue
        if run:
            bands.append(run)
        run = [half]
    if run:
        bands.append(run)

    free = [
        FreeBand(
            y=unit_y(rack, halves[0], len(halves) / 2),
            height=len(halves) / 2 * UNIT_HEIGHT,
            first_unit=halves[0],
            units=len(halves) / 2,
        )
        for halves in bands
    ]
    return space, free


def build_elevation(rack, devices_queryset=None) -> 'RackElevation':
    """
    Lay out a rack and the cables leaving it.

    Cables are read once for the whole rack rather than per device. A rack of forty servers
    with two links each is eighty cables, and asking per device turned that into eighty
    queries for an answer one query gives.

    `devices_queryset` is what the reader may see, and the view passes its own restricted one.
    A user allowed the rack but not its contents should get the cabinet and its free space, not
    an inventory of the machines in it.
    """
    base = Device.objects.all() if devices_queryset is None else devices_queryset
    devices = list(
        base.filter(rack=rack)
        .select_related('role', 'device_type', 'device_type__manufacturer', 'tenant')
        # For the Tags finder, in one query for the rack.
        .prefetch_related('tags')
        .order_by('position')
    )

    mounted, rear, unplaced = [], [], []
    for device in devices:
        if device.position is None:
            # A device in the rack but not mounted at a U, which is normal for a
            # child device in a chassis or for something simply not recorded yet.
            unplaced.append(device)
            continue
        u_height = float(device.device_type.u_height or 1)
        face = device.face or 'front'
        full_depth = bool(device.device_type.is_full_depth)

        # A full-depth device occupies both sides of the cabinet, so it is drawn on both.
        # A half-depth one shows on its mounted face only, and the other side is genuinely
        # free space there: drawing it on both would hide exactly the room you are looking
        # for when you ask what will fit.
        if face == 'front' or full_depth:
            mounted.append(_draw_device(rack, device, u_height, face, 'front'))
        if face == 'rear' or full_depth:
            rear.append(_draw_device(rack, device, u_height, face, 'rear'))

    every = mounted + rear
    ports_by_device = load_ports({m.device.pk for m in every})
    power_by_device = load_device_power(list({m.device.pk: m.device for m in every}.values()))
    for m in every:
        m.port_groups = ports_by_device.get(m.device.pk, [])
        m.power = power_by_device.get(m.device.pk)

    y_by_device = {m.device.pk: m.centre_y for m in every}
    runs = build_runs(rack, devices, y_by_device, devices_queryset=devices_queryset)
    fan_exits(runs, rack.u_height * UNIT_HEIGHT)

    reservations = _build_reservations(rack)
    space, free = _measure_space(rack, reservations)

    return RackElevation(
        rack=rack,
        units=rack.u_height,
        height=rack.u_height * UNIT_HEIGHT,
        devices=mounted,
        rear_devices=rear,
        reservations=reservations,
        runs=runs,
        unplaced=unplaced,
        space=space,
        free=free,
    )


def rack_summary(elevation: 'RackElevation') -> list:
    """
    The headline figures for a rack, above the drawing.

    What is in it, what is left, what is wired and what it draws. All four had been on the page
    already, spread between a line of muted text above the cabinet, a badge on a card halfway
    down, and a panel you had to select a device to see; a reader wanting to know whether this
    cabinet had room walked away with none of them.

    Costs nothing: everything here has already been resolved to draw the elevation.
    """
    from netbox_atlas.overlays import Stat
    from netbox_atlas.palette import utilisation_colour

    space = elevation.space
    total = space.get('total') or 0
    free = space.get('free') or 0
    reserved = space.get('reserved') or 0
    percent = (total - free) / total * 100 if total else 0

    # The tallest gap, because "30U free" spread over ten gaps of three will not take a 4U
    # chassis and the single number says it will.
    largest = max((band.units for band in elevation.free), default=0)

    external = sum(1 for run in elevation.runs if not run.internal)
    mounted = elevation.mounted
    connected = sum(m.connected_count for m in mounted)
    ports = sum(m.port_count for m in mounted)

    stats = [
        Stat(
            label='Devices',
            value=str(len(mounted)),
            detail=f'{len(elevation.unplaced)} with no U recorded'
            if elevation.unplaced
            else f'{elevation.rack.u_height}U cabinet',
        ),
        Stat(
            label='Free space',
            value=f'{free:g}U',
            detail=f'largest gap {largest:g}U' + (f', {reserved:g}U reserved' if reserved else ''),
            tone=utilisation_colour(percent),
        ),
        Stat(
            label='Cabling',
            value=str(len(elevation.runs)),
            detail=f'{external} leaving the rack' if external else 'none leaving the rack',
        ),
        Stat(
            label='Free ports',
            value=f'{ports - connected}' if ports else '—',
            detail=f'of {ports}, {connected} connected' if ports else 'none recorded',
        ),
    ]
    return stats

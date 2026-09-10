"""
Put a site's racks on a floor, so there is something to look at.

An empty floor draws nothing, and placing forty racks by hand before you can judge whether the
view is any use is the wrong order. This lays them out in rows by location and leaves the
operator to drag them into the real room.

It is a bootstrap aid for a demo or development database, not a production tool: it invents a
room that does not exist, and a plan whose whole value is that it matches the real room is
worth nothing when it was generated. It never runs on its own, and it never moves a rack
somebody has already placed.
"""

from dcim.models import Rack, Site
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from netbox_atlas.choices import MeasurementUnitChoices
from netbox_atlas.geometry import autoplace_racks, rack_footprint_cm
from netbox_atlas.models import CM_PER_UNIT, Floor, RackPlacement


class Command(BaseCommand):
    help = (
        'Create a floor per site and lay its unplaced racks out in rows. '
        'A bootstrap aid for a demo or development database: it invents a room that does not exist, '
        'so do not run it against production. See docs/development.md.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'sites',
            nargs='*',
            help='Site slugs. Every site with racks, if none are named.',
        )
        parser.add_argument(
            '--width',
            type=float,
            default=30,
            help='Floor width in metres for a floor this command creates (default: 30).',
        )
        parser.add_argument(
            '--depth',
            type=float,
            default=20,
            help='Floor depth in metres for a floor this command creates (default: 20).',
        )
        parser.add_argument(
            '--per-location',
            action='store_true',
            help=(
                'One floor per location rather than one per site. A site whose racks live in '
                'named rows or halls is several rooms, and a rack stands on only one floor.'
            ),
        )
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Move racks that are already placed. Off by default, so a hand-made layout survives.',
        )

    def handle(self, *args, **options):
        sites = Site.objects.filter(slug__in=options['sites']) if options['sites'] else Site.objects.all()
        if options['sites'] and sites.count() != len(options['sites']):
            found = set(sites.values_list('slug', flat=True))
            missing = ', '.join(sorted(set(options['sites']) - found))
            raise CommandError(f'No such site: {missing}')

        total_placed = 0
        for site in sites:
            racks = Rack.objects.filter(site=site).select_related('location').order_by('location', 'name')
            if not racks.exists():
                continue
            for location, room in self._rooms(racks, options['per_location']):
                total_placed += self._place(site, location, room, options)

        if not total_placed:
            self.stdout.write('Nothing to place.')

    def _rooms(self, racks, per_location: bool) -> list[tuple]:
        """
        The rooms to draw for one site, as the location each binds to and the racks in it.

        `None` is the site itself: every rack by default, and under --per-location the racks
        that name no location. Those still have to go somewhere, and the site is the only
        place left that is true of them.
        """
        if not per_location:
            return [(None, racks)]
        return [
            (location, racks.filter(location=location)) for location in dict.fromkeys(rack.location for rack in racks)
        ]

    def _place(self, site, location, racks, options) -> int:
        """
        Lay one room out. Returns how many racks it placed.
        """
        room = location or site
        floor, created = Floor.objects.get_or_create(
            site=None if location else site,
            location=location,
            name=f'{room.name} floor',
            defaults={
                'width': options['width'],
                'depth': options['depth'],
                'unit': MeasurementUnitChoices.METRES,
                'description': 'Created by atlas_autoplace. Drag the racks to match the room.',
            },
        )
        self.stdout.write(f'{room}: floor "{floor.name}" ({"created" if created else "existing"})')

        if not options['replace']:
            racks = racks.filter(atlas_placement__isnull=True)
        if not racks.exists():
            self.stdout.write('  every rack is already placed')
            return 0

        racks = list(racks)
        positions = autoplace_racks(racks, floor)

        with transaction.atomic():
            for rack, x, y in positions:
                RackPlacement.objects.update_or_create(
                    rack=rack,
                    defaults={'floor': floor, 'x': round(x, 1), 'y': round(y, 1), 'rotation': 0},
                )
            # Shrink a floor this command created to fit what it laid out. The default
            # room is deliberately generous so the layout has space to run into, which
            # leaves a small site drawn as a few racks marooned in a hall. A floor
            # somebody else made is left alone: its size is a statement about the real
            # room, not a frame around the drawing.
            if created and positions:
                self._fit_floor(floor, positions)

        skipped = len(racks) - len(positions)
        self.stdout.write(self.style.SUCCESS(f'  placed {len(positions)} rack(s)'))
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    f'  {skipped} did not fit in {floor.width}x{floor.depth}{floor.unit}; '
                    f're-run with a larger --width or --depth'
                )
            )
        return len(positions)

    def _fit_floor(self, floor, positions, margin_cm=150):
        """
        Resize a newly created floor to the bounding box of what was laid out.

        Measured to the far edge of each rack rather than to its centre, so a rack is never
        left half outside the room it was just put in.
        """
        right = max(x + rack_footprint_cm(rack)[0] / 2 for rack, x, _ in positions)
        bottom = max(y + rack_footprint_cm(rack)[1] / 2 for rack, _, y in positions)

        per_unit = CM_PER_UNIT[floor.unit]
        floor.width = round((right + margin_cm) / per_unit, 2)
        floor.depth = round((bottom + margin_cm) / per_unit, 2)
        floor.save()
        self.stdout.write(f'  sized the floor to {floor.width} x {floor.depth} {floor.unit}')

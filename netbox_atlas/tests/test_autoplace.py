"""
The bootstrap command that puts a site's racks on a floor.

The interesting case is a site with several rooms. A floor binds to a site or to a location,
never both, and a rack stands on at most one floor, so a site whose racks live in named
locations wants a floor per location rather than one hall holding all of them.
"""

from dcim.models import Location
from django.core.management import call_command

from netbox_atlas.models import Floor, RackPlacement
from netbox_atlas.tests.base import AtlasTestCase, make_rack


class AutoplaceTest(AtlasTestCase):
    def setUp(self):
        self.row1 = Location.objects.create(site=self.site, name='Row 1', slug='row-1')
        self.row2 = Location.objects.create(site=self.site, name='Row 2', slug='row-2')
        self.a = make_rack(self.site, name='A', location=self.row1)
        self.b = make_rack(self.site, name='B', location=self.row2)
        self.loose = make_rack(self.site, name='C')

    def _floor_of(self, rack):
        return RackPlacement.objects.get(rack=rack).floor

    def test_one_floor_holds_the_whole_site_by_default(self):
        call_command('atlas_autoplace', 'test-site', verbosity=0)
        floors = Floor.objects.all()
        self.assertEqual(floors.count(), 1)
        self.assertIsNone(floors.first().location)
        self.assertEqual({self._floor_of(r) for r in (self.a, self.b, self.loose)}, {floors.first()})

    def test_per_location_gives_each_room_its_own_floor(self):
        call_command('atlas_autoplace', 'test-site', per_location=True, verbosity=0)
        self.assertEqual(self._floor_of(self.a).location, self.row1)
        self.assertEqual(self._floor_of(self.b).location, self.row2)
        self.assertNotEqual(self._floor_of(self.a), self._floor_of(self.b))

    def test_a_rack_in_no_location_stays_on_the_site(self):
        call_command('atlas_autoplace', 'test-site', per_location=True, verbosity=0)
        floor = self._floor_of(self.loose)
        self.assertIsNone(floor.location)
        self.assertEqual(floor.site, self.site)

    def test_a_floor_is_named_after_the_room_it_draws(self):
        call_command('atlas_autoplace', 'test-site', per_location=True, verbosity=0)
        self.assertEqual(self._floor_of(self.a).name, 'Row 1 floor')

    def test_running_it_twice_does_not_make_a_second_floor(self):
        call_command('atlas_autoplace', 'test-site', per_location=True, verbosity=0)
        call_command('atlas_autoplace', 'test-site', per_location=True, verbosity=0)
        self.assertEqual(Floor.objects.count(), 3)

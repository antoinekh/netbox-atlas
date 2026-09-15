"""
Footprints and the automatic layout.

Pure functions over the ORM, so they need no browser and no request.
"""

from netbox_spatial_lens.geometry import autoplace_racks, natural_key, rack_footprint_cm
from netbox_spatial_lens.tests.base import LensTestCase, make_floor, make_rack


class NaturalKeyTest(LensTestCase):
    def test_digits_sort_as_numbers(self):
        names = ['R10', 'R2', 'R1', 'R20', 'R3']
        self.assertEqual(
            sorted(names, key=natural_key),
            ['R1', 'R2', 'R3', 'R10', 'R20'],
        )

    def test_plain_string_sort_would_be_wrong(self):
        # The reason this function exists: without it R10 lands between R1 and R2.
        self.assertEqual(sorted(['R10', 'R2', 'R1']), ['R1', 'R10', 'R2'])

    def test_case_is_ignored(self):
        self.assertEqual(sorted(['b1', 'A2'], key=natural_key), ['A2', 'b1'])

    def test_an_unnamed_rack_does_not_raise(self):
        self.assertEqual(natural_key(None), [''])


class FootprintTest(LensTestCase):
    def test_millimetres_convert_to_centimetres(self):
        rack = make_rack(self.site, outer_width=600, outer_depth=1070, outer_unit='mm')
        width, depth, estimated = rack_footprint_cm(rack)
        self.assertEqual((width, depth), (60.0, 107.0))
        self.assertFalse(estimated)

    def test_inches_convert_too(self):
        rack = make_rack(self.site, outer_width=24, outer_depth=42, outer_unit='in')
        width, depth, _ = rack_footprint_cm(rack)
        self.assertAlmostEqual(width, 60.96, places=2)
        self.assertAlmostEqual(depth, 106.68, places=2)

    def test_a_rack_with_no_dimensions_is_reported_as_estimated(self):
        # The page states how many were estimated, so this flag must not be lost: a guess
        # presented as a measurement is the failure this guards against.
        _, _, estimated = rack_footprint_cm(make_rack(self.site))
        self.assertTrue(estimated)

    def test_a_half_measured_rack_still_counts_as_estimated(self):
        rack = make_rack(self.site, outer_width=600, outer_unit='mm')
        _, _, estimated = rack_footprint_cm(rack)
        self.assertTrue(estimated)


class AutoplaceTest(LensTestCase):
    def setUp(self):
        self.floor = make_floor(self.site, width=20, depth=20)

    def test_racks_are_laid_out_in_natural_order(self):
        racks = [make_rack(self.site, name=n) for n in ('R10', 'R2', 'R1')]
        placed = autoplace_racks(racks, self.floor)
        self.assertEqual([r.name for r, _, _ in placed], ['R1', 'R2', 'R10'])

    def test_x_increases_along_a_row(self):
        racks = [make_rack(self.site, name=f'R{i}') for i in (1, 2, 3)]
        xs = [x for _, x, _ in autoplace_racks(racks, self.floor)]
        self.assertEqual(xs, sorted(xs))
        self.assertEqual(len(set(xs)), 3)

    def test_a_second_location_starts_a_new_row(self):
        from dcim.models import Location

        room = Location.objects.create(site=self.site, name='Room B', slug='room-b')
        first = make_rack(self.site, name='A1')
        second = make_rack(self.site, name='B1', location=room)
        placed = {r.name: y for r, _, y in autoplace_racks([first, second], self.floor)}
        self.assertNotEqual(placed['A1'], placed['B1'])

    def test_the_aisle_is_wider_than_the_gap(self):
        # Two spacings, because a room has two. One number for both draws a grid of boxes.
        from dcim.models import Location

        room = Location.objects.create(site=self.site, name='Room B', slug='room-b')
        racks = [make_rack(self.site, name='A1'), make_rack(self.site, name='A2')]
        racks.append(make_rack(self.site, name='B1', location=room))
        placed = {r.name: (x, y) for r, x, y in autoplace_racks(racks, self.floor)}
        along_row = abs(placed['A2'][0] - placed['A1'][0])
        between_rows = abs(placed['B1'][1] - placed['A1'][1])
        self.assertGreater(between_rows, along_row)

    def test_racks_that_do_not_fit_are_left_out_rather_than_stacked(self):
        tiny = make_floor(self.site, name='Tiny', width=1, depth=1)
        racks = [make_rack(self.site, name=f'R{i}') for i in range(5)]
        self.assertEqual(autoplace_racks(racks, tiny), [])

    def test_a_row_wraps_at_the_wall(self):
        narrow = make_floor(self.site, name='Narrow', width=3, depth=20)
        racks = [make_rack(self.site, name=f'R{i:02}') for i in range(6)]
        placed = autoplace_racks(racks, narrow)
        self.assertGreater(len({y for _, _, y in placed}), 1)

"""
A device mounted on the rear face only is a device like any other, facing the other way.
"""

from django.urls import reverse

from netbox_spatial_lens.elevation import build_elevation, rack_summary
from netbox_spatial_lens.ports import rack_allocation
from netbox_spatial_lens.tests.base import make_device, make_rack
from netbox_spatial_lens.tests.test_views import ViewTestCase


class RearDeviceTest(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.rack = make_rack(self.site, u_height=10)
        self.rear = make_device(
            self.site,
            self.rack,
            'rear-srv',
            self.role,
            self.manufacturer,
            full_depth=False,
            face='rear',
            interfaces=2,
            power_ports=1,
        )

    def test_it_is_mounted_on_the_rear(self):
        elevation = build_elevation(self.rack)
        self.assertEqual([(m.device, m.face) for m in elevation.devices], [(self.rear, 'rear')])

    def test_it_is_counted(self):
        stats = {s.label: s for s in rack_summary(build_elevation(self.rack))}
        self.assertEqual(stats['Devices'].value, '1')
        self.assertIn('of 3', stats['Free ports'].detail)

    def test_its_ports_are_in_the_allocation(self):
        totals = {group.label: group.total for group in rack_allocation(build_elevation(self.rack))}
        self.assertEqual(totals.get('Interfaces'), 2)

    def test_its_power_is_loaded(self):
        mounted = build_elevation(self.rack).devices[0]
        self.assertIsNotNone(mounted.power)
        self.assertEqual(mounted.power.allocated_watts, 100)

    def test_the_rack_page_colours_and_lists_it(self):
        response = self.client.get(f'{reverse("dcim:rack_lens", args=[self.rack.pk])}?colour=status')
        self.assertEqual([m.device for m in response.context['elevation'].devices], [self.rear])
        self.assertEqual(sum(e.count for e in response.context['device_legend']), 1)
        self.assertContains(response, f'data-lens-alloc="{self.rear.pk}"')
        self.assertContains(response, f'data-lens-cabling="{self.rear.pk}"')

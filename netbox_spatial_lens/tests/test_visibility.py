"""
Traces, the API layout and the rack's cabling name only what the reader may see.
"""

from dcim.models import Device, Site
from django.test import TestCase
from django.urls import reverse
from utilities.testing import create_test_user

from netbox_spatial_lens.cabling import RESTRICTED_LABEL
from netbox_spatial_lens.elevation import build_elevation
from netbox_spatial_lens.tests.base import LensTestCase, cable, make_device, make_floor, make_rack, place
from netbox_spatial_lens.tests.test_views import grant
from netbox_spatial_lens.tracing import trace_from


class TraceVisibilityTest(LensTestCase):
    def setUp(self):
        self.rack = make_rack(self.site, u_height=10)
        self.a = make_device(self.site, self.rack, 'a', self.role, self.manufacturer, position=1, interfaces=1)
        self.b = make_device(self.site, self.rack, 'b', self.role, self.manufacturer, position=2, interfaces=1)
        cable(self.a.interfaces.first(), self.b.interfaces.first())
        self.user = create_test_user()
        grant(self.user, 'dcim.cable')
        grant(self.user, 'dcim.interface', constraints={'device__name': 'a'})
        grant(self.user, 'dcim.device', constraints={'name': 'a'})

    def test_a_port_the_reader_may_not_see_is_not_traced(self):
        self.assertIsNone(trace_from('dcim.interface', self.b.interfaces.first().pk, user=self.user))

    def test_a_hop_the_reader_may_not_see_is_not_named(self):
        trace = trace_from('dcim.interface', self.a.interfaces.first().pk, user=self.user)
        hop = trace.hops[0]
        self.assertEqual(hop.to_label, RESTRICTED_LABEL)
        self.assertEqual(hop.to_device, '')
        self.assertIsNone(hop.device_id)
        self.assertNotIn('b', trace.reaches.split())

    def test_the_view_answers_404_for_a_hidden_port(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('plugins:netbox_spatial_lens:trace', args=['dcim.interface', self.b.interfaces.first().pk])
        )
        self.assertEqual(response.status_code, 404)


class RackCablingVisibilityTest(LensTestCase):
    def test_a_peer_the_reader_may_not_see_is_not_named(self):
        rack = make_rack(self.site, u_height=10)
        server = make_device(self.site, rack, 'srv', self.role, self.manufacturer, position=1, interfaces=1)
        switch = make_device(self.site, rack, 'tor', self.switch_role, self.manufacturer, position=5, interfaces=1)
        cable(server.interfaces.first(), switch.interfaces.first())

        run = build_elevation(rack, devices_queryset=Device.objects.filter(pk=server.pk)).runs[0]
        self.assertEqual(run.peer_name, RESTRICTED_LABEL)
        self.assertIsNone(run.peer_device)
        self.assertFalse(run.internal)


class ApiLayoutVisibilityTest(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name='Site', slug='site')
        self.floor = make_floor(self.site, width=20, depth=20)
        place(self.floor, make_rack(self.site, name='MINE'), x=100, y=100)
        place(self.floor, make_rack(self.site, name='HIDDEN'), x=400, y=100)
        self.user = create_test_user()
        self.client.force_login(self.user)
        grant(self.user, 'netbox_spatial_lens.floor')
        grant(self.user, 'dcim.rack', constraints={'name': 'MINE'})

    def test_the_layout_holds_only_the_racks_the_reader_may_see(self):
        response = self.client.get(reverse('plugins-api:netbox_spatial_lens-api:floor-layout', args=[self.floor.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([rack['name'] for rack in response.json()['racks']], ['MINE'])


class WorldActionTest(LensTestCase):
    def test_a_site_with_no_floor_says_it_opens_the_site(self):
        from netbox_spatial_lens.world import build_world

        self.site.latitude, self.site.longitude = 51.5, -0.12
        self.site.save()
        node = next(n for n in build_world().nodes if n.object_id == self.site.pk)
        self.assertEqual(node.action, 'Open the site')
        self.assertEqual(node.url, reverse('dcim:site_lens', args=[self.site.pk]))

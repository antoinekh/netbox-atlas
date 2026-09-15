"""
Following a path end to end, including the power chain NetBox stops short of.
"""

from netbox_spatial_lens.tests.base import (
    LensTestCase,
    cable,
    make_device,
    make_rack,
    power_feed,
)
from netbox_spatial_lens.tracing import trace_from


class TraceTest(LensTestCase):
    def setUp(self):
        self.rack = make_rack(self.site, u_height=10)
        self.a = make_device(self.site, self.rack, 'a', self.role, self.manufacturer, position=1, interfaces=1)
        self.b = make_device(self.site, self.rack, 'b', self.role, self.manufacturer, position=2, interfaces=1)

    def test_an_unknown_type_returns_nothing_rather_than_raising(self):
        # A stale link should be answered with "nothing to show", not a 500.
        self.assertIsNone(trace_from('dcim.nosuchmodel', 1))

    def test_a_missing_object_returns_nothing(self):
        self.assertIsNone(trace_from('dcim.interface', 10_000_000))

    def test_an_uncabled_port_traces_to_nothing(self):
        trace = trace_from('dcim.interface', self.a.interfaces.first().pk)
        self.assertEqual(trace.hops, [])
        self.assertFalse(trace.complete)

    def test_a_cabled_port_reaches_its_peer(self):
        cable(self.a.interfaces.first(), self.b.interfaces.first())
        trace = trace_from('dcim.interface', self.a.interfaces.first().pk)
        self.assertEqual(trace.length, 1)
        self.assertTrue(trace.complete)
        self.assertIn('b', trace.reaches)


class PowerChainTest(LensTestCase):
    """
    The walk past the outlet, which is the one thing this module adds to NetBox's own trace.
    """

    def setUp(self):
        self.rack = make_rack(self.site, u_height=10)
        self.feed = power_feed(self.rack)
        self.pdu = make_device(
            self.site,
            self.rack,
            'pdu',
            self.switch_role,
            self.manufacturer,
            position=1,
            power_ports=1,
            outlets=1,
        )
        self.server = make_device(self.site, self.rack, 'srv', self.role, self.manufacturer, position=2, power_ports=1)

    def test_netbox_alone_stops_at_the_outlet(self):
        # Not a test of our code: it pins the upstream behaviour the continuation exists for,
        # so if NetBox ever walks the whole chain itself this fails and tells us to drop ours.
        cable(self.pdu.powerports.first(), self.feed)
        cable(self.server.powerports.first(), self.pdu.poweroutlets.first())
        hops = self.server.powerports.first().trace()
        self.assertEqual(len(hops), 1)

    def test_the_chain_continues_through_the_pdu_to_the_feed(self):
        cable(self.pdu.powerports.first(), self.feed)
        cable(self.server.powerports.first(), self.pdu.poweroutlets.first())
        trace = trace_from('dcim.powerport', self.server.powerports.first().pk)
        self.assertEqual(trace.length, 2)
        self.assertIn(self.feed.name, trace.reaches)

    def test_it_stops_at_the_outlet_when_the_pdu_is_not_fed(self):
        cable(self.server.powerports.first(), self.pdu.poweroutlets.first())
        trace = trace_from('dcim.powerport', self.server.powerports.first().pk)
        self.assertEqual(trace.length, 1)
        self.assertIn('outlet0', trace.reaches)

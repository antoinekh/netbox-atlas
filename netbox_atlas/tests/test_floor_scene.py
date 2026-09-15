"""
The floor in 3D: where each cabinet stands, which way it faces, and where the cabling runs.
"""

import math

from django.conf import settings
from django.test import override_settings
from django.urls import reverse

from netbox_atlas.floor_cabling import build_floor_exits, build_floor_runs
from netbox_atlas.floor_scene import RUN_RISE_MIN_MM, TRAY_ABOVE_MM, build_floor_scene
from netbox_atlas.layout import build_layout, resolve_overlay
from netbox_atlas.scene import PLINTH_MM, ROOF_MM, UNIT_MM
from netbox_atlas.tests.base import AtlasTestCase, cable, make_device, make_floor, make_rack, place
from netbox_atlas.tests.test_views import ViewTestCase, grant


def _plan_front(rotation_degrees: float) -> tuple[float, float]:
    """
    Which way the plan says a rack faces: its front bar is on the local -y edge, turned the way
    SVG's rotate() turns it on a page whose y runs down.
    """
    angle = math.radians(rotation_degrees)
    # rotate() maps (x, y) to (x cos - y sin, x sin + y cos); the front is (0, -1).
    return (math.sin(angle), -math.cos(angle))


class RackStandTest(AtlasTestCase):
    def setUp(self):
        self.floor = make_floor(self.site, width=10, depth=8)
        self.rack = make_rack(self.site, name='R1', u_height=42, outer_width=600, outer_depth=1200, outer_unit='mm')

    def _scene(self, overlay=None):
        return build_floor_scene(self.floor, build_layout(self.floor, overlay))

    def test_it_stands_where_the_plan_puts_it(self):
        place(self.floor, self.rack, x=250, y=400)
        rack = self._scene().racks[0]
        self.assertEqual((rack.x, rack.z), (2500.0, 4000.0))

    def test_its_footprint_is_the_racks(self):
        place(self.floor, self.rack)
        entry = self._scene().as_json()['racks'][0]
        self.assertEqual((entry['width'], entry['depth']), (600.0, 1200.0))

    def test_it_is_as_tall_as_in_the_rack_view(self):
        place(self.floor, self.rack)
        self.assertAlmostEqual(self._scene().racks[0].height, PLINTH_MM + 42 * UNIT_MM + ROOF_MM)

    def test_it_faces_the_way_the_plan_draws_its_front(self):
        # Every placement in the demo data has rotation 0, so this is the one check that a turned
        # rack does not face backwards in 3D.
        for rotation in (0, 45, 90, 180, 270):
            with self.subTest(rotation=rotation):
                placement = place(self.floor, self.rack, rotation=rotation)
                front = self._scene().racks[0].front
                expected = _plan_front(rotation)
                self.assertAlmostEqual(front[0], expected[0])
                self.assertAlmostEqual(front[1], expected[1])
                placement.delete()

    def test_the_json_turns_it_the_opposite_way_to_the_plan(self):
        place(self.floor, self.rack, rotation=90)
        self.assertAlmostEqual(self._scene().as_json()['racks'][0]['rotation'], -math.pi / 2, places=4)

    def test_a_quantity_colouring_carries_its_reading(self):
        place(self.floor, self.rack)
        make_device(self.site, self.rack, 'srv', self.role, self.manufacturer, u_height=21)
        entry = self._scene(resolve_overlay('space')).as_json()['racks'][0]
        self.assertAlmostEqual(entry['fraction'], 0.5)
        self.assertEqual(entry['gauge'], '50%')

    def test_a_named_colouring_has_no_reading(self):
        place(self.floor, self.rack)
        entry = self._scene(resolve_overlay('role')).as_json()['racks'][0]
        self.assertIsNone(entry['fraction'])

    def test_it_leads_into_the_rack(self):
        place(self.floor, self.rack)
        entry = self._scene().as_json()['racks'][0]
        self.assertEqual(entry['url'], reverse('dcim:rack_atlas', args=[self.rack.pk]))

    def test_it_carries_the_ids_the_finders_narrow_by(self):
        place(self.floor, self.rack)
        self.rack.tags.add('cold-aisle')
        self.assertEqual(self._scene().racks[0].filters['rack-tags'], 'cold-aisle')

    def test_the_room_is_in_millimetres(self):
        room = self._scene().as_json()['room']
        self.assertEqual((room['width'], room['depth']), (10000.0, 8000.0))
        self.assertGreater(room['step'], 0)


class FloorCablingTest(AtlasTestCase):
    def setUp(self):
        self.floor = make_floor(self.site, width=20, depth=20)
        self.near = make_rack(self.site, name='RA', u_height=42)
        self.far = make_rack(self.site, name='RB', u_height=24)
        place(self.floor, self.near, x=100, y=100)
        place(self.floor, self.far, x=700, y=100)
        self.a = make_device(self.site, self.near, 'a', self.role, self.manufacturer, interfaces=2)
        self.b = make_device(self.site, self.far, 'b', self.role, self.manufacturer, interfaces=2)

    def _scene(self):
        placed = build_layout(self.floor, None)
        return build_floor_scene(self.floor, placed, build_floor_runs(placed), build_floor_exits(placed, self.floor))

    def test_a_run_starts_and_ends_on_the_tops_of_its_racks(self):
        cable(self.a.interfaces.all()[0], self.b.interfaces.all()[0])
        scene = self._scene()
        tops = {tuple(r.top) for r in scene.racks}
        run = scene.runs[0]
        self.assertEqual({tuple(run.points[0]), tuple(run.points[-1])}, tops)

    def test_a_run_arcs_above_the_taller_rack(self):
        cable(self.a.interfaces.all()[0], self.b.interfaces.all()[0])
        scene = self._scene()
        start, control, end = scene.runs[0].points
        # The curve's highest point is halfway between its ends and its control point.
        apex = (start[1] + end[1]) / 4 + control[1] / 2
        tallest = max(r.height for r in scene.racks)
        self.assertGreaterEqual(apex, tallest + RUN_RISE_MIN_MM - 1)

    def test_an_exit_rises_to_the_tray_and_runs_to_its_wall(self):
        from circuits.models import Circuit, CircuitTermination, CircuitType, Provider

        provider = Provider.objects.create(name='Acme Telecom', slug='acme-telecom')
        kind = CircuitType.objects.create(name='Transit', slug='transit')
        circuit = Circuit.objects.create(cid='CID-1', provider=provider, type=kind, status='active')
        end = CircuitTermination.objects.create(circuit=circuit, term_side='A', termination=self.site)
        cable(self.a.interfaces.all()[1], end)

        scene = self._scene()
        placed = build_layout(self.floor, None)
        wall = build_floor_exits(placed, self.floor)[0]
        exit_ = scene.exits[0]
        tray = max(r.height for r in scene.racks) + TRAY_ABOVE_MM
        rack = next(r for r in scene.racks if r.placed.rack == self.near)
        self.assertEqual(exit_.points[0], rack.top)
        self.assertEqual(exit_.points[1][1], round(tray, 1))
        self.assertEqual((exit_.points[2][0], exit_.points[2][2]), (round(wall.x * 10, 1), round(wall.y * 10, 1)))
        self.assertEqual(exit_.as_json()['kind'], 'circuit')

    def test_no_cabling_toggle_means_no_cabling(self):
        cable(self.a.interfaces.all()[0], self.b.interfaces.all()[0])
        scene = build_floor_scene(self.floor, build_layout(self.floor, None))
        self.assertEqual((scene.runs, scene.exits), ([], []))


class FloorPageTest(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.floor = make_floor(self.site)
        self.rack = make_rack(self.site, name='R1')
        place(self.floor, self.rack)

    def _get(self, query=''):
        return self.client.get(f'{self.floor.get_absolute_url()}{query}')

    def test_it_opens_in_3d_with_the_plan_beside_it(self):
        response = self._get()
        self.assertContains(response, 'data-atlas-floor-view="3d"')
        self.assertContains(response, 'data-atlas-floor-panel="3d"')
        # The plan is still on the page, hidden, so switching to it costs no request.
        self.assertContains(response, 'class="atlas-floor"')
        self.assertContains(response, 'id="atlas-floor3d-config"')
        self.assertEqual(response.context['floor3d_config']['scene']['racks'][0]['id'], self.rack.pk)

    def test_the_stage_and_three_are_in_the_import_map(self):
        response = self._get()
        self.assertContains(response, '"atlas/stage3d"')
        self.assertContains(response, 'build/three.module.js')

    def test_the_cabling_toggle_reaches_the_scene(self):
        response = self._get('?runs=1')
        self.assertIn('exits', response.context['floor3d_config']['scene'])

    def test_an_empty_setting_leaves_the_plan_working(self):
        plugins_config = {
            **settings.PLUGINS_CONFIG,
            'netbox_atlas': {**settings.PLUGINS_CONFIG['netbox_atlas'], 'three_base': ''},
        }
        with override_settings(PLUGINS_CONFIG=plugins_config):
            response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['floor3d_config']['enabled'])
        self.assertContains(response, 'class="atlas-floor"')

    def test_an_empty_floor_draws_no_stage(self):
        empty = make_floor(self.site, name='Empty')
        response = self.client.get(empty.get_absolute_url())
        self.assertNotContains(response, 'data-atlas-3d')
        self.assertNotContains(response, 'floor3d.js')


class FloorSceneVisibilityTest(ViewTestCase):
    def test_a_rack_the_reader_may_not_see_is_not_in_the_room(self):
        floor = make_floor(self.site)
        mine = make_rack(self.site, name='MINE')
        secret = make_rack(self.site, name='SECRETRACK')
        place(floor, mine, x=100)
        place(floor, secret, x=300)

        self.user.is_superuser = False
        self.user.save()
        grant(self.user, 'netbox_atlas.floor')
        grant(self.user, 'netbox_atlas.rackplacement')
        grant(self.user, 'dcim.rack', constraints={'name': 'MINE'})

        response = self.client.get(floor.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        names = [r['name'] for r in response.context['floor3d_config']['scene']['racks']]
        self.assertEqual(names, ['MINE'])
        self.assertNotContains(response, 'SECRETRACK')

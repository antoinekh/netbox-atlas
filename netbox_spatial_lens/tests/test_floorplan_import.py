"""
Reading a layout out of netbox-floorplan's Fabric.js canvas.

Tested against a captured canvas rather than the plugin itself, which cannot be installed on
NetBox 4.7 at all: its 0.9.2 release declares a maximum of 4.6.99.
"""

from django.test import SimpleTestCase

from netbox_spatial_lens.integrations.floorplan import extract_rack_placements

CANVAS = {
    'objects': [
        {
            'type': 'group',
            'left': 100,
            'top': 200,
            'angle': 90,
            'custom_meta': {'object_type': 'rack', 'object_id': '7'},
            'objects': [
                {'type': 'rect', 'custom_meta': {'object_type': 'rack', 'object_id': '7'}},
                {'type': 'i-text', 'text': 'R7'},
            ],
        },
        # A rack marker with no group of its own, as an older canvas stores it.
        {
            'type': 'rect',
            'left': 50,
            'top': 60,
            'custom_meta': {'object_type': 'rack', 'object_id': '8'},
        },
        # Things a hand-drawn canvas is full of, and which must be skipped.
        {'type': 'line', 'left': 0, 'top': 0},
        {'type': 'i-text', 'text': 'Hall A', 'left': 5, 'top': 5},
        {'type': 'rect', 'custom_meta': {'object_type': 'device', 'object_id': '3'}},
    ]
}


class ExtractTest(SimpleTestCase):
    def test_racks_are_found_and_others_are_skipped(self):
        placements = extract_rack_placements(CANVAS)
        self.assertEqual({p[0] for p in placements}, {7, 8})

    def test_the_group_carries_the_position(self):
        # Fabric moves the group, not the marker inside it, so the group is what to read.
        placements = {p[0]: p for p in extract_rack_placements(CANVAS)}
        self.assertEqual(placements[7][1:], (100.0, 200.0, 90.0))

    def test_a_marker_with_no_group_falls_back_to_its_own_position(self):
        placements = {p[0]: p for p in extract_rack_placements(CANVAS)}
        self.assertEqual(placements[8][1:3], (50.0, 60.0))

    def test_scale_converts_canvas_units(self):
        placements = {p[0]: p for p in extract_rack_placements(CANVAS, scale=2)}
        self.assertEqual(placements[7][1:3], (200.0, 400.0))

    def test_an_empty_canvas_is_not_an_error(self):
        self.assertEqual(extract_rack_placements({}), [])
        self.assertEqual(extract_rack_placements(None), [])

    def test_a_malformed_object_id_is_skipped(self):
        canvas = {'objects': [{'custom_meta': {'object_type': 'rack', 'object_id': 'nope'}}]}
        self.assertEqual(extract_rack_placements(canvas), [])

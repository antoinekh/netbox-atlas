"""
What a placement, a floor form and a background layer will accept, and what they leave behind.
"""

import tempfile
from pathlib import Path

from dcim.models import Location
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import override_settings

from netbox_atlas.forms import FloorForm
from netbox_atlas.layout import unplaced_racks
from netbox_atlas.models import Floor, FloorLayer, RackPlacement
from netbox_atlas.tests.base import AtlasTestCase, make_floor, make_rack


class PlacementLocationTest(AtlasTestCase):
    def setUp(self):
        self.hall = Location.objects.create(site=self.site, name='Hall', slug='hall')
        self.cage = Location.objects.create(site=self.site, name='Cage', slug='cage', parent=self.hall)
        self.annexe = Location.objects.create(site=self.site, name='Annexe', slug='annexe')
        self.floor = Floor.objects.create(name='Hall floor', location=self.hall, width=10, depth=10)

    def test_a_rack_from_another_room_is_refused(self):
        stray = make_rack(self.site, name='Stray', location=self.annexe)
        with self.assertRaises(ValidationError):
            RackPlacement(floor=self.floor, rack=stray, x=100, y=100).clean()

    def test_a_rack_in_a_nested_location_is_accepted(self):
        inside = make_rack(self.site, name='Inside', location=self.cage)
        RackPlacement(floor=self.floor, rack=inside, x=100, y=100).clean()

    def test_the_panel_offers_what_the_placement_accepts(self):
        inside = make_rack(self.site, name='Inside', location=self.cage)
        make_rack(self.site, name='Stray', location=self.annexe)
        self.assertEqual(list(unplaced_racks(self.floor)), [inside])


class PlacementBoundsTest(AtlasTestCase):
    def test_a_rack_outside_the_room_is_refused(self):
        floor = make_floor(self.site, width=10, depth=8)
        rack = make_rack(self.site)
        for x, y in ((-1, 100), (1001, 100), (100, 801)):
            with self.subTest(x=x, y=y), self.assertRaises(ValidationError):
                RackPlacement(floor=floor, rack=rack, x=x, y=y).clean()

    def test_a_rack_against_the_wall_is_accepted(self):
        floor = make_floor(self.site, width=10, depth=8)
        RackPlacement(floor=floor, rack=make_rack(self.site), x=1000, y=800).clean()


class FloorFormTest(AtlasTestCase):
    def _form(self, **data):
        return FloorForm(data={'name': 'Room', 'width': 10, 'depth': 8, 'unit': 'm', **data})

    def test_a_site_and_one_of_its_locations_binds_the_location(self):
        # The site narrows the location list, so filling in both is how the form is used.
        hall = Location.objects.create(site=self.site, name='Hall', slug='hall')
        form = self._form(site=self.site.pk, location=hall.pk)
        self.assertTrue(form.is_valid(), form.errors)
        floor = form.save()
        self.assertIsNone(floor.site)
        self.assertEqual(floor.location, hall)

    def test_a_location_in_another_site_is_refused(self):
        from dcim.models import Site

        elsewhere = Site.objects.create(name='Elsewhere', slug='elsewhere')
        hall = Location.objects.create(site=elsewhere, name='Hall', slug='hall')
        form = self._form(site=self.site.pk, location=hall.pk)
        self.assertFalse(form.is_valid())
        self.assertIn('location', form.errors)

    def test_a_location_floor_shows_its_site(self):
        hall = Location.objects.create(site=self.site, name='Hall', slug='hall')
        floor = Floor.objects.create(name='Hall floor', location=hall, width=10, depth=8)
        self.assertEqual(FloorForm(instance=floor).initial['site'], self.site.pk)


class LayerFileTest(AtlasTestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.floor = make_floor(self.site)

    def _layer(self, name='plan'):
        layer = FloorLayer(floor=self.floor, name=name, width=100, height=100)
        layer.file.save(f'{name}.png', ContentFile(b'image'), save=True)
        return layer

    def _exists(self, name: str) -> bool:
        return (Path(self.media.name) / name).exists()

    def test_deleting_the_floor_removes_the_image(self):
        # A cascade never calls the layer's own delete(), so the file was left behind.
        stored = self._layer().file.name
        with self.captureOnCommitCallbacks(execute=True):
            self.floor.delete()
        self.assertFalse(self._exists(stored))

    def test_deleting_the_layer_removes_the_image(self):
        layer = self._layer()
        stored = layer.file.name
        with self.captureOnCommitCallbacks(execute=True):
            layer.delete()
        self.assertFalse(self._exists(stored))

    def test_replacing_the_image_removes_the_old_one(self):
        layer = self._layer()
        old = layer.file.name
        with self.captureOnCommitCallbacks(execute=True):
            layer.file.save('new.png', ContentFile(b'other'), save=True)
        self.assertFalse(self._exists(old))
        self.assertTrue(self._exists(layer.file.name))

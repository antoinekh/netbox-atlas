"""
Custom fields offered as filters, the way tags are.
"""

import copy

from core.models import ObjectType
from dcim.models import Device, Rack
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from extras.models import CustomField, CustomFieldChoiceSet

from netbox_spatial_lens.field_filters import cells_for, field_filters
from netbox_spatial_lens.palette import NO_DATA
from netbox_spatial_lens.tests.base import make_device, make_floor, make_rack, place
from netbox_spatial_lens.tests.test_views import ViewTestCase


def offering(*names):
    """The plugin settings with `filter_custom_fields` set to `names`."""
    config = copy.deepcopy(settings.PLUGINS_CONFIG)
    config['netbox_spatial_lens']['filter_custom_fields'] = list(names)
    return override_settings(PLUGINS_CONFIG=config)


class FieldFilterTestCase(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.choices = CustomFieldChoiceSet.objects.create(
            name='Compliance',
            extra_choices=[['pci', 'PCI DSS'], ['sox', 'SOX'], ['iso 27001', 'ISO 27001']],
            choice_colors={'pci': 'f44336'},
        )
        self.compliancy = self.field('compliancy', 'select', Rack)
        self.audits = self.field('audits', 'multiselect', Rack)

        self.floor = make_floor(self.site)
        self.r1 = make_rack(self.site, name='R1')
        self.r2 = make_rack(self.site, name='R2')
        self.r3 = make_rack(self.site, name='R3')
        for index, rack in enumerate((self.r1, self.r2, self.r3)):
            place(self.floor, rack, x=100 + index * 200, y=100)
        self.set(self.r1, compliancy='pci', audits=['pci', 'iso 27001'])
        self.set(self.r2, compliancy='sox')

    def field(self, name, kind, model, **kwargs):
        custom_field = CustomField.objects.create(
            name=name, label=name.title(), type=kind, choice_set=self.choices, **kwargs
        )
        custom_field.object_types.set([ObjectType.objects.get_for_model(model)])
        return custom_field

    @staticmethod
    def set(obj, **values):
        obj.custom_field_data.update(values)
        obj.save()


class FieldFilterTest(FieldFilterTestCase):
    def test_nothing_is_offered_when_no_field_is_named(self):
        # Set explicitly: the deployment running the tests may name fields of its own.
        with offering():
            self.assertEqual(field_filters(Rack.objects.all(), Rack), [])

    def test_the_values_in_use_are_counted_in_choice_order(self):
        with offering('compliancy'):
            (item,) = field_filters(Rack.objects.all(), Rack)
        self.assertEqual([(v.label, v.count) for v in item.values], [('PCI DSS', 1), ('SOX', 1)])

    def test_a_choice_keeps_its_colour_and_the_others_get_their_own(self):
        with offering('compliancy'):
            (item,) = field_filters(Rack.objects.all(), Rack)
        pci, sox = item.values
        self.assertEqual(pci.colour, '#f44336')
        self.assertTrue(sox.colour.startswith('#'))
        self.assertNotIn(sox.colour, (pci.colour, NO_DATA))

    def test_a_multiselect_rack_carries_every_value(self):
        with offering('audits'):
            (item,) = field_filters(Rack.objects.all(), Rack)
            (cell,) = cells_for([item], Rack.objects.get(pk=self.r1.pk))
        # A value with a space in it becomes a key without one, since keys are split on spaces.
        self.assertEqual(cell.keys, 'pci iso-27001')

    def test_other_types_hidden_fields_and_other_models_are_skipped(self):
        CustomField.objects.create(name='notes', type='text').object_types.set([ObjectType.objects.get_for_model(Rack)])
        self.field('secret', 'select', Rack, ui_visible='hidden')
        self.field('owner', 'select', Device)
        with offering('notes', 'secret', 'owner'):
            self.assertEqual(field_filters(Rack.objects.all(), Rack), [])


class FieldFilterPageTest(FieldFilterTestCase):
    def test_the_floor_offers_the_field_like_tags(self):
        with offering('compliancy'):
            response = self.client.get(self.floor.get_absolute_url())
        self.assertContains(response, 'data-lens-finder="field0"')
        self.assertContains(response, 'data-lens-pick="pci"')
        self.assertContains(response, 'data-field0="pci"')
        self.assertContains(response, 'rack-tags field0"')

    def test_the_rack_table_has_a_column_for_the_field(self):
        with offering('compliancy'):
            response = self.client.get(self.floor.get_absolute_url())
        self.assertContains(response, '<button type="button" class="lens-sort">Compliancy</button>')
        self.assertContains(response, 'background-color: #f44336">PCI DSS</span>')

    def test_the_hover_card_names_the_value(self):
        with offering('compliancy'):
            response = self.client.get(self.floor.get_absolute_url())
        self.assertIn(('Compliancy', 'PCI DSS'), response.context['placed_racks'][0].facts)

    def test_a_field_with_no_value_in_use_offers_no_button(self):
        for rack in (self.r1, self.r2):
            rack.custom_field_data = {}
            rack.save()
        with offering('compliancy'):
            response = self.client.get(self.floor.get_absolute_url())
        self.assertNotContains(response, 'data-lens-finder="field0"')

    def test_the_rack_view_offers_a_device_field(self):
        self.field('device_compliancy', 'select', Device)
        device = make_device(self.site, self.r1, 'srv', self.role, self.manufacturer)
        self.set(device, device_compliancy='sox')
        with offering('device_compliancy'):
            response = self.client.get(reverse('dcim:rack_lens', args=[self.r1.pk]))
        self.assertContains(response, 'data-lens-finder="field0"')
        scene_device = response.context['rack3d_config']['scene']['devices'][0]
        self.assertEqual(scene_device['filters']['field0'], 'sox')

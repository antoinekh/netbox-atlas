"""
The example in docs/extending.md runs, and does what the page says it does.

A documented example nobody runs is wrong by the next release. This reads the code block out of
the page and runs it, so a change that breaks the example breaks a test.
"""

import re
from pathlib import Path
from unittest import skipUnless

from netbox_spatial_lens.overlays import UTILISATION_LEGEND, Overlay
from netbox_spatial_lens.palette import utilisation_colour
from netbox_spatial_lens.tests.base import LensTestCase, make_rack

EXTENDING = Path(__file__).resolve().parents[2] / 'docs' / 'extending.md'


def _example(first_line: str) -> str:
    """The Python block in docs/extending.md that starts with `first_line`."""
    for block in re.findall(r'```python\n(.*?)```', EXTENDING.read_text(), flags=re.S):
        if block.startswith(first_line):
            return block
    raise AssertionError(f'no example starting with {first_line!r} in {EXTENDING}')


# The docs are in the repository, not in the installed package.
@skipUnless(EXTENDING.exists(), 'docs/extending.md is not shipped with the package')
class ExtendingExampleTest(LensTestCase):
    def setUp(self):
        namespace = {}
        exec(_example('# yourplugin/lens.py'), namespace)
        self.heat_overlay = namespace['heat_overlay']

    def test_a_rack_with_both_values_is_gauged(self):
        rack = make_rack(self.site, name='Hot', cooling_capacity=10)
        rack.custom_field_data = {'heat_load_kw': 6}
        value = self.heat_overlay([rack])[rack.pk]
        self.assertEqual(value.value, 60)
        self.assertEqual(value.colour, utilisation_colour(60))
        self.assertEqual(value.label, '6 of 10 kW')

    def test_a_rack_with_a_value_missing_is_no_data(self):
        no_load = make_rack(self.site, name='NoLoad', cooling_capacity=10)
        no_capacity = make_rack(self.site, name='NoCapacity')
        no_capacity.custom_field_data = {'heat_load_kw': 6}
        overlay = Overlay('heat', 'Heat', self.heat_overlay, legend=UTILISATION_LEGEND)
        values = overlay.evaluate([no_load, no_capacity])
        self.assertFalse(values[no_load.pk].has_data)
        self.assertFalse(values[no_capacity.pk].has_data)
        self.assertEqual(overlay.legend_for(values.values())[-1].count, 2)

    def test_the_registration_example_names_real_functions(self):
        registration = _example('# yourplugin/__init__.py')
        from netbox_spatial_lens import overlays

        for name in ('register_overlay', 'UTILISATION_LEGEND'):
            self.assertIn(name, registration)
            self.assertTrue(hasattr(overlays, name), name)

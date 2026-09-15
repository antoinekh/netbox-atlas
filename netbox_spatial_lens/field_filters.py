"""
Custom fields as filters, the way tags are.

A select or multiselect custom field named in the `filter_custom_fields` setting gets a finder on
the floor (for racks) and in the rack view (for devices): the values in use, each with how many
carry it and in the choice set's own colour, to tick. A rack with any ticked value stays lit.

A value is carried on the page as a key made from it, not as the value itself: the finder splits
a list of keys on spaces, and a choice value may contain one.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from django.utils.text import slugify
from netbox.plugins import get_plugin_config

from netbox_spatial_lens.palette import NO_DATA, STATUS_COLOURS, distinct_colours

__all__ = (
    'FieldCell',
    'FieldFilter',
    'FieldValue',
    'cells_for',
    'field_filters',
)

# The custom field types that hold a choice from a list.
FIELD_TYPES = ('select', 'multiselect')


@dataclass
class FieldValue:
    """One choice of a custom field, as the page shows it."""

    key: str
    label: str
    colour: str
    count: int = 0


@dataclass
class FieldFilter:
    """One custom field offered as a filter on one page."""

    field: object
    # The finder group, and the name of the data attribute that carries the keys: `field0`.
    group: str
    # Stored value -> FieldValue, in the choice set's order.
    choices: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.field.label or self.field.name

    @property
    def values(self) -> list[FieldValue]:
        """The choices in use on this page, in the choice set's order."""
        return [value for value in self.choices.values() if value.count]

    def values_of(self, obj) -> list[FieldValue]:
        raw = (obj.custom_field_data or {}).get(self.field.name)
        if raw in (None, '', []):
            return []
        items = raw if isinstance(raw, list) else [raw]
        return [self.choices[item] for item in items if item in self.choices]


@dataclass
class FieldCell:
    """One custom field on one rack or device."""

    filter: FieldFilter
    values: list

    @property
    def keys(self) -> str:
        return ' '.join(value.key for value in self.values)

    @property
    def sort_value(self) -> str:
        return ', '.join(value.label for value in self.values)


def field_filters(objects: Iterable, model) -> list[FieldFilter]:
    """
    The custom fields to offer as filters for `objects`, which are all of `model`.

    Only fields named in the setting, of a choice type, assigned to `model` and not hidden in the
    UI. They come in the order the setting names them.
    """
    names = list(get_plugin_config('netbox_spatial_lens', 'filter_custom_fields') or [])
    if not names:
        return []

    from core.models import ObjectType
    from extras.models import CustomField

    found = {
        custom_field.name: custom_field
        for custom_field in CustomField.objects.filter(
            name__in=names, type__in=FIELD_TYPES, object_types=ObjectType.objects.get_for_model(model)
        )
        .exclude(ui_visible='hidden')
        .select_related('choice_set')
    }

    objects = list(objects)
    filters = []
    for name in names:
        if name not in found:
            continue
        item = FieldFilter(field=found[name], group=f'field{len(filters)}', choices=_choices(found[name]))
        for obj in objects:
            for value in item.values_of(obj):
                value.count += 1
        filters.append(item)
    return filters


def cells_for(filters: list[FieldFilter], obj) -> list[FieldCell]:
    """One cell per filter for `obj`, in the filters' order, empty where it has no value."""
    return [FieldCell(filter=item, values=item.values_of(obj)) for item in filters]


def _choices(custom_field) -> dict[str, FieldValue]:
    """Every choice of `custom_field` as a FieldValue, with a unique key and a colour."""
    pairs = [(value, str(label)) for value, label in custom_field.choices]
    choice_set = custom_field.choice_set
    colours = {value: _colour(choice_set.get_choice_color(value)) if choice_set else None for value, _ in pairs}
    # A choice with no colour of its own gets one that no other value on the page wears.
    fallback = distinct_colours((label for value, label in pairs if not colours[value]), reserved=(NO_DATA,))

    choices, used = {}, set()
    for index, (value, label) in enumerate(pairs):
        key = slugify(str(value)) or f'value-{index}'
        if key in used:
            key = f'{key}-{index}'
        used.add(key)
        choices[value] = FieldValue(key=key, label=label, colour=colours[value] or fallback[label])
    return choices


def _colour(name) -> str | None:
    """A choice colour as `#rrggbb`: a hex value as stored, or one of NetBox's colour names."""
    if not name:
        return None
    name = str(name).strip().lower().lstrip('#')
    if re.fullmatch(r'[0-9a-f]{6}', name):
        return f'#{name}'
    return STATUS_COLOURS.get(name)

import django_tables2 as tables
from netbox.tables import NetBoxTable, columns

from netbox_atlas.models import Floor, FloorLayer, RackPlacement

__all__ = (
    'FloorLayerTable',
    'FloorTable',
    'RackPlacementTable',
)


class FloorTable(NetBoxTable):
    name = tables.Column(linkify=True)
    # The floor's site however it was bound: a floor bound to a location has none of its own,
    # and an empty cell there read as a room in no site at all.
    site = tables.Column(
        accessor='effective_site',
        linkify=True,
        order_by=('site__name', 'location__site__name'),
        verbose_name='Site',
    )
    location = tables.Column(linkify=True)
    placement_count = columns.LinkedCountColumn(
        viewname='plugins:netbox_atlas:rackplacement_list',
        url_params={'floor_id': 'pk'},
        verbose_name='Racks',
    )
    tags = columns.TagColumn(url_name='plugins:netbox_atlas:floor_list')

    class Meta(NetBoxTable.Meta):
        model = Floor
        fields = (
            'pk',
            'id',
            'name',
            'site',
            'location',
            'width',
            'depth',
            'unit',
            'placement_count',
            'description',
            'tags',
            'created',
            'last_updated',
        )
        default_columns = ('name', 'site', 'location', 'width', 'depth', 'unit', 'placement_count')


class RackPlacementTable(NetBoxTable):
    rack = tables.Column(linkify=True)
    site = tables.Column(accessor='rack__site', linkify=True, verbose_name='Site')
    location = tables.Column(accessor='rack__location', linkify=True, verbose_name='Location')
    floor = tables.Column(linkify=True)
    tags = columns.TagColumn(url_name='plugins:netbox_atlas:rackplacement_list')

    class Meta(NetBoxTable.Meta):
        model = RackPlacement
        fields = (
            'pk',
            'id',
            'rack',
            'site',
            'location',
            'floor',
            'x',
            'y',
            'rotation',
            'tags',
            'created',
            'last_updated',
        )
        default_columns = ('rack', 'site', 'location', 'floor', 'x', 'y', 'rotation')


class FloorLayerTable(NetBoxTable):
    name = tables.Column(linkify=True)
    floor = tables.Column(linkify=True)
    enabled = columns.BooleanColumn()
    tags = columns.TagColumn(url_name='plugins:netbox_atlas:floorlayer_list')

    class Meta(NetBoxTable.Meta):
        model = FloorLayer
        fields = ('pk', 'id', 'name', 'floor', 'width', 'height', 'opacity', 'weight', 'enabled', 'tags')
        default_columns = ('name', 'floor', 'width', 'height', 'opacity', 'weight', 'enabled')

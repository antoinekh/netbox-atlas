from dcim.api.serializers import LocationSerializer, RackSerializer, SiteSerializer
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_spatial_lens.models import Floor, FloorLayer, RackPlacement

__all__ = (
    'FloorLayerSerializer',
    'FloorSerializer',
    'RackPlacementSerializer',
)


class FloorSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_spatial_lens-api:floor-detail')
    site = SiteSerializer(nested=True, required=False, allow_null=True)
    location = LocationSerializer(nested=True, required=False, allow_null=True)
    placement_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Floor
        fields = (
            'id',
            'url',
            'display',
            'name',
            'site',
            'location',
            'width',
            'depth',
            'unit',
            'placement_count',
            'description',
            'comments',
            'tags',
            'custom_fields',
            'created',
            'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name')


class RackPlacementSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_spatial_lens-api:rackplacement-detail')
    floor = FloorSerializer(nested=True)
    rack = RackSerializer(nested=True)

    class Meta:
        model = RackPlacement
        fields = (
            'id',
            'url',
            'display',
            'floor',
            'rack',
            'x',
            'y',
            'rotation',
            'tags',
            'custom_fields',
            'created',
            'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'rack', 'x', 'y', 'rotation')


class FloorLayerSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_spatial_lens-api:floorlayer-detail')
    floor = FloorSerializer(nested=True)
    # Where the browser actually fetches the image, whether it was uploaded or linked. A
    # client should not have to know which of the two fields was filled in.
    source = serializers.CharField(read_only=True)

    class Meta:
        model = FloorLayer
        fields = (
            'id',
            'url',
            'display',
            'floor',
            'name',
            'file',
            'external_url',
            'source',
            'x',
            'y',
            'width',
            'height',
            'rotation',
            'opacity',
            'weight',
            'enabled',
            'tags',
            'custom_fields',
            'created',
            'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'source')

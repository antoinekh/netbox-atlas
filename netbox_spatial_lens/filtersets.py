import django_filters
from dcim.models import Location, Rack, Site
from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet

from netbox_spatial_lens.models import Floor, FloorLayer, RackPlacement

__all__ = (
    'FloorFilterSet',
    'FloorLayerFilterSet',
    'RackPlacementFilterSet',
)


class FloorFilterSet(NetBoxModelFilterSet):
    site_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Site.objects.all(),
        method='filter_site',
        label='Site (ID)',
    )
    location_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Location.objects.all(),
        label='Location (ID)',
    )

    class Meta:
        model = Floor
        fields = ('id', 'name', 'unit', 'description')

    def filter_site(self, queryset, name: str, value):
        """
        Every floor in the sites, however each one was bound.

        A floor bound to a location has no site of its own, so filtering on the column alone
        left every room of a site with several rooms out of its own site's list.
        """
        if not value:
            return queryset
        return queryset.filter(Q(site__in=value) | Q(location__site__in=value))

    def search(self, queryset, name: str, value: str):
        if not value.strip():
            return queryset
        return queryset.filter(name__icontains=value) | queryset.filter(description__icontains=value)


class RackPlacementFilterSet(NetBoxModelFilterSet):
    floor_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Floor.objects.all(),
        label='Floor (ID)',
    )
    rack_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Rack.objects.all(),
        label='Rack (ID)',
    )
    # Where the rack is, as NetBox records it. The floor's own binding says which room; these
    # say which site and location the cabinet belongs to.
    site_id = django_filters.ModelMultipleChoiceFilter(
        field_name='rack__site',
        queryset=Site.objects.all(),
        label='Site (ID)',
    )
    location_id = django_filters.ModelMultipleChoiceFilter(
        field_name='rack__location',
        queryset=Location.objects.all(),
        label='Location (ID)',
    )

    class Meta:
        model = RackPlacement
        fields = ('id', 'x', 'y', 'rotation')

    def search(self, queryset, name: str, value: str):
        if not value.strip():
            return queryset
        return queryset.filter(rack__name__icontains=value)


class FloorLayerFilterSet(NetBoxModelFilterSet):
    floor_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Floor.objects.all(),
        label='Floor (ID)',
    )

    class Meta:
        model = FloorLayer
        fields = ('id', 'name', 'enabled')

    def search(self, queryset, name: str, value: str):
        if not value.strip():
            return queryset
        return queryset.filter(name__icontains=value)

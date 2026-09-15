from netbox.search import SearchIndex, register_search

from netbox_spatial_lens.models import Floor


@register_search
class FloorIndex(SearchIndex):
    model = Floor
    fields = (
        ('name', 100),
        ('description', 500),
        ('comments', 5000),
    )
    display_attrs = ('site', 'location', 'description')

from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

floor_item = PluginMenuItem(
    link='plugins:netbox_spatial_lens:floor_list',
    link_text='Floors',
    permissions=['netbox_spatial_lens.view_floor'],
    buttons=(
        PluginMenuButton(
            link='plugins:netbox_spatial_lens:floor_add',
            title='Add',
            icon_class='mdi mdi-plus-thick',
            permissions=['netbox_spatial_lens.add_floor'],
        ),
    ),
)

placement_item = PluginMenuItem(
    link='plugins:netbox_spatial_lens:rackplacement_list',
    link_text='Rack placements',
    permissions=['netbox_spatial_lens.view_rackplacement'],
)

world_item = PluginMenuItem(
    link='plugins:netbox_spatial_lens:world',
    link_text='World map',
    permissions=['dcim.view_site'],
)

layer_item = PluginMenuItem(
    link='plugins:netbox_spatial_lens:floorlayer_list',
    link_text='Background layers',
    permissions=['netbox_spatial_lens.view_floorlayer'],
    buttons=(
        PluginMenuButton(
            link='plugins:netbox_spatial_lens:floorlayer_add',
            title='Add',
            icon_class='mdi mdi-plus-thick',
            permissions=['netbox_spatial_lens.add_floorlayer'],
        ),
    ),
)

menu = PluginMenu(
    label='Spatial Lens',
    groups=(
        ('Estate', (world_item,)),
        ('Floor plans', (floor_item, placement_item, layer_item)),
    ),
    icon_class='mdi mdi-layers-search',
)

from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

floor_item = PluginMenuItem(
    link='plugins:netbox_atlas:floor_list',
    link_text='Floors',
    permissions=['netbox_atlas.view_floor'],
    buttons=(
        PluginMenuButton(
            link='plugins:netbox_atlas:floor_add',
            title='Add',
            icon_class='mdi mdi-plus-thick',
            permissions=['netbox_atlas.add_floor'],
        ),
    ),
)

placement_item = PluginMenuItem(
    link='plugins:netbox_atlas:rackplacement_list',
    link_text='Rack placements',
    permissions=['netbox_atlas.view_rackplacement'],
)

world_item = PluginMenuItem(
    link='plugins:netbox_atlas:world',
    link_text='World map',
    permissions=['dcim.view_site'],
)

layer_item = PluginMenuItem(
    link='plugins:netbox_atlas:floorlayer_list',
    link_text='Background layers',
    permissions=['netbox_atlas.view_floorlayer'],
    buttons=(
        PluginMenuButton(
            link='plugins:netbox_atlas:floorlayer_add',
            title='Add',
            icon_class='mdi mdi-plus-thick',
            permissions=['netbox_atlas.add_floorlayer'],
        ),
    ),
)

menu = PluginMenu(
    label='Atlas',
    groups=(
        ('Estate', (world_item,)),
        ('Floor plans', (floor_item, placement_item, layer_item)),
    ),
    icon_class='mdi mdi-floor-plan',
)

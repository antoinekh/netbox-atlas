# Configuration

Every setting is optional. Set them under `PLUGINS_CONFIG['netbox_atlas']` in NetBox's `configuration.py`.

| Setting | Default | What it does |
|---|---|---|
| `default_rack_width` | `600` | Width in millimetres used for a rack with no outer width recorded. Such a rack is marked as estimated. |
| `default_rack_depth` | `1070` | Depth in millimetres used for a rack with no outer depth recorded. |
| `grid_size` | `10` | Grid the layout editor snaps to, in centimetres. `0` turns snapping off. |
| `filter_custom_fields` | `[]` | Custom fields to offer as filters, the way tags are: a list of field names. See below. |
| `enable_builtin_overlays` | `True` | Floor colourings to offer: `True` for all, `False` for none, or a list from `'power'`, `'cooling'`, `'space'`, `'role'`. |
| `default_overlay` | `'power'` | Floor colouring used when the URL names none. |
| `enable_builtin_device_overlays` | `True` | Rack colourings to offer: `True`, `False`, or a list from `'role'`, `'status'`, `'tenant'`, `'cabling'`, `'power'`. |
| `default_device_overlay` | `'role'` | Rack colouring used when the URL names none. |
| `enable_builtin_site_overlays` | `True` | World map colourings to offer: `True`, `False`, or a list from `'group'`, `'status'`, `'tenant'`, `'region'`. |
| `default_site_overlay` | `'group'` | World map colouring used when the URL names none. |
| `map_tile_url` | OpenStreetMap tiles | Raster tile URL for the globe. `{theme}` in the URL becomes `light` or `dark`. `None` draws the globe with no basemap. |
| `map_attribution` | OpenStreetMap credit | Credit shown on the map for the tiles. |
| `map_js` | MapLibre 5.6.1 on cdnjs | Where the browser loads MapLibre from. Empty turns the world map off. |
| `map_css` | MapLibre 5.6.1 on cdnjs | Where the browser loads MapLibre's stylesheet from. |
| `map_glyphs` | OpenMapTiles fonts | Font server for the site names on the map. `None` draws the map without names. |

A name in a URL that no colouring answers to falls back to the default, and then to the first colouring registered, so an old link still opens.

## Custom fields as filters

A select or multiselect custom field can narrow the floor and the rack view the way tags do:

```python
PLUGINS_CONFIG = {
    'netbox_atlas': {
        'filter_custom_fields': ['compliancy'],
    },
}
```

- On the floor, a field assigned to racks gets a button beside **Tags**. It lists the values in use, with how many racks carry each, in the colours of the field's choice set. Tick values to narrow the plan and the rack table to the racks with any of them. The table also gets a column for the field, and the hover card names the rack's values.
- In the rack view, a field assigned to devices does the same for the devices.
- Ticks combine with the Tags filter, the find box and the legend, are kept in the URL, and Escape clears them.
- Other field types, and fields hidden in the UI, are skipped.

## A site with no internet access

The world map needs a browser with WebGL and a copy of MapLibre it can reach. The tiles and the fonts are optional. Host MapLibre's two files yourself, and point the map settings at your own servers, or turn the optional parts off:

```python
PLUGINS_CONFIG = {
    'netbox_atlas': {
        'map_js': 'https://static.example.internal/maplibre-gl/5.6.1/maplibre-gl.min.js',
        'map_css': 'https://static.example.internal/maplibre-gl/5.6.1/maplibre-gl.min.css',
        # Your own tile server, or None for a globe with no basemap.
        'map_tile_url': 'https://tiles.example.internal/{z}/{x}/{y}.png',
        'map_attribution': 'Internal tiles',
        # Your own glyph server, or None for a map without site names.
        'map_glyphs': None,
    },
}
```

The floor plans and the rack view need nothing from the network.

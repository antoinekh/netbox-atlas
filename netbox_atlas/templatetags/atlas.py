"""
Template tags.
"""

from pathlib import Path

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

from netbox_atlas import __version__

register = template.Library()


@register.simple_tag
def atlas_static(path: str) -> str:
    """
    A static URL that changes whenever the file does, so a browser cannot serve a stale asset.

    NetBox serves plugin static files with far-future caching, so a browser that has loaded
    atlas.css or a script once keeps using it. The symptom is not a missing file but a
    working page behaving like the previous version: an old event handler still bound, a rule
    that appears not to apply.

    Keyed on the file's modification time rather than on the plugin version. The version is
    the obvious choice and is wrong in exactly the case that matters most: during development
    it never changes, so every edit is served from cache and the fix appears not to work. The
    timestamp is right in both places, since a file changes when the plugin is upgraded too.
    """
    located = finders.find(path)
    if located:
        try:
            return f'{static(path)}?v={int(Path(located).stat().st_mtime)}'
        except OSError:
            pass
    # A path the finders cannot resolve, such as a collected file on remote storage. The
    # version is a weaker key but better than none.
    return f'{static(path)}?v={__version__}'


@register.simple_tag
def atlas_palette() -> str:
    """
    The semantic palette as CSS custom property declarations.
    """
    from django.utils.safestring import mark_safe

    from netbox_atlas.palette import css_variables

    # The values are hex literals from a module in this package, never user input.
    return mark_safe(' '.join(css_variables()))


@register.filter
def json_facts(facts) -> str:
    """
    Label/value pairs as JSON, safe to sit in a data attribute.

    The hover card is built in the browser from what the server already resolved, so the page
    needs the pairs on the element rather than a second request per rack. `json.dumps` escapes
    the quotes and Django escapes the rest on its way into the attribute, so a rack named with
    an angle bracket stays a rack name.
    """
    import json

    return json.dumps([[str(label), str(value)] for label, value in (facts or ())])

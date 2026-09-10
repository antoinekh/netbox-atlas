# netbox-atlas, plus netbox-branching when the stack is started with it.
#
# Branching is off by default: the plugin does not depend on it, and leaving it out keeps the
# stack close to a plain NetBox. `make up BRANCHING=true` turns it on, which is how the plugin
# is checked against a branch. See the Makefile.
import os
import sys

PLUGINS = ['netbox_atlas']

PLUGINS_CONFIG = {
    'netbox_atlas': {
        # The demo's rack and device custom field, offered as a filter like tags.
        'filter_custom_fields': ['compliancy'],
    },
}

if os.environ.get('NETBOX_BRANCHING', 'false').lower() == 'true':
    from netbox_branching.utilities import DynamicSchemaDict

    # netbox-branching must be last in PLUGINS, and it serves every request from a schema it
    # picks at request time, so DATABASES has to be its dict subclass and its router has to be
    # installed. The connection settings are still the ones netbox-docker built from the
    # environment: this file loads after configuration.py, so it re-wraps what that made rather
    # than restating the host, name and password.
    PLUGINS.append('netbox_branching')
    PLUGINS_CONFIG['netbox_branching'] = {}

    DATABASES = DynamicSchemaDict(sys.modules['netbox.configuration.configuration'].DATABASES)
    DATABASE_ROUTERS = ['netbox_branching.database.BranchAwareRouter']

"""
The plugin inside a branch.

netbox-branching gives every branch its own PostgreSQL schema and routes queries to whichever
one the request names. A plugin joins in by using change-logged models and nothing but the
ORM, which is all this one does, so there is no wiring to test: there is only the claim that
it works, and these are the tests that hold us to it. The tables are replicated into a branch,
a floor drawn in a branch stays in that branch, a page follows the branch the request asks
for, and a merge brings the work into main.

`Floor`, `RackPlacement` and `FloorLayer` derive from `NetBoxModel` and `PrimaryModel`, both of
which carry `ChangeLoggingMixin`, and that is the whole of the contract. If one of them is ever
given a base class without it, the model silently stops being branch-aware: edits made in a
branch would land in main straight away. `test_the_plugin_tables_are_replicated` is what
catches that.

Skipped unless netbox-branching is installed. `make up BRANCHING=true` starts a stack that has
it, and `make test` then runs them.
"""

import unittest
import uuid

from dcim.models import Site
from django.apps import apps
from django.test import RequestFactory, TransactionTestCase
from django.urls import reverse
from netbox.context_managers import event_tracking
from users.models import User

from netbox_atlas.models import Floor
from netbox_atlas.tests.base import make_floor, make_rack, place

BRANCHING_INSTALLED = apps.is_installed('netbox_branching')

if BRANCHING_INSTALLED:
    from netbox_branching.models import Branch
    from netbox_branching.utilities import activate_branch, get_tables_to_replicate


@unittest.skipUnless(BRANCHING_INSTALLED, 'netbox-branching is not installed')
class BranchTest(TransactionTestCase):
    """
    Provisioning copies every replicated table, so this is a `TransactionTestCase`: the schema
    is real DDL and cannot live inside the outer transaction a `TestCase` never commits.
    """

    serialized_rollback = True

    def setUp(self):
        self.user = User.objects.create_user(username='atlas', is_superuser=True)
        self.client.force_login(self.user)

        # Change logging is what a merge replays, and it only records inside a request context.
        # Objects created outside one exist but merge as nothing.
        self.request = RequestFactory().get(reverse('home'))
        self.request.id = uuid.uuid4()
        self.request.user = self.user

        with event_tracking(self.request):
            self.site = Site.objects.create(name='Test site', slug='test-site')
            self.rack = make_rack(self.site)

        self.branch = Branch(name='Atlas branch')
        self.branch.save(provision=False)
        self.branch.provision(user=self.user)
        # provision() marks the branch ready with a queryset update, which leaves the instance
        # in hand still saying NEW. Without this, merge() refuses the branch it just built.
        self.branch.refresh_from_db()
        self.addCleanup(self.branch.delete)

    def branch_url(self, url):
        return f'{url}?_branch={self.branch.schema_id}'

    def test_the_plugin_tables_are_replicated(self):
        # The models carry ChangeLoggingMixin, so branching picks them up with no registration.
        # If it ever stops, a branch edit writes straight to main and no other test here fails
        # loudly enough to say why.
        tables = get_tables_to_replicate()
        self.assertIn('netbox_atlas_floor', tables)
        self.assertIn('netbox_atlas_rackplacement', tables)
        self.assertIn('netbox_atlas_floorlayer', tables)

    def test_a_floor_drawn_in_a_branch_is_not_in_main(self):
        with activate_branch(self.branch), event_tracking(self.request):
            floor = make_floor(self.site, name='Branch floor')
            self.assertTrue(Floor.objects.filter(pk=floor.pk).exists())

        self.assertFalse(Floor.objects.filter(pk=floor.pk).exists())

    def test_a_placement_made_in_a_branch_is_not_in_main(self):
        with activate_branch(self.branch), event_tracking(self.request):
            floor = make_floor(self.site, name='Branch floor')
            place(floor, self.rack)
            self.assertEqual(floor.placements.count(), 1)

        self.assertFalse(Floor.objects.filter(pk=floor.pk).exists())

    def test_the_floor_list_follows_the_branch(self):
        with activate_branch(self.branch), event_tracking(self.request):
            make_floor(self.site, name='Branch floor')

        url = reverse('plugins:netbox_atlas:floor_list')
        self.assertNotContains(self.client.get(url), 'Branch floor')
        self.assertContains(self.client.get(self.branch_url(url)), 'Branch floor')

    def test_the_floor_draws_the_branch_layout(self):
        # The page is the point: a rack placed in a branch has to appear on the plan the branch
        # serves, and the same URL has to 404 in main because the floor is not there. Main is
        # asked first, because opening the branch leaves a cookie that keeps it active.
        with activate_branch(self.branch), event_tracking(self.request):
            floor = make_floor(self.site, name='Branch floor')
            place(floor, self.rack)
            url = floor.get_absolute_url()

        self.assertEqual(self.client.get(url).status_code, 404)

        response = self.client.get(self.branch_url(url))
        self.assertContains(response, 'atlas-floor')
        self.assertContains(response, self.rack.name)

    def test_the_branch_stays_active_across_requests(self):
        # Opening a page with ?_branch leaves a cookie, so the rest of the session reads that
        # branch. It is what lets the plugin's own links stay as they are: none of them carries
        # the branch, and all of them stay inside it.
        with activate_branch(self.branch), event_tracking(self.request):
            make_floor(self.site, name='Branch floor')

        url = reverse('plugins:netbox_atlas:floor_list')
        self.client.get(self.branch_url(url))
        self.assertContains(self.client.get(url), 'Branch floor')

    def test_merging_brings_the_floor_into_main(self):
        with activate_branch(self.branch), event_tracking(self.request):
            floor = make_floor(self.site, name='Branch floor')
            place(floor, self.rack)

        self.branch.merge(self.user)

        merged = Floor.objects.get(name='Branch floor')
        self.assertEqual(merged.placements.count(), 1)
        self.assertEqual(merged.placements.first().rack, self.rack)

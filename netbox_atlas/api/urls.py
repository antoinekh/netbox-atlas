from netbox.api.routers import NetBoxRouter

from netbox_atlas.api import views

app_name = 'netbox_atlas-api'

router = NetBoxRouter()
router.register('floors', views.FloorViewSet)
router.register('floor-layers', views.FloorLayerViewSet)
router.register('rack-placements', views.RackPlacementViewSet)

urlpatterns = router.urls

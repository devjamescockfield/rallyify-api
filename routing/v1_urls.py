from django.urls import path

from routing.user_data_views import (
    DriveCollectionView,
    DriveDetailView,
    DriveFuelView,
    SetDefaultVehicleView,
    VehicleCollectionView,
    VehicleDetailView,
)


urlpatterns = [
    path("vehicles", VehicleCollectionView.as_view(), name="v1-vehicle-list"),
    path(
        "vehicles/<uuid:vehicle_id>",
        VehicleDetailView.as_view(),
        name="v1-vehicle-detail",
    ),
    path(
        "vehicles/<uuid:vehicle_id>/set-default",
        SetDefaultVehicleView.as_view(),
        name="v1-vehicle-set-default",
    ),
    path("drives", DriveCollectionView.as_view(), name="v1-drive-list"),
    path(
        "drives/<uuid:drive_id>",
        DriveDetailView.as_view(),
        name="v1-drive-detail",
    ),
    path(
        "drives/<uuid:drive_id>/fuel",
        DriveFuelView.as_view(),
        name="v1-drive-fuel",
    ),
]

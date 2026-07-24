from django.contrib import admin
from django.urls import include, path

from routing.views import (
    graph_information,
    health,
    readiness,
    routing_information,
    submit_route_report,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health, name="health"),
    path("ready", readiness, name="readiness"),
    path("routing/graph-info", graph_information, name="graph-information"),
    path("routing/info", routing_information, name="routing-information"),
    path("route-reports", submit_route_report, name="mobile-route-report"),
    path("routes/", include("routing.urls")),
    path("v1/", include("routing.v1_urls")),
]

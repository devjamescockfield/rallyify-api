from django.urls import include, path

from routing.views import graph_information, health, readiness, submit_route_report

urlpatterns = [
    path("health", health, name="health"),
    path("ready", readiness, name="readiness"),
    path("routing/graph-info", graph_information, name="graph-information"),
    path("route-reports", submit_route_report, name="mobile-route-report"),
    path("routes/", include("routing.urls")),
]

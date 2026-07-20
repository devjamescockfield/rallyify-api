from django.urls import path

from routing.views import calculate_route, submit_route_report

urlpatterns = [
    path("calculate", calculate_route, name="calculate-route"),
    path("report", submit_route_report, name="route-report"),
]

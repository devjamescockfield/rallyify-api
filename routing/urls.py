from django.urls import path

from routing.views import calculate_route

urlpatterns = [
    path("calculate", calculate_route, name="calculate-route"),
]

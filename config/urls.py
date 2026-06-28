from django.urls import include, path

from routing.views import health

urlpatterns = [
    path("health", health, name="health"),
    path("routes/", include("routing.urls")),
]

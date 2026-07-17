from django.urls import include, path

from routing.views import health, readiness

urlpatterns = [
    path("health", health, name="health"),
    path("ready", readiness, name="readiness"),
    path("routes/", include("routing.urls")),
]

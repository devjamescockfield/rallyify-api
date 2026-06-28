from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from routing.valhalla import get_valhalla_status


@api_view(["GET"])
def health(request):
    return Response(
        {
            "ok": True,
            "service": "rallyify-routing-api",
            "valhalla": get_valhalla_status(),
        }
    )


@api_view(["POST"])
def calculate_route(request):
    return Response(
        {
            "error": "Route calculation is not implemented yet.",
            "code": "NOT_IMPLEMENTED",
        },
        status=status.HTTP_501_NOT_IMPLEMENTED,
    )

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from routing.serializers import RouteCalculationSerializer
from routing.valhalla import (
    InvalidValhallaResponseError,
    ValhallaUnavailableError,
    calculate_route as calculate_valhalla_route,
    get_valhalla_status,
)


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
    serializer = RouteCalculationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        route = calculate_valhalla_route(serializer.validated_data)
    except ValhallaUnavailableError:
        return Response(
            {
                "error": "Valhalla is unavailable.",
                "code": "VALHALLA_UNAVAILABLE",
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except InvalidValhallaResponseError:
        return Response(
            {
                "error": "Valhalla returned an invalid response.",
                "code": "INVALID_VALHALLA_RESPONSE",
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except Exception:
        return Response(
            {
                "error": "An unexpected error occurred.",
                "code": "INTERNAL_ERROR",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(route)

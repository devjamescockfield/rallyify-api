from django.conf import settings


def get_valhalla_status() -> dict[str, bool]:
    return {
        "configured": bool(settings.VALHALLA_URL),
        "reachable": False,
    }

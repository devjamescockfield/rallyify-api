from django.conf import settings
from django.core.checks import Warning, register


@register()
def routing_metadata_checks(app_configs, **kwargs):
    if settings.DEPLOYMENT_ENV not in {"staging", "production"}:
        return []

    warnings = []
    if not settings.VALHALLA_GRAPH_BUILD_ID:
        warnings.append(
            Warning(
                "VALHALLA_GRAPH_BUILD_ID is not configured.",
                hint="Set it to the identifier of the deployed Valhalla graph.",
                id="routing.W001",
            )
        )
    if not settings.VALHALLA_OSM_DATA_DATE:
        warnings.append(
            Warning(
                "VALHALLA_OSM_DATA_DATE is not configured.",
                hint="Set it to the source-data date used for the graph build.",
                id="routing.W002",
            )
        )
    return warnings

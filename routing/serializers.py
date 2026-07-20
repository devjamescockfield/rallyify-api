import math

from rest_framework import serializers

from routing.contracts import (
    ROUTE_REPORT_CATEGORIES,
    SUPPORTED_ROUTE_PRIORITIES,
    SUPPORTED_VEHICLE_PROFILES,
)


class StrictFieldsMixin:
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise serializers.ValidationError(
                    {field: ["Unexpected field."] for field in unknown}
                )
        return super().to_internal_value(data)


class FiniteFloatField(serializers.FloatField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if not math.isfinite(value):
            self.fail("invalid")
        return value


class WaypointSerializer(serializers.Serializer):
    latitude = FiniteFloatField(min_value=-90, max_value=90)
    longitude = FiniteFloatField(min_value=-180, max_value=180)
    name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=100,
    )


class RouteCalculationSerializer(serializers.Serializer):
    waypoints = WaypointSerializer(many=True, min_length=2, max_length=25)
    vehicleProfile = serializers.ChoiceField(choices=SUPPORTED_VEHICLE_PROFILES)
    roadPriority = serializers.ChoiceField(choices=SUPPORTED_ROUTE_PRIORITIES)
    units = serializers.ChoiceField(choices=["metric", "imperial"])
    avoidMotorways = serializers.BooleanField(default=False)


class ValhallaLocationSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    name = serializers.CharField(required=False, allow_blank=True)


class ValhallaPayloadSerializer(serializers.Serializer):
    locations = ValhallaLocationSerializer(
        many=True,
        min_length=2,
    )
    costing = serializers.CharField()
    costing_options = serializers.DictField()
    directions_options = serializers.DictField()


class ExactLocationSerializer(StrictFieldsMixin, serializers.Serializer):
    latitude = FiniteFloatField(min_value=-90, max_value=90)
    longitude = FiniteFloatField(min_value=-180, max_value=180)


class GeometryPointSerializer(serializers.ListField):
    child = FiniteFloatField()

    def __init__(self, **kwargs):
        kwargs.setdefault("min_length", 2)
        kwargs.setdefault("max_length", 2)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        longitude, latitude = super().to_internal_value(data)
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise serializers.ValidationError("Geometry coordinates are out of range.")
        return [longitude, latitude]


class CoarseRouteAreaSerializer(StrictFieldsMixin, serializers.Serializer):
    latitudeBand = FiniteFloatField(min_value=-90, max_value=90)
    longitudeBand = FiniteFloatField(min_value=-180, max_value=180)
    precision = serializers.ChoiceField(choices=["0.1_degree"])


class MobileRouteDiagnosticSerializer(StrictFieldsMixin, serializers.Serializer):
    appVersion = serializers.CharField(max_length=50)
    buildProfile = serializers.CharField(max_length=50)
    routeProvider = serializers.CharField(max_length=50)
    routingMode = serializers.ChoiceField(
        choices=["hosted", "direct", "local_offline", "unknown"]
    )
    providerRequestId = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
    )
    graphDataVersion = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
    )
    routePreference = serializers.ChoiceField(
        choices=[*SUPPORTED_ROUTE_PRIORITIES, "unknown"]
    )
    vehicleProfile = serializers.ChoiceField(choices=SUPPORTED_VEHICLE_PROFILES)
    routeDistanceMetres = FiniteFloatField(min_value=0, max_value=10_000_000)
    routeDurationSeconds = FiniteFloatField(min_value=0, max_value=2_592_000)
    activeManeuverIndex = serializers.IntegerField(
        min_value=0,
        max_value=100_000,
        allow_null=True,
    )
    timestamp = serializers.DateTimeField()
    coarseArea = CoarseRouteAreaSerializer(required=False)


class ConsentedManeuverSerializer(StrictFieldsMixin, serializers.Serializer):
    instruction = serializers.CharField(max_length=500)
    type = serializers.CharField(max_length=50)
    bearingAfter = FiniteFloatField(min_value=0, max_value=360)
    legIndex = serializers.IntegerField(min_value=0, max_value=10_000, required=False)
    maneuverIndex = serializers.IntegerField(
        min_value=0,
        max_value=100_000,
        required=False,
    )


class ConsentedRouteDetailsSerializer(StrictFieldsMixin, serializers.Serializer):
    routeGeometry = serializers.ListField(
        child=GeometryPointSerializer(),
        min_length=2,
        max_length=5000,
    )
    start = ExactLocationSerializer()
    destination = ExactLocationSerializer()
    approximateIncidentLocation = ExactLocationSerializer(required=False)
    currentManeuver = ConsentedManeuverSerializer(required=False)


class MobileRouteIssueReportSerializer(StrictFieldsMixin, serializers.Serializer):
    id = serializers.CharField(max_length=100)
    dedupeKey = serializers.CharField(max_length=100)
    category = serializers.ChoiceField(
        choices=[
            "wrongWay",
            "closedRoad",
            "unsafeRoad",
            "unnecessarilyLong",
            "wrongEntrance",
            "incorrectInstruction",
            "other",
        ]
    )
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    roadName = serializers.CharField(max_length=120, required=False, allow_blank=True)
    instructedDirection = serializers.CharField(
        max_length=240,
        required=False,
        allow_blank=True,
    )
    believedLegalDirection = serializers.CharField(
        max_length=240,
        required=False,
        allow_blank=True,
    )
    diagnostics = MobileRouteDiagnosticSerializer()
    locationConsent = serializers.BooleanField()
    consentedRouteDetails = ConsentedRouteDetailsSerializer(required=False)
    createdAt = serializers.DateTimeField()
    retryCount = serializers.IntegerField(min_value=0, max_value=1000)
    lastAttemptAt = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        has_details = "consentedRouteDetails" in attrs
        if has_details and not attrs["locationConsent"]:
            raise serializers.ValidationError(
                {
                    "locationConsent": (
                        "locationConsent must be true when exact route details "
                        "are supplied."
                    )
                }
            )
        if attrs["locationConsent"] and not has_details:
            raise serializers.ValidationError(
                {
                    "consentedRouteDetails": (
                        "Exact route details are required when locationConsent is true."
                    )
                }
            )
        return attrs


MOBILE_CATEGORY_MAPPING = {
    "wrongWay": "wrong_way_or_one_way",
    "closedRoad": "closed_or_inaccessible_road",
    "unsafeRoad": "unsafe_or_unsuitable_road",
    "unnecessarilyLong": "route_unnecessarily_long",
    "wrongEntrance": "wrong_destination_entrance",
    "incorrectInstruction": "incorrect_instruction",
    "other": "other",
}


class RouteIssueReportSerializer(StrictFieldsMixin, serializers.Serializer):
    routeRequestId = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
    )
    category = serializers.ChoiceField(choices=ROUTE_REPORT_CATEGORIES)
    provider = serializers.CharField(max_length=50)
    engineVersion = serializers.CharField(max_length=100, required=False, allow_blank=True)
    graphBuildId = serializers.CharField(max_length=100, required=False, allow_blank=True)
    osmDataDate = serializers.CharField(max_length=50, required=False, allow_blank=True)
    roadPriority = serializers.ChoiceField(
        choices=[*SUPPORTED_ROUTE_PRIORITIES, "unknown"]
    )
    vehicleProfile = serializers.ChoiceField(choices=SUPPORTED_VEHICLE_PROFILES)
    distanceMetres = FiniteFloatField(min_value=0, max_value=10_000_000)
    durationSeconds = FiniteFloatField(min_value=0, max_value=2_592_000)
    manoeuvreIndex = serializers.IntegerField(
        min_value=0,
        max_value=100_000,
        required=False,
        allow_null=True,
    )
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    incidentTime = serializers.DateTimeField()
    locationConsent = serializers.BooleanField()
    exactLocation = ExactLocationSerializer(required=False)
    start = ExactLocationSerializer(required=False)
    destination = ExactLocationSerializer(required=False)
    routeGeometry = serializers.ListField(
        child=GeometryPointSerializer(),
        min_length=2,
        max_length=5000,
        required=False,
    )
    currentManeuver = ConsentedManeuverSerializer(required=False)
    clientReportId = serializers.CharField(max_length=100, required=False)
    clientDedupeKey = serializers.CharField(max_length=100, required=False)
    appVersion = serializers.CharField(max_length=50, required=False)
    buildProfile = serializers.CharField(max_length=50, required=False)
    routingMode = serializers.CharField(max_length=50, required=False)
    coarseArea = CoarseRouteAreaSerializer(required=False)
    roadName = serializers.CharField(max_length=120, required=False, allow_blank=True)
    instructedDirection = serializers.CharField(
        max_length=240,
        required=False,
        allow_blank=True,
    )
    believedLegalDirection = serializers.CharField(
        max_length=240,
        required=False,
        allow_blank=True,
    )

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = {
                key: value
                for key, value in data.items()
                if key not in {"userId", "user_id"}
            }
        if isinstance(data, dict) and "diagnostics" in data:
            mobile = MobileRouteIssueReportSerializer(data=data)
            mobile.is_valid(raise_exception=True)
            data = self._adapt_mobile_report(mobile.validated_data)
        return super().to_internal_value(data)

    @staticmethod
    def _adapt_mobile_report(report):
        diagnostics = report["diagnostics"]
        details = report.get("consentedRouteDetails", {})
        adapted = {
            "routeRequestId": diagnostics.get("providerRequestId", ""),
            "category": MOBILE_CATEGORY_MAPPING[report["category"]],
            "provider": diagnostics["routeProvider"],
            "graphBuildId": diagnostics.get("graphDataVersion", ""),
            "roadPriority": diagnostics["routePreference"],
            "vehicleProfile": diagnostics["vehicleProfile"],
            "distanceMetres": diagnostics["routeDistanceMetres"],
            "durationSeconds": diagnostics["routeDurationSeconds"],
            "manoeuvreIndex": diagnostics["activeManeuverIndex"],
            "notes": report.get("description", ""),
            "incidentTime": diagnostics["timestamp"],
            "locationConsent": report["locationConsent"],
            "exactLocation": details.get("approximateIncidentLocation"),
            "start": details.get("start"),
            "destination": details.get("destination"),
            "routeGeometry": details.get("routeGeometry"),
            "currentManeuver": details.get("currentManeuver"),
            "clientReportId": report["id"],
            "clientDedupeKey": report["dedupeKey"],
            "appVersion": diagnostics["appVersion"],
            "buildProfile": diagnostics["buildProfile"],
            "routingMode": diagnostics["routingMode"],
            "coarseArea": diagnostics.get("coarseArea"),
            "roadName": report.get("roadName", ""),
            "instructedDirection": report.get("instructedDirection", ""),
            "believedLegalDirection": report.get("believedLegalDirection", ""),
        }
        return {key: value for key, value in adapted.items() if value is not None}

    def validate(self, attrs):
        exact_fields = (
            "exactLocation",
            "start",
            "destination",
            "routeGeometry",
            "currentManeuver",
        )
        supplied_exact_fields = [field for field in exact_fields if field in attrs]
        if supplied_exact_fields and not attrs["locationConsent"]:
            raise serializers.ValidationError(
                {
                    "locationConsent": (
                        "locationConsent must be true when exact location data is supplied."
                    )
                }
            )
        return attrs

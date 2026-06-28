from rest_framework import serializers


class WaypointSerializer(serializers.Serializer):
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    name = serializers.CharField(required=False, allow_blank=True)


class RouteCalculationSerializer(serializers.Serializer):
    waypoints = WaypointSerializer(many=True, min_length=2)
    vehicleProfile = serializers.ChoiceField(choices=["car", "motorbike", "caravan"])
    roadPriority = serializers.ChoiceField(choices=["fastest", "balanced", "scenic"])
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

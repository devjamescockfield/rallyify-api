from rest_framework import serializers


class RouteCalculationSerializer(serializers.Serializer):
    locations = serializers.ListField(
        child=serializers.DictField(),
        min_length=2,
        required=True,
    )
    costing = serializers.CharField(default="bicycle", required=False)

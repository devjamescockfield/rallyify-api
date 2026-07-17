from rest_framework.throttling import AnonRateThrottle


class RouteBurstThrottle(AnonRateThrottle):
    scope = "route_burst"


class RouteSustainedThrottle(AnonRateThrottle):
    scope = "route_sustained"

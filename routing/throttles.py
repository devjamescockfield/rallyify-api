from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class RouteBurstThrottle(AnonRateThrottle):
    scope = "route_burst"


class RouteSustainedThrottle(AnonRateThrottle):
    scope = "route_sustained"


class RouteReportThrottle(UserRateThrottle):
    scope = "route_report"

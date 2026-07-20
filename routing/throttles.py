from rest_framework.throttling import (
    AnonRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)


class RouteBurstThrottle(AnonRateThrottle):
    scope = "route_burst"


class RouteSustainedThrottle(AnonRateThrottle):
    scope = "route_sustained"


class RouteReportUserBurstThrottle(UserRateThrottle):
    scope = "route_report_user_burst"


class RouteReportUserHourlyThrottle(UserRateThrottle):
    scope = "route_report_user_hourly"


class RouteReportUserDailyThrottle(UserRateThrottle):
    scope = "route_report_user_daily"


class RouteReportIPThrottle(AnonRateThrottle):
    scope = "route_report_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class RouteReportIPDailyThrottle(RouteReportIPThrottle):
    scope = "route_report_ip_daily"


class RouteReportGlobalThrottle(SimpleRateThrottle):
    scope = "route_report_global"

    def get_rate(self):
        return super().get_rate() or None

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": "all"}

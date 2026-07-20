import hashlib
import hmac
from dataclasses import dataclass

from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


@dataclass(frozen=True)
class BetaReporter:
    fingerprint: str

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def pk(self) -> str:
        return self.fingerprint


class BetaReportAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        authorization = get_authorization_header(request).split()
        if not authorization:
            return None
        if len(authorization) != 2 or authorization[0].decode().lower() != "bearer":
            raise AuthenticationFailed("Invalid authorization header.")

        try:
            supplied_token = authorization[1].decode()
        except UnicodeError as exc:
            raise AuthenticationFailed("Invalid bearer token.") from exc

        for configured_token in settings.ROUTE_REPORT_BEARER_TOKENS:
            if hmac.compare_digest(supplied_token, configured_token):
                fingerprint = hashlib.sha256(configured_token.encode()).hexdigest()
                return BetaReporter(fingerprint=fingerprint), fingerprint

        raise AuthenticationFailed("Invalid bearer token.")

    def authenticate_header(self, request):
        return self.keyword

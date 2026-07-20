import uuid
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings
import jwt
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


@dataclass(frozen=True)
class SupabaseUser:
    subject: str

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def pk(self) -> str:
        return self.subject


@lru_cache(maxsize=4)
def _get_jwks_client(
    jwks_url: str,
    cache_seconds: int,
    timeout_seconds: int,
) -> PyJWKClient:
    return PyJWKClient(
        jwks_url,
        cache_keys=False,
        cache_jwk_set=True,
        lifespan=cache_seconds,
        timeout=timeout_seconds,
    )


def get_supabase_signing_key(token: str):
    client = _get_jwks_client(
        settings.SUPABASE_JWKS_URL,
        settings.SUPABASE_JWKS_CACHE_SECONDS,
        settings.SUPABASE_JWKS_TIMEOUT_SECONDS,
    )
    return client.get_signing_key_from_jwt(token).key


def verify_supabase_access_token(token: str) -> str:
    try:
        signing_key = get_supabase_signing_key(token)
        decode_kwargs = {
            "key": signing_key,
            "algorithms": settings.SUPABASE_JWT_ALGORITHMS,
            "issuer": settings.SUPABASE_JWT_ISSUER,
            "leeway": settings.SUPABASE_JWT_LEEWAY_SECONDS,
            "options": {
                "require": ["exp", "iss", "sub", "role"],
                "verify_aud": bool(settings.SUPABASE_JWT_AUDIENCE),
            },
        }
        if settings.SUPABASE_JWT_AUDIENCE:
            decode_kwargs["audience"] = settings.SUPABASE_JWT_AUDIENCE
        claims = jwt.decode(token, **decode_kwargs)
    except (InvalidTokenError, PyJWKClientError, ValueError) as exc:
        raise AuthenticationFailed("Invalid or expired Supabase access token.") from exc

    if claims.get("role") != "authenticated":
        raise AuthenticationFailed("Supabase access token is not a user token.")

    subject = claims.get("sub")
    if not isinstance(subject, str):
        raise AuthenticationFailed("Supabase access token has no valid subject.")
    try:
        subject = str(uuid.UUID(subject))
    except ValueError as exc:
        raise AuthenticationFailed("Supabase access token has no valid subject.") from exc
    return subject


class SupabaseJWTAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        authorization = get_authorization_header(request).split()
        if not authorization:
            return None
        try:
            scheme = authorization[0].decode("ascii")
            token = authorization[1].decode("ascii") if len(authorization) == 2 else ""
        except UnicodeError as exc:
            raise AuthenticationFailed("Invalid authorization header.") from exc
        if len(authorization) != 2 or scheme.lower() != "bearer":
            raise AuthenticationFailed("Invalid authorization header.")

        subject = verify_supabase_access_token(token)
        return SupabaseUser(subject=subject), subject

    def authenticate_header(self, request):
        return self.keyword

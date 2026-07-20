from django.core.exceptions import ImproperlyConfigured


DEVELOPMENT_SECRET_KEY = "django-insecure-rallyify-dev-secret-key"
PROTECTED_ENVIRONMENTS = {"staging", "production"}
SUPPORTED_ENVIRONMENTS = {"development", *PROTECTED_ENVIRONMENTS}


def parse_boolean_environment_variable(
    name: str,
    value: str,
) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(
        f"{name} must be a boolean value such as true or false."
    )


def validate_runtime_configuration(
    *,
    deployment_environment: str,
    debug: bool,
    secret_key_env: str | None,
    allowed_hosts_env: str | None,
    supabase_url: str = "",
    supabase_jwt_issuer: str = "",
) -> None:
    if deployment_environment not in SUPPORTED_ENVIRONMENTS:
        supported = ", ".join(sorted(SUPPORTED_ENVIRONMENTS))
        raise ImproperlyConfigured(
            f"DEPLOYMENT_ENV must be one of: {supported}."
        )

    if deployment_environment not in PROTECTED_ENVIRONMENTS:
        return

    errors = []
    if debug:
        errors.append("DEBUG must be false")
    if not secret_key_env or not secret_key_env.strip() or secret_key_env in {
        DEVELOPMENT_SECRET_KEY,
        "replace-me",
    }:
        errors.append(
            "SECRET_KEY must be set to a non-placeholder value"
        )
    configured_hosts = {
        host.strip()
        for host in (allowed_hosts_env or "").split(",")
        if host.strip()
    }
    if not configured_hosts:
        errors.append("ALLOWED_HOSTS must be explicitly configured")
    elif "*" in configured_hosts:
        errors.append("ALLOWED_HOSTS must not contain '*'")
    normalized_supabase_url = supabase_url.rstrip("/")
    expected_issuer = f"{normalized_supabase_url}/auth/v1"
    if not normalized_supabase_url.startswith("https://"):
        errors.append("SUPABASE_URL must be an HTTPS project URL")
    if supabase_jwt_issuer != expected_issuer:
        errors.append(
            "SUPABASE_JWT_ISSUER must identify SUPABASE_URL /auth/v1"
        )

    if errors:
        message = "; ".join(errors)
        raise ImproperlyConfigured(
            f"Invalid {deployment_environment} configuration: {message}."
        )

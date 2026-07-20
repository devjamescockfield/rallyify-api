import pytest
from django.core.exceptions import ImproperlyConfigured

from config.runtime import (
    DEVELOPMENT_SECRET_KEY,
    parse_boolean_environment_variable,
    validate_runtime_configuration,
)


def validate_protected_environment(**overrides):
    values = {
        "deployment_environment": "staging",
        "debug": False,
        "secret_key_env": "a-real-staging-secret",
        "allowed_hosts_env": "api-dev.example.com",
        "report_tokens_env": "a-secure-beta-report-token-that-is-long-enough",
    }
    values.update(overrides)
    validate_runtime_configuration(**values)


def test_valid_staging_configuration_is_accepted():
    validate_protected_environment()


@pytest.mark.parametrize("deployment_environment", ["staging", "production"])
def test_debug_is_rejected_in_protected_environments(deployment_environment):
    with pytest.raises(ImproperlyConfigured, match="DEBUG must be false"):
        validate_protected_environment(
            deployment_environment=deployment_environment,
            debug=True,
        )


@pytest.mark.parametrize(
    "secret_key",
    [None, "", "   ", "replace-me", DEVELOPMENT_SECRET_KEY],
)
def test_missing_or_placeholder_secret_is_rejected(secret_key):
    with pytest.raises(ImproperlyConfigured, match="SECRET_KEY"):
        validate_protected_environment(secret_key_env=secret_key)


@pytest.mark.parametrize("allowed_hosts", [None, "", "  ", ", ,", "*"])
def test_missing_or_wildcard_allowed_hosts_are_rejected(allowed_hosts):
    with pytest.raises(ImproperlyConfigured, match="ALLOWED_HOSTS"):
        validate_protected_environment(allowed_hosts_env=allowed_hosts)


@pytest.mark.parametrize(
    "report_tokens",
    [None, "", "short", "replace-with-a-long-random-beta-token"],
)
def test_missing_or_insecure_report_tokens_are_rejected(report_tokens):
    with pytest.raises(ImproperlyConfigured, match="ROUTE_REPORT_BEARER_TOKENS"):
        validate_protected_environment(report_tokens_env=report_tokens)


def test_development_keeps_local_fallbacks_available():
    validate_runtime_configuration(
        deployment_environment="development",
        debug=True,
        secret_key_env=None,
        allowed_hosts_env=None,
    )


def test_unknown_deployment_environment_is_rejected():
    with pytest.raises(ImproperlyConfigured, match="DEPLOYMENT_ENV"):
        validate_protected_environment(deployment_environment="prod")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("YES", True), ("false", False), ("0", False)],
)
def test_debug_boolean_values_are_parsed_strictly(value, expected):
    assert parse_boolean_environment_variable("DEBUG", value) is expected


def test_invalid_debug_boolean_value_is_rejected():
    with pytest.raises(ImproperlyConfigured, match="DEBUG"):
        parse_boolean_environment_variable("DEBUG", "flase")

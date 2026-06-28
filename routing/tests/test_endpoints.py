import pytest


@pytest.mark.django_db
def test_health_returns_200(client):
    response = client.get("/health")

    assert response.status_code == 200


@pytest.mark.django_db
def test_health_includes_service_name(client):
    response = client.get("/health")

    assert response.json()["service"] == "rallyify-routing-api"


@pytest.mark.django_db
def test_calculate_route_returns_501(client):
    response = client.post(
        "/routes/calculate",
        data={},
        content_type="application/json",
    )

    assert response.status_code == 501
    assert response.json() == {
        "error": "Route calculation is not implemented yet.",
        "code": "NOT_IMPLEMENTED",
    }

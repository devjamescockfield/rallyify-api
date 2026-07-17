from io import BytesIO
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from scripts import compare_route_priorities, smoke_test_route


class MockResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return b'{"ok": true}'


def normalized_headers(request):
    return {name.lower(): value for name, value in request.header_items()}


def test_smoke_health_request_sends_cloudflare_friendly_headers(monkeypatch):
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        return MockResponse()

    monkeypatch.setattr(smoke_test_route, "urlopen", urlopen)

    status, body = smoke_test_route.get_json("https://example.com/health")

    assert status == 200
    assert body == {"ok": True}
    assert normalized_headers(requests[0]) == {
        "accept": "application/json",
        "user-agent": "Rallyify-Smoke-Test/1.0",
    }


@pytest.mark.parametrize(
    "module",
    [smoke_test_route, compare_route_priorities],
)
def test_route_request_sends_cloudflare_friendly_headers(module, monkeypatch):
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        return MockResponse()

    monkeypatch.setattr(module, "urlopen", urlopen)

    status, body = module.post_json(
        "https://example.com/routes/calculate",
        {"waypoints": []},
    )

    assert status == 200
    assert body == {"ok": True}
    assert normalized_headers(requests[0]) == {
        "accept": "application/json",
        "content-type": "application/json",
        "user-agent": "Rallyify-Smoke-Test/1.0",
    }


@pytest.mark.parametrize(
    "module",
    [smoke_test_route, compare_route_priorities],
)
def test_cloudflare_http_error_prints_response_diagnostics(
    module,
    monkeypatch,
    capsys,
):
    def urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {
                "Server": "cloudflare",
                "CF-Ray": "example-ray-LHR",
            },
            BytesIO(b"<html>Cloudflare challenge</html>"),
        )

    monkeypatch.setattr(module, "urlopen", urlopen)

    status, body = module.request_json(Request("https://example.com/health"))

    assert status == 403
    assert body == {"raw": "<html>Cloudflare challenge</html>"}
    assert capsys.readouterr().err == (
        "HTTP error status: 403\n"
        "Server: cloudflare\n"
        "CF-Ray: example-ray-LHR\n"
        "Response body:\n"
        "<html>Cloudflare challenge</html>\n"
    )

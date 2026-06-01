import asyncio

import pytest

from app.services import apify_client
from app.services.apify_client import ApifyClient, ApifyError, apify_health


def test_apify_health_without_token(monkeypatch) -> None:
    settings = apify_client.get_settings()
    monkeypatch.setattr(settings, "apify_api_token", "")

    result = asyncio.run(apify_health())

    assert result["key_configured"] is False
    assert result["available"] is False
    assert "APIFY_API_TOKEN" in result["error"]


def test_apify_run_actor_requires_token(monkeypatch) -> None:
    settings = apify_client.get_settings()
    monkeypatch.setattr(settings, "apify_api_token", "")

    client = ApifyClient()
    with pytest.raises(ApifyError, match="APIFY_API_TOKEN"):
        asyncio.run(client.run_actor("test/actor", {}))


def test_apify_run_actor_success(monkeypatch) -> None:
    settings = apify_client.get_settings()
    monkeypatch.setattr(settings, "apify_api_token", "test-token")
    monkeypatch.setattr(settings, "apify_timeout_seconds", 5.0)

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict, json: dict):
            return FakeResponse({"data": {"id": "run-1"}})

        async def get(self, url: str, *, headers: dict, params: dict | None = None):
            if "/actor-runs/" in url:
                return FakeResponse({"data": {"status": "SUCCEEDED", "defaultDatasetId": "dataset-1"}})
            if "/datasets/" in url:
                return FakeResponse(
                    [
                        {"title": "Backend Developer", "url": "https://linkedin.com/jobs/1", "description": "Python FastAPI"},
                    ]
                )
            return FakeResponse({"data": {}})

    monkeypatch.setattr(apify_client.httpx, "AsyncClient", FakeClient)

    client = ApifyClient()
    items = asyncio.run(client.run_actor("test/actor", {"queries": ["python"]}))

    assert len(items) == 1
    assert items[0]["title"] == "Backend Developer"

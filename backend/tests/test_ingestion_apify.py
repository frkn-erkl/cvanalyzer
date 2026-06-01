import asyncio
from unittest.mock import AsyncMock, patch

from app.services.ingestion import ingest_url


def test_ingest_url_use_apify_false_skips_apify(monkeypatch) -> None:
    async def run() -> None:
        with patch("app.services.apify_ingest.fetch_job_document_via_apify", new=AsyncMock()) as apify_mock:
            monkeypatch.setattr(
                "app.services.ingestion.extract_text_from_bytes",
                lambda content, filename, content_type: type(
                    "Extracted", (), {"text": "Job description text " * 5, "metadata": {}}
                )(),
            )

            class FakeResponse:
                status_code = 200
                content = b"<html>job</html>"
                headers = {"content-type": "text/html"}

                def raise_for_status(self) -> None:
                    return None

            class FakeClient:
                def __init__(self, **kwargs) -> None:
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb) -> None:
                    return None

                async def get(self, url: str, headers: dict):
                    return FakeResponse()

            monkeypatch.setattr("app.services.ingestion.httpx.AsyncClient", FakeClient)
            monkeypatch.setattr("app.services.ingestion.get_cached_text", lambda key: None)
            monkeypatch.setattr("app.services.ingestion.set_cached_text", lambda key, text, metadata: None)

            document = await ingest_url("job", "https://www.linkedin.com/jobs/view/123", use_apify=False)

            apify_mock.assert_not_called()
            assert document.metadata["source"] == "url"

    asyncio.run(run())


def test_ingest_url_use_apify_true_uses_apify_for_linkedin(monkeypatch) -> None:
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "apify_enabled", True)
    monkeypatch.setattr(settings, "apify_api_token", "token")

    async def run() -> None:
        from app.services.ingestion import IngestedDocument

        apify_document = IngestedDocument(
            "Detailed LinkedIn job posting " * 5,
            "job:apify:abc",
            {"source": "apify", "url": "https://www.linkedin.com/jobs/view/123"},
        )

        with patch(
            "app.services.apify_ingest.fetch_job_document_via_apify",
            new=AsyncMock(return_value=apify_document),
        ) as apify_mock:
            monkeypatch.setattr("app.services.ingestion.get_cached_text", lambda key: None)

            document = await ingest_url("job", "https://www.linkedin.com/jobs/view/123", use_apify=True)

            apify_mock.assert_awaited_once()
            assert document.metadata["source"] == "apify"

    asyncio.run(run())


def test_ingest_url_apify_fail_falls_back_to_httpx(monkeypatch) -> None:
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "apify_enabled", True)
    monkeypatch.setattr(settings, "apify_api_token", "token")

    async def run() -> None:
        with patch("app.services.apify_ingest.fetch_job_document_via_apify", new=AsyncMock(return_value=None)):
            monkeypatch.setattr(
                "app.services.ingestion.extract_text_from_bytes",
                lambda content, filename, content_type: type(
                    "Extracted", (), {"text": "Fallback job text " * 5, "metadata": {}}
                )(),
            )

            class FakeResponse:
                status_code = 200
                content = b"<html>job</html>"
                headers = {"content-type": "text/html"}

                def raise_for_status(self) -> None:
                    return None

            class FakeClient:
                def __init__(self, **kwargs) -> None:
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb) -> None:
                    return None

                async def get(self, url: str, headers: dict):
                    return FakeResponse()

            monkeypatch.setattr("app.services.ingestion.httpx.AsyncClient", FakeClient)
            monkeypatch.setattr("app.services.ingestion.get_cached_text", lambda key: None)
            monkeypatch.setattr("app.services.ingestion.set_cached_text", lambda key, text, metadata: None)

            document = await ingest_url("job", "https://www.kariyer.net/is-ilani/123", use_apify=True)

            assert document.metadata["source"] == "url"
            assert document.metadata.get("apify_fallback") is True

    asyncio.run(run())


def test_ingest_url_non_job_domain_skips_apify(monkeypatch) -> None:
    async def run() -> None:
        with patch("app.services.apify_ingest.fetch_job_document_via_apify", new=AsyncMock()) as apify_mock:
            monkeypatch.setattr(
                "app.services.ingestion.extract_text_from_bytes",
                lambda content, filename, content_type: type(
                    "Extracted", (), {"text": "Generic job text " * 5, "metadata": {}}
                )(),
            )

            class FakeResponse:
                status_code = 200
                content = b"<html>job</html>"
                headers = {"content-type": "text/html"}

                def raise_for_status(self) -> None:
                    return None

            class FakeClient:
                def __init__(self, **kwargs) -> None:
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb) -> None:
                    return None

                async def get(self, url: str, headers: dict):
                    return FakeResponse()

            monkeypatch.setattr("app.services.ingestion.httpx.AsyncClient", FakeClient)
            monkeypatch.setattr("app.services.ingestion.get_cached_text", lambda key: None)
            monkeypatch.setattr("app.services.ingestion.set_cached_text", lambda key, text, metadata: None)

        document = await ingest_url("job", "https://example.com/jobs/123", use_apify=True)

        apify_mock.assert_not_called()
        assert document.metadata["source"] == "url"
        assert "apify_fallback" not in document.metadata

    asyncio.run(run())

import asyncio

from app.services.job_search import preview_job_search


def test_preview_job_search_builds_actor_payloads(monkeypatch) -> None:
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "apify_enabled", True)
    monkeypatch.setattr(settings, "apify_api_token", "token")
    monkeypatch.setattr(settings, "apify_linkedin_search_actor_id", "linkedin/search")
    monkeypatch.setattr(settings, "apify_kariyer_search_actor_id", "kariyer/search")

    async def fake_suggest_job_titles(**kwargs):
        from app.models import JobTitleSuggestion, JobTitleSuggestionsResult

        return JobTitleSuggestionsResult(
            suggestions=[
                JobTitleSuggestion(
                    title="Backend Developer",
                    fit_score=80,
                    reason="test",
                    search_keywords=["python", "fastapi"],
                    evidence=["Python"],
                )
            ],
            current_titles=[],
            used_llm=False,
            warnings=[],
        )

    async def fake_ingest_text(kind, text):
        from app.services.ingestion import IngestedDocument

        return IngestedDocument(
            "Python FastAPI developer with Docker experience " * 3,
            "cv:test",
            {"source": "text", "chars": 100, "cache_hit": False},
        )

    monkeypatch.setattr("app.services.job_search.suggest_job_titles", fake_suggest_job_titles)
    monkeypatch.setattr("app.services.job_search.ingest_text", fake_ingest_text)

    preview = asyncio.run(
        preview_job_search(
            cv_text="Python FastAPI developer with Docker experience " * 3,
            cv_url=None,
            cv_file_content=None,
            cv_filename=None,
            cv_content_type=None,
            sources=["linkedin", "kariyer"],
            location="Istanbul",
            max_results=5,
        )
    )

    assert preview.search_queries
    assert preview.apify_ready is True
    assert len(preview.apify_actors) == 2
    linkedin = next(item for item in preview.apify_actors if item.source == "linkedin")
    assert linkedin.actor_id == "linkedin/search"
    assert linkedin.run_input["count"] == 10
    assert linkedin.run_input["scrapeCompany"] is True
    assert linkedin.run_input["splitByLocation"] is False
    assert len(linkedin.run_input["urls"]) >= 1
    assert linkedin.run_input["urls"][0].startswith("https://www.linkedin.com/jobs/search/?")

    kariyer = next(item for item in preview.apify_actors if item.source == "kariyer")
    assert kariyer.actor_id == "kariyer/search"
    assert kariyer.run_input["keyword"] == "Backend Developer"
    assert kariyer.run_input["startUrls"] == ["https://www.kariyer.net/is-ilanlari/istanbul"]
    assert kariyer.run_input["results_wanted"] == 5
    assert kariyer.run_input["max_job_age"] == "all"
    assert kariyer.run_input["proxyConfiguration"] == {"useApifyProxy": False}
    assert "location" not in kariyer.run_input

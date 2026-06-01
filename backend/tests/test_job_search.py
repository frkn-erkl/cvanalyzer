import asyncio

from app.services.job_listings import JobListingCandidate, normalize_linkedin_items
from app.services.job_search import _build_search_queries, _rank_candidates, search_jobs


class FakeSuggestion:
    def __init__(self, title: str, keywords: list[str]) -> None:
        self.title = title
        self.search_keywords = keywords


class FakeProfile:
    skills = ["Python", "FastAPI", "Docker"]


def test_build_search_queries_deduplicates() -> None:
    suggestions = [
        FakeSuggestion("Backend Developer", ["python", "fastapi"]),
        FakeSuggestion("Software Engineer", ["python", "backend"]),
    ]
    queries = _build_search_queries(suggestions, FakeProfile())

    assert "Backend Developer" in queries
    assert "python" in queries
    assert "Docker" in queries
    assert len(queries) <= 8


def test_normalize_linkedin_items_deduplicates_urls() -> None:
    items = [
        {"title": "Dev", "url": "https://linkedin.com/jobs/1", "description": "Build APIs with Python"},
        {"title": "Dev duplicate", "url": "https://linkedin.com/jobs/1", "description": "Duplicate"},
    ]
    candidates = normalize_linkedin_items(items)

    assert len(candidates) == 1
    assert candidates[0].title == "Dev"


def test_search_jobs_without_apify_returns_queries_only(monkeypatch) -> None:
    async def fake_suggest_job_titles(**kwargs):
        from app.models import JobTitleSuggestion, JobTitleSuggestionsResult

        return JobTitleSuggestionsResult(
            suggestions=[
                JobTitleSuggestion(
                    title="Backend Developer",
                    fit_score=80,
                    reason="test",
                    search_keywords=["python"],
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
            "Python developer with FastAPI experience " * 3,
            "cv:test",
            {"source": "text", "chars": 100, "cache_hit": False},
        )

    monkeypatch.setattr("app.services.job_search.suggest_job_titles", fake_suggest_job_titles)
    monkeypatch.setattr("app.services.job_search.ingest_text", fake_ingest_text)

    result = asyncio.run(
        search_jobs(
            cv_text="Python developer with FastAPI experience " * 3,
            cv_url=None,
            cv_file_content=None,
            cv_filename=None,
            cv_content_type=None,
            sources=["linkedin"],
            use_apify=False,
        )
    )

    assert result.used_apify is False
    assert result.listings == []
    assert result.search_queries
    assert any("Apify kapalı" in warning for warning in result.warnings)


def test_search_jobs_apify_disabled_on_server(monkeypatch) -> None:
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "apify_enabled", False)
    monkeypatch.setattr(settings, "apify_api_token", "token")

    async def fake_suggest_job_titles(**kwargs):
        from app.models import JobTitleSuggestion, JobTitleSuggestionsResult

        return JobTitleSuggestionsResult(
            suggestions=[
                JobTitleSuggestion(
                    title="Backend Developer",
                    fit_score=80,
                    reason="test",
                    search_keywords=["python"],
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
            "Python developer with FastAPI experience " * 3,
            "cv:test",
            {"source": "text", "chars": 100, "cache_hit": False},
        )

    monkeypatch.setattr("app.services.job_search.suggest_job_titles", fake_suggest_job_titles)
    monkeypatch.setattr("app.services.job_search.ingest_text", fake_ingest_text)

    result = asyncio.run(
        search_jobs(
            cv_text="Python developer with FastAPI experience " * 3,
            cv_url=None,
            cv_file_content=None,
            cv_filename=None,
            cv_content_type=None,
            sources=["linkedin"],
            use_apify=True,
        )
    )

    assert result.used_apify is False
    assert any("APIFY_ENABLED" in warning for warning in result.warnings)


def test_rank_candidates_orders_by_fit_score(monkeypatch) -> None:
    async def fake_score_match(cv_text, job_text, cv_profile, job_profile, metadata, **kwargs):
        from app.models import ScoreBreakdown

        score = 90 if "senior" in job_text.lower() else 60
        breakdown = ScoreBreakdown(
            overall=score,
            technical_skills=score,
            experience_seniority=score,
            domain_keywords=score,
            education_certifications=score,
            language_communication=score,
            ats_compatibility=score,
        )
        return breakdown, {}, []

    def fake_build_skill_matches(cv_profile, job_profile):
        return [], [], []

    monkeypatch.setattr("app.services.job_search.score_match", fake_score_match)
    monkeypatch.setattr("app.services.job_search.build_skill_matches", fake_build_skill_matches)

    candidates = [
        JobListingCandidate(
            source="linkedin",
            title="Junior Dev",
            company="A",
            location=None,
            url="https://linkedin.com/jobs/1",
            description="Junior Python role",
        ),
        JobListingCandidate(
            source="linkedin",
            title="Senior Dev",
            company="B",
            location=None,
            url="https://linkedin.com/jobs/2",
            description="Senior Python role",
        ),
    ]

    ranked = asyncio.run(_rank_candidates("Python CV " * 5, FakeProfile(), candidates))

    assert ranked[0].title == "Senior Dev"
    assert ranked[0].fit_score >= ranked[1].fit_score

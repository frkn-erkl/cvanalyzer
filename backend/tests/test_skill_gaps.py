import pytest

from app import db
from app.config import get_settings
from app.models import AnalysisResult
from app.services.skill_gaps import (
    backfill_skill_gaps_from_analyses,
    clear_skill_gaps,
    get_skill_gap_summary,
    job_key_from_url,
    normalize_skill_name,
    record_listing_gaps,
)


@pytest.fixture(autouse=True)
def isolated_skill_gaps(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "database_path", tmp_path / "skill_gaps.db")
    db.init_db()
    clear_skill_gaps()
    yield
    clear_skill_gaps()


def test_normalize_skill_name_maps_mongodb() -> None:
    assert normalize_skill_name("MongoDB") == "mongodb"
    assert normalize_skill_name("mongo db") == "mongodb"


def test_same_url_does_not_increase_listing_count() -> None:
    url = "https://www.kariyer.net/is-ilani/backend-dev-1"
    key = job_key_from_url(url)
    record_listing_gaps(
        job_key=key,
        job_url=url,
        job_title="Backend Developer",
        company="Acme",
        source="job_search",
        missing_required=["mongodb"],
        missing_preferred=[],
    )
    record_listing_gaps(
        job_key=key,
        job_url=url,
        job_title="Backend Developer",
        company="Acme",
        source="job_search",
        missing_required=["mongodb", "docker"],
        missing_preferred=[],
    )

    summary = get_skill_gap_summary()
    mongo = next(item for item in summary.aggregates if item.skill_name == "mongodb")
    docker = next(item for item in summary.aggregates if item.skill_name == "docker")

    assert mongo.listing_count == 1
    assert docker.listing_count == 1
    assert summary.total_listings == 1


def test_two_listings_aggregate_same_skill() -> None:
    record_listing_gaps(
        job_key=job_key_from_url("https://example.com/job-1"),
        job_url="https://example.com/job-1",
        job_title="Job 1",
        company=None,
        source="analysis",
        missing_required=["mongodb"],
        missing_preferred=[],
    )
    record_listing_gaps(
        job_key=job_key_from_url("https://example.com/job-2"),
        job_url="https://example.com/job-2",
        job_title="Job 2",
        company=None,
        source="llm_analysis",
        missing_required=["mongodb"],
        missing_preferred=[],
    )

    summary = get_skill_gap_summary()
    mongo = next(item for item in summary.aggregates if item.skill_name == "mongodb")

    assert mongo.listing_count == 2
    assert summary.total_listings == 2
    assert {listing.source for listing in mongo.listings} == {"analysis", "llm_analysis"}


def _minimal_analysis_result(analysis_id: str, *, analysis_mode: str | None = None) -> dict:
    payload = {
        "id": analysis_id,
        "status": "completed",
        "scores": {
            "overall": 50,
            "technical_skills": 40,
            "experience_seniority": 50,
            "domain_keywords": 50,
            "education_certifications": 50,
            "language_communication": 50,
            "ats_compatibility": 50,
        },
        "cv_profile": {
            "skills": [],
            "languages": [],
            "education": [],
            "years_experience": 3,
            "evidence": {},
        },
        "job_profile": {
            "required_skills": ["mongodb"],
            "preferred_skills": ["aws"],
            "languages": [],
            "education": [],
            "responsibilities": [],
            "keywords": [],
            "evidence": {},
        },
        "matched_required_skills": [],
        "missing_required_skills": [{"name": "mongodb", "matched": False, "evidence": []}],
        "missing_preferred_skills": [{"name": "aws", "matched": False, "evidence": []}],
        "strengths": [],
        "improvement_suggestions": [],
        "tailored_cv_suggestions": [],
        "warnings": [],
        "metadata": {
            "job": {"url": "https://example.com/job-backfill"},
            **({"analysis_mode": analysis_mode} if analysis_mode else {}),
        },
    }
    AnalysisResult.model_validate(payload)
    return payload


def test_backfill_imports_completed_analysis_once() -> None:
    db.create_analysis("analysis-backfill-1")
    db.update_analysis(
        "analysis-backfill-1",
        "completed",
        result=_minimal_analysis_result("analysis-backfill-1", analysis_mode="llm_only"),
    )

    imported = backfill_skill_gaps_from_analyses()
    summary = get_skill_gap_summary()
    mongo = next(item for item in summary.aggregates if item.skill_name == "mongodb")

    assert imported == 1
    assert mongo.listing_count == 1
    assert mongo.listings[0].source == "llm_analysis"

    assert backfill_skill_gaps_from_analyses() == 0


def test_clear_skill_gaps_empties_summary() -> None:
    record_listing_gaps(
        job_key=job_key_from_url("https://example.com/job-3"),
        job_url="https://example.com/job-3",
        job_title="Job 3",
        company=None,
        source="job_search",
        missing_required=["kubernetes"],
        missing_preferred=["aws"],
    )

    clear_skill_gaps()
    summary = get_skill_gap_summary()

    assert summary.total_skills == 0
    assert summary.total_listings == 0
    assert summary.aggregates == []

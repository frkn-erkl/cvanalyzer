import asyncio

from app.services import job_titles
from app.services.job_titles import _deterministic_suggestions, _extract_current_titles
from app.services.scoring import extract_cv_profile
from tests.test_scoring import CV_TEXT


def test_extract_current_titles_from_cv_headline() -> None:
    titles = _extract_current_titles(CV_TEXT)
    assert any("backend developer" in title.casefold() for title in titles)


def test_deterministic_job_title_suggestions_for_backend_cv() -> None:
    profile = extract_cv_profile(CV_TEXT)
    current_titles = _extract_current_titles(CV_TEXT)
    result = _deterministic_suggestions(profile, current_titles, "tr")

    assert result.used_llm is False
    assert len(result.suggestions) >= 2
    titles = " ".join(item.title.casefold() for item in result.suggestions)
    assert "backend" in titles or "python" in titles
    assert all(40 <= item.fit_score <= 98 for item in result.suggestions)
    assert all(item.search_keywords for item in result.suggestions)


def test_suggest_job_titles_falls_back_without_llm() -> None:
    result = asyncio.run(
        job_titles.suggest_job_titles(
            cv_text=CV_TEXT,
            cv_url=None,
            cv_file_content=None,
            cv_filename=None,
            cv_content_type=None,
            language="tr",
            use_llm=False,
        )
    )

    assert result.used_llm is False
    assert len(result.suggestions) >= 1


def test_suggest_job_titles_uses_llm_when_available(monkeypatch) -> None:
    async def fake_llm(_: str, profile, current_titles, language, *, llm_provider="local"):
        from app.models import JobTitleSuggestion, JobTitleSuggestionsResult

        return JobTitleSuggestionsResult(
            suggestions=[
                JobTitleSuggestion(
                    title="Senior Backend Developer",
                    fit_score=90,
                    reason="Python and FastAPI experience",
                    search_keywords=["Senior Backend Developer", "Python"],
                    evidence=["6 years Python experience"],
                )
            ],
            current_titles=current_titles,
            used_llm=True,
        )

    monkeypatch.setattr(job_titles, "_llm_suggestions", fake_llm)

    async def fake_translate(text: str, *, purpose: str, provider=None):
        return text, {}

    monkeypatch.setattr(job_titles, "ensure_english_for_llm", fake_translate)

    result = asyncio.run(
        job_titles.suggest_job_titles(
            cv_text=CV_TEXT,
            cv_url=None,
            cv_file_content=None,
            cv_filename=None,
            cv_content_type=None,
            language="en",
            use_llm=True,
        )
    )

    assert result.used_llm is True
    assert result.suggestions[0].title == "Senior Backend Developer"

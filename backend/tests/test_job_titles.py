import asyncio

from app.services import job_titles
from app.services.job_titles import (
    _deterministic_suggestions,
    _extract_current_titles,
    _extract_job_titles_payload,
    _suggestions_from_payload,
)
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
    async def fake_llm(_: str, profile, current_titles, language, **kwargs):
        from app.models import JobTitleSuggestion, JobTitleSuggestionsResult

        return (
            JobTitleSuggestionsResult(
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
            ),
            None,
            None,
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


def test_extract_job_titles_payload_reads_json_from_thinking_when_response_empty() -> None:
    thinking = 'Plan complete.\n{"suggestions": [{"title": "Flutter Developer", "fit_score": 85, "reason": "ok", "search_keywords": ["Flutter"], "evidence": ["Dart"]}]}'
    payload = _extract_job_titles_payload("", thinking)
    assert payload is not None
    assert payload["suggestions"][0]["title"] == "Flutter Developer"


def test_suggest_job_titles_preserves_thinking_on_llm_json_failure(monkeypatch) -> None:
    async def failing_llm(*args, **kwargs):
        return None, "Yerel LLM düşünme tamamlandı ancak JSON yanıtı üretilemedi.", "Model planı burada."

    monkeypatch.setattr(job_titles, "_llm_suggestions", failing_llm)

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
            language="tr",
            use_llm=True,
        )
    )

    assert result.used_llm is False
    assert result.llm_thinking == "Model planı burada."
    assert any("JSON yanıtı üretilemedi" in warning for warning in result.warnings)


def test_suggestions_from_payload_builds_result() -> None:
    profile = extract_cv_profile(CV_TEXT)
    payload = {
        "suggestions": [
            {
                "title": "Mobile Developer",
                "fit_score": 82,
                "reason": "Flutter experience",
                "search_keywords": ["Mobile Developer", "Flutter"],
                "evidence": ["Built mobile apps"],
            }
        ]
    }
    result = _suggestions_from_payload(payload, profile=profile, current_titles=[], thinking="short plan")
    assert result is not None
    assert result.used_llm is True
    assert result.suggestions[0].title == "Mobile Developer"
    assert result.llm_thinking == "short plan"

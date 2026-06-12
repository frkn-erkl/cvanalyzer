import asyncio

import pytest

from app.services import cv_guided_edit
from app.models import CvEditSuggestion
from app.services.cv_guided_edit import (
    _apply_result_from_payload,
    _deterministic_fallback,
    _extract_cv_edit_payload,
    _suggestions_from_payload,
    apply_cv_edits,
)
from app.services.scoring import extract_cv_profile
from tests.test_scoring import CV_TEXT


def test_empty_guidance_raises() -> None:
    with pytest.raises(ValueError, match="yönlendirmesi gerekli"):
        asyncio.run(
            cv_guided_edit.suggest_cv_edits(
                cv_text=CV_TEXT,
                cv_url=None,
                cv_file_content=None,
                cv_filename=None,
                cv_content_type=None,
                guidance="   ",
            )
        )


def test_suggest_cv_edits_falls_back_without_llm() -> None:
    result = asyncio.run(
        cv_guided_edit.suggest_cv_edits(
            cv_text=CV_TEXT,
            cv_url=None,
            cv_file_content=None,
            cv_filename=None,
            cv_content_type=None,
            guidance="İyi bir endüstri mühendisi CV görünümü için öneriler",
            language="tr",
            use_llm=False,
        )
    )

    assert result.used_llm is False
    assert result.llm_requested is False
    assert result.overall_assessment
    assert len(result.suggestions) >= 1


def test_suggest_cv_edits_uses_llm_when_available(monkeypatch) -> None:
    async def fake_llm(_: str, profile, guidance, language, **kwargs):
        from app.models import CvEditSuggestion, CvEditSuggestionsResult

        return (
            CvEditSuggestionsResult(
                overall_assessment="CV is strong but layout could be more ATS-friendly.",
                suggestions=[
                    CvEditSuggestion(
                        category="layout",
                        title="Use clear section headings",
                        recommendation="Add distinct headings for Experience, Education, and Skills.",
                        priority="high",
                        evidence=["6 years Python experience"],
                    )
                ],
                strengths=["Strong backend experience"],
                gaps=["Limited metrics in bullets"],
                used_llm=True,
                llm_thinking="thinking trace",
            ),
            None,
            "thinking trace",
        )

    monkeypatch.setattr(cv_guided_edit, "_llm_suggestions", fake_llm)

    async def fake_translate(text: str, *, purpose: str, provider=None):
        return text, {}

    monkeypatch.setattr(cv_guided_edit, "ensure_english_for_llm", fake_translate)

    result = asyncio.run(
        cv_guided_edit.suggest_cv_edits(
            cv_text=CV_TEXT,
            cv_url=None,
            cv_file_content=None,
            cv_filename=None,
            cv_content_type=None,
            guidance="Professional industrial engineer CV layout suggestions",
            language="en",
            use_llm=True,
            llm_provider="cursor",
        )
    )

    assert result.used_llm is True
    assert result.suggestions[0].category == "layout"
    assert result.strengths == ["Strong backend experience"]
    assert result.llm_thinking == "thinking trace"


def test_extract_cv_edit_payload_from_json() -> None:
    payload = _extract_cv_edit_payload(
        '{"overall_assessment":"ok","suggestions":[{"title":"A","recommendation":"B"}]}',
        None,
    )
    assert payload is not None
    assert isinstance(payload.get("suggestions"), list)


def test_suggestions_from_payload_parses_items() -> None:
    profile = extract_cv_profile(CV_TEXT)
    result = _suggestions_from_payload(
        {
            "overall_assessment": "Genel değerlendirme",
            "strengths": ["Python deneyimi"],
            "gaps": ["Metrik eksikliği"],
            "suggestions": [
                {
                    "category": "content",
                    "title": "Profil özeti ekle",
                    "recommendation": "Üst bölüme kısa bir özet ekleyin.",
                    "priority": "high",
                    "evidence": ["Backend Developer"],
                }
            ],
        },
        profile=profile,
        thinking="trace",
    )

    assert result is not None
    assert result.overall_assessment == "Genel değerlendirme"
    assert len(result.suggestions) == 1
    assert result.suggestions[0].priority == "high"
    assert result.used_llm is True


def test_deterministic_fallback_includes_guidance_hint() -> None:
    profile = extract_cv_profile(CV_TEXT)
    result = _deterministic_fallback(profile, "Endüstri mühendisi CV görünümü", "tr")

    assert result.used_llm is False
    assert "Endüstri mühendisi" in result.overall_assessment
    assert len(result.suggestions) >= 1


def test_apply_cv_edits_requires_suggestions() -> None:
    with pytest.raises(ValueError, match="önerisi bulunamadı"):
        asyncio.run(
            apply_cv_edits(
                cv_text=CV_TEXT,
                cv_url=None,
                cv_file_content=None,
                cv_filename=None,
                cv_content_type=None,
                guidance="Profesyonel CV düzeni",
                suggestions=[],
                language="tr",
            )
        )


def test_apply_cv_edits_uses_llm_when_available(monkeypatch) -> None:
    async def fake_apply_llm(*args, **kwargs):
        from app.models import CvEditApplyResult

        return (
            CvEditApplyResult(
                updated_cv_text="John Doe\nBackend Developer\n\nExperience\n- Built APIs with Python",
                changes=[],
                warnings=[],
                used_llm=True,
                llm_thinking="apply trace",
            ),
            None,
            "apply trace",
        )

    monkeypatch.setattr(cv_guided_edit, "_llm_apply_edits", fake_apply_llm)

    async def fake_translate(text: str, *, purpose: str, provider=None):
        return text, {}

    monkeypatch.setattr(cv_guided_edit, "ensure_english_for_llm", fake_translate)

    suggestions = [
        CvEditSuggestion(
            category="content",
            title="Profil özeti ekle",
            recommendation="Üst bölüme kısa bir özet ekleyin.",
            priority="high",
            evidence=["Backend Developer"],
        )
    ]

    result = asyncio.run(
        apply_cv_edits(
            cv_text=CV_TEXT,
            cv_url=None,
            cv_file_content=None,
            cv_filename=None,
            cv_content_type=None,
            guidance="Profesyonel CV düzeni",
            suggestions=suggestions,
            language="tr",
            llm_provider="cursor",
        )
    )

    assert result.used_llm is True
    assert "Backend Developer" in result.updated_cv_text
    assert result.llm_thinking == "apply trace"


def test_apply_result_from_payload_requires_minimum_length() -> None:
    assert _apply_result_from_payload({"updated_cv_text": "short"}, thinking=None) is None

    result = _apply_result_from_payload(
        {
            "updated_cv_text": "A" * 120,
            "changes": [{"section": "Summary", "reason": "Added profile summary"}],
            "warnings": ["Kept all employers unchanged"],
        },
        thinking="trace",
    )

    assert result is not None
    assert len(result.updated_cv_text) >= 80
    assert result.changes[0].section == "Summary"

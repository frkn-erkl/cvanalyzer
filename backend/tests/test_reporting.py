import asyncio

from app.models import AnalysisResult
from app.models import ScoreBreakdown
from app.services import reporting
from app.services.reporting import (
    _LLM_SUMMARY_SYSTEM,
    _build_llm_summary_prompt,
    build_cv_add_suggestions,
    build_suggested_profile_summary,
    llm_summary,
)
from app.services.scoring import build_skill_matches, extract_cv_profile, extract_job_profile
from tests.test_scoring import CV_TEXT, JOB_TEXT


def test_build_suggested_profile_summary_uses_matched_skills() -> None:
    cv = extract_cv_profile(CV_TEXT)
    job = extract_job_profile(JOB_TEXT)
    matched, _, _ = build_skill_matches(cv, job)

    summary = build_suggested_profile_summary(cv, job, matched)

    assert "python" in summary.casefold()
    assert "fastapi" in summary.casefold()
    assert "kubernetes" not in summary.casefold()
    assert len(summary.split()) >= 20
    assert "ats" in summary.casefold()
    assert "Senior Backend Developer" in summary or "backend" in summary.casefold()


def test_build_cv_add_suggestions_lists_missing_required_skills() -> None:
    cv = extract_cv_profile(CV_TEXT)
    job = extract_job_profile(JOB_TEXT)
    _, missing_required, missing_preferred = build_skill_matches(cv, job)
    scores = ScoreBreakdown(
        overall=70,
        technical_skills=70,
        experience_seniority=80,
        domain_keywords=60,
        education_certifications=80,
        language_communication=80,
        ats_compatibility=55,
    )

    suggestions = build_cv_add_suggestions(cv, job, scores, missing_required, missing_preferred, CV_TEXT)

    titles = {item.title for item in suggestions}
    assert "kubernetes" in titles
    assert any(item.category == "preferred_skill" for item in suggestions)
    assert all(item.how_to_add for item in suggestions)


def test_build_cv_add_suggestions_includes_preferred_skills() -> None:
    cv = extract_cv_profile(CV_TEXT)
    job = extract_job_profile(JOB_TEXT)
    _, missing_required, missing_preferred = build_skill_matches(cv, job)
    scores = ScoreBreakdown(
        overall=70,
        technical_skills=70,
        experience_seniority=80,
        domain_keywords=60,
        education_certifications=80,
        language_communication=80,
        ats_compatibility=55,
    )

    suggestions = build_cv_add_suggestions(cv, job, scores, missing_required, missing_preferred, CV_TEXT)

    assert any(item.category == "preferred_skill" for item in suggestions)


def test_llm_summary_prompt_includes_quality_context(monkeypatch) -> None:
    cv = extract_cv_profile(CV_TEXT)
    job = extract_job_profile(JOB_TEXT)
    matched, missing_required, missing_preferred = build_skill_matches(cv, job)
    result = AnalysisResult(
        id="analysis-1",
        status="completed",
        scores=ScoreBreakdown(
            overall=82,
            technical_skills=90,
            experience_seniority=88,
            domain_keywords=80,
            education_certifications=80,
            language_communication=100,
            ats_compatibility=70,
        ),
        cv_profile=cv,
        job_profile=job,
        matched_required_skills=matched,
        missing_required_skills=missing_required,
        missing_preferred_skills=missing_preferred,
        strengths=["Python ve FastAPI deneyimi güçlü."],
        improvement_suggestions=["Kubernetes deneyimi varsa proje kanıtıyla görünür kılın."],
        tailored_cv_suggestions=["Profil özetini backend role göre yaz."],
        warnings=[],
        suggested_profile_summary="Senior backend profile summary candidate.",
    )
    captured: dict[str, object] = {}

    class FakeLLM:
        async def generate(self, prompt: str, **kwargs):
            captured["prompt"] = prompt
            captured["kwargs"] = kwargs
            return "rapor"

    monkeypatch.setattr(reporting, "get_llm_client", lambda provider=None: FakeLLM())

    summary, thinking = asyncio.run(llm_summary(result))

    assert summary == "rapor"
    assert thinking is None
    prompt = str(captured["prompt"])
    assert "## Karar" in prompt
    assert "Deterministik güçlü yönler" in prompt
    assert "bilgi uydurma" in prompt.casefold()
    assert captured["kwargs"] == {
        "system": _LLM_SUMMARY_SYSTEM,
        "temperature": 0.1,
        "num_predict": 700,
        "translate_input": False,
        "on_progress": None,
    }


def test_build_llm_summary_prompt_uses_turkish_empty_labels() -> None:
    cv = extract_cv_profile(CV_TEXT)
    job = extract_job_profile(JOB_TEXT)
    matched, missing_required, missing_preferred = build_skill_matches(cv, job)
    result = AnalysisResult(
        id="analysis-2",
        status="completed",
        scores=ScoreBreakdown(
            overall=50,
            technical_skills=40,
            experience_seniority=50,
            domain_keywords=45,
            education_certifications=70,
            language_communication=80,
            ats_compatibility=60,
        ),
        cv_profile=cv,
        job_profile=job,
        matched_required_skills=[],
        missing_required_skills=missing_required,
        missing_preferred_skills=missing_preferred,
        strengths=[],
        improvement_suggestions=[],
        tailored_cv_suggestions=[],
        warnings=[],
        suggested_profile_summary=None,
    )

    prompt = _build_llm_summary_prompt(result)

    assert "Eşleşen zorunlu beceriler: yok" in prompt
    assert "- yok" in prompt
    assert "## Güçlü yönler" in prompt

from app.models import (
    AnalysisResult,
    CvRewriteRequest,
    ScoreBreakdown,
    SkillMatch,
    StructuredJob,
    StructuredProfile,
)
from app.services.cv_rewrite import _build_prompt, _fallback_rewrite, _rewrite_quality_warnings, detect_unsupported_claims


def _analysis() -> AnalysisResult:
    return AnalysisResult(
        id="analysis-1",
        status="completed",
        scores=ScoreBreakdown(
            overall=62,
            technical_skills=60,
            experience_seniority=58,
            domain_keywords=55,
            education_certifications=85,
            language_communication=100,
            ats_compatibility=70,
        ),
        cv_profile=StructuredProfile(
            skills=["python", "fastapi", "postgresql"],
            languages=["ingilizce"],
            education=["Bilgisayar Mühendisliği lisans"],
            years_experience=3,
            seniority="mid",
            highlights=["Python ve FastAPI ile REST API geliştirdim."],
            evidence={"python": ["Python ve FastAPI ile REST API geliştirdim."]},
        ),
        job_profile=StructuredJob(
            required_skills=["python", "fastapi", "kubernetes"],
            preferred_skills=["aws"],
            languages=["ingilizce"],
            seniority="senior",
        ),
        matched_required_skills=[
            SkillMatch(name="python", matched=True),
            SkillMatch(name="fastapi", matched=True),
        ],
        missing_required_skills=[SkillMatch(name="kubernetes", matched=False)],
        missing_preferred_skills=[SkillMatch(name="aws", matched=False)],
        strengths=["Python ve FastAPI deneyimi var."],
        improvement_suggestions=["Kubernetes eksik."],
        tailored_cv_suggestions=["REST API deneyimini öne çıkar."],
        warnings=[],
        metadata={},
    )


def test_fallback_rewrite_does_not_add_missing_skills() -> None:
    analysis = _analysis()
    result = _fallback_rewrite(
        analysis,
        "Python ve FastAPI ile REST API geliştirdim.",
        CvRewriteRequest(deep_rewrite=False),
        "rewrite-1",
    )

    assert "python" in result.updated_cv_text.casefold()
    assert "fastapi" in result.updated_cv_text.casefold()
    assert "kubernetes" not in result.updated_cv_text.casefold()
    assert result.omitted_missing_skills == ["kubernetes", "aws"]
    assert result.language == "en"
    assert result.rewrite_id == "rewrite-1"
    assert "PROFILE SUMMARY" in result.updated_cv_text
    assert "ORIGINAL CV TEXT" not in result.updated_cv_text
    assert "ORIJINAL CV METNI" not in result.updated_cv_text.upper()


def test_fallback_rewrite_supports_turkish() -> None:
    analysis = _analysis()
    result = _fallback_rewrite(
        analysis,
        "Python ve FastAPI ile REST API geliştirdim.",
        CvRewriteRequest(language="tr", deep_rewrite=False),
        "rewrite-2",
    )

    assert result.language == "tr"
    assert "PROFIL OZETI" in result.updated_cv_text
    assert "ORIJINAL CV METNI" not in result.updated_cv_text.upper()


def test_sanitize_cv_output_removes_original_cv_appendix() -> None:
    from app.services.cv_rewrite import _sanitize_cv_output

    cleaned = _sanitize_cv_output(
        "PROFILE SUMMARY\nExperienced developer.\n\nORIGINAL CV TEXT\nOld CV content that should be removed."
    )

    assert cleaned == "PROFILE SUMMARY\nExperienced developer."
    assert "Old CV content" not in cleaned


def test_detect_unsupported_claims_blocks_missing_skill_and_seniority() -> None:
    analysis = _analysis()
    claims = detect_unsupported_claims(
        "Senior Backend Developer olarak Python, FastAPI, Kubernetes ve AWS deneyimim var.",
        analysis,
        "Python ve FastAPI ile REST API geliştirdim.",
    )

    blocked = {claim.claim for claim in claims if claim.severity == "blocked"}
    assert {"kubernetes", "aws", "senior/lead seviye iddiası"} <= blocked


def test_build_prompt_includes_quality_strategy_and_evidence() -> None:
    analysis = _analysis()
    prompt = _build_prompt(
        analysis,
        "Python ve FastAPI ile REST API geliştirdim.",
        "Senior backend role with Python, FastAPI, Kubernetes and AWS.",
        CvRewriteRequest(language="en", deep_rewrite=True),
    )

    assert "Writing strategy" in prompt
    assert "Strong CV evidence to preserve" in prompt
    assert "Suggested profile summary" in prompt
    assert "technology + responsibility + outcome" in prompt
    assert "Skills that must NOT be added to the CV: kubernetes, aws" in prompt


def test_rewrite_quality_warnings_flag_short_or_unverified_output() -> None:
    analysis = _analysis()
    warnings = _rewrite_quality_warnings(
        "PROFILE SUMMARY\nSenior developer with Kubernetes and AWS.",
        analysis,
        "en",
    )

    assert any("short" in warning for warning in warnings)
    assert any("kubernetes" in warning.casefold() for warning in warnings)
    assert any("aws" in warning.casefold() for warning in warnings)

import asyncio

from app.services import scoring
from app.services.scoring import build_skill_matches, extract_cv_profile, extract_job_profile, score_match


CV_TEXT = """
Senior Backend Developer
6 yıl Python, FastAPI, PostgreSQL, Docker ve AWS deneyimi.
REST API geliştirme, CI/CD ve mikroservis projelerinde görev aldım.
İngilizce profesyonel çalışma yetkinliği.
Bilgisayar Mühendisliği lisans.
"""

JOB_TEXT = """
Senior Backend Developer aranıyor.
Zorunlu gereklilikler: Python, FastAPI, PostgreSQL, Docker, AWS.
Tercihen Kubernetes ve Kafka deneyimi.
İngilizce iletişim beklenir.
"""


def test_extract_profiles_and_skill_matches() -> None:
    cv = extract_cv_profile(CV_TEXT)
    job = extract_job_profile(JOB_TEXT)
    matched, missing_required, missing_preferred = build_skill_matches(cv, job)

    assert "python" in cv.skills
    assert "fastapi" in job.required_skills
    assert {item.name for item in matched} >= {"python", "fastapi", "postgresql", "docker", "aws"}
    assert missing_required == []
    assert {item.name for item in missing_preferred} == {"kafka", "kubernetes"}


def test_score_match_uses_mocked_semantic_similarity(monkeypatch) -> None:
    async def fake_similarity(_: str, __: str) -> float:
        return 0.82

    monkeypatch.setattr(scoring, "semantic_similarity", fake_similarity)
    cv = extract_cv_profile(CV_TEXT)
    job = extract_job_profile(JOB_TEXT)
    scores, metrics, details = asyncio.run(score_match(CV_TEXT, JOB_TEXT, cv, job))

    assert scores.overall >= 80
    assert scores.technical_skills >= 75
    assert scores.ats_compatibility >= 35
    assert metrics["semantic_similarity"] == 0.82
    assert len(details) == 7
    assert any(detail.key == "ats_compatibility" for detail in details)
    assert details[1].key == "technical_skills"
    assert any("Zorunlu beceri eşleşmesi" in factor for factor in details[1].factors)


def test_score_ats_compatibility_rewards_structured_cv() -> None:
    structured_cv = """
John Doe
john.doe@example.com | +90 555 123 4567 | linkedin.com/in/johndoe

PROFILE SUMMARY
Backend developer with 5 years of experience.

SKILLS
Python, FastAPI, PostgreSQL, Docker, AWS

EXPERIENCE
- Built REST APIs with Python and FastAPI in 2021-2024.
- Deployed services with Docker and AWS in 2022.

EDUCATION
Bachelor of Computer Engineering, 2019
"""
    score, factors = scoring.score_ats_compatibility(structured_cv, {"format": "text", "source": "text"})
    assert score >= 75
    assert any("E-posta" in factor for factor in factors)
    assert any("ATS" in factor or "Madde" in factor for factor in factors)


def test_score_ats_compatibility_penalizes_noisy_pdf_text() -> None:
    noisy_cv = "Name\n�email broken�\n" + ("long unstructured block " * 80)
    score, factors = scoring.score_ats_compatibility(noisy_cv, {"format": "pdf", "source": "file"})
    assert score < 60
    assert any("bozuk karakter" in factor for factor in factors)

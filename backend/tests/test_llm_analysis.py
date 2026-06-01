import asyncio

from app.models import AnalysisResult
from app.services import llm_analysis
from app.services.llm_analysis import _map_payload_to_result, _normalize_payload, _validate_payload
from tests.test_scoring import CV_TEXT, JOB_TEXT


SAMPLE_LLM_PAYLOAD = {
    "scores": {
        "overall": 84,
        "technical_skills": 88,
        "experience_seniority": 82,
        "domain_keywords": 76,
        "education_certifications": 70,
        "language_communication": 85,
        "ats_compatibility": 72,
    },
    "score_details": [
        {
            "key": "technical_skills",
            "label": "Teknik beceriler",
            "score": 88,
            "weight": "Genel skora %38 katkı",
            "method": "CV ve ilan zorunlu becerileri karşılaştırıldı.",
            "factors": ["Python, FastAPI, PostgreSQL eşleşiyor."],
        }
    ],
    "cv_profile": {
        "skills": ["python", "fastapi", "postgresql", "docker", "aws"],
        "languages": ["English"],
        "education": ["Computer Engineering"],
        "certifications": [],
        "years_experience": 6,
        "seniority": "senior",
        "highlights": ["6 years Python and FastAPI experience"],
        "evidence": {},
    },
    "job_profile": {
        "required_skills": ["python", "fastapi", "postgresql", "docker", "aws"],
        "preferred_skills": ["kubernetes", "kafka"],
        "languages": ["English"],
        "education": [],
        "seniority": "senior",
        "responsibilities": ["Build backend services"],
        "keywords": ["backend", "api"],
        "evidence": {},
    },
    "matched_required_skills": [
        {
            "name": "python",
            "matched": True,
            "evidence": [{"label": "CV", "source": "cv", "snippet": "6 yıl Python deneyimi"}],
        }
    ],
    "missing_required_skills": [],
    "missing_preferred_skills": [
        {
            "name": "kubernetes",
            "matched": False,
            "evidence": [{"label": "Job", "source": "job", "snippet": "Tercihen Kubernetes deneyimi"}],
        }
    ],
    "strengths": ["Teknik beceriler ilanla güçlü örtüşüyor."],
    "improvement_suggestions": ["Kubernetes deneyimi varsa görünür kılın."],
    "tailored_cv_suggestions": ["Deneyim maddelerinde ölçülebilir etki vurgulayın."],
    "cv_add_suggestions": [
        {
            "title": "Kubernetes",
            "category": "preferred_skill",
            "priority": "medium",
            "reason": "İlan tercih edilen beceri olarak belirtiyor.",
            "how_to_add": "Yalnızca gerçek deneyim varsa ekleyin.",
            "job_evidence": ["Tercihen Kubernetes deneyimi"],
        }
    ],
    "suggested_profile_summary": "Kıdemli backend geliştirici; Python ve FastAPI deneyimi.",
    "llm_summary": "## Karar\nCV bu ilan için güçlü.\n\n## Güçlü yönler\n- Python deneyimi\n\n## Kritik boşluklar\n- Kubernetes\n\n## Önerilen profil özeti\nKıdemli backend geliştirici.\n\n## CV'ye somut adımlar\n- Ölçülebilir etki ekleyin.",
    "warnings": ["Skorlar LLM yorumuna dayanır."],
}


def test_validate_payload_accepts_complete_llm_analysis() -> None:
    assert _validate_payload(SAMPLE_LLM_PAYLOAD) is True


def test_validate_payload_rejects_missing_scores() -> None:
    payload = dict(SAMPLE_LLM_PAYLOAD)
    payload.pop("scores")
    assert _validate_payload(payload) is False


def test_map_payload_to_result_builds_analysis_result() -> None:
    result = _map_payload_to_result("analysis-1", SAMPLE_LLM_PAYLOAD)

    assert isinstance(result, AnalysisResult)
    assert result.id == "analysis-1"
    assert result.scores.overall == 84
    assert result.scores.technical_skills == 88
    assert len(result.score_details) == 7
    assert result.matched_required_skills[0].name == "python"
    assert result.missing_preferred_skills[0].name == "kubernetes"
    assert result.llm_summary.startswith("## Karar")
    assert result.cv_add_suggestions[0].title == "Kubernetes"


def test_normalize_payload_builds_summary_when_missing() -> None:
    payload = dict(SAMPLE_LLM_PAYLOAD)
    payload.pop("llm_summary")

    normalized = _normalize_payload(payload)

    assert _validate_payload(normalized) is True
    assert normalized["llm_summary"].startswith("## Karar")


def test_run_llm_analysis_fails_when_ollama_unavailable(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_update(analysis_id: str, status: str, *, error: str | None = None, result=None) -> None:
        captured["status"] = status
        captured["error"] = error

    async def fake_translate(text: str, *, purpose: str, provider=None):
        return text, {}

    class FakeLLM:
        async def health(self):
            return {"available": False, "error": "connection refused"}

    monkeypatch.setattr(llm_analysis.db, "update_analysis", fake_update)
    monkeypatch.setattr(llm_analysis, "ensure_english_for_llm", fake_translate)
    monkeypatch.setattr(llm_analysis, "get_llm_client", lambda provider=None: FakeLLM())

    asyncio.run(
        llm_analysis.run_llm_analysis(
            analysis_id="analysis-no-ollama",
            cv_text=CV_TEXT,
            cv_url=None,
            cv_file_content=None,
            cv_filename=None,
            cv_content_type=None,
            job_url=None,
            job_text=JOB_TEXT,
        )
    )

    assert captured["status"] == "failed"
    assert captured["error"] is not None
    assert "Ollama" in captured["error"]


def test_run_llm_analysis_fails_without_llm_response(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_update(analysis_id: str, status: str, *, error: str | None = None, result=None) -> None:
        captured["status"] = status
        captured["error"] = error

    async def fake_generate(*args, **kwargs):
        return None, (
            "Yerel LLM 360 saniye içinde yanıt vermedi. "
            "Analiz büyük CV/ilan metinlerinde birkaç dakika sürebilir; tekrar deneyin veya metni kısaltın."
        )

    async def fake_translate(text: str, *, purpose: str, provider=None):
        return text, {}

    class FakeLLM:
        async def health(self):
            return {"available": True}

    monkeypatch.setattr(llm_analysis.db, "update_analysis", fake_update)
    monkeypatch.setattr(llm_analysis, "_generate_llm_analysis_payload", fake_generate)
    monkeypatch.setattr(llm_analysis, "ensure_english_for_llm", fake_translate)
    monkeypatch.setattr(llm_analysis, "get_llm_client", lambda provider=None: FakeLLM())

    asyncio.run(
        llm_analysis.run_llm_analysis(
            analysis_id="analysis-failed",
            cv_text=CV_TEXT,
            cv_url=None,
            cv_file_content=None,
            cv_filename=None,
            cv_content_type=None,
            job_url=None,
            job_text=JOB_TEXT,
        )
    )

    assert captured["status"] == "failed"
    assert captured["error"] is not None


def test_run_llm_analysis_completes_with_valid_llm_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_update(analysis_id: str, status: str, *, error: str | None = None, result=None) -> None:
        captured["status"] = status
        captured["result"] = result
        captured["error"] = error

    async def fake_generate(*args, **kwargs):
        return SAMPLE_LLM_PAYLOAD, None

    async def fake_translate(text: str, *, purpose: str, provider=None):
        return text, {}

    class FakeLLM:
        async def health(self):
            return {"available": True}

    monkeypatch.setattr(llm_analysis.db, "update_analysis", fake_update)
    monkeypatch.setattr(llm_analysis, "_generate_llm_analysis_payload", fake_generate)
    monkeypatch.setattr(llm_analysis, "ensure_english_for_llm", fake_translate)
    monkeypatch.setattr(llm_analysis, "get_llm_client", lambda provider=None: FakeLLM())

    asyncio.run(
        llm_analysis.run_llm_analysis(
            analysis_id="analysis-ok",
            cv_text=CV_TEXT,
            cv_url=None,
            cv_file_content=None,
            cv_filename=None,
            cv_content_type=None,
            job_url=None,
            job_text=JOB_TEXT,
        )
    )

    assert captured["status"] == "completed"
    assert captured["error"] is None
    result = captured["result"]
    assert isinstance(result, dict)
    assert result["metadata"]["analysis_mode"] == "llm_only"
    assert result["metadata"]["output_sources"]["skill_matching"] == "llm"

from uuid import uuid4

from app.config import LlmProvider
from app import db
from app.models import AnalysisResult
from app.services.ingestion import (
    ingest_text,
    ingest_upload_bytes,
    ingest_url,
    validate_non_empty,
)
from app.services.reporting import (
    build_cv_add_suggestions,
    build_suggested_profile_summary,
    deterministic_recommendations,
    llm_summary,
)
from app.services.scoring import build_skill_matches, extract_cv_profile, extract_job_profile, score_match


def _apify_job_warnings(job_document) -> list[str]:
    if job_document.metadata.get("apify_fallback"):
        message = job_document.metadata.get("apify_error")
        if isinstance(message, str) and message.strip():
            return [message]
        return ["Apify ile ilan metni alınamadı; standart link ingest kullanıldı."]
    return []


async def create_analysis_job() -> str:
    analysis_id = str(uuid4())
    db.create_analysis(analysis_id)
    return analysis_id


async def run_analysis(
    *,
    analysis_id: str,
    cv_text: str | None,
    cv_url: str | None,
    cv_file_content: bytes | None,
    cv_filename: str | None,
    cv_content_type: str | None,
    job_url: str | None,
    job_text: str | None,
    deep_analysis: bool,
    llm_provider: LlmProvider = "local",
    use_apify: bool = False,
) -> None:
    db.update_analysis(analysis_id, "running")
    try:
        cv_document = await _ingest_cv(cv_text, cv_url, cv_file_content, cv_filename, cv_content_type)
        job_document = await _ingest_job(job_url, job_text, use_apify=use_apify)
        validate_non_empty(cv_document, "CV")
        validate_non_empty(job_document, "İş ilanı")

        cv_profile = extract_cv_profile(cv_document.text)
        job_profile = extract_job_profile(job_document.text)
        scores, metrics, score_details = await score_match(
            cv_document.text,
            job_document.text,
            cv_profile,
            job_profile,
            cv_document.metadata,
        )
        matched, missing_required, missing_preferred = build_skill_matches(cv_profile, job_profile)
        strengths, improvements, tailored, warnings = deterministic_recommendations(
            cv_profile,
            job_profile,
            scores,
            missing_required,
            missing_preferred,
        )
        warnings = [*warnings, *_apify_job_warnings(job_document)]
        cv_add_suggestions = build_cv_add_suggestions(
            cv_profile,
            job_profile,
            scores,
            missing_required,
            missing_preferred,
            cv_document.text,
        )
        suggested_profile_summary = build_suggested_profile_summary(cv_profile, job_profile, matched)

        semantic_similarity = metrics.get("semantic_similarity", -1)
        domain_scoring_source = "embedding" if isinstance(semantic_similarity, (int, float)) and semantic_similarity >= 0 else "keyword_fallback"
        output_sources: dict[str, str] = {
            "domain_scoring": domain_scoring_source,
            "recommendations": "deterministic",
            "profile_summary": "deterministic",
            "cv_add_suggestions": "deterministic",
            "skill_matching": "deterministic",
            "summary": "skipped",
        }

        result = AnalysisResult(
            id=analysis_id,
            status="completed",
            scores=scores,
            score_details=score_details,
            cv_profile=cv_profile,
            job_profile=job_profile,
            matched_required_skills=matched,
            missing_required_skills=missing_required,
            missing_preferred_skills=missing_preferred,
            strengths=strengths,
            improvement_suggestions=improvements,
            tailored_cv_suggestions=tailored,
            cv_add_suggestions=cv_add_suggestions,
            suggested_profile_summary=suggested_profile_summary,
            warnings=warnings,
            metadata={
                "cv": {**cv_document.metadata, "cache_key": cv_document.cache_key},
                "job": {**job_document.metadata, "cache_key": job_document.cache_key},
                "metrics": metrics,
                "deep_analysis": deep_analysis,
                "llm_provider": llm_provider,
                "use_apify": use_apify,
                "output_sources": output_sources,
            },
        )
        if deep_analysis:
            result.llm_summary = await llm_summary(result, llm_provider=llm_provider)
            output_sources["summary"] = "llm" if result.llm_summary else "fallback"
        db.update_analysis(analysis_id, "completed", result=result.model_dump())
    except Exception as exc:  # noqa: BLE001 - persisted for UI visibility
        db.update_analysis(analysis_id, "failed", error=str(exc))


async def _ingest_cv(
    cv_text: str | None,
    cv_url: str | None,
    cv_file_content: bytes | None,
    cv_filename: str | None,
    cv_content_type: str | None,
):
    if cv_text and cv_text.strip():
        return await ingest_text("cv", cv_text)
    if cv_file_content and cv_filename:
        return ingest_upload_bytes("cv", cv_file_content, filename=cv_filename, content_type=cv_content_type)
    if cv_url:
        return await ingest_url("cv", cv_url)
    raise ValueError("CV metni, CV linki veya CV dosyası gerekli.")


async def _ingest_job(job_url: str | None, job_text: str | None, *, use_apify: bool = False):
    from app.services.apify_utils import effective_use_apify

    if job_url and job_url.strip():
        active, _ = effective_use_apify(use_apify)
        return await ingest_url("job", job_url, use_apify=active)
    if job_text and job_text.strip():
        return await ingest_text("job", job_text)
    raise ValueError("İş ilanı linki veya iş ilanı metni gerekli.")

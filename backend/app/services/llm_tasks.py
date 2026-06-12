from __future__ import annotations

from app import db
from app.config import LlmProvider
from app.models import CvEditSuggestion, CvRewriteRequest
from app.services.cv_guided_edit import apply_cv_edits, suggest_cv_edits
from app.services.cv_rewrite import rewrite_cv_for_analysis
from app.services.job_titles import suggest_job_titles
from app.services.llm_progress import set_llm_task_status_message


async def run_rewrite_task(
    task_id: str,
    analysis_id: str,
    request: CvRewriteRequest,
) -> None:
    db.update_llm_task(task_id, "running")
    set_llm_task_status_message(task_id, "CV güncelleme görevi başlatıldı...")
    try:
        result = await rewrite_cv_for_analysis(analysis_id, request, task_id=task_id)
        db.update_llm_task(task_id, "completed", result=result.model_dump())
    except Exception as exc:  # noqa: BLE001
        db.update_llm_task(task_id, "failed", error=str(exc))


async def run_job_titles_task(
    task_id: str,
    *,
    cv_text: str | None,
    cv_url: str | None,
    cv_file_content: bytes | None,
    cv_filename: str | None,
    cv_content_type: str | None,
    language: str,
    llm_provider: LlmProvider,
) -> None:
    db.update_llm_task(task_id, "running")
    set_llm_task_status_message(task_id, "İş unvanı önerileri görevi başlatıldı...")
    try:
        result = await suggest_job_titles(
            cv_text=cv_text,
            cv_url=cv_url,
            cv_file_content=cv_file_content,
            cv_filename=cv_filename,
            cv_content_type=cv_content_type,
            language=language,  # type: ignore[arg-type]
            use_llm=True,
            llm_provider=llm_provider,
            task_id=task_id,
        )
        db.update_llm_task(task_id, "completed", result=result.model_dump())
    except Exception as exc:  # noqa: BLE001
        db.update_llm_task(task_id, "failed", error=str(exc))


async def run_cv_edit_task(
    task_id: str,
    *,
    cv_text: str | None,
    cv_url: str | None,
    cv_file_content: bytes | None,
    cv_filename: str | None,
    cv_content_type: str | None,
    guidance: str,
    language: str,
    llm_provider: LlmProvider,
) -> None:
    db.update_llm_task(task_id, "running")
    set_llm_task_status_message(task_id, "CV düzenleme önerileri görevi başlatıldı...")
    try:
        result = await suggest_cv_edits(
            cv_text=cv_text,
            cv_url=cv_url,
            cv_file_content=cv_file_content,
            cv_filename=cv_filename,
            cv_content_type=cv_content_type,
            guidance=guidance,
            language=language,  # type: ignore[arg-type]
            use_llm=True,
            llm_provider=llm_provider,
            task_id=task_id,
        )
        db.update_llm_task(task_id, "completed", result=result.model_dump())
    except Exception as exc:  # noqa: BLE001
        db.update_llm_task(task_id, "failed", error=str(exc))


async def run_cv_apply_task(
    task_id: str,
    *,
    cv_text: str | None,
    cv_url: str | None,
    cv_file_content: bytes | None,
    cv_filename: str | None,
    cv_content_type: str | None,
    guidance: str,
    suggestions: list[CvEditSuggestion],
    language: str,
    llm_provider: LlmProvider,
) -> None:
    db.update_llm_task(task_id, "running")
    set_llm_task_status_message(task_id, "CV metnine öneriler uygulanıyor...")
    try:
        result = await apply_cv_edits(
            cv_text=cv_text,
            cv_url=cv_url,
            cv_file_content=cv_file_content,
            cv_filename=cv_filename,
            cv_content_type=cv_content_type,
            guidance=guidance,
            suggestions=suggestions,
            language=language,  # type: ignore[arg-type]
            llm_provider=llm_provider,
            task_id=task_id,
        )
        db.update_llm_task(task_id, "completed", result=result.model_dump())
    except Exception as exc:  # noqa: BLE001
        db.update_llm_task(task_id, "failed", error=str(exc))

import json
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import normalize_llm_provider
from app.db import create_llm_task, get_analysis, get_cv_rewrite, get_llm_task, update_llm_task_progress
from app.models import (
    AnalysisJob,
    CvEditSuggestion,
    CvEditSuggestionsResult,
    CvRewriteRequest,
    CvRewriteResult,
    JobTitleSuggestionsResult,
    LlmTaskJob,
)
from app.services.analysis import create_analysis_job, run_analysis
from app.services.llm_analysis import run_llm_analysis
from app.services.cv_guided_edit import apply_cv_edits, suggest_cv_edits
from app.services.cv_rewrite import rewrite_cv_for_analysis
from app.services.job_titles import suggest_job_titles
from app.services.job_runner import schedule_analysis_job
from app.services.llm import llm_health
from app.services.llm_tasks import run_cv_apply_task, run_cv_edit_task, run_job_titles_task, run_rewrite_task
from app.services.pdf_export import pdf_path_for_rewrite


router = APIRouter(tags=["analysis"])


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "on", "yes"}


def _parse_cv_edit_suggestions(raw_json: str) -> list[CvEditSuggestion]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Öneri listesi geçerli JSON değil.") from exc
    if not isinstance(payload, list) or not payload:
        raise HTTPException(status_code=400, detail="Uygulanacak CV düzenleme önerisi bulunamadı.")
    suggestions: list[CvEditSuggestion] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        recommendation = str(item.get("recommendation", "")).strip()
        if not title or not recommendation:
            continue
        suggestions.append(
            CvEditSuggestion(
                category=str(item.get("category", "general")).strip() or "general",
                title=title,
                recommendation=recommendation,
                priority=item.get("priority", "medium"),  # type: ignore[arg-type]
                evidence=[str(line).strip() for line in item.get("evidence", []) if str(line).strip()],
            )
        )
    if not suggestions:
        raise HTTPException(status_code=400, detail="Uygulanacak CV düzenleme önerisi bulunamadı.")
    return suggestions


@router.post("/analysis", response_model=AnalysisJob)
async def analyze(
    cv_text: str | None = Form(default=None),
    cv_url: str | None = Form(default=None),
    cv_file: UploadFile | None = File(default=None),
    job_url: str | None = Form(default=None),
    job_text: str | None = Form(default=None),
    deep_analysis: bool = Form(default=False),
    llm_provider: str = Form(default="local"),
    use_apify: str = Form(default="false"),
) -> AnalysisJob:
    cv_file_content = await cv_file.read() if cv_file and cv_file.filename else None
    analysis_id = await create_analysis_job()
    provider = normalize_llm_provider(llm_provider)
    schedule_analysis_job(
        run_analysis(
            analysis_id=analysis_id,
            cv_text=cv_text,
            cv_url=cv_url,
            cv_file_content=cv_file_content,
            cv_filename=cv_file.filename if cv_file else None,
            cv_content_type=cv_file.content_type if cv_file else None,
            job_url=job_url,
            job_text=job_text,
            deep_analysis=deep_analysis,
            llm_provider=provider,
            use_apify=_parse_bool(use_apify),
        )
    )
    row = get_analysis(analysis_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Analiz kaydı oluşturulamadı.")
    return AnalysisJob(**row)


@router.post("/llm-analysis", response_model=AnalysisJob)
async def analyze_with_llm(
    cv_text: str | None = Form(default=None),
    cv_url: str | None = Form(default=None),
    cv_file: UploadFile | None = File(default=None),
    job_url: str | None = Form(default=None),
    job_text: str | None = Form(default=None),
    llm_provider: str = Form(default="local"),
    use_apify: str = Form(default="false"),
) -> AnalysisJob:
    cv_file_content = await cv_file.read() if cv_file and cv_file.filename else None
    analysis_id = await create_analysis_job()
    provider = normalize_llm_provider(llm_provider)
    schedule_analysis_job(
        run_llm_analysis(
            analysis_id=analysis_id,
            cv_text=cv_text,
            cv_url=cv_url,
            cv_file_content=cv_file_content,
            cv_filename=cv_file.filename if cv_file else None,
            cv_content_type=cv_file.content_type if cv_file else None,
            job_url=job_url,
            job_text=job_text,
            llm_provider=provider,
            use_apify=_parse_bool(use_apify),
        )
    )
    row = get_analysis(analysis_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Analiz kaydı oluşturulamadı.")
    return AnalysisJob(**row)


@router.get("/analysis/{analysis_id}", response_model=AnalysisJob)
def get_analysis_status(analysis_id: str) -> AnalysisJob:
    row = get_analysis(analysis_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Analiz bulunamadı.")
    return AnalysisJob(**row)


@router.post("/analysis/{analysis_id}/rewrite-cv")
async def rewrite_cv(analysis_id: str, request: CvRewriteRequest):
    if request.deep_rewrite and request.llm_provider == "local":
        task_id = str(uuid4())
        create_llm_task(task_id, "rewrite")
        update_llm_task_progress(
            task_id,
            {
                "thinking": "CV güncelleme görevi sıraya alındı; kısa süre içinde başlayacak.",
                "response": "",
                "phase": "thinking",
            },
        )
        schedule_analysis_job(run_rewrite_task(task_id, analysis_id, request))
        row = get_llm_task(task_id)
        if row is None:
            raise HTTPException(status_code=500, detail="CV güncelleme görevi oluşturulamadı.")
        return LlmTaskJob(**row)
    try:
        return await rewrite_cv_for_analysis(analysis_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CV güncelleme sırasında hata: {exc}") from exc


@router.get("/analysis/{analysis_id}/rewrite-cv/{rewrite_id}/pdf")
def download_rewrite_pdf(analysis_id: str, rewrite_id: str) -> FileResponse:
    row = get_cv_rewrite(rewrite_id)
    if row is None or row["analysis_id"] != analysis_id:
        raise HTTPException(status_code=404, detail="CV PDF çıktısı bulunamadı.")
    pdf_path = pdf_path_for_rewrite(rewrite_id)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF dosyası bulunamadı veya henüz üretilmedi.")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"updated-cv-{rewrite_id}.pdf",
        content_disposition_type="inline",
    )


@router.get("/llm/health")
async def llm_health_endpoint(provider: str | None = None) -> dict:
    return await llm_health(provider)


@router.get("/llm-tasks/{task_id}", response_model=LlmTaskJob)
def get_llm_task_status(task_id: str) -> LlmTaskJob:
    row = get_llm_task(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="LLM görevi bulunamadı.")
    return LlmTaskJob(**row)


@router.post("/job-title-suggestions")
async def job_title_suggestions(
    cv_text: str | None = Form(default=None),
    cv_url: str | None = Form(default=None),
    cv_file: UploadFile | None = File(default=None),
    language: str = Form(default="tr"),
    use_llm: str = Form(default="true"),
    llm_provider: str = Form(default="local"),
):
    cv_file_content = await cv_file.read() if cv_file and cv_file.filename else None
    normalized_language = language if language in {"tr", "en"} else "tr"
    use_llm_enabled = use_llm.strip().lower() in {"true", "1", "on", "yes"}
    provider = normalize_llm_provider(llm_provider)
    if use_llm_enabled and provider == "local":
        task_id = str(uuid4())
        create_llm_task(task_id, "job_titles")
        update_llm_task_progress(
            task_id,
            {
                "thinking": "İş unvanı önerileri sıraya alındı; kısa süre içinde başlayacak.",
                "response": "",
                "phase": "thinking",
            },
        )
        schedule_analysis_job(
            run_job_titles_task(
                task_id,
                cv_text=cv_text,
                cv_url=cv_url,
                cv_file_content=cv_file_content,
                cv_filename=cv_file.filename if cv_file else None,
                cv_content_type=cv_file.content_type if cv_file else None,
                language=normalized_language,
                llm_provider=provider,
            )
        )
        row = get_llm_task(task_id)
        if row is None:
            raise HTTPException(status_code=500, detail="İş unvanı görevi oluşturulamadı.")
        return LlmTaskJob(**row)
    try:
        return await suggest_job_titles(
            cv_text=cv_text,
            cv_url=cv_url,
            cv_file_content=cv_file_content,
            cv_filename=cv_file.filename if cv_file else None,
            cv_content_type=cv_file.content_type if cv_file else None,
            language=normalized_language,  # type: ignore[arg-type]
            use_llm=use_llm_enabled,
            llm_provider=provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"İş unvanı önerisi üretilemedi: {exc}") from exc


@router.post("/cv-edit-suggestions")
async def cv_edit_suggestions(
    cv_text: str | None = Form(default=None),
    cv_url: str | None = Form(default=None),
    cv_file: UploadFile | None = File(default=None),
    guidance: str = Form(default=""),
    language: str = Form(default="tr"),
    use_llm: str = Form(default="true"),
    llm_provider: str = Form(default="local"),
):
    normalized_guidance = guidance.strip()
    if not normalized_guidance:
        raise HTTPException(status_code=400, detail="CV düzenleme yönlendirmesi gerekli.")

    cv_file_content = await cv_file.read() if cv_file and cv_file.filename else None
    normalized_language = language if language in {"tr", "en"} else "tr"
    use_llm_enabled = use_llm.strip().lower() in {"true", "1", "on", "yes"}
    provider = normalize_llm_provider(llm_provider)
    if use_llm_enabled and provider == "local":
        task_id = str(uuid4())
        create_llm_task(task_id, "cv_edit")
        update_llm_task_progress(
            task_id,
            {
                "thinking": "CV düzenleme önerileri sıraya alındı; kısa süre içinde başlayacak.",
                "response": "",
                "phase": "thinking",
            },
        )
        schedule_analysis_job(
            run_cv_edit_task(
                task_id,
                cv_text=cv_text,
                cv_url=cv_url,
                cv_file_content=cv_file_content,
                cv_filename=cv_file.filename if cv_file else None,
                cv_content_type=cv_file.content_type if cv_file else None,
                guidance=normalized_guidance,
                language=normalized_language,
                llm_provider=provider,
            )
        )
        row = get_llm_task(task_id)
        if row is None:
            raise HTTPException(status_code=500, detail="CV düzenleme görevi oluşturulamadı.")
        return LlmTaskJob(**row)
    try:
        return await suggest_cv_edits(
            cv_text=cv_text,
            cv_url=cv_url,
            cv_file_content=cv_file_content,
            cv_filename=cv_file.filename if cv_file else None,
            cv_content_type=cv_file.content_type if cv_file else None,
            guidance=normalized_guidance,
            language=normalized_language,  # type: ignore[arg-type]
            use_llm=use_llm_enabled,
            llm_provider=provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CV düzenleme önerisi üretilemedi: {exc}") from exc


@router.post("/cv-apply-edits")
async def cv_apply_edits(
    cv_text: str | None = Form(default=None),
    cv_url: str | None = Form(default=None),
    cv_file: UploadFile | None = File(default=None),
    guidance: str = Form(default=""),
    language: str = Form(default="tr"),
    llm_provider: str = Form(default="local"),
    suggestions_json: str = Form(default=""),
):
    normalized_guidance = guidance.strip()
    if not normalized_guidance:
        raise HTTPException(status_code=400, detail="CV düzenleme yönlendirmesi gerekli.")

    suggestions = _parse_cv_edit_suggestions(suggestions_json)
    cv_file_content = await cv_file.read() if cv_file and cv_file.filename else None
    normalized_language = language if language in {"tr", "en"} else "tr"
    provider = normalize_llm_provider(llm_provider)

    if provider == "local":
        task_id = str(uuid4())
        create_llm_task(task_id, "cv_edit_apply")
        update_llm_task_progress(
            task_id,
            {
                "thinking": "CV metnine öneriler uygulanması sıraya alındı; kısa süre içinde başlayacak.",
                "response": "",
                "phase": "thinking",
            },
        )
        schedule_analysis_job(
            run_cv_apply_task(
                task_id,
                cv_text=cv_text,
                cv_url=cv_url,
                cv_file_content=cv_file_content,
                cv_filename=cv_file.filename if cv_file else None,
                cv_content_type=cv_file.content_type if cv_file else None,
                guidance=normalized_guidance,
                suggestions=suggestions,
                language=normalized_language,
                llm_provider=provider,
            )
        )
        row = get_llm_task(task_id)
        if row is None:
            raise HTTPException(status_code=500, detail="CV düzenleme uygulama görevi oluşturulamadı.")
        return LlmTaskJob(**row)
    try:
        return await apply_cv_edits(
            cv_text=cv_text,
            cv_url=cv_url,
            cv_file_content=cv_file_content,
            cv_filename=cv_file.filename if cv_file else None,
            cv_content_type=cv_file.content_type if cv_file else None,
            guidance=normalized_guidance,
            suggestions=suggestions,
            language=normalized_language,  # type: ignore[arg-type]
            llm_provider=provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CV düzenleme uygulanamadı: {exc}") from exc

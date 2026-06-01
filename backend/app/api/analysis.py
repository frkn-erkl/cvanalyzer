from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import normalize_llm_provider
from app.db import get_analysis, get_cv_rewrite
from app.models import AnalysisJob, CvRewriteRequest, CvRewriteResult, JobTitleSuggestionsResult
from app.services.analysis import create_analysis_job, run_analysis
from app.services.llm_analysis import run_llm_analysis
from app.services.cv_rewrite import rewrite_cv_for_analysis
from app.services.job_titles import suggest_job_titles
from app.services.llm import llm_health
from app.services.pdf_export import pdf_path_for_rewrite


router = APIRouter(tags=["analysis"])


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "on", "yes"}


@router.post("/analysis", response_model=AnalysisJob)
async def analyze(
    background_tasks: BackgroundTasks,
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
    background_tasks.add_task(
        run_analysis,
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
    row = get_analysis(analysis_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Analiz kaydı oluşturulamadı.")
    return AnalysisJob(**row)


@router.post("/llm-analysis", response_model=AnalysisJob)
async def analyze_with_llm(
    background_tasks: BackgroundTasks,
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
    background_tasks.add_task(
        run_llm_analysis,
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


@router.post("/analysis/{analysis_id}/rewrite-cv", response_model=CvRewriteResult)
async def rewrite_cv(analysis_id: str, request: CvRewriteRequest) -> CvRewriteResult:
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


@router.post("/job-title-suggestions", response_model=JobTitleSuggestionsResult)
async def job_title_suggestions(
    cv_text: str | None = Form(default=None),
    cv_url: str | None = Form(default=None),
    cv_file: UploadFile | None = File(default=None),
    language: str = Form(default="tr"),
    use_llm: str = Form(default="true"),
    llm_provider: str = Form(default="local"),
) -> JobTitleSuggestionsResult:
    cv_file_content = await cv_file.read() if cv_file and cv_file.filename else None
    normalized_language = language if language in {"tr", "en"} else "tr"
    use_llm_enabled = use_llm.strip().lower() in {"true", "1", "on", "yes"}
    provider = normalize_llm_provider(llm_provider)
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

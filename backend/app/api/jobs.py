from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import LlmProvider, normalize_llm_provider
from app.models import JobSearchPreviewResult, JobSearchResult
from app.services.apify_client import apify_health
from app.services.job_search import JobSearchSource, preview_job_search, search_jobs


router = APIRouter(tags=["jobs"])


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "on", "yes"}


def _parse_sources(raw: str | None) -> list[JobSearchSource]:
    if not raw or not raw.strip():
        return ["linkedin", "kariyer"]
    sources: list[JobSearchSource] = []
    for item in raw.split(","):
        normalized = item.strip().lower()
        if normalized in {"linkedin", "kariyer"} and normalized not in sources:
            sources.append(normalized)  # type: ignore[arg-type]
    return sources or ["linkedin", "kariyer"]


@router.get("/apify/health")
async def apify_health_endpoint() -> dict:
    return await apify_health()


async def _read_job_search_form(
    cv_text: str | None,
    cv_url: str | None,
    cv_file: UploadFile | None,
    sources: str,
    location: str | None,
    max_results: int | None,
    language: str,
    use_llm: str,
    llm_provider: str,
):
    cv_file_content = await cv_file.read() if cv_file and cv_file.filename else None
    normalized_language: LlmProvider | str = language if language in {"tr", "en"} else "tr"
    provider = normalize_llm_provider(llm_provider)
    return {
        "cv_text": cv_text,
        "cv_url": cv_url,
        "cv_file_content": cv_file_content,
        "cv_filename": cv_file.filename if cv_file else None,
        "cv_content_type": cv_file.content_type if cv_file else None,
        "sources": _parse_sources(sources),
        "location": location.strip() if location and location.strip() else None,
        "max_results": max_results,
        "language": normalized_language,
        "use_llm": _parse_bool(use_llm),
        "llm_provider": provider,
    }


@router.post("/job-search/preview", response_model=JobSearchPreviewResult)
async def job_search_preview(
    cv_text: str | None = Form(default=None),
    cv_url: str | None = Form(default=None),
    cv_file: UploadFile | None = File(default=None),
    sources: str = Form(default="linkedin,kariyer"),
    location: str | None = Form(default=None),
    max_results: int | None = Form(default=None),
    language: str = Form(default="tr"),
    use_llm: str = Form(default="false"),
    llm_provider: str = Form(default="local"),
) -> JobSearchPreviewResult:
    params = await _read_job_search_form(
        cv_text, cv_url, cv_file, sources, location, max_results, language, use_llm, llm_provider
    )
    try:
        return await preview_job_search(
            cv_text=params["cv_text"],
            cv_url=params["cv_url"],
            cv_file_content=params["cv_file_content"],
            cv_filename=params["cv_filename"],
            cv_content_type=params["cv_content_type"],
            sources=params["sources"],
            location=params["location"],
            max_results=params["max_results"],
            language=params["language"],  # type: ignore[arg-type]
            use_llm=params["use_llm"],
            llm_provider=params["llm_provider"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Apify önizlemesi başarısız: {exc}") from exc


@router.post("/job-search", response_model=JobSearchResult)
async def job_search(
    cv_text: str | None = Form(default=None),
    cv_url: str | None = Form(default=None),
    cv_file: UploadFile | None = File(default=None),
    sources: str = Form(default="linkedin,kariyer"),
    use_apify: str = Form(default="false"),
    location: str | None = Form(default=None),
    max_results: int | None = Form(default=None),
    language: str = Form(default="tr"),
    use_llm: str = Form(default="false"),
    llm_provider: str = Form(default="local"),
) -> JobSearchResult:
    params = await _read_job_search_form(
        cv_text, cv_url, cv_file, sources, location, max_results, language, use_llm, llm_provider
    )
    try:
        return await search_jobs(
            cv_text=params["cv_text"],
            cv_url=params["cv_url"],
            cv_file_content=params["cv_file_content"],
            cv_filename=params["cv_filename"],
            cv_content_type=params["cv_content_type"],
            sources=params["sources"],
            use_apify=_parse_bool(use_apify),
            location=params["location"],
            max_results=params["max_results"],
            language=params["language"],  # type: ignore[arg-type]
            use_llm=params["use_llm"],
            llm_provider=params["llm_provider"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"İlan araması başarısız: {exc}") from exc

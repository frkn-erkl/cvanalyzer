from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analysis import router as analysis_router
from app.api.jobs import router as jobs_router
from app.config import get_settings
from app.db import init_db
from app.services.job_runner import shutdown_job_runner


settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()
    from app.config import get_settings
    from app.db import fail_stale_running_analyses

    settings = get_settings()
    stale = fail_stale_running_analyses(max_age_seconds=settings.llm_analysis_timeout_seconds + 120)
    if stale:
        print(f"Marked {stale} stale analysis job(s) as failed.")
    from app.db import fail_stale_running_llm_tasks

    stale_tasks = fail_stale_running_llm_tasks(max_age_seconds=settings.llm_analysis_timeout_seconds + 120)
    if stale_tasks:
        print(f"Marked {stale_tasks} stale LLM task(s) as failed.")
    from app.services.skill_gaps import backfill_skill_gaps_from_analyses

    backfilled = backfill_skill_gaps_from_analyses()
    if backfilled:
        print(f"Backfilled skill gaps from {backfilled} completed analysis(es).")


@app.on_event("shutdown")
def shutdown() -> None:
    shutdown_job_runner()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(analysis_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")

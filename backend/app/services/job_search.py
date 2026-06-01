from __future__ import annotations

import asyncio
import hashlib
from typing import Literal

from app.config import LlmProvider, get_settings
from app.db import get_cached_text, set_cached_text
from app.models import JobListingMatch, JobSearchResult
from app.services.apify_client import ApifyClient, ApifyError
from app.services.apify_utils import apify_actor_fingerprint, effective_use_apify
from app.services.ingestion import ingest_text, ingest_upload_bytes, ingest_url, validate_non_empty
from app.services.job_listings import (
    JobListingCandidate,
    build_kariyer_search_input,
    build_linkedin_search_input,
    normalize_kariyer_items,
    normalize_linkedin_items,
)
from app.services.job_titles import suggest_job_titles
from app.services.scoring import build_skill_matches, extract_cv_profile, extract_job_profile, score_match

JobSearchSource = Literal["linkedin", "kariyer"]


async def _prepare_job_search(
    *,
    cv_text: str | None,
    cv_url: str | None,
    cv_file_content: bytes | None,
    cv_filename: str | None,
    cv_content_type: str | None,
    sources: list[JobSearchSource],
    location: str | None = None,
    max_results: int | None = None,
    language: Literal["tr", "en"] = "tr",
    use_llm: bool = False,
    llm_provider: LlmProvider = "local",
):
    settings = get_settings()
    warnings: list[str] = []
    max_per_source = max_results or settings.apify_max_results_per_source
    normalized_sources = _normalize_sources(sources)

    cv_document = await _ingest_cv(cv_text, cv_url, cv_file_content, cv_filename, cv_content_type)
    validate_non_empty(cv_document, "CV")
    cv_profile = extract_cv_profile(cv_document.text)

    title_result = await suggest_job_titles(
        cv_text=cv_document.text,
        cv_url=None,
        cv_file_content=None,
        cv_filename=None,
        cv_content_type=None,
        language=language,
        use_llm=use_llm,
        llm_provider=llm_provider,
    )
    search_queries = _build_search_queries(title_result.suggestions, cv_profile)
    warnings.extend(title_result.warnings)

    return {
        "cv_document": cv_document,
        "cv_profile": cv_profile,
        "search_queries": search_queries,
        "title_suggestions": [item.title for item in title_result.suggestions[:4]],
        "warnings": warnings,
        "normalized_sources": normalized_sources,
        "max_per_source": max_per_source,
        "location": location,
    }


def _build_apify_actor_previews(
    sources: list[JobSearchSource],
    search_queries: list[str],
    location: str | None,
    max_results: int,
) -> tuple[list, list[str], bool]:
    from app.models import ApifyActorPreview

    settings = get_settings()
    warnings: list[str] = []
    previews: list[ApifyActorPreview] = []
    ready = True

    for source in sources:
        if source == "linkedin":
            actor_id = settings.apify_linkedin_search_actor_id.strip()
            run_input = build_linkedin_search_input(
                queries=search_queries,
                location=location,
                max_results=max_results,
            )
        else:
            actor_id = settings.apify_kariyer_search_actor_id.strip()
            run_input = build_kariyer_search_input(
                queries=search_queries,
                location=location,
                max_results=max_results,
            )

        configured = bool(actor_id)
        if not configured:
            warnings.append(f"{source} için Apify actor ID yapılandırılmamış.")
            ready = False

        previews.append(
            ApifyActorPreview(
                source=source,
                actor_id=actor_id or "(tanımlı değil)",
                configured=configured,
                run_input=run_input,
            )
        )

    apify_active, apify_warning = effective_use_apify(True)
    if not apify_active:
        if apify_warning:
            warnings.append(apify_warning)
        ready = False

    return previews, warnings, ready and apify_active


async def preview_job_search(
    *,
    cv_text: str | None,
    cv_url: str | None,
    cv_file_content: bytes | None,
    cv_filename: str | None,
    cv_content_type: str | None,
    sources: list[JobSearchSource],
    location: str | None = None,
    max_results: int | None = None,
    language: Literal["tr", "en"] = "tr",
    use_llm: bool = False,
    llm_provider: LlmProvider = "local",
):
    from app.models import JobSearchPreviewResult

    context = await _prepare_job_search(
        cv_text=cv_text,
        cv_url=cv_url,
        cv_file_content=cv_file_content,
        cv_filename=cv_filename,
        cv_content_type=cv_content_type,
        sources=sources,
        location=location,
        max_results=max_results,
        language=language,
        use_llm=use_llm,
        llm_provider=llm_provider,
    )
    actor_previews, actor_warnings, apify_ready = _build_apify_actor_previews(
        context["normalized_sources"],
        context["search_queries"],
        context["location"],
        context["max_per_source"],
    )
    warnings = [*context["warnings"], *actor_warnings]

    return JobSearchPreviewResult(
        search_queries=context["search_queries"],
        cv_skills=context["cv_profile"].skills[:8],
        title_suggestions=context["title_suggestions"],
        sources=context["normalized_sources"],
        location=context["location"],
        max_results_per_source=context["max_per_source"],
        apify_ready=apify_ready,
        apify_actors=actor_previews,
        warnings=warnings,
    )


async def search_jobs(
    *,
    cv_text: str | None,
    cv_url: str | None,
    cv_file_content: bytes | None,
    cv_filename: str | None,
    cv_content_type: str | None,
    sources: list[JobSearchSource],
    use_apify: bool,
    location: str | None = None,
    max_results: int | None = None,
    language: Literal["tr", "en"] = "tr",
    use_llm: bool = False,
    llm_provider: LlmProvider = "local",
) -> JobSearchResult:
    settings = get_settings()
    context = await _prepare_job_search(
        cv_text=cv_text,
        cv_url=cv_url,
        cv_file_content=cv_file_content,
        cv_filename=cv_filename,
        cv_content_type=cv_content_type,
        sources=sources,
        location=location,
        max_results=max_results,
        language=language,
        use_llm=use_llm,
        llm_provider=llm_provider,
    )
    search_queries = context["search_queries"]
    warnings = list(context["warnings"])
    normalized_sources = context["normalized_sources"]
    max_per_source = context["max_per_source"]
    cv_document = context["cv_document"]
    cv_profile = context["cv_profile"]

    if not use_apify:
        return JobSearchResult(
            listings=[],
            search_queries=search_queries,
            used_apify=False,
            sources_searched=normalized_sources,
            warnings=[*warnings, "Apify kapalı; ilan araması yapılmadı."],
        )

    apify_active, apify_warning = effective_use_apify(True)
    if not apify_active:
        return JobSearchResult(
            listings=[],
            search_queries=search_queries,
            used_apify=False,
            sources_searched=normalized_sources,
            warnings=[*warnings, apify_warning or "Apify kullanılamıyor."],
        )

    cache_key = _search_cache_key(
        cv_document.cache_key,
        normalized_sources,
        search_queries,
        location,
        max_per_source,
        apify_actor_fingerprint(),
    )
    cached = get_cached_text(cache_key)
    if cached:
        import json

        payload = json.loads(cached[0])
        return JobSearchResult.model_validate(payload)

    client = ApifyClient()
    candidates, source_warnings, apify_invoked = await _fetch_candidates(
        client, normalized_sources, search_queries, location, max_per_source
    )
    warnings.extend(source_warnings)
    ranked = await _rank_candidates(cv_document.text, cv_profile, candidates)
    result = JobSearchResult(
        listings=ranked[: max_per_source * max(1, len(normalized_sources))],
        search_queries=search_queries,
        used_apify=apify_invoked,
        sources_searched=normalized_sources,
        warnings=warnings,
    )
    set_cached_text(cache_key, result.model_dump_json(), {"source": "job_search", "count": len(result.listings)})
    return result


async def _fetch_candidates(
    client: ApifyClient,
    sources: list[JobSearchSource],
    search_queries: list[str],
    location: str | None,
    max_results: int,
) -> tuple[list[JobListingCandidate], list[str], bool]:
    settings = get_settings()
    warnings: list[str] = []
    tasks = []
    for source in sources:
        if source == "linkedin" and settings.apify_linkedin_search_actor_id.strip():
            tasks.append(
                _run_source_search(
                    client,
                    source="linkedin",
                    actor_id=settings.apify_linkedin_search_actor_id,
                    run_input=build_linkedin_search_input(
                        queries=search_queries,
                        location=location,
                        max_results=max_results,
                    ),
                    normalizer=normalize_linkedin_items,
                )
            )
        elif source == "kariyer" and settings.apify_kariyer_search_actor_id.strip():
            tasks.append(
                _run_source_search(
                    client,
                    source="kariyer",
                    actor_id=settings.apify_kariyer_search_actor_id,
                    run_input=build_kariyer_search_input(
                        queries=search_queries,
                        location=location,
                        max_results=max_results,
                    ),
                    normalizer=normalize_kariyer_items,
                )
            )
        else:
            warnings.append(f"{source} için Apify actor ID yapılandırılmamış.")

    if not tasks:
        warnings.append("Hiçbir kaynak için arama actor'u tanımlı değil.")
        return [], warnings, False

    batches = await asyncio.gather(*tasks)
    merged: list[JobListingCandidate] = []
    for candidates, batch_warnings in batches:
        merged.extend(candidates)
        warnings.extend(batch_warnings)
    return merged, warnings, True


async def _run_source_search(
    client: ApifyClient,
    *,
    source: JobSearchSource,
    actor_id: str,
    run_input: dict,
    normalizer,
) -> tuple[list[JobListingCandidate], list[str]]:
    warnings: list[str] = []
    try:
        items = await client.run_actor(actor_id, run_input)
        candidates = normalizer(items)
        if not candidates:
            warnings.append(f"{source} araması sonuç döndürmedi.")
        return candidates, warnings
    except ApifyError as exc:
        warnings.append(f"{source} Apify araması başarısız: {exc}")
        return [], warnings


async def _rank_candidates(
    cv_text: str,
    cv_profile,
    candidates: list[JobListingCandidate],
) -> list[JobListingMatch]:
    ranked: list[JobListingMatch] = []
    for candidate in candidates:
        job_profile = extract_job_profile(candidate.description)
        scores, _, _ = await score_match(
            cv_text,
            candidate.description,
            cv_profile,
            job_profile,
            {"source": candidate.source},
            fast=True,
        )
        matched, _, _ = build_skill_matches(cv_profile, job_profile)
        ranked.append(
            JobListingMatch(
                source=candidate.source,
                title=candidate.title,
                company=candidate.company,
                location=candidate.location,
                url=candidate.url,
                fit_score=scores.overall,
                matched_skills=[match.name for match in matched if match.matched][:8],
                description_preview=candidate.description[:280],
                posted_at=candidate.posted_at,
            )
        )
    ranked.sort(key=lambda item: item.fit_score, reverse=True)
    return ranked


def _build_search_queries(suggestions, cv_profile) -> list[str]:
    queries: list[str] = []
    for suggestion in suggestions[:4]:
        queries.append(suggestion.title)
        queries.extend(suggestion.search_keywords[:3])
    for skill in cv_profile.skills[:4]:
        if skill not in queries:
            queries.append(skill)
    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        key = query.casefold()
        if key in seen or len(query.strip()) < 2:
            continue
        seen.add(key)
        deduped.append(query.strip())
    return deduped[:8] or ["software developer"]


def _normalize_sources(sources: list[JobSearchSource]) -> list[JobSearchSource]:
    if not sources:
        return ["linkedin", "kariyer"]
    normalized: list[JobSearchSource] = []
    for source in sources:
        if source in {"linkedin", "kariyer"} and source not in normalized:
            normalized.append(source)
    return normalized or ["linkedin", "kariyer"]


def _search_cache_key(
    cv_cache_key: str,
    sources: list[JobSearchSource],
    queries: list[str],
    location: str | None,
    max_results: int,
    actor_fingerprint: str,
) -> str:
    digest = hashlib.sha256(
        "|".join(
            [
                cv_cache_key,
                ",".join(sources),
                ",".join(queries),
                location or "",
                str(max_results),
                actor_fingerprint,
            ]
        ).encode("utf-8")
    ).hexdigest()
    return f"job-search:{digest}"


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
    raise ValueError("CV metni, dosyası veya linki gerekli.")

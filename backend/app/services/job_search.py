from __future__ import annotations

import asyncio
from typing import Literal

from app.config import LlmProvider, get_settings
from app.models import JobListingMatch, JobSearchResult
from app.services.apify_client import ApifyClient, ApifyError
from app.services.apify_utils import effective_use_apify
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
from app.services.skill_gaps import record_job_search_listings

JobSearchSource = Literal["linkedin", "kariyer"]

NON_TECH_TITLE_TERMS = (
    "gayrimenkul",
    "emlak",
    "satış danışman",
    "satis danisman",
    "satış uzman",
    "satis uzman",
    "muhasebe",
    "finans uzman",
    "kahvaltı",
    "kahvalti",
    "aşçı",
    "asci",
    "garson",
    "hemşire",
    "hemsire",
    "depo personel",
    "kargo",
    "lojistik",
    "güvenlik görev",
    "guvenlik gorev",
    "temizlik",
    "sekreter",
    "hostes",
    "komi",
    "kasiyer",
    "tezgahtar",
    "forklift",
    "tesisat",
    "montaj",
    "üretim",
    "uretim",
    "insaat",
    "inşaat",
    "nakliye",
    "cagri merkezi",
    "çağrı merkezi",
    "turizm danışman",
)

SEARCH_STOPWORDS = frozenset(
    {
        "and",
        "the",
        "for",
        "with",
        "ve",
        "ile",
        "senior",
        "junior",
        "kidemli",
        "mid",
        "lead",
        "staff",
    }
)


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
    search_queries_override: list[str] | None = None,
    location_override: str | None = None,
    apify_run_inputs_override: dict[str, dict] | None = None,
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
    search_queries = _apply_search_queries_override(context["search_queries"], search_queries_override)
    effective_location = location_override.strip() if location_override and location_override.strip() else context["location"]
    warnings = list(context["warnings"])
    normalized_sources = context["normalized_sources"]
    max_per_source = context["max_per_source"]
    cv_document = context["cv_document"]
    cv_profile = context["cv_profile"]

    if search_queries_override:
        warnings.append("Arama sorguları önizleme ekranından manuel olarak düzenlendi.")
    if location_override and location_override.strip():
        warnings.append("Konum önizleme ekranından manuel olarak düzenlendi.")
    if apify_run_inputs_override:
        warnings.append("Apify actor girdileri önizleme ekranından manuel olarak düzenlendi.")

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

    client = ApifyClient()
    candidates, source_warnings, apify_invoked = await _fetch_candidates(
        client,
        normalized_sources,
        search_queries,
        effective_location,
        max_per_source,
        run_inputs_override=apify_run_inputs_override,
    )
    warnings.extend(source_warnings)
    ranked = await _rank_candidates(cv_document.text, cv_profile, candidates, search_queries)
    if candidates and not ranked:
        warnings.append(
            f"Apify {len(candidates)} ilan döndürdü ancak CV profiline uygun sonuç kalmadı; filtreler sıkılaştırıldı."
        )
    listings = ranked[: max_per_source * max(1, len(normalized_sources))]
    record_job_search_listings(listings)
    return JobSearchResult(
        listings=listings,
        search_queries=search_queries,
        used_apify=apify_invoked,
        sources_searched=normalized_sources,
        warnings=warnings,
    )


def _apply_search_queries_override(
    generated: list[str],
    override: list[str] | None,
) -> list[str]:
    if not override:
        return generated
    from app.services.job_listings import _sanitize_search_queries

    sanitized = _sanitize_search_queries(override)
    return sanitized or generated


async def _fetch_candidates(
    client: ApifyClient,
    sources: list[JobSearchSource],
    search_queries: list[str],
    location: str | None,
    max_results: int,
    *,
    run_inputs_override: dict[str, dict] | None = None,
) -> tuple[list[JobListingCandidate], list[str], bool]:
    settings = get_settings()
    warnings: list[str] = []
    tasks = []
    overrides = run_inputs_override or {}
    for source in sources:
        if source == "linkedin" and settings.apify_linkedin_search_actor_id.strip():
            run_input = overrides.get("linkedin") or build_linkedin_search_input(
                queries=search_queries,
                location=location,
                max_results=max_results,
            )
            tasks.append(
                _run_source_search(
                    client,
                    source="linkedin",
                    actor_id=settings.apify_linkedin_search_actor_id,
                    run_input=run_input,
                    normalizer=normalize_linkedin_items,
                )
            )
        elif source == "kariyer" and settings.apify_kariyer_search_actor_id.strip():
            run_input = overrides.get("kariyer") or build_kariyer_search_input(
                queries=search_queries,
                location=location,
                max_results=max_results,
            )
            tasks.append(
                _run_source_search(
                    client,
                    source="kariyer",
                    actor_id=settings.apify_kariyer_search_actor_id,
                    run_input=run_input,
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
    return _dedupe_candidates(merged), warnings, True


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
        if not candidates and items:
            warnings.append(f"{source} araması {len(items)} kayıt döndürdü ancak beklenen alanlar bulunamadı.")
        elif not candidates:
            if source == "kariyer":
                warnings.append(
                    f"{source} araması sonuç döndürmedi. Kariyer actor API/proxy hatası olabilir; "
                    "Apify run loglarını kontrol edin veya APIFY_TIMEOUT_SECONDS değerini artırın."
                )
            else:
                warnings.append(f"{source} araması sonuç döndürmedi.")
        return candidates, warnings
    except ApifyError as exc:
        warnings.append(f"{source} Apify araması başarısız: {exc}")
        return [], warnings


async def _rank_candidates(
    cv_text: str,
    cv_profile,
    candidates: list[JobListingCandidate],
    search_queries: list[str],
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
        matched, missing_required, missing_preferred = build_skill_matches(cv_profile, job_profile)
        if _is_irrelevant_listing_for_profile(candidate, cv_profile, matched, search_queries):
            continue
        ranked.append(
            JobListingMatch(
                source=candidate.source,
                title=candidate.title,
                company=candidate.company,
                location=candidate.location,
                url=candidate.url,
                fit_score=scores.overall,
                matched_skills=[match.name for match in matched if match.matched][:8],
                missing_required_skills=[match.name for match in missing_required][:8],
                missing_preferred_skills=[match.name for match in missing_preferred][:8],
                description_preview=candidate.description[:280],
                posted_at=candidate.posted_at,
            )
        )
    ranked.sort(key=lambda item: item.fit_score, reverse=True)
    return ranked


def _is_irrelevant_listing_for_profile(
    candidate: JobListingCandidate,
    cv_profile,
    matched_skills,
    search_queries: list[str],
) -> bool:
    if not getattr(cv_profile, "skills", None):
        return False
    if matched_skills:
        return False
    if _matches_search_queries(candidate, search_queries):
        return False
    if _has_software_signal(candidate, cv_profile):
        return False
    return _has_non_technical_signal(candidate)


def _dedupe_candidates(candidates: list[JobListingCandidate]) -> list[JobListingCandidate]:
    deduped: list[JobListingCandidate] = []
    seen_urls: set[str] = set()
    for candidate in candidates:
        key = candidate.url.casefold()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        deduped.append(candidate)
    return deduped


def _matches_search_queries(candidate: JobListingCandidate, search_queries: list[str]) -> bool:
    tokens = _search_query_tokens(search_queries)
    if not tokens:
        return False
    text = _normalize_search_text(f"{candidate.title}\n{candidate.description}")
    return any(token in text for token in tokens)


def _search_query_tokens(search_queries: list[str]) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for query in search_queries:
        for token in _normalize_search_text(query).split():
            if len(token) < 4 or token in SEARCH_STOPWORDS:
                continue
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return tokens


def _has_non_technical_signal(candidate: JobListingCandidate) -> bool:
    text = _normalize_search_text(f"{candidate.title}\n{candidate.description}")
    return any(term in text for term in NON_TECH_TITLE_TERMS)


def _has_software_signal(candidate: JobListingCandidate, cv_profile) -> bool:
    text = _normalize_search_text(f"{candidate.title}\n{candidate.description}")
    if any(_normalize_search_text(skill) in text for skill in cv_profile.skills):
        return True
    software_terms = (
        "yazilim",
        "software",
        "developer",
        "gelistirici",
        "programci",
        "backend",
        "frontend",
        "full stack",
        "fullstack",
        "mobile",
        "mobil",
        "flutter",
        "react",
        "javascript",
        "typescript",
        "python",
        "java",
        "node",
        ".net",
        "c#",
        "devops",
        "cloud",
        "data engineer",
        "veri muhendisi",
        "data scientist",
        "veri bilim",
        "machine learning",
        "yapay zeka",
        "qa",
        "test otomasyon",
    )
    return any(term in text for term in software_terms)


def _normalize_search_text(value: str) -> str:
    return value.casefold().replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c")


def _build_search_queries(suggestions, cv_profile) -> list[str]:
    queries: list[str] = []
    for suggestion in suggestions[:4]:
        if isinstance(suggestion.title, str) and suggestion.title.strip():
            queries.append(suggestion.title.strip())
        for keyword in suggestion.search_keywords[:3]:
            if isinstance(keyword, str) and _looks_like_job_title(keyword):
                queries.append(keyword.strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        key = query.casefold()
        if key in seen or len(query) < 2:
            continue
        seen.add(key)
        deduped.append(query)
    return deduped[:8] or ["software developer"]


def _looks_like_job_title(value: str) -> bool:
    normalized = value.strip().casefold()
    role_terms = (
        "developer",
        "engineer",
        "architect",
        "analyst",
        "specialist",
        "consultant",
        "manager",
        "lead",
        "mühendis",
        "geliştirici",
        "uzman",
        "danışman",
        "mimar",
        "analist",
        "yazılım",
    )
    return any(term in normalized for term in role_terms)


def _normalize_sources(sources: list[JobSearchSource]) -> list[JobSearchSource]:
    if not sources:
        return ["linkedin", "kariyer"]
    normalized: list[JobSearchSource] = []
    for source in sources:
        if source in {"linkedin", "kariyer"} and source not in normalized:
            normalized.append(source)
    return normalized or ["linkedin", "kariyer"]


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

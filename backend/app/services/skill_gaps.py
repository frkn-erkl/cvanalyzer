from __future__ import annotations

import hashlib
import re
from typing import Literal
from urllib.parse import urlparse, urlunparse

from app import db
from app.models import AnalysisResult, JobListingMatch, SkillGapAggregate, SkillGapListingRef, SkillGapSummaryResponse
from app.services.scoring import SKILLS

SkillGapSource = Literal["job_search", "analysis", "llm_analysis"]
GapType = Literal["required", "preferred"]


def normalize_skill_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name.strip()).casefold().replace("ı", "i")
    if not cleaned:
        return ""
    for skill in SKILLS:
        skill_key = skill.casefold().replace("ı", "i")
        if cleaned == skill_key:
            return skill
        compact = cleaned.replace(" ", "").replace(".", "")
        skill_compact = skill_key.replace(" ", "").replace(".", "")
        if compact == skill_compact:
            return skill
    return cleaned.replace(" ", "")


def job_key_from_url(url: str) -> str:
    parsed = urlparse(url.strip())
    normalized = urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            parsed.query,
            "",
        )
    )
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"url:{digest}"


def job_key_from_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())[:4000]
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"text:{digest}"


def _normalize_skill_list(skills: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for skill in skills:
        canonical = normalize_skill_name(skill)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)
    return normalized


def record_listing_gaps(
    *,
    job_key: str,
    job_url: str | None,
    job_title: str,
    company: str | None,
    source: SkillGapSource,
    missing_required: list[str],
    missing_preferred: list[str],
) -> None:
    required = _normalize_skill_list(missing_required)
    preferred = _normalize_skill_list(missing_preferred)
    if not required and not preferred:
        return

    title = job_title.strip() or "İlan"
    db.upsert_skill_gap_listing(
        job_key,
        job_url=job_url,
        job_title=title,
        company=company.strip() if company else None,
        source=source,
    )
    db.replace_skill_gap_items(
        job_key,
        missing_required=required,
        missing_preferred=preferred,
    )


def _analysis_job_key(
    *,
    result: AnalysisResult,
    job_metadata: dict,
    job_text: str | None,
) -> str:
    job_url = job_metadata.get("url") if isinstance(job_metadata.get("url"), str) else None
    if job_url and job_url.strip():
        return job_key_from_url(job_url)
    if job_text and job_text.strip():
        return job_key_from_text(job_text)
    return f"analysis:{result.id}"


def backfill_skill_gaps_from_analyses() -> int:
    existing_keys = db.get_skill_gap_job_keys()
    imported = 0
    for row in db.list_completed_analyses():
        result_data = row.get("result")
        if not isinstance(result_data, dict):
            continue
        try:
            result = AnalysisResult.model_validate(result_data)
        except Exception:
            continue

        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        job_meta = metadata.get("job")
        if not isinstance(job_meta, dict):
            job_meta = {}
        cache_key = job_meta.get("cache_key")
        job_text = db.get_cached_text_value(cache_key) if isinstance(cache_key, str) else None
        job_key = _analysis_job_key(result=result, job_metadata=job_meta, job_text=job_text)
        if job_key in existing_keys:
            continue

        source: SkillGapSource = (
            "llm_analysis" if metadata.get("analysis_mode") == "llm_only" else "analysis"
        )
        record_analysis_gaps(
            result=result,
            job_metadata=job_meta,
            job_text=job_text,
            source=source,
        )
        existing_keys.add(job_key)
        imported += 1
    return imported


def get_skill_gap_summary() -> SkillGapSummaryResponse:
    rows = db.get_skill_gap_summary_rows()
    aggregates = [
        SkillGapAggregate(
            skill_name=row["skill_name"],
            gap_type=row["gap_type"],  # type: ignore[arg-type]
            listing_count=row["listing_count"],
            listings=[
                SkillGapListingRef(
                    job_key=listing["job_key"],
                    job_title=listing["job_title"],
                    job_url=listing["job_url"],
                    company=listing["company"],
                    source=listing["source"],  # type: ignore[arg-type]
                    last_seen_at=listing["last_seen_at"],
                )
                for listing in row["listings"]
            ],
        )
        for row in rows
    ]
    total_listings = len({listing.job_key for item in aggregates for listing in item.listings})
    return SkillGapSummaryResponse(
        aggregates=aggregates,
        total_skills=len(aggregates),
        total_listings=total_listings,
    )


def clear_skill_gaps() -> None:
    db.clear_skill_gaps()


def _job_title_from_text(job_text: str | None) -> str:
    if not job_text or not job_text.strip():
        return "İlan metni"
    for line in job_text.splitlines():
        cleaned = line.strip()
        if cleaned and len(cleaned) <= 120:
            return cleaned
    return "İlan metni"


def record_job_search_listings(listings: list[JobListingMatch]) -> None:
    for listing in listings:
        record_listing_gaps(
            job_key=job_key_from_url(listing.url),
            job_url=listing.url,
            job_title=listing.title,
            company=listing.company,
            source="job_search",
            missing_required=listing.missing_required_skills,
            missing_preferred=listing.missing_preferred_skills,
        )


def record_analysis_gaps(
    *,
    result: AnalysisResult,
    job_metadata: dict,
    job_text: str | None,
    source: SkillGapSource,
) -> None:
    missing_required = [match.name for match in result.missing_required_skills]
    missing_preferred = [match.name for match in result.missing_preferred_skills]
    if not missing_required and not missing_preferred:
        return

    job_url = job_metadata.get("url") if isinstance(job_metadata.get("url"), str) else None
    if job_url and job_url.strip():
        job_key = job_key_from_url(job_url)
        job_title = _job_title_from_text(job_text) if job_text else job_url
    elif job_text and job_text.strip():
        job_key = job_key_from_text(job_text)
        job_title = _job_title_from_text(job_text)
    else:
        job_key = f"analysis:{result.id}"
        job_title = "İlan metni"

    record_listing_gaps(
        job_key=job_key,
        job_url=job_url,
        job_title=job_title,
        company=None,
        source=source,
        missing_required=missing_required,
        missing_preferred=missing_preferred,
    )

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

JobSource = Literal["linkedin", "kariyer"]


@dataclass(frozen=True)
class JobListingCandidate:
    source: JobSource
    title: str
    company: str | None
    location: str | None
    url: str
    description: str
    posted_at: str | None = None


def detect_job_source(url: str) -> JobSource | None:
    host = urlparse(url.strip()).netloc.casefold().replace("www.", "")
    if _host_matches_domain(host, "linkedin.com"):
        return "linkedin"
    if _host_matches_domain(host, "kariyer.net"):
        return "kariyer"
    return None


def _host_matches_domain(host: str, domain: str) -> bool:
    domain = domain.casefold()
    return host == domain or host.endswith(f".{domain}")


def build_linkedin_search_input(*, queries: list[str], location: str | None, max_results: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "queries": queries[:5],
        "maxItems": max_results,
    }
    if location:
        payload["location"] = location
    return payload


def build_kariyer_search_input(*, queries: list[str], location: str | None, max_results: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "keyword": queries[0] if queries else "developer",
        "keywords": queries[:5],
        "maxResults": max_results,
    }
    if location:
        payload["location"] = location
    return payload


def build_job_url_input(url: str) -> dict[str, Any]:
    return {
        "startUrls": [{"url": url}],
        "urls": [url],
        "url": url,
    }


def normalize_linkedin_items(items: list[dict[str, Any]]) -> list[JobListingCandidate]:
    candidates: list[JobListingCandidate] = []
    seen_urls: set[str] = set()
    for item in items:
        candidate = _normalize_item(item, source="linkedin")
        if candidate is None:
            continue
        key = candidate.url.casefold()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        candidates.append(candidate)
    return candidates


def normalize_kariyer_items(items: list[dict[str, Any]]) -> list[JobListingCandidate]:
    candidates: list[JobListingCandidate] = []
    seen_urls: set[str] = set()
    for item in items:
        candidate = _normalize_item(item, source="kariyer")
        if candidate is None:
            continue
        key = candidate.url.casefold()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        candidates.append(candidate)
    return candidates


def normalize_job_detail_item(item: dict[str, Any], *, source: JobSource, fallback_url: str) -> JobListingCandidate | None:
    candidate = _normalize_item(item, source=source)
    if candidate is not None:
        return candidate
    description = _first_string(item, "description", "jobDescription", "text", "content")
    title = _first_string(item, "title", "jobTitle", "position", "name") or "Job posting"
    if not description and not title:
        return None
    return JobListingCandidate(
        source=source,
        title=title,
        company=_first_string(item, "company", "companyName", "employer"),
        location=_first_string(item, "location", "city", "place"),
        url=fallback_url,
        description=description or title,
        posted_at=_first_string(item, "postedAt", "datePosted", "publishedAt"),
    )


def _normalize_item(item: dict[str, Any], *, source: JobSource) -> JobListingCandidate | None:
    title = _first_string(item, "title", "jobTitle", "position", "name", "role")
    url = _first_string(item, "url", "link", "jobUrl", "jobLink", "applyUrl", "detailUrl")
    description = _first_string(
        item,
        "description",
        "jobDescription",
        "snippet",
        "summary",
        "text",
        "content",
    )
    if not title or not url:
        return None
    if len(description.strip()) < 20:
        description = "\n".join(part for part in (title, description) if part)
    return JobListingCandidate(
        source=source,
        title=title,
        company=_first_string(item, "company", "companyName", "employer", "organization"),
        location=_first_string(item, "location", "city", "place", "region"),
        url=url,
        description=description,
        posted_at=_first_string(item, "postedAt", "datePosted", "publishedAt", "listedAt"),
    )


def _first_string(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None

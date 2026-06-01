from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlencode, urlparse

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


def build_linkedin_jobs_search_url(keyword: str, location: str | None = None) -> str:
    params: dict[str, str] = {"keywords": keyword.strip()}
    if location and location.strip():
        params["location"] = _ascii_fold_location(location)
    return f"https://www.linkedin.com/jobs/search/?{urlencode(params)}"


def build_linkedin_search_input(*, queries: list[str], location: str | None, max_results: int) -> dict[str, Any]:
    """Input for LinkedIn jobs search actor (``APIFY_LINKEDIN_SEARCH_ACTOR_ID``)."""
    search_queries = _sanitize_search_queries(queries) or ["software developer"]
    locations = _split_locations(location)
    return {
        "urls": [
            build_linkedin_jobs_search_url(query, location_item)
            for query in search_queries
            for location_item in locations
        ][:10],
        "scrapeCompany": True,
        "count": max(10, max_results),
        "splitByLocation": False,
    }


KARIYER_DEFAULT_START_URL = "https://www.kariyer.net/is-ilanlari"


def build_kariyer_listing_start_urls(location: str | None) -> list[str]:
    locations = _kariyer_locations(location)
    if locations:
        return [f"https://www.kariyer.net/is-ilanlari/{_kariyer_city_slug(item)}" for item in locations[:2]]
    return [KARIYER_DEFAULT_START_URL]


def build_kariyer_search_input(*, queries: list[str], location: str | None, max_results: int) -> dict[str, Any]:
    """Build input for Kariyer.net search actor (``APIFY_KARIYER_SEARCH_ACTOR_ID``).

    Many actors have no ``location`` field — cities are passed via ``startUrls``.
    When cities are known, combine ``keyword`` with city listing URLs.
    """
    search_queries = _sanitize_search_queries(queries) or ["yazilim muhendisi"]
    locations = _kariyer_locations(location)
    payload: dict[str, Any] = {
        "results_wanted": max_results,
        "max_pages": _kariyer_max_pages(max_results),
        "max_job_age": "all",
        "proxyConfiguration": {"useApifyProxy": False},
    }

    if locations:
        payload["startUrls"] = build_kariyer_listing_start_urls(location)

    payload["keyword"] = search_queries[0]
    return payload


def build_job_url_input(url: str) -> dict[str, Any]:
    return {
        "startUrls": [{"url": url}],
        "urls": [url],
        "url": url,
    }


def _kariyer_max_pages(max_results: int) -> int:
    return max(3, min(20, (max_results + 9) // 10))


def _sanitize_search_queries(queries: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for query in queries[:8]:
        if not isinstance(query, str):
            continue
        text = query.strip()
        if len(text) < 2:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned[:5]


def _split_locations(location: str | None) -> list[str | None]:
    if not location or not location.strip():
        return [None]
    locations: list[str] = []
    seen: set[str] = set()
    for raw_location in location.replace(";", ",").split(","):
        text = raw_location.strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        locations.append(text)
    return locations[:3] or [None]


def _kariyer_locations(location: str | None) -> list[str]:
    locations: list[str] = []
    for location_item in _split_locations(location):
        if not location_item:
            continue
        if location_item.casefold() in {"remote", "uzaktan"}:
            continue
        locations.append(location_item)
    return locations[:2]


def _kariyer_keyword_slug(keyword: str, *, separator: str) -> str:
    folded = _ascii_fold_location(keyword)
    return separator.join(part for part in folded.split() if part)


def _kariyer_city_slug(location: str) -> str:
    return _kariyer_keyword_slug(location, separator="-")


def _ascii_fold_location(location: str) -> str:
    # LinkedIn public search is more stable with lowercase ASCII city names.
    translated = location.translate(str.maketrans({"İ": "I", "ı": "i"}))
    return unicodedata.normalize("NFKD", translated).encode("ascii", "ignore").decode("ascii").strip().lower()


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
    description = _first_string(item, "description_text", "descriptionText", "description", "jobDescription", "text", "content")
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
        posted_at=_first_string(item, "posting_date", "postedAt", "datePosted", "publishedAt"),
    )


def _normalize_item(item: dict[str, Any], *, source: JobSource) -> JobListingCandidate | None:
    title = _first_string(item, "title", "jobTitle", "position", "name", "role")
    url = _first_string(item, "url", "link", "jobUrl", "jobLink", "applyUrl", "detailUrl")
    description = _first_string(
        item,
        "description_text",
        "descriptionText",
        "description",
        "jobDescription",
        "snippet",
        "summary",
        "text",
        "content",
    ) or ""
    if not title or not url:
        return None
    if len(description.strip()) < 20:
        description = "\n".join(part for part in (title, description) if part and part.strip())
    if not description.strip():
        description = title
    return JobListingCandidate(
        source=source,
        title=title,
        company=_first_string(item, "company", "companyName", "employer", "organization"),
        location=_first_string(item, "location", "city", "place", "region"),
        url=url,
        description=description,
        posted_at=_first_string(
            item,
            "posting_date",
            "postedAt",
            "datePosted",
            "publishedAt",
            "listedAt",
        ),
    )


def _first_string(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None

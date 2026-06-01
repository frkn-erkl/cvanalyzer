from __future__ import annotations

from app.config import get_settings
from app.db import get_cached_text, set_cached_text
from app.services.apify_client import ApifyClient, ApifyError
from app.services.apify_utils import effective_use_apify
from app.services.ingestion import IngestedDocument, _cache_key, _truncate
from app.services.job_listings import (
    build_job_url_input,
    detect_job_source,
    normalize_job_detail_item,
    normalize_kariyer_items,
    normalize_linkedin_items,
)


async def fetch_job_document_via_apify(url: str) -> IngestedDocument | None:
    settings = get_settings()
    source = detect_job_source(url)
    apify_active, _ = effective_use_apify(True)
    if source is None or not apify_active:
        return None

    actor_id = (
        settings.apify_linkedin_job_actor_id
        if source == "linkedin"
        else settings.apify_kariyer_job_actor_id
    ).strip()
    if not actor_id:
        return None

    cache_lookup = _cache_key("job", f"apify-url:{url}", url.encode("utf-8"))
    cached = get_cached_text(cache_lookup)
    if cached:
        cached_text, metadata = cached
        metadata = dict(metadata)
        metadata["cache_hit"] = True
        return IngestedDocument(cached_text, cache_lookup, metadata)

    client = ApifyClient()
    try:
        items = await client.run_actor(actor_id, build_job_url_input(url))
    except ApifyError:
        return None

    normalizer = normalize_linkedin_items if source == "linkedin" else normalize_kariyer_items
    candidates = normalizer(items)
    if not candidates and items:
        detail = normalize_job_detail_item(items[0], source=source, fallback_url=url)
        if detail:
            candidates = [detail]
    if not candidates:
        return None

    candidate = candidates[0]
    text = _truncate(candidate.description)
    content_hash_key = _cache_key("job", f"apify-content:{source}", text.encode("utf-8"))
    metadata = {
        "source": "apify",
        "url": url,
        "listing_source": source,
        "title": candidate.title,
        "company": candidate.company or "",
        "chars": len(text),
        "cache_hit": False,
        "apify_actor": actor_id,
    }
    set_cached_text(content_hash_key, text, metadata)
    set_cached_text(cache_lookup, text, metadata)
    return IngestedDocument(text, content_hash_key, metadata)

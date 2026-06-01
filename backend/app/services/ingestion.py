import hashlib
from dataclasses import dataclass
from typing import Literal

import httpx
from fastapi import UploadFile

from app.config import get_settings
from app.db import get_cached_text, set_cached_text
from app.services.extraction import ExtractedText, clean_text, extract_text_from_bytes


SourceKind = Literal["cv", "job"]


@dataclass(frozen=True)
class IngestedDocument:
    text: str
    cache_key: str
    metadata: dict[str, str | int | bool]


async def ingest_text(kind: SourceKind, text: str) -> IngestedDocument:
    normalized = _truncate(clean_text(text))
    cache_key = _cache_key(kind, "text", normalized.encode("utf-8"))
    cached = get_cached_text(cache_key)
    if cached:
        cached_text, metadata = cached
        metadata = dict(metadata)
        metadata["cache_hit"] = True
        return IngestedDocument(cached_text, cache_key, metadata)

    metadata: dict[str, str | int | bool] = {"source": "text", "chars": len(normalized), "cache_hit": False}
    set_cached_text(cache_key, normalized, metadata)
    return IngestedDocument(normalized, cache_key, metadata)


async def ingest_upload(kind: SourceKind, upload: UploadFile) -> IngestedDocument:
    content = await upload.read()
    return ingest_upload_bytes(
        kind,
        content,
        filename=upload.filename,
        content_type=upload.content_type,
    )


def ingest_upload_bytes(
    kind: SourceKind,
    content: bytes,
    *,
    filename: str | None,
    content_type: str | None,
) -> IngestedDocument:
    cache_key = _cache_key(kind, f"file:{filename or 'upload'}", content)
    cached = get_cached_text(cache_key)
    if cached:
        cached_text, metadata = cached
        metadata = dict(metadata)
        metadata["cache_hit"] = True
        return IngestedDocument(cached_text, cache_key, metadata)

    extracted = extract_text_from_bytes(
        content,
        filename=filename,
        content_type=content_type,
    )
    text = _truncate(extracted.text)
    metadata = {
        "source": "file",
        "filename": filename or "upload",
        "content_type": content_type or "application/octet-stream",
        "chars": len(text),
        "cache_hit": False,
        **extracted.metadata,
    }
    set_cached_text(cache_key, text, metadata)
    return IngestedDocument(text, cache_key, metadata)


async def ingest_url(kind: SourceKind, url: str, *, use_apify: bool = False) -> IngestedDocument:
    settings = get_settings()
    url = url.strip()
    cached_by_url = get_cached_text(_cache_key(kind, "url", url.encode("utf-8")))
    if cached_by_url:
        cached_text, metadata = cached_by_url
        metadata = dict(metadata)
        metadata["cache_hit"] = True
        return IngestedDocument(cached_text, _cache_key(kind, "url", url.encode("utf-8")), metadata)

    apify_attempted = False
    if kind == "job" and use_apify:
        from app.services.apify_ingest import fetch_job_document_via_apify
        from app.services.apify_utils import effective_use_apify
        from app.services.job_listings import detect_job_source

        apify_active, _ = effective_use_apify(True)
        if apify_active and detect_job_source(url) is not None:
            apify_attempted = True
            apify_document = await fetch_job_document_via_apify(url)
            if apify_document is not None:
                return apify_document

    async with httpx.AsyncClient(follow_redirects=True, timeout=settings.request_timeout_seconds) as client:
        response = await client.get(url, headers={"User-Agent": "LocalCVAnalyzer/1.0"})
        response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    extracted = extract_text_from_bytes(
        response.content,
        filename=url,
        content_type=content_type,
    )
    text = _truncate(extracted.text)
    content_hash_key = _cache_key(kind, "url-content", response.content)
    metadata = {
        "source": "url",
        "url": url,
        "status_code": response.status_code,
        "content_type": content_type,
        "chars": len(text),
        "cache_hit": False,
        **extracted.metadata,
    }
    if apify_attempted:
        metadata["apify_fallback"] = True
        metadata["apify_error"] = "Apify ile ilan metni alınamadı; standart link ingest kullanıldı."
    set_cached_text(content_hash_key, text, metadata)
    set_cached_text(_cache_key(kind, "url", url.encode("utf-8")), text, metadata)
    return IngestedDocument(text, content_hash_key, metadata)


def validate_non_empty(document: IngestedDocument, label: str) -> None:
    if len(document.text.strip()) < 40:
        raise ValueError(f"{label} metni çıkarılamadı veya çok kısa görünüyor.")


def _cache_key(kind: SourceKind, source: str, content: bytes) -> str:
    digest = hashlib.sha256(content).hexdigest()
    return f"{kind}:{source}:{digest}"


def _truncate(text: str) -> str:
    return text[: get_settings().max_input_chars]

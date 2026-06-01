import hashlib
import re
from typing import Any

import httpx
from langdetect import LangDetectException, detect_langs

from app.config import LlmProvider, get_settings, normalize_llm_provider
from app.db import get_cached_text, set_cached_text

TURKISH_CHARS = set("çğıöşüÇĞİÖŞÜ")


async def ensure_english_for_llm(
    text: str,
    *,
    purpose: str = "llm_input",
    provider: LlmProvider | str | None = None,
) -> tuple[str, dict[str, Any]]:
    settings = get_settings()
    normalized_provider = normalize_llm_provider(provider or settings.default_llm_provider)
    metadata: dict[str, Any] = {
        "purpose": purpose,
        "was_translated": False,
        "detected_language": None,
        "cache_hit": False,
        "chars": len(text),
        "provider": normalized_provider,
    }
    if normalized_provider == "cursor":
        return text, metadata
    if not settings.auto_translate_llm_input_to_english or not text.strip():
        return text, metadata

    detected = detect_language(text)
    metadata["detected_language"] = detected
    if is_english_text(detected, text):
        return text, metadata

    cache_key = _translation_cache_key(text)
    cached = get_cached_text(cache_key)
    if cached:
        metadata["cache_hit"] = True
        metadata["was_translated"] = True
        return cached[0], metadata

    translated = await _translate_to_english(text, purpose=purpose)
    if not translated or translated.strip() == text.strip():
        return text, metadata

    set_cached_text(
        cache_key,
        translated,
        {
            "detected_language": detected,
            "was_translated": True,
            "purpose": purpose,
            "chars": len(translated),
        },
    )
    metadata["was_translated"] = True
    return translated, metadata


async def ensure_english_prompt(prompt: str) -> tuple[str, dict[str, Any]]:
    return await ensure_english_for_llm(prompt, purpose="prompt")


def detect_language(text: str) -> str | None:
    sample = text[:2000].strip()
    if not sample:
        return None
    if _turkish_heuristic(sample):
        return "tr"
    try:
        candidates = detect_langs(sample)
    except LangDetectException:
        return None
    if not candidates:
        return None
    top = candidates[0]
    if top.prob >= get_settings().translation_min_confidence:
        return top.lang
    return None


def is_english_text(detected: str | None, text: str) -> bool:
    if detected == "en":
        return True
    if detected in {"tr", "de", "fr", "es", "it", "pt", "ar", "ru"}:
        return False
    if _turkish_heuristic(text[:2000]):
        return False
    return sum(1 for char in text if char in TURKISH_CHARS) == 0


async def _translate_to_english(text: str, *, purpose: str) -> str | None:
    settings = get_settings()
    chunks = _chunk_text(text, settings.translation_chunk_chars)
    translated_chunks: list[str] = []
    for chunk in chunks:
        prompt = f"""Translate the following text to English.
Rules:
- Preserve names, company names, dates, skills, and technical terms.
- Do not add, remove, or invent information.
- Output only the translated text with no commentary.

Purpose: {purpose}

Text:
{chunk}
"""
        result = await _ollama_generate_raw(prompt, temperature=0.0)
        if not result:
            return None
        translated_chunks.append(result.strip())
    return "\n\n".join(translated_chunks)


async def _ollama_generate_raw(prompt: str, *, temperature: float) -> str | None:
    settings = get_settings()
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt[: settings.max_llm_context_chars],
        "stream": False,
        "think": False,
        "options": {
            "temperature": temperature,
            "num_ctx": settings.ollama_num_ctx,
            "num_predict": settings.translation_num_predict,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(f"{settings.ollama_base_url}/api/generate", json=payload)
            response.raise_for_status()
        return response.json().get("response", "").strip() or None
    except Exception:
        return None


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= chunk_size:
            current = paragraph
            continue
        for index in range(0, len(paragraph), chunk_size):
            chunks.append(paragraph[index : index + chunk_size])
        current = ""
    if current:
        chunks.append(current)
    return chunks or [text]


def _turkish_heuristic(text: str) -> bool:
    if any(char in TURKISH_CHARS for char in text):
        return True
    normalized = text.casefold()
    turkish_words = (" ve ", " için ", " deneyim", " yil", " yıl", " ilan", " beceri", " görev", " sorumluluk")
    padded = f" {normalized} "
    return any(word in padded for word in turkish_words)


def _translation_cache_key(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"translate:en:{digest}"

from __future__ import annotations

from app.config import get_settings


def effective_use_apify(requested: bool) -> tuple[bool, str | None]:
    if not requested:
        return False, None
    settings = get_settings()
    if not settings.apify_enabled:
        return False, "Apify sunucuda devre dışı (APIFY_ENABLED=false)."
    if not settings.apify_api_token.strip():
        return False, "APIFY_API_TOKEN tanımlı değil; backend/.env dosyasını kontrol edin."
    return True, None


def apify_actor_fingerprint() -> str:
    settings = get_settings()
    parts = [
        settings.apify_linkedin_search_actor_id.strip(),
        settings.apify_linkedin_job_actor_id.strip(),
        settings.apify_kariyer_search_actor_id.strip(),
        settings.apify_kariyer_job_actor_id.strip(),
    ]
    return "|".join(parts)

from __future__ import annotations

from app import db
from app.config import LlmProvider, get_settings
from app.models import (
    AnalysisResult,
    CvAddSuggestion,
    Evidence,
    ScoreBreakdown,
    ScoreDetail,
    SkillMatch,
    StructuredJob,
    StructuredProfile,
)
from app.services.analysis import _ingest_cv, _ingest_job, _apify_job_warnings
from app.services.cv_rewrite import _parse_json_response
from app.services.ingestion import validate_non_empty
from app.services.language import ensure_english_for_llm
from app.services.llm import get_llm_client
from app.services.llm_progress import analysis_progress_callback, merge_thinking_metadata
from app.services.skill_gaps import record_analysis_gaps

_LLM_ANALYSIS_SYSTEM = (
    "You are an evidence-based career analysis assistant. "
    "Base every claim only on the provided CV and job posting text. "
    "Never mark a skill as matched or as a strength unless the CV supports it. "
    "Respond with a single valid JSON object only. "
    "Do not wrap JSON in markdown fences and do not add commentary before or after the JSON."
)

_SCORE_KEYS = (
    "overall",
    "technical_skills",
    "experience_seniority",
    "domain_keywords",
    "education_certifications",
    "language_communication",
    "ats_compatibility",
)

_SCORE_LABELS = {
    "overall": "Genel uygunluk",
    "technical_skills": "Teknik beceriler",
    "experience_seniority": "Deneyim / seniority",
    "domain_keywords": "Domain anahtar kelimeleri",
    "education_certifications": "Eğitim / sertifika",
    "language_communication": "Dil / iletişim",
    "ats_compatibility": "ATS uyumluluğu",
}

_CV_ADD_CATEGORIES = {
    "required_skill",
    "preferred_skill",
    "language",
    "keyword",
    "experience",
    "format",
    "education",
}

_CV_ADD_PRIORITIES = {"high", "medium", "low"}


async def run_llm_analysis(
    *,
    analysis_id: str,
    cv_text: str | None,
    cv_url: str | None,
    cv_file_content: bytes | None,
    cv_filename: str | None,
    cv_content_type: str | None,
    job_url: str | None,
    job_text: str | None,
    llm_provider: LlmProvider = "local",
    use_apify: bool = False,
) -> None:
    db.update_analysis(analysis_id, "running")
    try:
        db.update_analysis_progress(
            analysis_id,
            {"thinking": "", "response": "", "phase": "thinking"},
        )
        cv_document = await _ingest_cv(cv_text, cv_url, cv_file_content, cv_filename, cv_content_type)
        job_document = await _ingest_job(job_url, job_text, use_apify=use_apify)
        validate_non_empty(cv_document, "CV")
        validate_non_empty(job_document, "İş ilanı")

        cv_text_for_llm, cv_lang_meta = await ensure_english_for_llm(
            cv_document.text, purpose="cv", provider=llm_provider
        )
        job_text_for_llm, job_lang_meta = await ensure_english_for_llm(
            job_document.text, purpose="job", provider=llm_provider
        )

        llm_health = await get_llm_client(llm_provider).health()
        if not llm_health.get("available"):
            detail = llm_health.get("error")
            provider_label = "Cursor API" if llm_provider == "cursor" else "Ollama"
            if isinstance(detail, str) and detail.strip():
                raise ValueError(f"{provider_label} kullanılamıyor: {detail.strip()}")
            raise ValueError(f"{provider_label} çalışmıyor veya gerekli LLM modeli yapılandırılmamış.")

        llm_payload, llm_failure, llm_thinking = await _generate_llm_analysis_payload(
            cv_text_for_llm,
            job_text_for_llm,
            llm_provider=llm_provider,
            analysis_id=analysis_id,
        )
        if llm_payload is None:
            raise ValueError(llm_failure or "LLM geçerli analiz JSON'u üretemedi.")

        result = _map_payload_to_result(analysis_id, llm_payload)
        result.warnings = [*result.warnings, *_apify_job_warnings(job_document)]
        output_sources = {
            "domain_scoring": "llm",
            "recommendations": "llm",
            "profile_summary": "llm",
            "cv_add_suggestions": "llm",
            "skill_matching": "llm",
            "summary": "llm",
        }
        result.metadata = merge_thinking_metadata(
            {
                "cv": {**cv_document.metadata, "cache_key": cv_document.cache_key},
                "job": {**job_document.metadata, "cache_key": job_document.cache_key},
                "analysis_mode": "llm_only",
                "deep_analysis": True,
                "llm_provider": llm_provider,
                "use_apify": use_apify,
                "output_sources": output_sources,
                "llm_translation": {
                    "cv": cv_lang_meta,
                    "job": job_lang_meta,
                },
            },
            llm_thinking,
        )
        record_analysis_gaps(
            result=result,
            job_metadata=job_document.metadata,
            job_text=job_document.text,
            source="llm_analysis",
        )
        db.update_analysis(analysis_id, "completed", result=result.model_dump())
    except Exception as exc:  # noqa: BLE001 - persisted for UI visibility
        db.update_analysis(analysis_id, "failed", error=str(exc))


async def _generate_llm_analysis_payload(
    cv_text: str,
    job_text: str,
    *,
    llm_provider: LlmProvider = "local",
    analysis_id: str,
) -> tuple[dict | None, str | None, str | None]:
    settings = get_settings()
    prompt = _build_llm_analysis_prompt(
        cv_text[: settings.llm_analysis_cv_chars],
        job_text[: settings.llm_analysis_job_chars],
    )
    provider_label = "Cursor API" if llm_provider == "cursor" else "Yerel LLM"
    last_failure = f"{provider_label} geçerli analiz JSON'u üretemedi."
    last_thinking: str | None = None
    on_progress = analysis_progress_callback(analysis_id)
    client = get_llm_client(llm_provider)

    for attempt in range(2):
        num_predict = settings.llm_analysis_num_predict if attempt == 0 else settings.llm_analysis_num_predict + 1024
        if hasattr(client, "generate_detailed"):
            detailed = await client.generate_detailed(
                prompt,
                system=_LLM_ANALYSIS_SYSTEM,
                temperature=0.1 if attempt == 0 else 0.05,
                num_predict=num_predict,
                translate_input=False,
                timeout_seconds=settings.llm_analysis_timeout_seconds,
                on_progress=on_progress,
            )
            response = detailed.text
            last_thinking = detailed.thinking or last_thinking
        else:
            response = await client.generate(
                prompt,
                system=_LLM_ANALYSIS_SYSTEM,
                temperature=0.1 if attempt == 0 else 0.05,
                num_predict=num_predict,
                translate_input=False,
                timeout_seconds=settings.llm_analysis_timeout_seconds,
                on_progress=on_progress,
            )
        if not response:
            last_failure = (
                f"{provider_label} {int(settings.llm_analysis_timeout_seconds)} saniye içinde yanıt vermedi. "
                "Analiz büyük CV/ilan metinlerinde birkaç dakika sürebilir; tekrar deneyin veya metni kısaltın."
            )
            continue

        payload = _parse_json_response(response)
        if payload is None:
            last_failure = (
                f"{provider_label} yanıt verdi ancak JSON parse edilemedi; çıktı token limitinde kesilmiş olabilir."
            )
            continue

        normalized = _normalize_payload(payload)
        if _validate_payload(normalized):
            return normalized, None, last_thinking

        last_failure = f"{provider_label} yanıt verdi ancak beklenen analiz alanları eksik veya geçersiz."

    return None, last_failure, last_thinking


def _build_llm_analysis_prompt(cv_text: str, job_text: str) -> str:
    return f"""
Analyze the CV against the job posting below. Return ONLY valid JSON matching this exact shape.
Do not invent skills, employers, certifications, or experience not supported by the CV text.
Write all user-facing text fields in Turkish (technical terms like Python, Kubernetes are allowed).

CV:
{cv_text}

Job posting:
{job_text}

Required JSON shape:
{{
  "scores": {{
    "overall": 78,
    "technical_skills": 82,
    "experience_seniority": 75,
    "domain_keywords": 70,
    "education_certifications": 65,
    "language_communication": 80,
    "ats_compatibility": 72
  }},
  "score_details": [
    {{
      "key": "technical_skills",
      "label": "Teknik beceriler",
      "score": 82,
      "weight": "Genel skora %38 katkı",
      "method": "How this score was judged from CV/job evidence",
      "factors": ["short evidence-based factor"]
    }}
  ],
  "cv_profile": {{
    "skills": ["python", "fastapi"],
    "languages": ["English"],
    "education": ["Computer Engineering"],
    "certifications": [],
    "years_experience": 6,
    "seniority": "senior",
    "highlights": ["short CV evidence line"],
    "evidence": {{}}
  }},
  "job_profile": {{
    "required_skills": ["python", "fastapi"],
    "preferred_skills": ["kubernetes"],
    "languages": ["English"],
    "education": [],
    "seniority": "senior",
    "responsibilities": ["short responsibility from job"],
    "keywords": ["backend", "api"],
    "evidence": {{}}
  }},
  "matched_required_skills": [
    {{
      "name": "python",
      "matched": true,
      "evidence": [{{"label": "CV", "source": "cv", "snippet": "short quote"}}]
    }}
  ],
  "missing_required_skills": [
    {{
      "name": "kubernetes",
      "matched": false,
      "evidence": [{{"label": "Job", "source": "job", "snippet": "short quote"}}]
    }}
  ],
  "missing_preferred_skills": [],
  "strengths": ["evidence-based strength in Turkish"],
  "improvement_suggestions": ["evidence-based improvement in Turkish"],
  "tailored_cv_suggestions": ["concrete CV edit suggestion in Turkish"],
  "cv_add_suggestions": [
    {{
      "title": "Kubernetes",
      "category": "required_skill",
      "priority": "high",
      "reason": "why this matters for the job",
      "how_to_add": "how to add only if truly supported",
      "job_evidence": ["short job quote"]
    }}
  ],
  "suggested_profile_summary": "2-4 sentence ATS-friendly profile summary in Turkish",
  "llm_summary": "Markdown summary in Turkish with headings: ## Karar, ## Güçlü yönler, ## Kritik boşluklar, ## Önerilen profil özeti, ## CV'ye somut adımlar",
  "warnings": ["optional caution in Turkish"]
}}

Rules:
- Output must be one JSON object only.
- All score values must be integers from 0 to 100.
- Include score_details for every score key: overall, technical_skills, experience_seniority, domain_keywords, education_certifications, language_communication, ats_compatibility.
- matched_required_skills must only include required skills clearly supported by the CV.
- missing_required_skills and missing_preferred_skills must come from the job posting.
- cv_add_suggestions category must be one of: required_skill, preferred_skill, language, keyword, experience, format, education.
- cv_add_suggestions priority must be one of: high, medium, low.
- llm_summary must use exactly these markdown headings in order: ## Karar, ## Güçlü yönler, ## Kritik boşluklar, ## Önerilen profil özeti, ## CV'ye somut adımlar.
- Escape newlines inside JSON string values as \\n.
- Do not use deterministic keyword lists; reason directly from the provided texts.
"""


def _normalize_payload(payload: dict) -> dict:
    normalized = dict(payload)
    llm_summary = normalized.get("llm_summary")
    if not isinstance(llm_summary, str) or not llm_summary.strip():
        strengths = _string_list(normalized.get("strengths", []))
        improvements = _string_list(normalized.get("improvement_suggestions", []))
        tailored = _string_list(normalized.get("tailored_cv_suggestions", []))
        profile = _optional_string(normalized.get("suggested_profile_summary")) or "Profil özeti üretilemedi."
        normalized["llm_summary"] = _build_fallback_summary(strengths, improvements, tailored, profile)
    return normalized


def _build_fallback_summary(
    strengths: list[str],
    improvements: list[str],
    tailored: list[str],
    profile: str,
) -> str:
    def bullets(values: list[str]) -> str:
        return "\n".join(f"- {value}" for value in values[:5]) or "- Belirgin madde yok."

    return (
        "## Karar\n"
        "CV–ilan eşleşmesi LLM tarafından değerlendirildi.\n\n"
        f"## Güçlü yönler\n{bullets(strengths)}\n\n"
        f"## Kritik boşluklar\n{bullets(improvements)}\n\n"
        f"## Önerilen profil özeti\n{profile}\n\n"
        f"## CV'ye somut adımlar\n{bullets(tailored)}"
    )


def _validate_payload(payload: dict) -> bool:
    scores = payload.get("scores")
    if not isinstance(scores, dict):
        return False
    for key in _SCORE_KEYS:
        value = scores.get(key)
        if not isinstance(value, (int, float)):
            return False
        if not 0 <= int(value) <= 100:
            return False
    required_lists = (
        "strengths",
        "improvement_suggestions",
        "tailored_cv_suggestions",
        "matched_required_skills",
        "missing_required_skills",
        "missing_preferred_skills",
    )
    for key in required_lists:
        if not isinstance(payload.get(key), list):
            return False
    if not isinstance(payload.get("cv_profile"), dict):
        return False
    if not isinstance(payload.get("job_profile"), dict):
        return False
    llm_summary = payload.get("llm_summary")
    if not isinstance(llm_summary, str) or not llm_summary.strip():
        return False
    return True


def _map_payload_to_result(analysis_id: str, payload: dict) -> AnalysisResult:
    scores = _parse_scores(payload["scores"])
    score_details = _parse_score_details(payload.get("score_details"), scores)
    cv_profile = _parse_cv_profile(payload["cv_profile"])
    job_profile = _parse_job_profile(payload["job_profile"])
    matched = _parse_skill_matches(payload["matched_required_skills"], default_matched=True)
    missing_required = _parse_skill_matches(payload["missing_required_skills"], default_matched=False)
    missing_preferred = _parse_skill_matches(payload["missing_preferred_skills"], default_matched=False)
    cv_add_suggestions = _parse_cv_add_suggestions(payload.get("cv_add_suggestions", []))
    warnings = _string_list(payload.get("warnings", []))

    return AnalysisResult(
        id=analysis_id,
        status="completed",
        scores=scores,
        score_details=score_details,
        cv_profile=cv_profile,
        job_profile=job_profile,
        matched_required_skills=matched,
        missing_required_skills=missing_required,
        missing_preferred_skills=missing_preferred,
        strengths=_string_list(payload.get("strengths", [])),
        improvement_suggestions=_string_list(payload.get("improvement_suggestions", [])),
        tailored_cv_suggestions=_string_list(payload.get("tailored_cv_suggestions", [])),
        cv_add_suggestions=cv_add_suggestions,
        suggested_profile_summary=_optional_string(payload.get("suggested_profile_summary")),
        llm_summary=str(payload.get("llm_summary", "")).strip(),
        warnings=warnings,
        metadata={},
    )


def _parse_scores(raw: dict) -> ScoreBreakdown:
    return ScoreBreakdown(**{key: _clamp_score(raw.get(key, 0)) for key in _SCORE_KEYS})


def _parse_score_details(raw: object, scores: ScoreBreakdown) -> list[ScoreDetail]:
    details: list[ScoreDetail] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip()
            if key not in _SCORE_KEYS:
                continue
            details.append(
                ScoreDetail(
                    key=key,
                    label=str(item.get("label") or _SCORE_LABELS[key]),
                    score=_clamp_score(item.get("score", getattr(scores, key))),
                    weight=_optional_string(item.get("weight")),
                    method=str(item.get("method") or "LLM tarafından CV ve ilan metnine dayalı değerlendirme."),
                    factors=_string_list(item.get("factors", [])),
                )
            )
    existing = {detail.key for detail in details}
    for key in _SCORE_KEYS:
        if key in existing:
            continue
        details.append(
            ScoreDetail(
                key=key,
                label=_SCORE_LABELS[key],
                score=getattr(scores, key),
                method="LLM tarafından CV ve ilan metnine dayalı değerlendirme.",
                factors=[],
            )
        )
    order = {key: index for index, key in enumerate(_SCORE_KEYS)}
    details.sort(key=lambda detail: order.get(detail.key, 99))
    return details


def _parse_cv_profile(raw: dict) -> StructuredProfile:
    return StructuredProfile(
        skills=_string_list(raw.get("skills", [])),
        languages=_string_list(raw.get("languages", [])),
        education=_string_list(raw.get("education", [])),
        certifications=_string_list(raw.get("certifications", [])),
        years_experience=_optional_float(raw.get("years_experience")),
        seniority=_optional_string(raw.get("seniority")),
        highlights=_string_list(raw.get("highlights", [])),
        evidence=_string_dict(raw.get("evidence", {})),
    )


def _parse_job_profile(raw: dict) -> StructuredJob:
    return StructuredJob(
        required_skills=_string_list(raw.get("required_skills", [])),
        preferred_skills=_string_list(raw.get("preferred_skills", [])),
        languages=_string_list(raw.get("languages", [])),
        education=_string_list(raw.get("education", [])),
        seniority=_optional_string(raw.get("seniority")),
        responsibilities=_string_list(raw.get("responsibilities", [])),
        keywords=_string_list(raw.get("keywords", [])),
        evidence=_string_dict(raw.get("evidence", {})),
    )


def _parse_skill_matches(raw: object, *, default_matched: bool) -> list[SkillMatch]:
    if not isinstance(raw, list):
        return []
    matches: list[SkillMatch] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        matches.append(
            SkillMatch(
                name=name,
                matched=bool(item.get("matched", default_matched)),
                evidence=_parse_evidence(item.get("evidence", [])),
            )
        )
    return matches


def _parse_evidence(raw: object) -> list[Evidence]:
    if not isinstance(raw, list):
        return []
    evidence: list[Evidence] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        if source not in {"cv", "job"}:
            continue
        snippet = str(item.get("snippet", "")).strip()
        if not snippet:
            continue
        evidence.append(
            Evidence(
                label=str(item.get("label") or ("CV" if source == "cv" else "İlan")),
                source=source,
                snippet=snippet,
            )
        )
    return evidence


def _parse_cv_add_suggestions(raw: object) -> list[CvAddSuggestion]:
    if not isinstance(raw, list):
        return []
    suggestions: list[CvAddSuggestion] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        category = str(item.get("category", "format")).strip()
        priority = str(item.get("priority", "medium")).strip()
        reason = str(item.get("reason", "")).strip()
        how_to_add = str(item.get("how_to_add", "")).strip()
        if not title or not reason or not how_to_add:
            continue
        if category not in _CV_ADD_CATEGORIES:
            category = "format"
        if priority not in _CV_ADD_PRIORITIES:
            priority = "medium"
        suggestions.append(
            CvAddSuggestion(
                title=title,
                category=category,  # type: ignore[arg-type]
                priority=priority,  # type: ignore[arg-type]
                reason=reason,
                how_to_add=how_to_add,
                job_evidence=_string_list(item.get("job_evidence", [])),
            )
        )
    return suggestions


def _clamp_score(value: object) -> int:
    try:
        numeric = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, numeric))


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _string_dict(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key, raw_values in value.items():
        values = _string_list(raw_values)
        if values:
            result[str(key)] = values
    return result

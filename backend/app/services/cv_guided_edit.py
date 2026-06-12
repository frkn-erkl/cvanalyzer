from typing import Literal

from app.config import LlmProvider, get_settings
import json

from app.models import CvEditApplyChange, CvEditApplyResult, CvEditSuggestion, CvEditSuggestionsResult, StructuredProfile
from app.services.cv_rewrite import _parse_json_response, _sanitize_cv_output
from app.services.ingestion import ingest_text, ingest_upload_bytes, ingest_url, validate_non_empty
from app.services.language import ensure_english_for_llm
from app.services.llm import get_llm_client
from app.services.llm_progress import progress_callback_for_provider, set_llm_task_status_message
from app.services.scoring import extract_cv_profile

EditLanguage = Literal["tr", "en"]

_CV_EDIT_SYSTEM = (
    "You are an evidence-based CV review assistant. "
    "Return ONLY valid JSON in your final answer. "
    "Do not rewrite the CV; provide review suggestions only. "
    "Keep internal reasoning brief so the JSON response is not truncated."
)

_CV_APPLY_SYSTEM = (
    "You are an evidence-based CV editor. "
    "Return ONLY valid JSON in your final answer. "
    "Apply the provided suggestions to the CV without inventing new facts. "
    "Keep internal reasoning brief so the JSON response is not truncated."
)


async def suggest_cv_edits(
    *,
    cv_text: str | None,
    cv_url: str | None,
    cv_file_content: bytes | None,
    cv_filename: str | None,
    cv_content_type: str | None,
    guidance: str,
    language: EditLanguage = "tr",
    use_llm: bool = True,
    llm_provider: LlmProvider = "local",
    task_id: str | None = None,
) -> CvEditSuggestionsResult:
    normalized_guidance = guidance.strip()
    if not normalized_guidance:
        raise ValueError("CV düzenleme yönlendirmesi gerekli.")

    settings = get_settings()
    if len(normalized_guidance) > settings.cv_edit_guidance_chars:
        normalized_guidance = normalized_guidance[: settings.cv_edit_guidance_chars]

    if task_id:
        set_llm_task_status_message(task_id, "CV okunuyor ve profil çıkarılıyor...")
    cv_document = await _ingest_cv(cv_text, cv_url, cv_file_content, cv_filename, cv_content_type)
    validate_non_empty(cv_document, "CV")
    cv_profile = extract_cv_profile(cv_document.text)
    fallback = _deterministic_fallback(cv_profile, normalized_guidance, language)

    if not use_llm:
        fallback.llm_requested = False
        return fallback

    if task_id and llm_provider == "local":
        set_llm_task_status_message(
            task_id,
            "CV yerel model için İngilizceye çevriliyor; bu adım birkaç dakika sürebilir.",
        )
    cv_text_for_llm, lang_meta = await ensure_english_for_llm(
        cv_document.text, purpose="cv", provider=llm_provider
    )
    if task_id:
        set_llm_task_status_message(task_id, "CV düzenleme önerileri için model düşünmeye başlıyor...")
    llm_result, llm_failure, llm_thinking = await _llm_suggestions(
        cv_text_for_llm,
        cv_profile,
        normalized_guidance,
        language,
        llm_provider=llm_provider,
        task_id=task_id,
    )
    if llm_result is None:
        warnings = list(fallback.warnings)
        provider_label = "Cursor API" if llm_provider == "cursor" else "Yerel LLM"
        detail = llm_failure or f"{provider_label} yanıt veremedi."
        warnings.append(f"{detail} Temel profil tabanlı öneriler kullanıldı.")
        fallback.warnings = warnings
        fallback.llm_requested = True
        fallback.llm_thinking = llm_thinking
        return fallback

    if lang_meta.get("was_translated"):
        llm_result.warnings.append("LLM girdisi yerel model için İngilizceye çevrildi.")
    llm_result.llm_requested = True
    return llm_result


async def _ingest_cv(
    cv_text: str | None,
    cv_url: str | None,
    cv_file_content: bytes | None,
    cv_filename: str | None,
    cv_content_type: str | None,
):
    if cv_text:
        return await ingest_text("cv", cv_text)
    if cv_file_content:
        return ingest_upload_bytes("cv", cv_file_content, filename=cv_filename, content_type=cv_content_type)
    if cv_url:
        return await ingest_url("cv", cv_url)
    raise ValueError("CV metni, dosyası veya linki gerekli.")


def _deterministic_fallback(
    profile: StructuredProfile,
    guidance: str,
    language: EditLanguage,
) -> CvEditSuggestionsResult:
    skills = ", ".join(profile.skills[:8]) or ("none" if language == "en" else "yok")
    strengths = profile.highlights[:4] or profile.skills[:4]
    if language == "tr":
        overall = (
            f"LLM kapalı olduğu için yalnızca temel profil sinyalleri kullanıldı. "
            f"Yönlendirme: «{guidance[:120]}{'…' if len(guidance) > 120 else ''}»"
        )
        suggestions = [
            CvEditSuggestion(
                category="content",
                title="Profil özeti güçlendirilsin",
                recommendation=(
                    "CV'nin üst kısmına rol hedefinizi ve en güçlü kanıtlarınızı özetleyen "
                    "2-3 cümlelik bir profil paragrafı ekleyin."
                ),
                priority="high",
                evidence=strengths[:2],
            ),
            CvEditSuggestion(
                category="keywords",
                title="Beceri görünürlüğünü artırın",
                recommendation=(
                    f"CV'de görünen beceriler ({skills}) yönlendirmenizle uyumlu bölümlerde "
                    "açıkça tekrar edilmeli; yalnızca kanıtlanabilir becerileri vurgulayın."
                ),
                priority="medium",
                evidence=profile.skills[:3],
            ),
        ]
        gaps = []
        if not profile.highlights:
            gaps.append("Deneyim maddelerinde somut sonuç veya sorumluluk kanıtı sınırlı görünüyor.")
    else:
        overall = (
            f"Only basic profile signals were used because LLM is off. "
            f"Guidance: «{guidance[:120]}{'…' if len(guidance) > 120 else ''}»"
        )
        suggestions = [
            CvEditSuggestion(
                category="content",
                title="Strengthen the profile summary",
                recommendation=(
                    "Add a 2-3 sentence profile at the top summarizing your target role and strongest evidence."
                ),
                priority="high",
                evidence=strengths[:2],
            ),
            CvEditSuggestion(
                category="keywords",
                title="Increase skill visibility",
                recommendation=(
                    f"Surface verified skills ({skills}) in sections aligned with your guidance; "
                    "do not add unverifiable claims."
                ),
                priority="medium",
                evidence=profile.skills[:3],
            ),
        ]
        gaps = []
        if not profile.highlights:
            gaps.append("Experience bullets show limited measurable outcomes or responsibility evidence.")

    return CvEditSuggestionsResult(
        overall_assessment=overall,
        suggestions=suggestions,
        strengths=strengths,
        gaps=gaps,
        used_llm=False,
        warnings=[],
    )


def _extract_cv_edit_payload(response: str | None, thinking: str | None) -> dict | None:
    for text in (response, thinking):
        if not text or not text.strip():
            continue
        payload = _parse_json_response(text)
        if payload is not None and isinstance(payload.get("suggestions"), list):
            return payload
    return None


def _normalize_priority(value: object) -> Literal["high", "medium", "low"]:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"high", "medium", "low"}:
            return normalized  # type: ignore[return-value]
    return "medium"


def _suggestions_from_payload(
    payload: dict,
    *,
    profile: StructuredProfile,
    thinking: str | None,
) -> CvEditSuggestionsResult | None:
    raw_items = payload.get("suggestions")
    if not isinstance(raw_items, list):
        return None

    suggestions: list[CvEditSuggestion] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        recommendation = str(item.get("recommendation", "")).strip()
        if not title or not recommendation:
            continue
        category = str(item.get("category", "general")).strip() or "general"
        evidence = [str(line).strip() for line in item.get("evidence", []) if str(line).strip()]
        suggestions.append(
            CvEditSuggestion(
                category=category,
                title=title,
                recommendation=recommendation,
                priority=_normalize_priority(item.get("priority")),
                evidence=evidence or profile.highlights[:2],
            )
        )

    if not suggestions:
        return None

    overall = str(payload.get("overall_assessment", "")).strip()
    if not overall:
        overall = "CV, verilen yönlendirmeye göre incelendi."

    strengths = [str(line).strip() for line in payload.get("strengths", []) if str(line).strip()]
    gaps = [str(line).strip() for line in payload.get("gaps", []) if str(line).strip()]

    return CvEditSuggestionsResult(
        overall_assessment=overall,
        suggestions=suggestions[:12],
        strengths=strengths or profile.highlights[:4],
        gaps=gaps,
        used_llm=True,
        llm_requested=True,
        llm_thinking=thinking,
        warnings=[],
    )


async def _llm_suggestions(
    cv_text: str,
    profile: StructuredProfile,
    guidance: str,
    language: EditLanguage,
    *,
    llm_provider: LlmProvider = "local",
    task_id: str | None = None,
) -> tuple[CvEditSuggestionsResult | None, str | None, str | None]:
    settings = get_settings()
    skills = ", ".join(profile.skills[:12]) or "none"
    highlights = "\n".join(f"- {line}" for line in profile.highlights[:6]) or "- none"
    output_language = "Turkish" if language == "tr" else "English"
    provider_label = "Cursor API" if llm_provider == "cursor" else "Yerel LLM"
    prompt = f"""
Review the CV below according to the user's guidance. Do NOT rewrite the CV text.
Provide actionable suggestions only.

User guidance:
{guidance[: settings.cv_edit_guidance_chars]}

Hard rules:
- Do not invent skills, employers, certifications, or achievements not supported by the CV.
- Do not output a rewritten CV; suggestions and analysis only.
- Each suggestion must reference CV evidence when possible.
- Align recommendations with the user's guidance while staying factual.

CV excerpt:
{cv_text[: settings.cv_edit_cv_chars]}

Extracted skills: {skills}
Years of experience: {profile.years_experience if profile.years_experience is not None else "unknown"}
Seniority signal: {profile.seniority or "unknown"}
CV highlights:
{highlights}

Return ONLY valid JSON with this shape:
{{
  "overall_assessment": "Short summary of how the CV aligns with the guidance",
  "strengths": ["existing CV strengths relevant to the guidance"],
  "gaps": ["gaps or weaknesses relative to the guidance"],
  "suggestions": [
    {{
      "category": "layout",
      "title": "Short suggestion title",
      "recommendation": "Specific actionable advice",
      "priority": "high",
      "evidence": ["short CV-based evidence"]
    }}
  ]
}}

Rules:
- Write overall_assessment, strengths, gaps, title, and recommendation in {output_language}.
- category examples: layout, content, keywords, experience, education, format.
- priority must be high, medium, or low.
- Provide 5-10 suggestions when the CV has enough content.
"""

    last_thinking: str | None = None
    last_failure: str | None = None
    for attempt in range(2):
        num_predict = settings.cv_edit_num_predict if attempt == 0 else settings.cv_edit_num_predict + 1024
        response, thinking = await _llm_generate_text(
            prompt,
            llm_provider=llm_provider,
            num_predict=num_predict,
            task_id=task_id,
            system=_CV_EDIT_SYSTEM,
            temperature=0.1 if attempt == 0 else 0.05,
        )
        last_thinking = thinking or last_thinking

        if not response and not thinking:
            last_failure = (
                f"{provider_label} {int(settings.llm_analysis_timeout_seconds)} saniye içinde yanıt vermedi."
            )
            continue

        payload = _extract_cv_edit_payload(response, thinking)
        if payload is None:
            if not response and thinking:
                last_failure = (
                    f"{provider_label} düşünme tamamlandı ancak JSON yanıtı üretilemedi; "
                    "çıktı token limitinde kesilmiş olabilir."
                )
            elif response:
                last_failure = f"{provider_label} yanıt verdi ancak JSON parse edilemedi."
            else:
                last_failure = f"{provider_label} geçerli bir JSON yanıtı üretemedi."
            continue

        result = _suggestions_from_payload(payload, profile=profile, thinking=last_thinking)
        if result is not None:
            return result, None, last_thinking

        last_failure = f"{provider_label} yanıt verdi ancak öneriler eksik veya geçersiz."

    return None, last_failure, last_thinking


async def _llm_generate_text(
    prompt: str,
    *,
    llm_provider: LlmProvider,
    num_predict: int,
    task_id: str | None = None,
    system: str | None = None,
    temperature: float = 0.2,
) -> tuple[str | None, str | None]:
    settings = get_settings()
    on_progress = progress_callback_for_provider(
        llm_provider,
        task_id=task_id,
    )
    client = get_llm_client(llm_provider)
    if hasattr(client, "generate_detailed"):
        detailed = await client.generate_detailed(
            prompt,
            system=system,
            temperature=temperature,
            num_predict=num_predict,
            translate_input=False,
            timeout_seconds=settings.llm_analysis_timeout_seconds,
            on_progress=on_progress,
        )
        return detailed.text, detailed.thinking
    text = await client.generate(
        prompt,
        system=system,
        temperature=temperature,
        num_predict=num_predict,
        translate_input=False,
        timeout_seconds=settings.llm_analysis_timeout_seconds,
        on_progress=on_progress,
    )
    return text, None


async def apply_cv_edits(
    *,
    cv_text: str | None,
    cv_url: str | None,
    cv_file_content: bytes | None,
    cv_filename: str | None,
    cv_content_type: str | None,
    guidance: str,
    suggestions: list[CvEditSuggestion],
    language: EditLanguage = "tr",
    llm_provider: LlmProvider = "local",
    task_id: str | None = None,
) -> CvEditApplyResult:
    normalized_guidance = guidance.strip()
    if not normalized_guidance:
        raise ValueError("CV düzenleme yönlendirmesi gerekli.")
    if not suggestions:
        raise ValueError("Uygulanacak CV düzenleme önerisi bulunamadı.")

    if task_id:
        set_llm_task_status_message(task_id, "CV okunuyor; öneriler metne uygulanacak...")
    cv_document = await _ingest_cv(cv_text, cv_url, cv_file_content, cv_filename, cv_content_type)
    validate_non_empty(cv_document, "CV")

    if task_id and llm_provider == "local":
        set_llm_task_status_message(
            task_id,
            "CV yerel model için İngilizceye çevriliyor; bu adım birkaç dakika sürebilir.",
        )
    cv_text_for_llm, lang_meta = await ensure_english_for_llm(
        cv_document.text, purpose="cv", provider=llm_provider
    )
    if task_id:
        set_llm_task_status_message(task_id, "Öneriler CV metnine uygulanıyor...")

    result, failure, thinking = await _llm_apply_edits(
        cv_text_for_llm,
        normalized_guidance,
        suggestions,
        language,
        llm_provider=llm_provider,
        task_id=task_id,
    )
    if result is None:
        provider_label = "Cursor API" if llm_provider == "cursor" else "Yerel LLM"
        detail = failure or f"{provider_label} CV düzenlemesi üretemedi."
        raise RuntimeError(detail)

    if lang_meta.get("was_translated"):
        result.warnings.append("LLM girdisi yerel model için İngilizceye çevrildi.")
    result.llm_requested = True
    result.llm_thinking = thinking
    return result


def _suggestions_for_prompt(suggestions: list[CvEditSuggestion]) -> str:
    payload = [
        {
            "category": item.category,
            "title": item.title,
            "recommendation": item.recommendation,
            "priority": item.priority,
            "evidence": item.evidence,
        }
        for item in suggestions
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _apply_result_from_payload(
    payload: dict,
    *,
    thinking: str | None,
) -> CvEditApplyResult | None:
    updated_cv_text = _sanitize_cv_output(str(payload.get("updated_cv_text", "")).strip())
    if len(updated_cv_text) < 80:
        return None

    changes: list[CvEditApplyChange] = []
    for item in payload.get("changes", []):
        if not isinstance(item, dict):
            continue
        section = str(item.get("section", "Genel")).strip() or "Genel"
        reason = str(item.get("reason", "")).strip()
        if not reason:
            continue
        evidence = [str(line).strip() for line in item.get("evidence", []) if str(line).strip()]
        changes.append(CvEditApplyChange(section=section, reason=reason, evidence=evidence))

    warnings = [str(item).strip() for item in payload.get("warnings", []) if str(item).strip()]
    return CvEditApplyResult(
        updated_cv_text=updated_cv_text,
        changes=changes,
        warnings=warnings,
        used_llm=True,
        llm_requested=True,
        llm_thinking=thinking,
    )


async def _llm_apply_edits(
    cv_text: str,
    guidance: str,
    suggestions: list[CvEditSuggestion],
    language: EditLanguage,
    *,
    llm_provider: LlmProvider = "local",
    task_id: str | None = None,
) -> tuple[CvEditApplyResult | None, str | None, str | None]:
    settings = get_settings()
    output_language = "Turkish" if language == "tr" else "English"
    provider_label = "Cursor API" if llm_provider == "cursor" else "Yerel LLM"
    suggestions_json = _suggestions_for_prompt(suggestions)
    prompt = f"""
Apply the review suggestions below to the full CV text.
Rewrite the entire CV in {output_language} while preserving factual accuracy.

User guidance:
{guidance[: settings.cv_edit_guidance_chars]}

Suggestions to apply:
{suggestions_json}

Hard rules:
- Apply every high-priority suggestion when possible; apply medium/low suggestions when they fit naturally.
- Do NOT invent employers, certifications, degrees, skills, dates, or achievements not supported by the original CV.
- Do NOT remove verified experience, education, or contact details unless a suggestion explicitly requires restructuring.
- Keep the CV ATS-readable with clear sections.
- Output the complete updated CV text, not a diff-only summary.

Original CV:
{cv_text[: settings.cv_edit_cv_chars]}

Return ONLY valid JSON with this shape:
{{
  "updated_cv_text": "full updated CV text in {output_language}",
  "changes": [
    {{
      "section": "Profile Summary",
      "reason": "Which suggestion was applied and why",
      "evidence": ["short CV-based evidence"]
    }}
  ],
  "warnings": ["any limitations or suggestions that could not be applied safely"]
}}

Rules:
- updated_cv_text must contain the full CV body.
- Write changes.reason in {output_language}.
- List 3-8 changes when possible.
"""

    last_thinking: str | None = None
    last_failure: str | None = None
    for attempt in range(2):
        num_predict = settings.cv_edit_apply_num_predict if attempt == 0 else settings.cv_edit_apply_num_predict + 1024
        response, thinking = await _llm_generate_text(
            prompt,
            llm_provider=llm_provider,
            num_predict=num_predict,
            task_id=task_id,
            system=_CV_APPLY_SYSTEM,
            temperature=0.1 if attempt == 0 else 0.05,
        )
        last_thinking = thinking or last_thinking

        if not response and not thinking:
            last_failure = (
                f"{provider_label} {int(settings.llm_analysis_timeout_seconds)} saniye içinde yanıt vermedi."
            )
            continue

        payload = _parse_json_response(response or "")
        if payload is None and thinking:
            payload = _parse_json_response(thinking)
        if payload is None:
            if not response and thinking:
                last_failure = (
                    f"{provider_label} düşünme tamamlandı ancak JSON yanıtı üretilemedi; "
                    "çıktı token limitinde kesilmiş olabilir."
                )
            elif response:
                last_failure = f"{provider_label} yanıt verdi ancak JSON parse edilemedi."
            else:
                last_failure = f"{provider_label} geçerli bir JSON yanıtı üretemedi."
            continue

        result = _apply_result_from_payload(payload, thinking=last_thinking)
        if result is not None:
            return result, None, last_thinking

        last_failure = f"{provider_label} yanıt verdi ancak güncellenmiş CV metni eksik veya geçersiz."

    return None, last_failure, last_thinking

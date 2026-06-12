import json
import re
from uuid import uuid4

from app import db
from app.config import LlmProvider, get_settings
from app.models import (
    AnalysisResult,
    CvRewriteChange,
    CvRewriteRequest,
    CvRewriteResult,
    UnsupportedClaim,
)
from app.services.latex import (
    build_latex_rewrite_prompt,
    is_latex_source,
    latex_to_plain_text,
    sanitize_latex_output,
)
from app.services.language import ensure_english_for_llm
from app.services.llm import get_llm_client
from app.services.llm_progress import progress_callback_for_provider
from app.services.pdf_export import compile_latex_to_pdf
from app.services.reporting import build_suggested_profile_summary


async def rewrite_cv_for_analysis(
    analysis_id: str,
    request: CvRewriteRequest,
    *,
    task_id: str | None = None,
) -> CvRewriteResult:
    row = db.get_analysis(analysis_id)
    if row is None or row["status"] != "completed" or row["result"] is None:
        raise ValueError("Tamamlanmış analiz bulunamadı.")

    analysis = AnalysisResult(**row["result"])
    cv_text = _load_cached_source(analysis, "cv")
    job_text = _load_cached_source(analysis, "job")
    rewrite_id = str(uuid4())
    llm_provider = request.llm_provider
    fallback = _fallback_rewrite(analysis, cv_text, request, rewrite_id)
    result = fallback

    wants_latex = request.output_format in {"auto", "latex"} and is_latex_source(cv_text)

    if request.deep_rewrite and wants_latex:
        llm_result = await _llm_latex_rewrite(
            analysis, cv_text, job_text, request, rewrite_id, llm_provider=llm_provider, task_id=task_id
        )
        if llm_result is not None:
            claims = detect_unsupported_claims(latex_to_plain_text(llm_result.updated_cv_text), analysis, cv_text)
            llm_result.unsupported_claims = claims
            if any(claim.severity == "blocked" for claim in claims):
                fallback.warnings.append("LLM LaTeX çıktısı CV'de kanıtı olmayan iddialar içerdiği için güvenli fallback kullanıldı.")
                fallback.unsupported_claims = claims
            else:
                result = llm_result
    elif wants_latex:
        result.updated_latex_text = cv_text
        result.latex_source_available = True
        result.format_preserved = True
        result.compile_warnings.append("Yerel LLM kapalı olduğu için orijinal LaTeX kaynak metni korundu; içerik güvenli fallback metninde güncellendi.")
    elif request.deep_rewrite:
        cv_text_for_llm, cv_lang_meta = await ensure_english_for_llm(
            cv_text, purpose="cv", provider=llm_provider
        )
        job_text_for_llm, job_lang_meta = await ensure_english_for_llm(
            job_text, purpose="job", provider=llm_provider
        )
        llm_result = await _llm_rewrite(
            analysis,
            cv_text_for_llm,
            job_text_for_llm,
            request,
            rewrite_id,
            llm_provider=llm_provider,
            task_id=task_id,
        )
        if llm_result is not None:
            if cv_lang_meta.get("was_translated") or job_lang_meta.get("was_translated"):
                llm_result.warnings.append("LLM input was translated to English for local model processing.")
            claims = detect_unsupported_claims(llm_result.updated_cv_text, analysis, cv_text)
            llm_result.unsupported_claims = claims
            if any(claim.severity == "blocked" for claim in claims):
                fallback.warnings.append("LLM çıktısı CV'de kanıtı olmayan iddialar içerdiği için güvenli fallback kullanıldı.")
                fallback.unsupported_claims = claims
                result = fallback
            else:
                result = llm_result

    if request.compile_pdf and result.updated_latex_text:
        pdf_path, compile_warnings = compile_latex_to_pdf(result.updated_latex_text, rewrite_id)
        result.compile_warnings.extend(compile_warnings)
        if pdf_path is not None:
            result.pdf_available = True
            result.pdf_download_url = f"/api/analysis/{analysis_id}/rewrite-cv/{rewrite_id}/pdf"

    if request.compile_pdf and not result.updated_latex_text:
        result.compile_warnings.append(
            "CV LaTeX kaynak olarak algılanmadı (PDF/DOCX veya düz metin). "
            "LaTeX formatı korumak ve PDF üretmek için .tex dosyası yükleyin veya LaTeX kaynağını metin olarak yapıştırın."
        )

    db.save_cv_rewrite(rewrite_id, analysis_id, "completed", result=result.model_dump())
    return result


def detect_unsupported_claims(updated_cv_text: str, analysis: AnalysisResult, original_cv_text: str) -> list[UnsupportedClaim]:
    normalized_output = _normalize(updated_cv_text)
    original_normalized = _normalize(original_cv_text)
    claims: list[UnsupportedClaim] = []

    cv_skills = set(analysis.cv_profile.skills)
    missing_skills = [
        skill
        for skill in [*analysis.job_profile.required_skills, *analysis.job_profile.preferred_skills]
        if skill not in cv_skills
    ]
    for skill in missing_skills:
        if _contains_term(normalized_output, skill) and not _contains_term(original_normalized, skill):
            claims.append(
                UnsupportedClaim(
                    claim=skill,
                    reason="Bu beceri iş ilanında var ancak CV'de kanıtlanmış beceriler arasında değil.",
                    severity="blocked",
                )
            )

    cv_rank = _seniority_rank(analysis.cv_profile.seniority)
    if cv_rank < 3 and re.search(r"\b(senior|kidemli|lead|principal|staff)\b", normalized_output):
        if not re.search(r"\b(senior|kidemli|lead|principal|staff)\b", original_normalized):
            claims.append(
                UnsupportedClaim(
                    claim="senior/lead seviye iddiası",
                    reason="CV'de bu seniority seviyesini destekleyen açık ifade bulunmuyor.",
                    severity="blocked",
                )
            )

    if re.search(r"\b(certified|sertifikali|sertifika sahibi)\b", normalized_output) and not re.search(
        r"\b(certified|sertifikali|sertifika|certificate)\b",
        original_normalized,
    ):
        claims.append(
            UnsupportedClaim(
                claim="sertifika iddiası",
                reason="CV'de sertifika kanıtı yokken çıktı sertifika sahibi gibi ifade içeriyor.",
                severity="blocked",
            )
        )

    return claims


def _fallback_rewrite(analysis: AnalysisResult, cv_text: str, request: CvRewriteRequest, rewrite_id: str) -> CvRewriteResult:
    matched_skills = [match.name for match in analysis.matched_required_skills]
    omitted = _omitted_missing_skills(analysis)
    summary = _summary_text(analysis, matched_skills, request.tone, request.language)
    skills_line = ", ".join([*matched_skills, *[skill for skill in analysis.cv_profile.skills if skill not in matched_skills]][:16])
    labels = _labels(request.language)
    updated_cv = _build_fallback_cv_text(analysis, cv_text, request)
    changes = [
        CvRewriteChange(
            section=labels["profile_section"],
            after=summary,
            reason=labels["profile_reason"],
            evidence=analysis.cv_profile.highlights[:2],
        ),
        CvRewriteChange(
            section=labels["skills_section"],
            after=skills_line or labels["skills_change_fallback"],
            reason=labels["skills_reason"],
            evidence=matched_skills[:8],
        ),
    ]
    warnings = [labels["fallback_warning"]]
    if omitted:
        warnings.append(labels["omitted_warning"])

    return CvRewriteResult(
        rewrite_id=rewrite_id,
        analysis_id=analysis.id,
        updated_cv_text=updated_cv,
        updated_latex_text=cv_text if is_latex_source(cv_text) else None,
        changes=changes,
        preserved_items=analysis.cv_profile.highlights[:6],
        omitted_missing_skills=omitted,
        unsupported_claims=[],
        warnings=warnings,
        latex_source_available=is_latex_source(cv_text),
        format_preserved=is_latex_source(cv_text),
        used_llm=False,
        llm_requested=request.deep_rewrite,
        tone=request.tone,
        language=request.language,
    )


async def _llm_generate_text(
    prompt: str,
    *,
    llm_provider: LlmProvider,
    num_predict: int,
    task_id: str | None = None,
    analysis_id: str | None = None,
) -> tuple[str | None, str | None]:
    on_progress = progress_callback_for_provider(
        llm_provider,
        analysis_id=analysis_id,
        task_id=task_id,
    )
    client = get_llm_client(llm_provider)
    if hasattr(client, "generate_detailed"):
        detailed = await client.generate_detailed(
            prompt,
            temperature=0.1,
            num_predict=num_predict,
            translate_input=False,
            on_progress=on_progress,
        )
        return detailed.text, detailed.thinking
    text = await client.generate(
        prompt,
        temperature=0.1,
        num_predict=num_predict,
        translate_input=False,
        on_progress=on_progress,
    )
    return text, None


async def _llm_rewrite(
    analysis: AnalysisResult,
    cv_text: str,
    job_text: str,
    request: CvRewriteRequest,
    rewrite_id: str,
    *,
    llm_provider: LlmProvider = "local",
    task_id: str | None = None,
) -> CvRewriteResult | None:
    prompt = _build_prompt(analysis, cv_text, job_text, request)
    settings = get_settings()
    response, thinking = await _llm_generate_text(
        prompt,
        llm_provider=llm_provider,
        num_predict=settings.cv_rewrite_num_predict,
        task_id=task_id,
        analysis_id=analysis.id,
    )
    if not response:
        return None
    payload = _parse_json_response(response)
    if payload is None:
        return None

    updated_cv_text = _sanitize_cv_output(str(payload.get("updated_cv_text", "")).strip())
    if len(updated_cv_text) < 80:
        return None
    changes = [
        CvRewriteChange(
            section=str(item.get("section", "Genel")),
            before=item.get("before"),
            after=str(item.get("after", "")),
            reason=str(item.get("reason", _default_change_reason(request.language))),
            evidence=[str(evidence) for evidence in item.get("evidence", []) if str(evidence).strip()],
        )
        for item in payload.get("changes", [])
        if isinstance(item, dict)
    ]
    warnings = [str(item) for item in payload.get("warnings", []) if str(item).strip()]
    warnings.extend(_rewrite_quality_warnings(updated_cv_text, analysis, request.language))
    return CvRewriteResult(
        rewrite_id=rewrite_id,
        analysis_id=analysis.id,
        updated_cv_text=updated_cv_text,
        changes=changes,
        preserved_items=[str(item) for item in payload.get("preserved_items", []) if str(item).strip()],
        omitted_missing_skills=_omitted_missing_skills(analysis),
        unsupported_claims=[],
        warnings=warnings,
        used_llm=True,
        llm_requested=request.deep_rewrite,
        llm_thinking=thinking,
        tone=request.tone,
        language=request.language,
    )


async def _llm_latex_rewrite(
    analysis: AnalysisResult,
    cv_text: str,
    job_text: str,
    request: CvRewriteRequest,
    rewrite_id: str,
    *,
    llm_provider: LlmProvider = "local",
    task_id: str | None = None,
) -> CvRewriteResult | None:
    prompt = build_latex_rewrite_prompt(cv_text, job_text, analysis, request)
    settings = get_settings()
    response, thinking = await _llm_generate_text(
        prompt,
        llm_provider=llm_provider,
        num_predict=settings.cv_rewrite_num_predict,
        task_id=task_id,
        analysis_id=analysis.id,
    )
    if not response:
        return None
    latex_text, latex_warnings = sanitize_latex_output(response)
    if len(latex_text) < 120 or not is_latex_source(latex_text):
        return None
    return CvRewriteResult(
        rewrite_id=rewrite_id,
        analysis_id=analysis.id,
        updated_cv_text=latex_text,
        updated_latex_text=latex_text,
        changes=[
            CvRewriteChange(
                section="LaTeX CV",
                after="Updated LaTeX source",
                reason="Preserved the original LaTeX template while tailoring readable CV content to the job posting.",
                evidence=analysis.cv_profile.highlights[:3],
            )
        ],
        preserved_items=analysis.cv_profile.highlights[:6],
        omitted_missing_skills=_omitted_missing_skills(analysis),
        unsupported_claims=[],
        warnings=latex_warnings,
        latex_source_available=True,
        format_preserved=True,
        used_llm=True,
        llm_requested=request.deep_rewrite,
        llm_thinking=thinking,
        tone=request.tone,
        language=request.language,
    )


def _build_prompt(analysis: AnalysisResult, cv_text: str, job_text: str, request: CvRewriteRequest) -> str:
    settings = get_settings()
    matched = ", ".join(match.name for match in analysis.matched_required_skills) or "none"
    cv_skills = ", ".join(analysis.cv_profile.skills) or "none"
    omitted = ", ".join(_omitted_missing_skills(analysis)) or "none"
    job_required = ", ".join(analysis.job_profile.required_skills) or "none"
    job_preferred = ", ".join(analysis.job_profile.preferred_skills) or "none"
    profile_summary = build_suggested_profile_summary(
        analysis.cv_profile,
        analysis.job_profile,
        analysis.matched_required_skills,
    )
    cv_evidence = _prompt_lines(analysis.cv_profile.highlights[:6])
    job_focus = _prompt_lines(analysis.job_profile.responsibilities[:6] or analysis.job_profile.keywords[:8])
    output_language = "English" if request.language == "en" else "Turkish"
    tone_map = {
        "professional_ats": "professional, ATS-friendly, with clear headings and job-aligned keywords",
        "concise_professional_ats": "professional, ATS-friendly, concise, and keyword-focused",
        "professional": "professional and realistic",
        "concise": "concise, clear, and realistic",
        "ats_friendly": "ATS-friendly with clear headings and keyword focus",
    }
    if request.language == "tr":
        tone_map = {
            "professional_ats": "profesyonel, ATS uyumlu, açık başlıklar ve iş ilanıyla uyumlu anahtar kelimeler kullanan",
            "concise_professional_ats": "profesyonel, ATS uyumlu, kısa, net ve anahtar kelime odaklı",
            "professional": "profesyonel ve gerçekçi",
            "concise": "kısa, sade ve gerçekçi",
            "ats_friendly": "ATS uyumlu, açık başlıklar ve anahtar kelime odaklı",
        }
    return f"""
You are an evidence-based CV editing assistant.
Task: Tailor the CV below to the job posting.

Hard rules:
- Do not add skills, certifications, education, years of experience, or seniority not supported by the CV.
- Do not add missing skills to the CV; only report them separately.
- Do not invent projects, exaggerated achievements, or unverifiable metrics.
- Rewrite existing content in a {tone_map.get(request.tone, tone_map["professional_ats"])} style.
- Write the updated CV in {output_language}.
- Return a complete, submission-ready CV only. Do not append the original CV, reference blocks, or meta sections such as "Original CV Text".
- Respond with JSON only.

Writing strategy:
- Start the CV with a strong profile summary inspired by the suggested summary below, but keep it factual.
- Highlight matched required skills only when the original CV supports them.
- Rephrase existing experience bullets as technology + responsibility + outcome. If no measurable result exists, do not invent one.
- Keep the CV concise, ATS-readable, and aligned to the job's language.
- Put missing skills only in warnings or omitted_missing_skills, never in updated_cv_text.

Verified CV skills: {cv_skills}
Required job skills: {job_required}
Preferred job skills: {job_preferred}
Matched required skills: {matched}
Skills that must NOT be added to the CV: {omitted}
CV seniority: {analysis.cv_profile.seniority}
Job seniority: {analysis.job_profile.seniority}
Suggested profile summary to improve, not copy blindly: {profile_summary}

Strong CV evidence to preserve:
{cv_evidence}

Job focus:
{job_focus}

Original CV:
{cv_text[: settings.cv_rewrite_cv_chars]}

Job posting:
{job_text[: settings.cv_rewrite_job_chars]}

JSON format:
{{
  "updated_cv_text": "updated CV text in {output_language}",
  "changes": [
    {{"section": "section", "before": "old text or null", "after": "new text", "reason": "why", "evidence": ["CV evidence"]}}
  ],
  "preserved_items": ["preserved factual item"],
  "warnings": ["warning"]
}}
"""


def _build_fallback_cv_text(analysis: AnalysisResult, cv_text: str, request: CvRewriteRequest) -> str:
    matched_skills = [match.name for match in analysis.matched_required_skills]
    summary = _summary_text(analysis, matched_skills, request.tone, request.language)
    skills_line = ", ".join([*matched_skills, *[skill for skill in analysis.cv_profile.skills if skill not in matched_skills]][:16])
    labels = _labels(request.language)

    experience_lines = _experience_lines(analysis, cv_text, labels)
    education_lines = "\n".join(f"- {item}" for item in analysis.cv_profile.education[:4])

    sections = [
        f"{labels['profile_summary']}\n{summary}",
        f"{labels['core_skills']}\n{skills_line or labels['skills_fallback']}",
        f"{labels.get('experience', labels.get('job_aligned_experience', 'EXPERIENCE'))}\n{experience_lines}",
    ]
    if education_lines:
        sections.append(f"{labels.get('education', 'EDUCATION')}\n{education_lines}")

    return "\n\n".join(sections).strip()


def _experience_lines(analysis: AnalysisResult, cv_text: str, labels: dict[str, str]) -> str:
    highlights = [item.strip() for item in analysis.cv_profile.highlights[:6] if item.strip()]
    if highlights:
        return "\n".join(f"- {item}" for item in highlights)

    extracted = _extract_experience_section(cv_text)
    if extracted:
        return extracted

    return f"- {labels['highlights_fallback']}"


def _extract_experience_section(cv_text: str) -> str:
    match = re.search(
        r"(?:^|\n)(?:EXPERIENCE|WORK EXPERIENCE|PROFESSIONAL EXPERIENCE|DENEYIM|IS DENEYIMI)\s*\n([\s\S]*?)(?=\n(?:EDUCATION|EGITIM|SKILLS|PROJECTS|CERTIFICATIONS|SERTIFIKA|LANGUAGES|DILLER)\b|\Z)",
        cv_text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""

    body = match.group(1).strip()
    if len(body) < 40:
        return ""

    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return "\n".join(lines[:12])


_META_SECTION_PATTERN = re.compile(
    r"\n(?:ORIGINAL CV TEXT|ORIJINAL CV METNI|Original CV(?: Text)?|Orijinal CV(?: Metni)?)\s*:?\s*\n[\s\S]*$",
    re.IGNORECASE,
)


def _sanitize_cv_output(text: str) -> str:
    return _META_SECTION_PATTERN.sub("", text.strip()).strip()


def _load_cached_source(analysis: AnalysisResult, source: str) -> str:
    metadata = analysis.metadata.get(source, {})
    cache_key = metadata.get("cache_key") if isinstance(metadata, dict) else None
    if not isinstance(cache_key, str):
        raise ValueError(f"{source} cache key bulunamadı. Analizi yeniden çalıştırın.")
    text = db.get_cached_text_value(cache_key)
    if text is None:
        raise ValueError(f"{source} metni cache içinde bulunamadı. Analizi yeniden çalıştırın.")
    return text


def _parse_json_response(response: str) -> dict | None:
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _summary_text(analysis: AnalysisResult, matched_skills: list[str], tone: str, language: str) -> str:
    seniority = _seniority_label(analysis.cv_profile.seniority, language)
    skills = ", ".join(matched_skills[:6]) or ", ".join(analysis.cv_profile.skills[:6])
    omitted = set(_omitted_missing_skills(analysis))
    focus_terms = [term for term in analysis.job_profile.keywords if term not in omitted]
    if not focus_terms:
        focus_terms = matched_skills or analysis.cv_profile.skills
    focus = ", ".join(focus_terms[:4]) or ("software delivery" if language == "en" else "yazılım geliştirme")
    highlight = analysis.cv_profile.highlights[0].strip().rstrip(".") if analysis.cv_profile.highlights else ""
    if language == "en":
        if tone in {"concise_professional_ats", "concise"}:
            base = f"{seniority} candidate with verified experience in {skills}, positioned for {focus} roles."
        else:
            base = f"{seniority} candidate with verified {skills} experience, aligned with {focus} responsibilities in a professional ATS-friendly profile."
        if highlight:
            return f"{base} Key evidence: {highlight}."
        return f"{base} Add concrete project outcomes in the Experience section where supported."
    if tone in {"concise_professional_ats", "concise"}:
        base = f"{seniority} aday; {skills} alanındaki doğrulanmış deneyimini {focus} odaklı roller için net ve ATS uyumlu şekilde konumlandırır."
    else:
        base = f"{seniority} aday; {skills} deneyimini {focus} beklentileriyle uyumlu, profesyonel ve ATS dostu bir profil içinde öne çıkarır."
    if highlight:
        return f"{base} Öne çıkan kanıt: {highlight}."
    return f"{base} Deneyim bölümünde desteklenen somut proje sonuçlarıyla güçlendirilmelidir."


def _labels(language: str) -> dict[str, str]:
    if language == "en":
        return {
            "profile_summary": "PROFILE SUMMARY",
            "core_skills": "CORE SKILLS",
            "experience": "EXPERIENCE",
            "education": "EDUCATION",
            "job_aligned_experience": "EXPERIENCE",
            "profile_section": "Profile Summary",
            "skills_section": "Core Skills",
            "profile_reason": "Added to make the CV easier to scan for this job posting.",
            "skills_reason": "Only verified skills relevant to the posting were highlighted.",
            "skills_fallback": "No clear technical skills were detected; add verified skills with concrete project examples.",
            "skills_change_fallback": "Skill list should be strengthened with verified examples.",
            "highlights_fallback": "Existing experience bullets should be rewritten with job-aligned keywords.",
            "fallback_warning": "This output was generated in safe fallback mode; unverified skills were not added.",
            "omitted_warning": "Missing job skills were not added to the CV and are shown separately.",
        }
    return {
        "profile_summary": "PROFIL OZETI",
        "core_skills": "ANA YETKINLIKLER",
        "experience": "DENEYIM",
        "education": "EGITIM",
        "job_aligned_experience": "DENEYIM",
        "profile_section": "Profil Özeti",
        "skills_section": "Ana Yetkinlikler",
        "profile_reason": "CV'yi ilanın diliyle daha hızlı okunabilir hale getirmek için eklendi.",
        "skills_reason": "Yalnızca CV'de kanıtlanan ve ilana temas eden beceriler öne çıkarıldı.",
        "skills_fallback": "CV'de açık teknik beceri tespit edilemedi; mevcut becerileri somut proje örnekleriyle yazın.",
        "skills_change_fallback": "Beceri listesi güçlendirilmeli.",
        "highlights_fallback": "CV'deki mevcut deneyim maddeleri ilana uygun anahtar kelimelerle daha net ifade edilmeli.",
        "fallback_warning": "Bu çıktı gerçekçi fallback modunda üretildi; CV'de kanıtlanmayan beceriler eklenmedi.",
        "omitted_warning": "Eksik ilan becerileri CV'ye eklenmedi; ayrı geliştirme alanı olarak gösterildi.",
    }


def _default_change_reason(language: str) -> str:
    return "Reworded more clearly for this job posting." if language == "en" else "İlana göre daha açık ifade edildi."


def _prompt_lines(values: list[str]) -> str:
    cleaned = [value.strip() for value in values if value and value.strip()]
    if not cleaned:
        return "- none"
    return "\n".join(f"- {value[:260]}" for value in cleaned)


def _rewrite_quality_warnings(updated_cv_text: str, analysis: AnalysisResult, language: str) -> list[str]:
    warnings: list[str] = []
    normalized = _normalize(updated_cv_text)
    word_count = len(re.findall(r"\w+", updated_cv_text))
    has_profile = bool(
        re.search(
            r"\b(profile summary|summary|professional summary|profil ozeti|profil özeti|ozet|özet)\b",
            normalized,
        )
    )
    if word_count < 80:
        warnings.append(
            "LLM output is short; review whether the CV has enough role-specific detail."
            if language == "en"
            else "LLM çıktısı kısa; CV'nin role özel yeterli detay içerip içermediğini kontrol edin."
        )
    if not has_profile:
        warnings.append(
            "LLM output does not include a clear profile summary section."
            if language == "en"
            else "LLM çıktısında net bir profil özeti bölümü bulunmuyor."
        )
    for match in [*analysis.missing_required_skills, *analysis.missing_preferred_skills]:
        if _contains_term(normalized, match.name):
            warnings.append(
                f"Review `{match.name}`: it appears in the output but was not verified in the original CV."
                if language == "en"
                else f"`{match.name}` ifadesini kontrol edin: çıktı içinde var ancak orijinal CV'de doğrulanmadı."
            )
    return _unique(warnings)


def _seniority_label(value: str | None, language: str) -> str:
    if language == "en":
        mapping = {"junior": "Junior", "mid": "Mid-level", "senior": "Senior"}
        return mapping.get(value or "", "Experienced")
    mapping = {"junior": "Junior", "mid": "Orta seviye", "senior": "Kıdemli/Senior"}
    return mapping.get(value or "", "Deneyimli")


def _omitted_missing_skills(analysis: AnalysisResult) -> list[str]:
    values = [match.name for match in [*analysis.missing_required_skills, *analysis.missing_preferred_skills]]
    return _unique(values)


def _contains_term(normalized_text: str, term: str) -> bool:
    pattern = rf"(?<![\w+#]){re.escape(_normalize(term))}(?![\w+#])"
    return bool(re.search(pattern, normalized_text))


def _normalize(text: str) -> str:
    return text.casefold().replace("ı", "i")


def _seniority_rank(value: str | None) -> int:
    return {"junior": 1, "mid": 2, "senior": 3}.get(value or "", 0)


def _unique(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result

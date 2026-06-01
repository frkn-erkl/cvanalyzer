from typing import Literal

from app.config import LlmProvider, get_settings
from app.models import JobTitleSuggestion, JobTitleSuggestionsResult, StructuredProfile
from app.services.cv_rewrite import _parse_json_response
from app.services.ingestion import ingest_text, ingest_upload_bytes, ingest_url, validate_non_empty
from app.services.language import ensure_english_for_llm
from app.services.llm import get_llm_client
from app.services.scoring import extract_cv_profile

TitleLanguage = Literal["tr", "en"]

ROLE_CANDIDATES: list[tuple[frozenset[str], list[str], list[str]]] = [
    (frozenset({"python", "fastapi", "django", "flask"}), ["Backend Developer", "Python Developer", "API Developer"], ["Backend Developer", "Python Developer", "API Developer"]),
    (frozenset({"react", "angular", "vue", "typescript", "javascript"}), ["Frontend Developer", "React Developer", "Full Stack Developer"], ["Frontend Developer", "React Developer", "Full Stack Developer"]),
    (frozenset({"docker", "kubernetes", "terraform", "ansible", "ci/cd"}), ["DevOps Engineer", "Platform Engineer", "Site Reliability Engineer"], ["DevOps Engineer", "Platform Engineer", "Site Reliability Engineer"]),
    (frozenset({"aws", "azure", "gcp"}), ["Cloud Engineer", "Cloud Architect", "Infrastructure Engineer"], ["Cloud Engineer", "Cloud Architect", "Infrastructure Engineer"]),
    (frozenset({"postgresql", "mysql", "mongodb", "redis", "sql"}), ["Backend Developer", "Database Developer", "Data Engineer"], ["Backend Developer", "Database Developer", "Data Engineer"]),
    (frozenset({"flutter", "android", "ios", "swift", "kotlin"}), ["Mobile Developer", "Android Developer", "iOS Developer"], ["Mobile Developer", "Android Developer", "iOS Developer"]),
    (frozenset({"pytorch", "tensorflow", "pandas"}), ["Machine Learning Engineer", "Data Scientist", "AI Engineer"], ["Machine Learning Engineer", "Data Scientist", "AI Engineer"]),
    (frozenset({".net", "c#"}), [".NET Developer", "Backend Developer", "Software Engineer"], [".NET Developer", "Backend Developer", "Software Engineer"]),
    (frozenset({"java", "spring"}), ["Java Developer", "Backend Developer", "Software Engineer"], ["Java Developer", "Backend Developer", "Software Engineer"]),
    (frozenset({"go", "rust"}), ["Backend Developer", "Systems Engineer", "Software Engineer"], ["Backend Developer", "Systems Engineer", "Software Engineer"]),
]

TITLE_HINTS = (
    "developer",
    "engineer",
    "architect",
    "manager",
    "analyst",
    "designer",
    "consultant",
    "specialist",
    "lead",
    "director",
    "geliştirici",
    "mühendis",
    "uzman",
    "danışman",
    "mimar",
)


async def suggest_job_titles(
    *,
    cv_text: str | None,
    cv_url: str | None,
    cv_file_content: bytes | None,
    cv_filename: str | None,
    cv_content_type: str | None,
    language: TitleLanguage = "tr",
    use_llm: bool = True,
    llm_provider: LlmProvider = "local",
) -> JobTitleSuggestionsResult:
    cv_document = await _ingest_cv(cv_text, cv_url, cv_file_content, cv_filename, cv_content_type)
    validate_non_empty(cv_document, "CV")
    cv_profile = extract_cv_profile(cv_document.text)
    current_titles = _extract_current_titles(cv_document.text)
    fallback = _deterministic_suggestions(cv_profile, current_titles, language)

    if not use_llm:
        fallback.llm_requested = False
        return fallback

    cv_text_for_llm, lang_meta = await ensure_english_for_llm(
        cv_document.text, purpose="cv", provider=llm_provider
    )
    llm_result = await _llm_suggestions(
        cv_text_for_llm, cv_profile, current_titles, language, llm_provider=llm_provider
    )
    if llm_result is None:
        warnings = list(fallback.warnings)
        provider_label = "Cursor API" if llm_provider == "cursor" else "Yerel LLM"
        warnings.append(f"{provider_label} yanıt veremedi; beceri tabanlı deterministik unvan önerileri kullanıldı.")
        fallback.warnings = warnings
        fallback.llm_requested = True
        return fallback

    if lang_meta.get("was_translated"):
        llm_result.warnings.append("LLM girdisi yerel model için İngilizceye çevrildi.")
    llm_result.current_titles = current_titles or llm_result.current_titles
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


def _extract_current_titles(text: str) -> list[str]:
    titles: list[str] = []
    for raw_line in text.splitlines()[:8]:
        line = raw_line.strip(" \t-•|")
        if not line or len(line) > 90:
            continue
        normalized = line.casefold()
        if any(hint in normalized for hint in TITLE_HINTS):
            if line not in titles:
                titles.append(line)
    return titles[:3]


def _seniority_prefix(profile: StructuredProfile, language: TitleLanguage) -> str:
    seniority = (profile.seniority or "").casefold()
    years = profile.years_experience
    if seniority == "senior" or (years is not None and years >= 5):
        return "Senior" if language == "en" else "Kıdemli"
    if seniority == "mid" or (years is not None and years >= 2):
        return "" if language == "en" else ""
    if seniority == "junior" or (years is not None and years < 2):
        return "Junior" if language == "en" else "Junior"
    return ""


def _deterministic_suggestions(
    profile: StructuredProfile,
    current_titles: list[str],
    language: TitleLanguage,
) -> JobTitleSuggestionsResult:
    skill_set = set(profile.skills)
    prefix = _seniority_prefix(profile, language)
    suggestions: list[JobTitleSuggestion] = []
    seen_titles: set[str] = set()

    for required_skills, en_titles, tr_titles in ROLE_CANDIDATES:
        overlap = skill_set & required_skills
        if len(overlap) < max(1, min(2, len(required_skills))):
            continue
        role_titles = tr_titles if language == "tr" else en_titles
        matched = ", ".join(sorted(overlap))
        for base_title in role_titles:
            title = f"{prefix} {base_title}".strip() if prefix else base_title
            key = title.casefold()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            evidence = profile.highlights[:2] or [f"CV becerileri: {matched}"]
            suggestions.append(
                JobTitleSuggestion(
                    title=title,
                    fit_score=min(95, 68 + len(overlap) * 8),
                    reason=(
                        f"CV'de {matched} becerileri görünüyor; bu unvanla arama yapmak profilinizle uyumlu."
                        if language == "tr"
                        else f"CV shows {matched}; searching with this title aligns with your profile."
                    ),
                    search_keywords=_search_keywords(title, overlap, language),
                    evidence=evidence,
                )
            )

    if not suggestions:
        generic = "Software Engineer" if language == "en" else "Yazılım Mühendisi"
        title = f"{prefix} {generic}".strip() if prefix else generic
        suggestions.append(
            JobTitleSuggestion(
                title=title,
                fit_score=55,
                reason=(
                    "CV'den net bir rol sinyali çıkmadı; genel yazılım unvanıyla aramaya başlayabilirsiniz."
                    if language == "tr"
                    else "No strong role signal was found; start with a general software title."
                ),
                search_keywords=[generic],
                evidence=profile.highlights[:2] or profile.skills[:4],
            )
        )

    suggestions.sort(key=lambda item: item.fit_score, reverse=True)
    return JobTitleSuggestionsResult(
        suggestions=suggestions[:8],
        current_titles=current_titles,
        used_llm=False,
        warnings=[],
    )


def _search_keywords(title: str, skills: set[str], language: TitleLanguage) -> list[str]:
    keywords = [title]
    keywords.extend(sorted(skills)[:4])
    if language == "tr":
        keywords.append("remote")
    return keywords[:6]


async def _llm_suggestions(
    cv_text: str,
    profile: StructuredProfile,
    current_titles: list[str],
    language: TitleLanguage,
    *,
    llm_provider: LlmProvider = "local",
) -> JobTitleSuggestionsResult | None:
    settings = get_settings()
    skills = ", ".join(profile.skills[:12]) or "none"
    highlights = "\n".join(f"- {line}" for line in profile.highlights[:6]) or "- none"
    current = ", ".join(current_titles) or "none"
    output_language = "Turkish" if language == "tr" else "English"

    prompt = f"""
You are a career search assistant. Based only on the CV evidence below, suggest 6-8 realistic job titles the candidate should search for on job boards.
Do not invent skills, employers, or seniority that are not supported by the CV.
Prefer titles that match LinkedIn/Indeed style naming.
Include a mix of specific and slightly broader titles when justified by the CV.

CV excerpt:
{cv_text[: settings.job_title_cv_chars]}

Extracted skills: {skills}
Years of experience: {profile.years_experience if profile.years_experience is not None else "unknown"}
Seniority signal: {profile.seniority or "unknown"}
Current title hints from CV: {current}
CV highlights:
{highlights}

Return ONLY valid JSON with this shape:
{{
  "suggestions": [
    {{
      "title": "Senior Backend Developer",
      "fit_score": 88,
      "reason": "Why this title fits the CV",
      "search_keywords": ["Senior Backend Developer", "Python", "FastAPI"],
      "evidence": ["short CV-based evidence"]
    }}
  ]
}}

Rules:
- Write title, reason, and search_keywords in {output_language}.
- fit_score must be an integer from 40 to 98.
- Do not recommend titles requiring skills absent from the CV.
- search_keywords should help the user search on LinkedIn, Indeed, or Kariyer.net.
"""

    response = await get_llm_client(llm_provider).generate(
        prompt,
        num_predict=settings.job_title_num_predict,
        translate_input=False,
        temperature=0.2,
    )
    if not response:
        return None

    payload = _parse_json_response(response)
    if payload is None:
        return None

    raw_items = payload.get("suggestions")
    if not isinstance(raw_items, list):
        return None

    suggestions: list[JobTitleSuggestion] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        try:
            fit_score = int(item.get("fit_score", 70))
        except (TypeError, ValueError):
            fit_score = 70
        fit_score = max(40, min(98, fit_score))
        reason = str(item.get("reason", "")).strip() or "CV profiline dayalı öneri."
        search_keywords = [str(keyword).strip() for keyword in item.get("search_keywords", []) if str(keyword).strip()]
        evidence = [str(line).strip() for line in item.get("evidence", []) if str(line).strip()]
        suggestions.append(
            JobTitleSuggestion(
                title=title,
                fit_score=fit_score,
                reason=reason,
                search_keywords=search_keywords or [title],
                evidence=evidence or profile.highlights[:2],
            )
        )

    if not suggestions:
        return None

    suggestions.sort(key=lambda item: item.fit_score, reverse=True)
    return JobTitleSuggestionsResult(
        suggestions=suggestions[:8],
        current_titles=current_titles,
        used_llm=True,
        llm_requested=True,
        warnings=[],
    )

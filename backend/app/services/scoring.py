import re
from collections import Counter

from app.models import Evidence, ScoreBreakdown, ScoreDetail, SkillMatch, StructuredJob, StructuredProfile
from app.services.llm import semantic_similarity


SKILLS = [
    ".net",
    "agile",
    "airflow",
    "android",
    "angular",
    "ansible",
    "aws",
    "azure",
    "c#",
    "ci/cd",
    "css",
    "django",
    "docker",
    "elasticsearch",
    "fastapi",
    "figma",
    "firebase",
    "flask",
    "flutter",
    "gcp",
    "git",
    "go",
    "graphql",
    "html",
    "ios",
    "java",
    "javascript",
    "jenkins",
    "kafka",
    "kotlin",
    "kubernetes",
    "laravel",
    "linux",
    "mongodb",
    "mysql",
    "nestjs",
    "next.js",
    "node.js",
    "php",
    "postgresql",
    "python",
    "pytorch",
    "react",
    "redis",
    "rest api",
    "rust",
    "scala",
    "spring",
    "sql",
    "swift",
    "tailwind",
    "tensorflow",
    "terraform",
    "typescript",
    "vue",
]

LANGUAGES = ["türkçe", "ingilizce", "almanca", "fransızca", "arapça", "spanish", "english", "turkish", "german"]
EDUCATION_TERMS = ["lisans", "yüksek lisans", "master", "bachelor", "university", "üniversite", "mühendisliği"]
CERT_TERMS = ["sertifika", "certificate", "certified", "aws certified", "azure certified", "scrum"]
REQUIRED_HINTS = ["required", "must", "zorunlu", "aranan", "gereklilik", "requirements", "şart"]
PREFERRED_HINTS = ["preferred", "nice to have", "tercihen", "artı", "plus", "bonus"]


def extract_cv_profile(text: str) -> StructuredProfile:
    normalized = _normalize(text)
    lines = _important_lines(text)
    skills = _extract_terms(normalized, SKILLS)
    languages = _extract_terms(normalized, LANGUAGES)
    education = _extract_lines(lines, EDUCATION_TERMS)
    certifications = _extract_lines(lines, CERT_TERMS)
    years = _extract_years(normalized)
    seniority = _seniority_from_years(years)
    highlights = _top_highlight_lines(lines, skills)
    evidence = {skill: _evidence_lines(lines, skill) for skill in skills}
    return StructuredProfile(
        skills=skills,
        languages=languages,
        education=education,
        certifications=certifications,
        years_experience=years,
        seniority=seniority,
        highlights=highlights,
        evidence=evidence,
    )


def extract_job_profile(text: str) -> StructuredJob:
    normalized = _normalize(text)
    lines = _important_lines(text)
    all_skills = _extract_terms(normalized, SKILLS)
    required = _extract_contextual_skills(lines, REQUIRED_HINTS) or all_skills
    preferred = [skill for skill in _extract_contextual_skills(lines, PREFERRED_HINTS) if skill not in required]
    languages = _extract_terms(normalized, LANGUAGES)
    education = _extract_lines(lines, EDUCATION_TERMS)
    seniority = _extract_seniority(normalized)
    responsibilities = _extract_responsibilities(lines)
    keywords = _top_keywords(normalized)
    evidence = {skill: _evidence_lines(lines, skill) for skill in all_skills}
    return StructuredJob(
        required_skills=required,
        preferred_skills=preferred,
        languages=languages,
        education=education,
        seniority=seniority,
        responsibilities=responsibilities,
        keywords=keywords,
        evidence=evidence,
    )


async def score_match(
    cv_text: str,
    job_text: str,
    cv: StructuredProfile,
    job: StructuredJob,
    cv_metadata: dict[str, str | int | bool] | None = None,
    *,
    fast: bool = False,
) -> tuple[ScoreBreakdown, dict[str, float], list[ScoreDetail]]:
    required_skill_score = _ratio_score([skill in cv.skills for skill in job.required_skills])
    preferred_skill_score = _ratio_score([skill in cv.skills for skill in job.preferred_skills]) if job.preferred_skills else 70
    technical = round(required_skill_score * 0.75 + preferred_skill_score * 0.25)

    seniority = _score_seniority(cv, job)
    languages = _score_languages(cv, job)
    education = _score_education(cv, job)
    keyword_overlap = _keyword_overlap_score(cv_text, job_text)
    if fast:
        semantic = None
    else:
        semantic = await semantic_similarity(cv_text, job_text)
    domain_keywords = round((semantic * 100) if semantic is not None else keyword_overlap)
    ats_compatibility, ats_factors = score_ats_compatibility(cv_text, cv_metadata or {})
    overall = round(
        technical * 0.38
        + seniority * 0.22
        + domain_keywords * 0.2
        + education * 0.1
        + languages * 0.1
    )
    breakdown = ScoreBreakdown(
        overall=_clamp(overall),
        technical_skills=_clamp(technical),
        experience_seniority=_clamp(seniority),
        domain_keywords=_clamp(domain_keywords),
        education_certifications=_clamp(education),
        language_communication=_clamp(languages),
        ats_compatibility=_clamp(ats_compatibility),
    )
    metrics = {
        "required_skill_score": required_skill_score,
        "preferred_skill_score": preferred_skill_score,
        "keyword_overlap_score": keyword_overlap,
        "semantic_similarity": semantic if semantic is not None else -1,
        "ats_compatibility": float(ats_compatibility),
    }
    details = build_score_details(cv_text, job_text, cv, job, breakdown, metrics, ats_factors)
    return breakdown, metrics, details


def build_score_details(
    cv_text: str,
    job_text: str,
    cv: StructuredProfile,
    job: StructuredJob,
    scores: ScoreBreakdown,
    metrics: dict[str, float],
    ats_factors: list[str],
) -> list[ScoreDetail]:
    required_total = len(job.required_skills)
    required_matched = sum(1 for skill in job.required_skills if skill in cv.skills)
    preferred_total = len(job.preferred_skills)
    preferred_matched = sum(1 for skill in job.preferred_skills if skill in cv.skills)
    matched_required = [skill for skill in job.required_skills if skill in cv.skills]
    missing_required = [skill for skill in job.required_skills if skill not in cv.skills]
    missing_preferred = [skill for skill in job.preferred_skills if skill not in cv.skills]

    technical_factors = [
        f"Zorunlu beceri eşleşmesi: {required_matched}/{required_total or '—'} (%{int(metrics['required_skill_score'])}) — formülde %75 ağırlık",
        f"Tercih edilen beceri eşleşmesi: {preferred_matched}/{preferred_total or '—'} (%{int(metrics['preferred_skill_score'])}) — formülde %25 ağırlık",
    ]
    if matched_required:
        technical_factors.append(f"Eşleşen zorunlu beceriler: {', '.join(matched_required)}")
    if missing_required:
        technical_factors.append(f"Eksik zorunlu beceriler: {', '.join(missing_required)}")
    if job.preferred_skills:
        if missing_preferred:
            technical_factors.append(f"Eksik tercih edilen beceriler: {', '.join(missing_preferred)}")
    else:
        technical_factors.append("İlanda ayrı tercih edilen beceri bulunamadı; bu alt skor için nötr varsayılan (%70) kullanıldı.")

    seniority_factors = _seniority_factors(cv, job, scores.experience_seniority)
    domain_factors = _domain_factors(cv_text, job_text, metrics, scores.domain_keywords)
    education_factors = _education_factors(cv, job)
    language_factors = _language_factors(cv, job)

    return [
        ScoreDetail(
            key="overall",
            label="Genel uygunluk",
            score=scores.overall,
            method="Alt skorların ağırlıklı toplamı: teknik %38, deneyim %22, domain %20, eğitim %10, dil %10.",
            factors=[
                f"Teknik beceriler: {scores.technical_skills}",
                f"Deneyim / seniority: {scores.experience_seniority}",
                f"Domain anahtar kelimeleri: {scores.domain_keywords}",
                f"Eğitim / sertifika: {scores.education_certifications}",
                f"Dil / iletişim: {scores.language_communication}",
            ],
        ),
        ScoreDetail(
            key="technical_skills",
            label="Teknik beceriler",
            score=scores.technical_skills,
            weight="Genel skora %38 katkı",
            method="CV ve ilandaki bilinen teknik beceri listesi karşılaştırılır; zorunlu ve tercih edilen eşleşmeler birleştirilir.",
            factors=technical_factors,
        ),
        ScoreDetail(
            key="experience_seniority",
            label="Deneyim / seniority",
            score=scores.experience_seniority,
            weight="Genel skora %22 katkı",
            method="CV'deki deneyim yılı ve seniority seviyesi, ilanın beklediği seviye ile kıyaslanır.",
            factors=seniority_factors,
        ),
        ScoreDetail(
            key="domain_keywords",
            label="Domain anahtar kelimeleri",
            score=scores.domain_keywords,
            weight="Genel skora %20 katkı",
            method="Ollama embedding benzerliği varsa o kullanılır; yoksa CV ile ilan metni arasındaki ortak anahtar kelime oranı hesaplanır.",
            factors=domain_factors,
        ),
        ScoreDetail(
            key="education_certifications",
            label="Eğitim / sertifika",
            score=scores.education_certifications,
            weight="Genel skora %10 katkı",
            method="CV'deki eğitim ve sertifika ifadeleri, ilanın eğitim beklentileriyle karşılaştırılır.",
            factors=education_factors,
        ),
        ScoreDetail(
            key="language_communication",
            label="Dil / iletişim",
            score=scores.language_communication,
            weight="Genel skora %10 katkı",
            method="İlanda geçen dil beklentilerinin CV'de karşılanma oranı hesaplanır.",
            factors=language_factors,
        ),
        ScoreDetail(
            key="ats_compatibility",
            label="ATS uyumluluğu",
            score=scores.ats_compatibility,
            weight="CV format skoru; genel ilan uygunluğuna dahil değil",
            method="CV metni ve dosya formatı ATS sistemlerinin okuyabileceği yapı, iletişim bilgisi ve metin çıkarım kalitesine göre puanlanır.",
            factors=ats_factors,
        ),
    ]


def _seniority_factors(cv: StructuredProfile, job: StructuredJob, score: int) -> list[str]:
    cv_label = _seniority_label(cv.seniority)
    job_label = _seniority_label(job.seniority)
    factors = [
        f"CV seniority: {cv_label}",
        f"İlan seniority: {job_label}",
    ]
    if cv.years_experience is not None:
        factors.append(f"CV'den çıkarılan deneyim: {cv.years_experience:g} yıl")
    else:
        factors.append("CV'de açık deneyim yılı ifadesi bulunamadı.")

    if not job.seniority:
        factors.append("İlanda net seniority beklentisi yok; deneyim bilgisine göre varsayılan puan verildi.")
    elif cv.seniority == job.seniority:
        factors.append("Seniority seviyeleri birebir eşleşti.")
    elif score >= 88:
        factors.append("CV seviyesi ilanın beklediği seviyenin üzerinde veya eşdeğer kabul edildi.")
    elif score == 58:
        factors.append("CV seviyesi ilanın bir alt basamağında; kısmi uyum sayıldı.")
    else:
        factors.append("Seniority uyumsuzluğu yüksek; deneyim seviyesi ilanın beklentisinin altında görünüyor.")
    return factors


def _domain_factors(cv_text: str, job_text: str, metrics: dict[str, float], score: int) -> list[str]:
    overlap_tokens = _overlap_tokens(cv_text, job_text)
    job_token_count = len(set(_tokens(job_text)))
    semantic = metrics.get("semantic_similarity", -1)
    factors: list[str] = []
    if semantic >= 0:
        factors.append(f"Yerel embedding benzerliği: %{round(semantic * 100)}")
    else:
        overlap = int(metrics["keyword_overlap_score"])
        factors.append(f"Embedding kullanılamadı; anahtar kelime örtüşmesi: %{overlap}")
        factors.append(f"İlan metnindeki {job_token_count} anahtar kelimeden {len(overlap_tokens)} tanesi CV'de de geçiyor.")
    if overlap_tokens:
        preview = ", ".join(overlap_tokens[:12])
        suffix = "..." if len(overlap_tokens) > 12 else ""
        factors.append(f"Ortak kelimelerden örnekler: {preview}{suffix}")
    else:
        factors.append("CV ile ilan arasında belirgin ortak domain kelimesi bulunamadı.")
    if score < 30:
        factors.append("Metinler farklı alan/rol dili kullanıyor olabilir; CV özeti ilanın kelimeleriyle hizalanmalı.")
    return factors


def _education_factors(cv: StructuredProfile, job: StructuredJob) -> list[str]:
    factors: list[str] = []
    if cv.education:
        factors.append(f"CV eğitim ifadeleri: {' | '.join(cv.education[:3])}")
    else:
        factors.append("CV'de eğitim ifadesi tespit edilmedi.")
    if cv.certifications:
        factors.append(f"CV sertifikaları: {' | '.join(cv.certifications[:3])}")
    else:
        factors.append("CV'de sertifika ifadesi tespit edilmedi.")
    if job.education:
        factors.append(f"İlan eğitim beklentisi: {' | '.join(job.education[:3])}")
    else:
        factors.append("İlanda açık eğitim şartı yok; CV'deki eğitim/sertifika varlığına göre puanlandı.")
    return factors


def _language_factors(cv: StructuredProfile, job: StructuredJob) -> list[str]:
    if not job.languages:
        return [
            "İlanda açık dil beklentisi bulunamadı; varsayılan nötr puan (%80) verildi.",
            f"CV'de tespit edilen diller: {', '.join(cv.languages) or 'yok'}",
        ]
    matched = [language for language in job.languages if language in cv.languages]
    missing = [language for language in job.languages if language not in cv.languages]
    factors = [
        f"İlanda istenen diller: {', '.join(job.languages)}",
        f"CV'de tespit edilen diller: {', '.join(cv.languages) or 'yok'}",
    ]
    if matched:
        factors.append(f"Eşleşen diller: {', '.join(matched)}")
    if missing:
        factors.append(f"Eksik diller: {', '.join(missing)}")
    return factors


def _seniority_label(value: str | None) -> str:
    mapping = {"junior": "junior", "mid": "orta", "senior": "kıdemli/senior"}
    return mapping.get(value or "", "belirsiz")


def _overlap_tokens(cv_text: str, job_text: str) -> list[str]:
    cv_tokens = set(_tokens(cv_text))
    job_tokens = set(_tokens(job_text))
    return sorted(cv_tokens & job_tokens)


def build_skill_matches(cv: StructuredProfile, job: StructuredJob) -> tuple[list[SkillMatch], list[SkillMatch], list[SkillMatch]]:
    matched = [_skill_match(skill, True, cv, job) for skill in job.required_skills if skill in cv.skills]
    missing_required = [_skill_match(skill, False, cv, job) for skill in job.required_skills if skill not in cv.skills]
    missing_preferred = [_skill_match(skill, False, cv, job) for skill in job.preferred_skills if skill not in cv.skills]
    return matched, missing_required, missing_preferred


def _skill_match(skill: str, matched: bool, cv: StructuredProfile, job: StructuredJob) -> SkillMatch:
    evidence = [
        Evidence(label=skill, source="job", snippet=line)
        for line in job.evidence.get(skill, [])[:2]
    ]
    if matched:
        evidence.extend(Evidence(label=skill, source="cv", snippet=line) for line in cv.evidence.get(skill, [])[:2])
    return SkillMatch(name=skill, matched=matched, evidence=evidence)


def _normalize(text: str) -> str:
    return text.casefold().replace("ı", "i")


def _important_lines(text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return [line for line in lines if 5 <= len(line) <= 260][:300]


def _extract_terms(normalized_text: str, terms: list[str]) -> list[str]:
    found = []
    for term in terms:
        pattern = rf"(?<![\w+#]){re.escape(_normalize(term))}(?![\w+#])"
        if re.search(pattern, normalized_text):
            found.append(term)
    return found


def _extract_contextual_skills(lines: list[str], hints: list[str]) -> list[str]:
    skills: list[str] = []
    for line in lines:
        normalized = _normalize(line)
        if any(hint in normalized for hint in hints):
            skills.extend(_extract_terms(normalized, SKILLS))
    return _unique(skills)


def _extract_lines(lines: list[str], terms: list[str]) -> list[str]:
    results = []
    for line in lines:
        normalized = _normalize(line)
        if any(_normalize(term) in normalized for term in terms):
            results.append(line)
    return results[:6]


def _extract_responsibilities(lines: list[str]) -> list[str]:
    hints = ["responsibilities", "sorumluluk", "görev", "you will", "beklenen"]
    selected = [line for line in lines if any(hint in _normalize(line) for hint in hints)]
    return selected[:8] or lines[:5]


def _extract_years(normalized_text: str) -> float | None:
    matches = re.findall(r"(\d{1,2})\+?\s*(?:yil|year|sene)", normalized_text)
    values = [int(match) for match in matches if int(match) <= 40]
    return float(max(values)) if values else None


def _extract_seniority(normalized_text: str) -> str | None:
    if re.search(r"\b(lead|principal|staff|senior|kidemli)\b", normalized_text):
        return "senior"
    if re.search(r"\b(mid|middle|orta)\b", normalized_text):
        return "mid"
    if re.search(r"\b(junior|entry|stajyer|yeni mezun)\b", normalized_text):
        return "junior"
    years = _extract_years(normalized_text)
    return _seniority_from_years(years)


def _seniority_from_years(years: float | None) -> str | None:
    if years is None:
        return None
    if years >= 5:
        return "senior"
    if years >= 2:
        return "mid"
    return "junior"


def _score_seniority(cv: StructuredProfile, job: StructuredJob) -> int:
    if not job.seniority:
        return 75 if cv.years_experience is None else 85
    if cv.seniority == job.seniority:
        return 100
    order = {"junior": 1, "mid": 2, "senior": 3}
    cv_rank = order.get(cv.seniority or "", 0)
    job_rank = order.get(job.seniority, 0)
    if cv_rank >= job_rank and cv_rank > 0:
        return 88
    if cv_rank == job_rank - 1:
        return 58
    return 35


def _score_languages(cv: StructuredProfile, job: StructuredJob) -> int:
    if not job.languages:
        return 80
    return _ratio_score([language in cv.languages for language in job.languages])


def _score_education(cv: StructuredProfile, job: StructuredJob) -> int:
    if not job.education:
        return 80 if cv.education or cv.certifications else 65
    if cv.education:
        return 85
    if cv.certifications:
        return 70
    return 40


def _keyword_overlap_score(cv_text: str, job_text: str) -> int:
    cv_tokens = set(_tokens(cv_text))
    job_counts = Counter(_tokens(job_text))
    job_tokens = {token for token, count in job_counts.items() if count >= 1}
    if not job_tokens:
        return 0
    return round(len(cv_tokens & job_tokens) / len(job_tokens) * 100)


def _tokens(text: str) -> list[str]:
    stopwords = {"ve", "ile", "the", "and", "bir", "için", "in", "of", "to", "a", "or", "ya", "da"}
    return [token for token in re.findall(r"[\w+#.]{3,}", _normalize(text)) if token not in stopwords]


def _top_keywords(normalized_text: str) -> list[str]:
    counts = Counter(_tokens(normalized_text))
    return [word for word, _ in counts.most_common(25)]


def _top_highlight_lines(lines: list[str], skills: list[str]) -> list[str]:
    selected = [line for line in lines if any(skill in _normalize(line) for skill in skills)]
    return selected[:8]


def _evidence_lines(lines: list[str], term: str) -> list[str]:
    normalized_term = _normalize(term)
    return [line for line in lines if normalized_term in _normalize(line)][:3]


def _ratio_score(values: list[bool]) -> int:
    if not values:
        return 70
    return round(sum(1 for value in values if value) / len(values) * 100)


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _clamp(value: int) -> int:
    return max(0, min(100, value))


ATS_SECTION_HEADERS = (
    "experience",
    "work experience",
    "professional experience",
    "employment",
    "education",
    "skills",
    "technical skills",
    "core skills",
    "projects",
    "certifications",
    "summary",
    "profile",
    "deneyim",
    "is deneyimi",
    "egitim",
    "yetkinlik",
    "beceri",
    "projeler",
    "sertifika",
    "ozet",
    "profil",
)


def score_ats_compatibility(cv_text: str, metadata: dict[str, str | int | bool]) -> tuple[int, list[str]]:
    normalized = _normalize(cv_text)
    lines = _important_lines(cv_text)
    factors: list[str] = []
    score = 0

    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", cv_text):
        score += 15
        factors.append("E-posta adresi tespit edildi (+15).")
    else:
        factors.append("E-posta adresi bulunamadı; ATS için iletişim bilgisi eksik.")

    contact_hits = 0
    if re.search(r"(\+?\d[\d\s().-]{7,}\d|linkedin\.com|github\.com)", normalized):
        contact_hits += 1
    if re.search(r"\b(phone|telefon|mobile|gsm)\b", normalized):
        contact_hits += 1
    if contact_hits:
        score += 10
        factors.append("Telefon veya profil linki tespit edildi (+10).")
    else:
        factors.append("Telefon veya LinkedIn/GitHub linki belirgin değil.")

    section_hits = sum(1 for header in ATS_SECTION_HEADERS if re.search(rf"\b{re.escape(header)}\b", normalized))
    section_score = min(30, section_hits * 6)
    score += section_score
    factors.append(f"Standart CV bölüm başlıkları: {section_hits} adet (+{section_score}).")

    bullet_lines = sum(1 for line in lines if re.match(r"^[\-*•●]\s+\S", line.strip()))
    if bullet_lines >= 3:
        score += 15
        factors.append(f"Madde işaretli deneyim satırları: {bullet_lines} adet (+15).")
    elif bullet_lines >= 1:
        score += 8
        factors.append(f"Az sayıda madde işareti var: {bullet_lines} adet (+8).")
    else:
        factors.append("Madde işaretli deneyim satırı az; ATS için bullet formatı önerilir.")

    avg_line_len = round(sum(len(line) for line in lines) / max(len(lines), 1))
    if avg_line_len <= 140:
        score += 10
        factors.append(f"Satır uzunlukları okunabilir (ortalama {avg_line_len} karakter, +10).")
    elif avg_line_len <= 200:
        score += 5
        factors.append(f"Satır uzunlukları kabul edilebilir (ortalama {avg_line_len} karakter, +5).")
    else:
        factors.append(f"Uzun metin blokları var (ortalama {avg_line_len} karakter); ATS parse zorlaşabilir.")

    if re.search(r"\b(19|20)\d{2}\b", cv_text) or re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|ocak|subat|mart|nisan|mayis|haziran|temmuz|agustos|eylul|ekim|kasim|aralik)\b", normalized):
        score += 10
        factors.append("Tarih ifadeleri mevcut (+10).")
    else:
        factors.append("Açık tarih ifadesi bulunamadı; deneyim dönemleri ATS için önemli.")

    skill_count = len(_extract_terms(normalized, SKILLS))
    if skill_count >= 5:
        score += 10
        factors.append(f"Düz metin beceri anahtar kelimeleri: {skill_count} adet (+10).")
    elif skill_count >= 2:
        score += 5
        factors.append(f"Sınırlı beceri anahtar kelimesi: {skill_count} adet (+5).")
    else:
        factors.append("Beceri anahtar kelimeleri zayıf; Skills bölümü net yazılmalı.")

    char_count = len(cv_text.strip())
    if 400 <= char_count <= 12000:
        score += 10
        factors.append(f"CV metin uzunluğu uygun ({char_count} karakter, +10).")
    elif char_count < 400:
        factors.append(f"CV metni çok kısa ({char_count} karakter); ATS için yetersiz içerik riski.")
    else:
        score += 5
        factors.append(f"CV metni uzun ({char_count} karakter); gereksiz bloklar ATS parse'ını zorlaştırabilir (+5).")

    replacement_chars = cv_text.count("\ufffd") + cv_text.count("�")
    if replacement_chars == 0:
        score += 10
        factors.append("Metin çıkarımında bozuk karakter yok (+10).")
    else:
        factors.append(f"PDF/DOCX çıkarımında {replacement_chars} bozuk karakter var; ATS parse riski yüksek.")

    pipe_lines = sum(1 for line in lines if line.count("|") >= 2)
    if pipe_lines >= 3:
        score -= 10
        factors.append(f"Tablo benzeri satırlar ({pipe_lines} adet); çok sütunlu layout ATS için riskli (-10).")
    elif pipe_lines == 0:
        score += 5
        factors.append("Tablo/sütun izi düşük (+5).")

    source = str(metadata.get("format", metadata.get("source", "text"))).lower()
    filename = str(metadata.get("filename", "")).lower()
    if source == "latex" or filename.endswith(".tex"):
        score += 5
        factors.append("LaTeX kaynak tespit edildi; PDF çıktısı sade layout ile ATS dostu olmalı (+5).")
    elif source == "pdf":
        factors.append("CV PDF olarak yüklendi; ATS kalitesi metin çıkarımına bağlı.")
    elif source in {"docx", "text"}:
        score += 5
        factors.append(f"{source.upper()} formatı genelde ATS parse için uygundur (+5).")

    return _clamp(score), factors

from app.models import (
    AnalysisResult,
    CvAddSuggestion,
    ScoreBreakdown,
    SkillMatch,
    StructuredJob,
    StructuredProfile,
)
from app.config import LlmProvider, get_settings
from app.services.llm import get_llm_client


def deterministic_recommendations(
    cv: StructuredProfile,
    job: StructuredJob,
    scores: ScoreBreakdown,
    missing_required: list[SkillMatch],
    missing_preferred: list[SkillMatch],
) -> tuple[list[str], list[str], list[str], list[str]]:
    strengths = []
    if scores.technical_skills >= 75:
        strengths.append("Teknik beceriler iş ilanındaki temel beklentilerle güçlü şekilde örtüşüyor.")
    if scores.experience_seniority >= 80:
        strengths.append("Deneyim seviyesi ilandaki seniority beklentisine yakın veya üzerinde.")
    if cv.highlights:
        strengths.append(f"CV'de öne çıkan kanıt: {cv.highlights[0]}")
    if not strengths:
        strengths.append("CV bazı anahtar alanlarda eşleşme içeriyor ancak iş ilanına göre daha hedefli ifade edilmeli.")

    improvements = []
    for match in missing_required[:5]:
        improvements.append(f"Zorunlu görünen `{match.name}` becerisi CV'de açıkça yer almıyor; gerçek deneyim varsa somut proje/sonuçla ekleyin.")
    for match in missing_preferred[:3]:
        improvements.append(f"Tercih edilen `{match.name}` becerisi için varsa kısa bir örnek veya araç deneyimi eklenebilir.")
    if scores.domain_keywords < 55:
        improvements.append("CV özeti ve deneyim maddeleri ilandaki domain kelimeleriyle daha net hizalanmalı.")
    if scores.language_communication < 70:
        improvements.append("İlanda istenen dil/iletişim beklentileri CV'de daha görünür hale getirilmeli.")
    if scores.ats_compatibility < 65:
        improvements.append("CV ATS uyumluluğu düşük; standart bölüm başlıkları, madde işaretleri ve düz metin beceri listesi kullanın.")
    if scores.ats_compatibility < 45:
        improvements.append("PDF/DOCX metin çıkarımında bozuk karakter veya tablo/sütun yapısı var; tek sütun, sade bir CV formatına geçin.")

    tailored = [
        "CV özet bölümünü bu ilana göre 3-4 satırlık hedefli bir profil açıklamasıyla başlatın.",
        "Deneyim maddelerinde teknoloji + sorumluluk + ölçülebilir etki formatını kullanın.",
        "CV'ye yalnızca gerçekten sahip olduğunuz beceri ve deneyimleri ekleyin; eksik becerileri öğrenme planı olarak ayırın.",
    ]

    warnings = []
    if missing_required:
        warnings.append("Skor, CV'de açıkça görülen bilgilerle hesaplandı; örtük deneyimler eşleşmemiş olabilir.")
    if scores.overall < 50:
        warnings.append("Bu ilan için başvuru yapılacaksa CV ciddi şekilde hedeflenmeli veya beceri açığı kapatılmalı.")

    return strengths, improvements or ["Belirgin eksik bulunmadı; CV ifadelerini ilana özel anahtar kelimelerle güçlendirin."], tailored, warnings


def build_cv_add_suggestions(
    cv: StructuredProfile,
    job: StructuredJob,
    scores: ScoreBreakdown,
    missing_required: list[SkillMatch],
    missing_preferred: list[SkillMatch],
    cv_text: str,
) -> list[CvAddSuggestion]:
    suggestions: list[CvAddSuggestion] = []
    normalized_cv = cv_text.casefold()

    for match in missing_required[:8]:
        evidence = [item.snippet for item in match.evidence if item.source == "job"][:2]
        suggestions.append(
            CvAddSuggestion(
                title=match.name,
                category="required_skill",
                priority="high",
                reason="İş ilanında zorunlu görünen bir beceri; CV'de açık ifade yok.",
                how_to_add=_skill_add_example(match.name),
                job_evidence=evidence,
            )
        )

    for match in missing_preferred[:6]:
        evidence = [item.snippet for item in match.evidence if item.source == "job"][:2]
        suggestions.append(
            CvAddSuggestion(
                title=match.name,
                category="preferred_skill",
                priority="medium",
                reason="İlan tercih edilen beceriler arasında sayıyor; CV'de görünmüyor.",
                how_to_add=_skill_add_example(match.name),
                job_evidence=evidence,
            )
        )

    for language in job.languages:
        if language not in cv.languages:
            suggestions.append(
                CvAddSuggestion(
                    title=language,
                    category="language",
                    priority="high" if len(job.languages) <= 2 else "medium",
                    reason="İlanda dil beklentisi var; CV'de aynı dil belirtilmemiş.",
                    how_to_add=f"Languages / Diller bölümüne `{language}` ekleyin veya özette iletişim seviyenizi yazın (ör. professional working proficiency).",
                    job_evidence=[],
                )
            )

    if job.seniority and cv.seniority:
        seniority_order = {"junior": 1, "mid": 2, "senior": 3}
        if seniority_order.get(cv.seniority, 0) < seniority_order.get(job.seniority, 0):
            suggestions.append(
                CvAddSuggestion(
                    title="Deneyim seviyesi vurgusu",
                    category="experience",
                    priority="high",
                    reason=f"İlan `{job.seniority}` seviye bekliyor; CV `{cv.seniority}` seviyesinde görünüyor.",
                    how_to_add="Liderlik, sahiplenilen modül/ekip büyüklüğü, mimari karar veya uçtan uca sahiplenme örneklerini deneyim maddelerine ekleyin — yalnızca gerçekten yaptıysanız.",
                    job_evidence=[],
                )
            )

    for keyword in _missing_job_keywords(normalized_cv, job):
        suggestions.append(
            CvAddSuggestion(
                title=keyword,
                category="keyword",
                priority="medium",
                reason="İlan metninde sık geçen domain kelimesi CV'de yok veya zayıf.",
                how_to_add=f"Özet veya ilgili deneyim maddesinde `{keyword}` geçen gerçek bir proje cümlesi ekleyin.",
                job_evidence=[],
            )
        )

    if job.education and not cv.education:
        suggestions.append(
            CvAddSuggestion(
                title="Eğitim bilgisi",
                category="education",
                priority="medium",
                reason="İlanda eğitim beklentisi var; CV'de eğitim bölümü net değil.",
                how_to_add="Education / Eğitim bölümüne derece, bölüm, okul ve mezuniyet yılını ekleyin.",
                job_evidence=job.education[:2],
            )
        )

    if scores.ats_compatibility < 70:
        suggestions.append(
            CvAddSuggestion(
                title="ATS dostu bölüm yapısı",
                category="format",
                priority="medium" if scores.ats_compatibility >= 50 else "high",
                reason=f"ATS uyumluluk skoru düşük ({scores.ats_compatibility}/100).",
                how_to_add="Profile Summary, Skills, Experience, Education başlıklarını standart isimlerle ekleyin; deneyimleri madde işaretli ve tarihli yazın.",
                job_evidence=[],
            )
        )

    if not suggestions:
        suggestions.append(
            CvAddSuggestion(
                title="Belirgin ekleme zorunluluğu yok",
                category="format",
                priority="low",
                reason="Zorunlu beceri açığı görünmüyor; mevcut deneyimleri ilanın anahtar kelimeleriyle daha görünür yazmanız yeterli olabilir.",
                how_to_add="Var olan maddeleri teknoloji + görev + sonuç formatında yeniden ifade edin; yeni beceri eklemeyin.",
                job_evidence=[],
            )
        )

    return suggestions


def _skill_add_example(skill: str) -> str:
    return (
        f"Skills veya ilgili deneyim maddesine yalnızca gerçek kullanımınız varsa ekleyin: "
        f"\"{skill} ile [somut proje/görev] geliştirdim; [ölçülebilir sonuç].\""
    )


def _missing_job_keywords(normalized_cv: str, job: StructuredJob) -> list[str]:
    missing: list[str] = []
    for keyword in job.keywords[:20]:
        normalized_keyword = keyword.casefold().replace("ı", "i")
        if len(normalized_keyword) < 4:
            continue
        if normalized_keyword in normalized_cv:
            continue
        if keyword in set(job.required_skills + job.preferred_skills):
            continue
        missing.append(keyword)
        if len(missing) >= 5:
            break
    return missing


def build_suggested_profile_summary(
    cv: StructuredProfile,
    job: StructuredJob,
    matched_required: list[SkillMatch],
) -> str:
    language = _profile_summary_language(cv)
    skill_pool = _verified_summary_skills(cv, job, matched_required)
    skills_text = _join_terms(skill_pool[:6], language) or ("teknik beceriler" if language == "tr" else "core technical skills")
    seniority = _profile_seniority_label(cv.seniority, language)
    years = cv.years_experience
    highlight = _clean_highlight(cv.highlights[0]) if cv.highlights else None
    focus = _job_focus_phrase(job, language)

    if language == "tr":
        years_part = f"{years:g} yıllık deneyime sahip " if years is not None else ""
        opening = f"{years_part}{seniority.lower()} aday; {skills_text} alanlarında doğrulanmış deneyim sunar."
        alignment = f"{focus} odaklı pozisyonlar için mevcut proje ve sorumluluklarını ATS uyumlu, net ve sonuç odaklı bir dille konumlandırır."
        if highlight:
            closing = f"Öne çıkan kanıt: {_summary_evidence_phrase(highlight, language)}"
        elif cv.education:
            closing = f"Eğitim altyapısı: {_clean_highlight(cv.education[0])}."
        else:
            closing = "Deneyim maddelerinde gerçek proje kapsamı, kullanılan teknolojiler ve ölçülebilir katkılarla desteklenmelidir."
        return f"{opening} {alignment} {closing}"

    years_part = f"with {years:g}+ years of experience " if years is not None else "with demonstrated experience "
    opening = (
        f"{seniority} professional {years_part}across {skills_text}. "
        f"Positions verified project experience for roles focused on {focus} with clear, ATS-friendly language."
    )
    if highlight:
        closing = f"Key CV evidence: {_summary_evidence_phrase(highlight, language)}."
    elif cv.education:
        closing = f"Educational background: {_clean_highlight(cv.education[0])}."
    else:
        closing = "Best supported by concrete project scope, technologies used, and measurable contributions in the Experience section."
    return f"{opening} {closing}"


def _verified_summary_skills(
    cv: StructuredProfile,
    job: StructuredJob,
    matched_required: list[SkillMatch],
) -> list[str]:
    matched = [match.name for match in matched_required if match.matched and match.name in cv.skills]
    job_terms = set(job.required_skills + job.preferred_skills + job.keywords)
    relevant_cv_skills = [skill for skill in cv.skills if skill in job_terms and skill not in matched]
    fallback = [skill for skill in cv.skills if skill not in matched and skill not in relevant_cv_skills]
    return _unique_terms([*matched, *relevant_cv_skills, *fallback])[:8]


def _join_terms(values: list[str], language: str) -> str:
    values = [value for value in values if value]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    conjunction = " ve " if language == "tr" else " and "
    return ", ".join(values[:-1]) + conjunction + values[-1]


def _unique_terms(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _summary_evidence_phrase(text: str, language: str) -> str:
    cleaned = _clean_highlight(text).rstrip(".")
    if language == "tr":
        return f"{cleaned}."
    return f"{cleaned}."


def _profile_summary_language(cv: StructuredProfile) -> str:
    normalized = {language.casefold().replace("ı", "i") for language in cv.languages}
    if normalized & {"turkce", "turkish"} and not normalized & {"ingilizce", "english"}:
        return "tr"
    return "en"


def _profile_seniority_label(value: str | None, language: str) -> str:
    if language == "tr":
        mapping = {"junior": "Junior", "mid": "Orta seviye", "senior": "Kıdemli/Senior"}
        return mapping.get(value or "", "Deneyimli")
    mapping = {"junior": "Junior", "mid": "Mid-level", "senior": "Senior"}
    return mapping.get(value or "", "Experienced")


def _clean_highlight(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) > 180:
        return cleaned[:177].rstrip() + "..."
    return cleaned


def _job_focus_phrase(job: StructuredJob, language: str) -> str:
    skill_terms = set(job.required_skills + job.preferred_skills)
    focus_terms = [keyword for keyword in job.keywords if keyword not in skill_terms][:4]
    if not focus_terms:
        focus_terms = _role_terms_from_responsibilities(job.responsibilities)[:4]
    joined = ", ".join(focus_terms)
    if language == "tr":
        return joined or "yazılım geliştirme"
    return joined or "software delivery"


def _role_terms_from_responsibilities(responsibilities: list[str]) -> list[str]:
    role_terms = []
    for line in responsibilities:
        normalized = line.casefold()
        for term in ("backend", "frontend", "fullstack", "mobile", "data", "devops", "software", "api"):
            if term in normalized and term not in role_terms:
                role_terms.append(term)
    return role_terms


_LLM_SUMMARY_SYSTEM = (
    "Sen kanıta dayalı kariyer analizi asistanısın. "
    "Yalnızca Türkçe yaz. İngilizce cümle veya başlık kullanma "
    "(Python, Kubernetes gibi teknik terimler ve yaygın rol adları hariç). "
    "CV'de kanıtı olmayan beceriyi güçlü yön olarak yazma. "
    "Motivasyon klişesi ve genel kariyer tavsiyesi kullanma."
)

_LLM_SUMMARY_FEW_SHOT = """## Karar
CV bu ilan için güçlü görünüyor; zorunlu becerilerin çoğu kanıtlanmış, Kubernetes boşluğu netleştirilmeli.

## Güçlü yönler
- Python ve FastAPI deneyimi ilandaki backend beklentisiyle örtüşüyor.
- Deneyim seviyesi senior rol beklentisine yakın.

## Kritik boşluklar
- Kubernetes CV'de açık değil; varsa proje kanıtı ekleyin, yoksa öğrenme planını ayrı belirtin.

## Önerilen profil özeti
Kıdemli backend geliştirici; Python ve FastAPI ile API geliştirme deneyimi. Ölçülebilir performans ve sahiplenilen modül örnekleriyle desteklenmiş profil.

## CV'ye somut adımlar
- Deneyim maddelerinde teknoloji + sorumluluk + ölçülebilir etki formatını kullanın.
- Eksik zorunlu becerileri yalnızca gerçekten varsa ekleyin; yoksa öğrenme planını ayrı satırda belirtin.
- Profil özetini ilandaki domain kelimeleriyle 3-4 satırda hizalayın.
- ATS uyumu için düz metin beceri listesi ve standart bölüm başlıkları kullanın.
"""


def _build_llm_summary_prompt(result: AnalysisResult) -> str:
    missing_required = ", ".join(match.name for match in result.missing_required_skills[:8]) or "yok"
    matched = ", ".join(match.name for match in result.matched_required_skills[:8]) or "yok"
    cv_highlights = _bullet_context(result.cv_profile.highlights[:5], empty_label="yok")
    job_responsibilities = _bullet_context(result.job_profile.responsibilities[:5], empty_label="yok")
    strengths = _bullet_context(result.strengths[:4], empty_label="yok")
    improvements = _bullet_context(result.improvement_suggestions[:5], empty_label="yok")
    tailored = _bullet_context(result.tailored_cv_suggestions[:4], empty_label="yok")
    suggested_summary = result.suggested_profile_summary or "yok"
    return f"""
Aşağıdaki skorlar ve kanıtlara dayanarak bu CV–ilan eşleşmesi için kısa, somut bir rapor yaz.
Bilgi uydurma. CV'de olmayan beceriyi güçlü yön diye yazma; eksikler için "öğrenme planı", "deneyim varsa görünür kılın" veya "proje kanıtı ekleyin" ifadelerini kullan.
Aşağıdaki deterministik maddeleri yeniden icat etme; anlamı koruyarak birleştir, sırala ve bu ilana özel 1-2 cümle ekle.

Skorlar:
- Genel uygunluk: {result.scores.overall}/100
- Teknik beceriler: {result.scores.technical_skills}/100
- Deneyim / seniority: {result.scores.experience_seniority}/100
- Domain anahtar kelimeleri: {result.scores.domain_keywords}/100
- Eşleşen zorunlu beceriler: {matched}
- Eksik zorunlu beceriler: {missing_required}
- CV seniority: {result.cv_profile.seniority or "belirsiz"}
- İlan seniority: {result.job_profile.seniority or "belirsiz"}
- Deterministik profil özeti adayı: {suggested_summary}

CV kanıt öne çıkanları:
{cv_highlights}

İlan sorumlulukları / odak:
{job_responsibilities}

Deterministik güçlü yönler (taslak):
{strengths}

Deterministik geliştirme önerileri (taslak):
{improvements}

Deterministik CV dokunuşları (taslak):
{tailored}

Kalite kuralları:
- Profesyonel, net Türkçe; kısa cümleler.
- Kararı bu role özel ver; genel motivasyon cümlesi yazma.
- Güçlü yönlerde yalnızca CV kanıtı olan becerileri say.
- Profil özeti bölümünde CV'ye yapıştırılabilir 2-4 cümle öner.
- Tam olarak aşağıdaki başlık yapısını kullan; başka başlık ekleme.

Örnek çıktı formatı (ton ve yapı için; içeriği kopyalama):
{_LLM_SUMMARY_FEW_SHOT.strip()}

Zorunlu çıktı başlıkları (sırayla):
## Karar
## Güçlü yönler
## Kritik boşluklar
## Önerilen profil özeti
## CV'ye somut adımlar
"""


async def llm_summary(
    result: AnalysisResult,
    *,
    llm_provider: LlmProvider = "local",
    analysis_id: str | None = None,
) -> tuple[str | None, str | None]:
    from app.services.llm_progress import analysis_progress_callback

    client = get_llm_client(llm_provider)
    settings = get_settings()
    on_progress = analysis_progress_callback(analysis_id) if analysis_id else None
    if hasattr(client, "generate_detailed"):
        detailed = await client.generate_detailed(
            _build_llm_summary_prompt(result),
            system=_LLM_SUMMARY_SYSTEM,
            temperature=0.1,
            num_predict=settings.llm_summary_num_predict,
            translate_input=False,
            on_progress=on_progress,
        )
        return detailed.text, detailed.thinking
    text = await client.generate(
        _build_llm_summary_prompt(result),
        system=_LLM_SUMMARY_SYSTEM,
        temperature=0.1,
        num_predict=settings.llm_summary_num_predict,
        translate_input=False,
        on_progress=on_progress,
    )
    return text, None


def _bullet_context(values: list[str], *, empty_label: str = "none") -> str:
    if not values:
        return f"- {empty_label}"
    return "\n".join(f"- {_clean_highlight(value)}" for value in values)

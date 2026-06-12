from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import LlmProvider


JobStatus = Literal["queued", "running", "completed", "failed"]
RewriteTone = Literal[
    "professional_ats",
    "concise_professional_ats",
    "professional",
    "concise",
    "ats_friendly",
]
RewriteLanguage = Literal["en", "tr"]
RewriteOutputFormat = Literal["auto", "text", "latex"]


class Evidence(BaseModel):
    label: str
    source: Literal["cv", "job"]
    snippet: str


class SkillMatch(BaseModel):
    name: str
    matched: bool
    evidence: list[Evidence] = Field(default_factory=list)


class CvAddSuggestion(BaseModel):
    title: str
    category: Literal[
        "required_skill",
        "preferred_skill",
        "language",
        "keyword",
        "experience",
        "format",
        "education",
    ]
    priority: Literal["high", "medium", "low"]
    reason: str
    how_to_add: str
    job_evidence: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    overall: int
    technical_skills: int
    experience_seniority: int
    domain_keywords: int
    education_certifications: int
    language_communication: int
    ats_compatibility: int


class ScoreDetail(BaseModel):
    key: str
    label: str
    score: int
    weight: str | None = None
    method: str
    factors: list[str] = Field(default_factory=list)


class StructuredProfile(BaseModel):
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    years_experience: float | None = None
    seniority: str | None = None
    highlights: list[str] = Field(default_factory=list)
    evidence: dict[str, list[str]] = Field(default_factory=dict)


class StructuredJob(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    seniority: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    evidence: dict[str, list[str]] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    id: str
    status: Literal["completed"]
    scores: ScoreBreakdown
    score_details: list[ScoreDetail] = Field(default_factory=list)
    cv_profile: StructuredProfile
    job_profile: StructuredJob
    matched_required_skills: list[SkillMatch]
    missing_required_skills: list[SkillMatch]
    missing_preferred_skills: list[SkillMatch]
    strengths: list[str]
    improvement_suggestions: list[str]
    tailored_cv_suggestions: list[str]
    cv_add_suggestions: list[CvAddSuggestion] = Field(default_factory=list)
    suggested_profile_summary: str | None = None
    llm_summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LlmAnalysisProgress(BaseModel):
    thinking: str = ""
    response: str = ""
    phase: Literal["thinking", "responding"] = "thinking"


class AnalysisJob(BaseModel):
    id: str
    status: JobStatus
    error: str | None = None
    result: AnalysisResult | None = None
    progress: LlmAnalysisProgress | None = None


class LlmTaskJob(BaseModel):
    id: str
    kind: Literal["rewrite", "job_titles", "cv_edit", "cv_edit_apply"]
    status: JobStatus
    error: str | None = None
    progress: LlmAnalysisProgress | None = None
    result: dict[str, Any] | None = None


class CvRewriteRequest(BaseModel):
    tone: RewriteTone = "professional_ats"
    language: RewriteLanguage = "en"
    deep_rewrite: bool = True
    output_format: RewriteOutputFormat = "auto"
    compile_pdf: bool = True
    llm_provider: LlmProvider = "local"


class CvRewriteChange(BaseModel):
    section: str
    before: str | None = None
    after: str
    reason: str
    evidence: list[str] = Field(default_factory=list)


class UnsupportedClaim(BaseModel):
    claim: str
    reason: str
    severity: Literal["warning", "blocked"] = "warning"


class CvRewriteResult(BaseModel):
    rewrite_id: str
    analysis_id: str
    updated_cv_text: str
    updated_latex_text: str | None = None
    changes: list[CvRewriteChange] = Field(default_factory=list)
    preserved_items: list[str] = Field(default_factory=list)
    omitted_missing_skills: list[str] = Field(default_factory=list)
    unsupported_claims: list[UnsupportedClaim] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    pdf_available: bool = False
    pdf_download_url: str | None = None
    latex_source_available: bool = False
    format_preserved: bool = False
    compile_warnings: list[str] = Field(default_factory=list)
    used_llm: bool = False
    llm_requested: bool = True
    llm_thinking: str | None = None
    tone: RewriteTone = "professional_ats"
    language: RewriteLanguage = "en"


class JobTitleSuggestion(BaseModel):
    title: str
    fit_score: int
    reason: str
    search_keywords: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class JobTitleSuggestionsResult(BaseModel):
    suggestions: list[JobTitleSuggestion]
    current_titles: list[str] = Field(default_factory=list)
    used_llm: bool = False
    llm_requested: bool = True
    llm_thinking: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CvEditSuggestion(BaseModel):
    category: str
    title: str
    recommendation: str
    priority: Literal["high", "medium", "low"] = "medium"
    evidence: list[str] = Field(default_factory=list)


class CvEditSuggestionsResult(BaseModel):
    overall_assessment: str
    suggestions: list[CvEditSuggestion]
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    used_llm: bool = False
    llm_requested: bool = True
    llm_thinking: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CvEditApplyChange(BaseModel):
    section: str
    reason: str
    evidence: list[str] = Field(default_factory=list)


class CvEditApplyResult(BaseModel):
    updated_cv_text: str
    changes: list[CvEditApplyChange] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    used_llm: bool = False
    llm_requested: bool = True
    llm_thinking: str | None = None


JobListingSource = Literal["linkedin", "kariyer"]


class ApifyActorPreview(BaseModel):
    source: JobListingSource
    actor_id: str
    configured: bool
    run_input: dict[str, object] = Field(default_factory=dict)


class JobSearchPreviewResult(BaseModel):
    search_queries: list[str] = Field(default_factory=list)
    cv_skills: list[str] = Field(default_factory=list)
    title_suggestions: list[str] = Field(default_factory=list)
    sources: list[JobListingSource] = Field(default_factory=list)
    location: str | None = None
    max_results_per_source: int = 10
    apify_ready: bool = False
    apify_actors: list[ApifyActorPreview] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class JobListingMatch(BaseModel):
    source: JobListingSource
    title: str
    company: str | None = None
    location: str | None = None
    url: str
    fit_score: int
    matched_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    missing_preferred_skills: list[str] = Field(default_factory=list)
    description_preview: str = ""
    posted_at: str | None = None


class JobSearchResult(BaseModel):
    listings: list[JobListingMatch] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    used_apify: bool = False
    sources_searched: list[JobListingSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


SkillGapSource = Literal["job_search", "analysis", "llm_analysis"]
SkillGapType = Literal["required", "preferred"]


class SkillGapListingRef(BaseModel):
    job_key: str
    job_title: str
    job_url: str | None = None
    company: str | None = None
    source: SkillGapSource
    last_seen_at: str | None = None


class SkillGapAggregate(BaseModel):
    skill_name: str
    gap_type: SkillGapType
    listing_count: int
    listings: list[SkillGapListingRef] = Field(default_factory=list)


class SkillGapSummaryResponse(BaseModel):
    aggregates: list[SkillGapAggregate] = Field(default_factory=list)
    total_skills: int = 0
    total_listings: int = 0

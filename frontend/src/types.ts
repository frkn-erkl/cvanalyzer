export type LlmProvider = "local" | "cursor";

export type ScoreBreakdown = {
  overall: number;
  technical_skills: number;
  experience_seniority: number;
  domain_keywords: number;
  education_certifications: number;
  language_communication: number;
  ats_compatibility: number;
};

export type ScoreDetail = {
  key: string;
  label: string;
  score: number;
  weight?: string | null;
  method: string;
  factors: string[];
};

export type SkillMatch = {
  name: string;
  matched: boolean;
  evidence: { label: string; source: "cv" | "job"; snippet: string }[];
};

export type CvAddSuggestion = {
  title: string;
  category:
    | "required_skill"
    | "preferred_skill"
    | "language"
    | "keyword"
    | "experience"
    | "format"
    | "education";
  priority: "high" | "medium" | "low";
  reason: string;
  how_to_add: string;
  job_evidence: string[];
};

export type AnalysisResult = {
  id: string;
  status: "completed";
  scores: ScoreBreakdown;
  score_details?: ScoreDetail[];
  matched_required_skills: SkillMatch[];
  missing_required_skills: SkillMatch[];
  missing_preferred_skills: SkillMatch[];
  strengths: string[];
  improvement_suggestions: string[];
  tailored_cv_suggestions: string[];
  cv_add_suggestions?: CvAddSuggestion[];
  suggested_profile_summary?: string | null;
  llm_summary?: string | null;
  warnings: string[];
  cv_profile: {
    skills: string[];
    languages: string[];
    seniority?: string | null;
    years_experience?: number | null;
  };
  job_profile: {
    required_skills: string[];
    preferred_skills: string[];
    languages: string[];
    seniority?: string | null;
  };
  metadata: Record<string, unknown>;
};

export type LlmAnalysisProgress = {
  thinking: string;
  response?: string;
  phase: "thinking" | "responding";
};

export type LlmTaskJob = {
  id: string;
  kind: "rewrite" | "job_titles" | "cv_edit" | "cv_edit_apply";
  status: "queued" | "running" | "completed" | "failed";
  error?: string | null;
  progress?: LlmAnalysisProgress | null;
  result?: Record<string, unknown> | null;
};

export type AnalysisJob = {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  error?: string | null;
  result?: AnalysisResult | null;
  progress?: LlmAnalysisProgress | null;
};

export type CvRewriteRequest = {
  tone: "professional_ats" | "concise_professional_ats";
  language: "en" | "tr";
  deep_rewrite: boolean;
  output_format: "auto" | "text" | "latex";
  compile_pdf: boolean;
  llm_provider?: LlmProvider;
};

export type CvRewriteChange = {
  section: string;
  before?: string | null;
  after: string;
  reason: string;
  evidence: string[];
};

export type UnsupportedClaim = {
  claim: string;
  reason: string;
  severity: "warning" | "blocked";
};

export type CvRewriteResult = {
  rewrite_id: string;
  analysis_id: string;
  updated_cv_text: string;
  updated_latex_text?: string | null;
  changes: CvRewriteChange[];
  preserved_items: string[];
  omitted_missing_skills: string[];
  unsupported_claims: UnsupportedClaim[];
  warnings: string[];
  pdf_available: boolean;
  pdf_download_url?: string | null;
  latex_source_available: boolean;
  format_preserved: boolean;
  compile_warnings: string[];
  used_llm: boolean;
  llm_requested?: boolean;
  llm_thinking?: string | null;
  tone: CvRewriteRequest["tone"];
  language: CvRewriteRequest["language"];
};

export type JobListingMatch = {
  source: "linkedin" | "kariyer";
  title: string;
  company?: string | null;
  location?: string | null;
  url: string;
  fit_score: number;
  matched_skills: string[];
  missing_required_skills: string[];
  missing_preferred_skills: string[];
  description_preview?: string | null;
  posted_at?: string | null;
};

export type ApifyActorPreview = {
  source: "linkedin" | "kariyer";
  actor_id: string;
  configured: boolean;
  run_input: Record<string, unknown>;
};

export type JobSearchPreviewResult = {
  search_queries: string[];
  cv_skills: string[];
  title_suggestions: string[];
  sources: ("linkedin" | "kariyer")[];
  location?: string | null;
  max_results_per_source: number;
  apify_ready: boolean;
  apify_actors: ApifyActorPreview[];
  warnings: string[];
};

export type JobSearchResult = {
  listings: JobListingMatch[];
  search_queries: string[];
  used_apify: boolean;
  sources_searched: ("linkedin" | "kariyer")[];
  warnings: string[];
};

export type JobTitleSuggestion = {
  title: string;
  fit_score: number;
  reason: string;
  search_keywords: string[];
  evidence: string[];
};

export type JobTitleSuggestionsResult = {
  suggestions: JobTitleSuggestion[];
  current_titles: string[];
  used_llm: boolean;
  llm_requested?: boolean;
  llm_thinking?: string | null;
  warnings: string[];
};

export type CvEditSuggestion = {
  category: string;
  title: string;
  recommendation: string;
  priority: "high" | "medium" | "low";
  evidence: string[];
};

export type CvEditSuggestionsResult = {
  overall_assessment: string;
  suggestions: CvEditSuggestion[];
  strengths: string[];
  gaps: string[];
  used_llm: boolean;
  llm_requested?: boolean;
  llm_thinking?: string | null;
  warnings: string[];
};

export type CvEditApplyChange = {
  section: string;
  reason: string;
  evidence: string[];
};

export type CvEditApplyResult = {
  updated_cv_text: string;
  changes: CvEditApplyChange[];
  warnings: string[];
  used_llm: boolean;
  llm_requested?: boolean;
  llm_thinking?: string | null;
};

export type SkillGapSource = "job_search" | "analysis" | "llm_analysis";
export type SkillGapType = "required" | "preferred";

export type SkillGapListingRef = {
  job_key: string;
  job_title: string;
  job_url?: string | null;
  company?: string | null;
  source: SkillGapSource;
  last_seen_at?: string | null;
};

export type SkillGapAggregate = {
  skill_name: string;
  gap_type: SkillGapType;
  listing_count: number;
  listings: SkillGapListingRef[];
};

export type SkillGapSummary = {
  aggregates: SkillGapAggregate[];
  total_skills: number;
  total_listings: number;
};

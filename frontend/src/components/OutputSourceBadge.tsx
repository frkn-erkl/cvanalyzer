export type OutputSourceKind = "llm" | "deterministic" | "embedding" | "fallback" | "skipped";

const SOURCE_LABELS: Record<OutputSourceKind, string> = {
  llm: "LLM",
  deterministic: "Deterministik",
  embedding: "LLM (embedding)",
  fallback: "Deterministik (fallback)",
  skipped: "Deterministik (LLM kapalı)",
};

const SOURCE_CLASS: Record<OutputSourceKind, string> = {
  llm: "source-llm",
  deterministic: "source-deterministic",
  embedding: "source-embedding",
  fallback: "source-fallback",
  skipped: "source-skipped",
};

type Props = {
  source: OutputSourceKind;
};

export default function OutputSourceBadge({ source }: Props) {
  return (
    <span className={`output-source-badge ${SOURCE_CLASS[source]}`} title="Bu bölümün çıktı kaynağı">
      {SOURCE_LABELS[source]}
    </span>
  );
}

export function rewriteOutputSource(llmRequested: boolean, usedLlm: boolean): OutputSourceKind {
  if (!llmRequested) {
    return "skipped";
  }
  return usedLlm ? "llm" : "fallback";
}

export function jobTitleOutputSource(llmRequested: boolean, usedLlm: boolean): OutputSourceKind {
  if (!llmRequested) {
    return "skipped";
  }
  return usedLlm ? "llm" : "fallback";
}

export function cvEditOutputSource(llmRequested: boolean, usedLlm: boolean): OutputSourceKind {
  if (!llmRequested) {
    return "skipped";
  }
  return usedLlm ? "llm" : "fallback";
}

export type AnalysisOutputSources = {
  summary?: "llm" | "fallback" | "skipped";
  domain_scoring?: "embedding" | "keyword_fallback" | "llm";
  recommendations?: "deterministic" | "llm";
  profile_summary?: "deterministic" | "llm";
  cv_add_suggestions?: "deterministic" | "llm";
  skill_matching?: "deterministic" | "llm";
};

export function isLlmOnlyAnalysis(metadata: Record<string, unknown>): boolean {
  return metadata.analysis_mode === "llm_only";
}

export function analysisSectionSource(
  metadata: Record<string, unknown>,
  section: keyof AnalysisOutputSources,
  fallback: OutputSourceKind = "deterministic",
): OutputSourceKind {
  const sources = readAnalysisOutputSources(metadata);
  const value = sources[section];
  if (value === "llm") {
    return "llm";
  }
  if (value === "embedding") {
    return "embedding";
  }
  if (value === "keyword_fallback") {
    return "deterministic";
  }
  if (isLlmOnlyAnalysis(metadata)) {
    return "llm";
  }
  return fallback;
}

export function readAnalysisOutputSources(metadata: Record<string, unknown>): AnalysisOutputSources {
  const raw = metadata.output_sources;
  if (!raw || typeof raw !== "object") {
    return {};
  }
  return raw as AnalysisOutputSources;
}

export function summaryOutputSource(
  metadata: Record<string, unknown>,
  llmSummary: string | null | undefined,
): OutputSourceKind {
  const sources = readAnalysisOutputSources(metadata);
  if (sources.summary === "llm") {
    return "llm";
  }
  if (sources.summary === "fallback") {
    return "fallback";
  }
  if (sources.summary === "skipped") {
    return "skipped";
  }
  if (llmSummary) {
    return "llm";
  }
  if (metadata.deep_analysis === true) {
    return "fallback";
  }
  return "skipped";
}

export function domainScoringSource(metadata: Record<string, unknown>): OutputSourceKind {
  const sources = readAnalysisOutputSources(metadata);
  if (sources.domain_scoring === "llm") {
    return "llm";
  }
  if (sources.domain_scoring === "embedding") {
    return "embedding";
  }
  if (sources.domain_scoring === "keyword_fallback") {
    return "deterministic";
  }
  if (isLlmOnlyAnalysis(metadata)) {
    return "llm";
  }
  const metrics = metadata.metrics;
  if (metrics && typeof metrics === "object") {
    const semantic = (metrics as { semantic_similarity?: number }).semantic_similarity;
    if (typeof semantic === "number" && semantic >= 0) {
      return "embedding";
    }
  }
  return "deterministic";
}

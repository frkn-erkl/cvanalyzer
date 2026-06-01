import type { AnalysisResult as Result, LlmProvider, ScoreDetail } from "../types";
import CvAddSuggestionsPanel from "./CvAddSuggestionsPanel";
import CvRewritePanel from "./CvRewritePanel";
import LlmSummaryContent from "./LlmSummaryContent";
import OutputSourceBadge, {
  analysisSectionSource,
  domainScoringSource,
  summaryOutputSource,
} from "./OutputSourceBadge";
import SectionHeading from "./SectionHeading";

type Props = {
  result: Result;
  llmProvider: LlmProvider;
};

const METRIC_KEYS = [
  "ats_compatibility",
  "technical_skills",
  "experience_seniority",
  "domain_keywords",
  "education_certifications",
  "language_communication",
] as const;

export default function AnalysisResult({ result, llmProvider }: Props) {
  const detailsByKey = Object.fromEntries((result.score_details ?? []).map((detail) => [detail.key, detail]));
  const overallDetail = detailsByKey.overall;
  const summarySource = summaryOutputSource(result.metadata, result.llm_summary);
  const domainSource = domainScoringSource(result.metadata);
  const scoreSource = analysisSectionSource(result.metadata, "recommendations");
  const listSource = analysisSectionSource(result.metadata, "recommendations");
  const skillSource = analysisSectionSource(result.metadata, "skill_matching");
  const profileSummarySource = analysisSectionSource(result.metadata, "profile_summary");
  const cvAddSource = analysisSectionSource(result.metadata, "cv_add_suggestions");

  return (
    <section className="results">
      <div className="score-card">
        <div>
          <div className="section-heading-row">
            <span className="eyebrow">Genel Uygunluk</span>
            <OutputSourceBadge source={scoreSource} />
          </div>
          <strong>{result.scores.overall}</strong>
          <span>/100</span>
        </div>
        <div>
          <p>{decisionText(result.scores.overall)}</p>
          {overallDetail && <p className="score-method light">{overallDetail.method}</p>}
        </div>
      </div>

      <div className="grid">
        {METRIC_KEYS.map((key) => (
          <Score
            key={key}
            detail={detailsByKey[key]}
            label={detailsByKey[key]?.label ?? labelForKey(key)}
            source={key === "domain_keywords" ? domainSource : scoreSource}
            value={result.scores[key]}
          />
        ))}
      </div>

      {summarySource !== "skipped" && (
        <article className="panel">
          <SectionHeading source={summarySource} title="Yerel LLM Yorumu" />
          {result.llm_summary ? (
            <LlmSummaryContent text={result.llm_summary} />
          ) : (
            <p className="hint">Yerel LLM yanıt veremedi; analiz tamamlanamadı.</p>
          )}
        </article>
      )}

      <List items={result.strengths} source={listSource} title="Güçlü Taraflar" />
      <List items={result.improvement_suggestions} source={listSource} title="Geliştirme Önerileri" />
      <CvAddSuggestionsPanel
        source={cvAddSource}
        suggestedProfileSummary={result.suggested_profile_summary}
        profileSummarySource={profileSummarySource}
        suggestions={result.cv_add_suggestions ?? []}
      />
      <List items={result.tailored_cv_suggestions} source={listSource} title="CV'ye Uygulanacak Somut Dokunuşlar" />
      <CvRewritePanel analysisId={result.id} llmProvider={llmProvider} />

      <article className="panel">
        <SectionHeading source={skillSource} title="Beceri Eşleşmesi" />
        <SkillChips skills={result.matched_required_skills.map((item) => item.name)} source={skillSource} title="Eşleşen zorunlu beceriler" tone="ok" />
        <SkillChips skills={result.missing_required_skills.map((item) => item.name)} source={skillSource} title="Eksik zorunlu beceriler" tone="danger" />
        <SkillChips skills={result.missing_preferred_skills.map((item) => item.name)} source={skillSource} title="Eksik tercih edilen beceriler" tone="warn" />
      </article>

      {result.warnings.length > 0 && <List items={result.warnings} source={listSource} title="Uyarılar" />}
    </section>
  );
}

function Score({
  label,
  value,
  detail,
  source,
}: {
  label: string;
  value: number;
  detail?: ScoreDetail;
  source: "deterministic" | "embedding" | "llm" | "fallback" | "skipped";
}) {
  return (
    <div className="panel metric">
      <div className="metric-header">
        <div className="section-heading-row">
          <span>{label}</span>
          <OutputSourceBadge source={source} />
        </div>
        {detail?.weight && <span className="metric-weight">{detail.weight}</span>}
      </div>
      <strong>{value}</strong>
      <div className="bar">
        <div style={{ width: `${value}%` }} />
      </div>
      {detail && (
        <div className="score-detail">
          <p className="score-method">{detail.method}</p>
          <ul className="score-factors">
            {detail.factors.map((factor) => (
              <li key={factor}>{factor}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function List({
  title,
  items,
  source,
}: {
  title: string;
  items: string[];
  source: "deterministic" | "embedding" | "llm" | "fallback" | "skipped";
}) {
  return (
    <article className="panel">
      <SectionHeading as="h2" source={source} title={title} />
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </article>
  );
}

function SkillChips({
  title,
  skills,
  tone,
  source,
}: {
  title: string;
  skills: string[];
  tone: "ok" | "warn" | "danger";
  source: "deterministic" | "embedding" | "llm" | "fallback" | "skipped";
}) {
  return (
    <div className="skill-group">
      <div className="section-heading-row">
        <h3>{title}</h3>
        <OutputSourceBadge source={source} />
      </div>
      <div className="chips">
        {skills.length > 0 ? skills.map((skill) => <span className={`chip ${tone}`} key={skill}>{skill}</span>) : <span className="muted">Yok</span>}
      </div>
    </div>
  );
}

function labelForKey(key: (typeof METRIC_KEYS)[number]) {
  const labels: Record<(typeof METRIC_KEYS)[number], string> = {
    ats_compatibility: "ATS uyumluluğu",
    technical_skills: "Teknik beceriler",
    experience_seniority: "Deneyim / seniority",
    domain_keywords: "Domain anahtar kelimeleri",
    education_certifications: "Eğitim / sertifika",
    language_communication: "Dil / iletişim",
  };
  return labels[key];
}

function decisionText(score: number) {
  if (score >= 80) return "CV bu ilan için güçlü görünüyor; küçük hedefleme iyileştirmeleri yeterli olabilir.";
  if (score >= 60) return "CV kısmen uygun; eksik beceri ve ifade boşlukları kapatılırsa başvuru güçlenir.";
  return "CV bu ilan için zayıf görünüyor; zorunlu beklentiler ve deneyim anlatımı ciddi şekilde ele alınmalı.";
}

import { useState } from "react";
import type { CvAddSuggestion } from "../types";
import SectionHeading from "./SectionHeading";
import OutputSourceBadge, { type OutputSourceKind } from "./OutputSourceBadge";

type Props = {
  suggestions: CvAddSuggestion[];
  suggestedProfileSummary?: string | null;
  source?: OutputSourceKind;
  profileSummarySource?: OutputSourceKind;
};

const CATEGORY_LABELS: Record<CvAddSuggestion["category"], string> = {
  required_skill: "Zorunlu beceri",
  preferred_skill: "Tercih edilen beceri",
  language: "Dil",
  keyword: "Domain kelimesi",
  experience: "Deneyim",
  format: "Format",
  education: "Eğitim",
};

const PRIORITY_LABELS: Record<CvAddSuggestion["priority"], string> = {
  high: "Yüksek",
  medium: "Orta",
  low: "Düşük",
};

export default function CvAddSuggestionsPanel({
  suggestions,
  suggestedProfileSummary,
  source = "deterministic",
  profileSummarySource = source,
}: Props) {
  const [copied, setCopied] = useState(false);

  if (suggestions.length === 0 && !suggestedProfileSummary) {
    return null;
  }

  async function copySummary() {
    if (!suggestedProfileSummary) {
      return;
    }
    await navigator.clipboard.writeText(suggestedProfileSummary);
    setCopied(true);
  }

  return (
    <article className="panel add-suggestions-panel">
      <SectionHeading
        hint="CV'niz otomatik güncellenmez. Aşağıdaki maddeleri yalnızca gerçekten sahip olduğunuz deneyim ve beceriler için ekleyin."
        source={source}
        title="CV'ye Ne Eklemelisiniz?"
      />

      {suggestedProfileSummary && (
        <section className="profile-summary-suggestion">
          <div className="rewrite-result-header">
            <div>
              <div className="section-heading-row">
                <h3>Önerilen Profile Summary</h3>
                <OutputSourceBadge source={profileSummarySource} />
              </div>
              <p className="hint">CV'nizdeki kanıtlanmış bilgilere dayalı, ilana hizalı örnek özet paragraf.</p>
            </div>
            <button className="secondary" onClick={copySummary} type="button">
              {copied ? "Kopyalandı" : "Özeti kopyala"}
            </button>
          </div>
          <pre className="profile-summary-text">{suggestedProfileSummary}</pre>
        </section>
      )}

      {suggestions.length > 0 && (
        <ul className="add-suggestions-list">
          {suggestions.map((item) => (
            <li className="add-suggestion-card" key={`${item.category}-${item.title}`}>
              <div className="add-suggestion-header">
                <strong>{item.title}</strong>
                <div className="add-suggestion-badges">
                  <span className={`chip ${priorityTone(item.priority)}`}>{PRIORITY_LABELS[item.priority]}</span>
                  <span className="chip">{CATEGORY_LABELS[item.category]}</span>
                </div>
              </div>
              <p className="add-suggestion-reason">{item.reason}</p>
              <div className="add-suggestion-how">
                <span className="eyebrow">Nasıl eklenir</span>
                <p>{item.how_to_add}</p>
              </div>
              {item.job_evidence.length > 0 && (
                <div className="add-suggestion-evidence">
                  <span className="eyebrow">İlandan kanıt</span>
                  <ul>
                    {item.job_evidence.map((snippet) => (
                      <li key={snippet}>{snippet}</li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

function priorityTone(priority: CvAddSuggestion["priority"]) {
  if (priority === "high") {
    return "danger";
  }
  if (priority === "medium") {
    return "warn";
  }
  return "ok";
}

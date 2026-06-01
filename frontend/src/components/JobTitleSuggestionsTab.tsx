import { FormEvent, useState } from "react";
import { suggestJobTitles } from "../api";
import type { JobTitleSuggestionsResult, LlmProvider } from "../types";
import LlmOptionToggle from "./LlmOptionToggle";
import LlmProviderSelect from "./LlmProviderSelect";
import OutputSourceBadge, { jobTitleOutputSource } from "./OutputSourceBadge";
import SectionHeading from "./SectionHeading";

type CvMode = "text" | "file" | "url";

type Props = {
  llmProvider: LlmProvider;
  onLlmProviderChange: (provider: LlmProvider) => void;
};

export default function JobTitleSuggestionsTab({ llmProvider, onLlmProviderChange }: Props) {
  const [cvMode, setCvMode] = useState<CvMode>("text");
  const [language, setLanguage] = useState<"tr" | "en">("tr");
  const [useLlm, setUseLlm] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<JobTitleSuggestionsResult | null>(null);
  const [copiedTitle, setCopiedTitle] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    data.set("language", language);
    data.set("use_llm", useLlm ? "true" : "false");
    data.set("llm_provider", llmProvider);

    if (cvMode === "text") {
      data.delete("cv_file");
      data.delete("cv_url");
    } else if (cvMode === "file") {
      data.delete("cv_text");
      data.delete("cv_url");
    } else {
      data.delete("cv_text");
      data.delete("cv_file");
    }

    setBusy(true);
    setError(null);
    setCopiedTitle(null);
    try {
      const response = await suggestJobTitles(data);
      setResult(response);
    } catch (submitError) {
      setResult(null);
      setError(submitError instanceof Error ? submitError.message : "İş unvanı önerileri alınamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function copyTitle(title: string) {
    await navigator.clipboard.writeText(title);
    setCopiedTitle(title);
  }

  const titleSource = result
    ? jobTitleOutputSource(result.llm_requested ?? useLlm, result.used_llm)
    : undefined;

  return (
    <div className="job-title-tab">
      <form className="panel form" onSubmit={handleSubmit}>
        <section>
          <div className="section-title">
            <h2>CV</h2>
            <div className="section-title-actions">
              <LlmProviderSelect disabled={busy} onChange={onLlmProviderChange} value={llmProvider} />
              <LlmOptionToggle checked={useLlm} disabled={busy} onChange={setUseLlm} />
              <div className="toggle">
                <button type="button" className={cvMode === "text" ? "active" : ""} onClick={() => setCvMode("text")}>
                  Metin
                </button>
                <button type="button" className={cvMode === "file" ? "active" : ""} onClick={() => setCvMode("file")}>
                  Dosya
                </button>
                <button type="button" className={cvMode === "url" ? "active" : ""} onClick={() => setCvMode("url")}>
                  Link
                </button>
              </div>
            </div>
          </div>
          {cvMode === "text" && (
            <textarea name="cv_text" rows={12} placeholder="CV metnini buraya yapıştırın..." required />
          )}
          {cvMode === "file" && (
            <input name="cv_file" type="file" accept=".pdf,.docx,.txt,.tex,.html,.htm" required />
          )}
          {cvMode === "url" && (
            <input name="cv_url" type="url" placeholder="https://example.com/cv.pdf" required />
          )}
        </section>

        <div className="rewrite-controls">
          <label>
            Öneri dili
            <select value={language} onChange={(event) => setLanguage(event.target.value as "tr" | "en")}>
              <option value="tr">Türkçe</option>
              <option value="en">English</option>
            </select>
          </label>
        </div>

        <button className="primary" disabled={busy} type="submit">
          {busy ? "Unvanlar üretiliyor..." : "İş unvanı önerileri al"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {result && (
        <section className="results job-title-results">
          <article className="panel">
            <SectionHeading
              actions={<LlmOptionToggle checked={useLlm} disabled={busy} onChange={setUseLlm} />}
              hint={
                result.used_llm
                  ? "Yerel LLM, CV kanıtlarına dayalı unvan önerileri üretti."
                  : "Beceri tabanlı deterministik unvan önerileri kullanıldı."
              }
              source={titleSource}
              title="Aramanız Gereken Unvanlar"
            />

            {result.current_titles.length > 0 && (
              <div className="skill-group">
                <h3>CV'deki mevcut unvan ipuçları</h3>
                <div className="chips">
                  {result.current_titles.map((title) => (
                    <span className="chip ok" key={title}>
                      {title}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="job-title-list">
              {result.suggestions.map((item) => (
                <article className="job-title-card" key={item.title}>
                  <div className="job-title-card-header">
                    <div>
                      <h3>{item.title}</h3>
                      <span className="fit-score">Uyum: {item.fit_score}/100</span>
                    </div>
                    <button className="secondary" onClick={() => copyTitle(item.title)} type="button">
                      {copiedTitle === item.title ? "Kopyalandı" : "Unvanı kopyala"}
                    </button>
                  </div>
                  <p>{item.reason}</p>
                  {item.search_keywords.length > 0 && (
                    <div className="skill-group">
                      <h4>Arama anahtar kelimeleri</h4>
                      <div className="chips">
                        {item.search_keywords.map((keyword) => (
                          <span className="chip" key={`${item.title}-${keyword}`}>
                            {keyword}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {item.evidence.length > 0 && (
                    <ul className="score-factors">
                      {item.evidence.map((line) => (
                        <li key={`${item.title}-${line}`}>{line}</li>
                      ))}
                    </ul>
                  )}
                </article>
              ))}
            </div>

            {result.warnings.length > 0 && (
              <ul className="score-factors">
                {result.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            )}
          </article>
        </section>
      )}
    </div>
  );
}

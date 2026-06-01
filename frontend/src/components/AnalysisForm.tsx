import { FormEvent, useEffect, useState } from "react";
import LlmOptionToggle from "./LlmOptionToggle";
import LlmProviderSelect from "./LlmProviderSelect";
import type { LlmProvider } from "../types";

function isApifyJobUrl(url: string): boolean {
  try {
    const host = new URL(url).hostname.replace(/^www\./i, "").toLowerCase();
    return (
      host === "linkedin.com" ||
      host.endsWith(".linkedin.com") ||
      host === "kariyer.net" ||
      host.endsWith(".kariyer.net")
    );
  } catch {
    return false;
  }
}

type Props = {
  onSubmit: (formData: FormData) => Promise<void>;
  busy: boolean;
  showLlmToggle?: boolean;
  submitLabel?: string;
  busyLabel?: string;
  llmHint?: string;
  llmProvider: LlmProvider;
  onLlmProviderChange: (provider: LlmProvider) => void;
  initialJobUrl?: string;
};

type CvMode = "text" | "file" | "url";
type JobMode = "url" | "text";

export default function AnalysisForm({
  onSubmit,
  busy,
  showLlmToggle = true,
  submitLabel = "Analizi Başlat",
  busyLabel = "Analiz ediliyor...",
  llmHint = "Açıkken analiz sonuçlarına seçilen LLM sağlayıcısı ile üretilmiş detaylı Türkçe yorum eklenir.",
  llmProvider,
  onLlmProviderChange,
  initialJobUrl = "",
}: Props) {
  const [cvMode, setCvMode] = useState<CvMode>("text");
  const [jobMode, setJobMode] = useState<JobMode>("url");
  const [deepAnalysis, setDeepAnalysis] = useState(false);
  const [useApify, setUseApify] = useState(false);
  const [jobUrl, setJobUrl] = useState(initialJobUrl);

  useEffect(() => {
    if (initialJobUrl) {
      setJobUrl(initialJobUrl);
      setJobMode("url");
      if (isApifyJobUrl(initialJobUrl)) {
        setUseApify(true);
      }
    }
  }, [initialJobUrl]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    data.set("deep_analysis", deepAnalysis ? "true" : "false");
    data.set("llm_provider", llmProvider);
    data.set("use_apify", useApify ? "true" : "false");

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

    if (jobMode === "url") {
      data.delete("job_text");
    } else {
      data.delete("job_url");
    }

    await onSubmit(data);
  }

  return (
    <form className="panel form" onSubmit={handleSubmit}>
      <section>
        <div className="section-title">
          <h2>CV</h2>
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
        {cvMode === "text" && (
          <textarea name="cv_text" rows={12} placeholder="CV metnini buraya yapıştırın..." />
        )}
        {cvMode === "file" && (
          <input name="cv_file" type="file" accept=".pdf,.docx,.txt,.tex,.html,.htm" />
        )}
        {cvMode === "url" && (
          <input name="cv_url" type="url" placeholder="https://example.com/cv.pdf" />
        )}
      </section>

      <section>
        <div className="section-title">
          <h2>İş İlanı</h2>
          <div className="toggle">
            <button type="button" className={jobMode === "url" ? "active" : ""} onClick={() => setJobMode("url")}>
              Link
            </button>
            <button type="button" className={jobMode === "text" ? "active" : ""} onClick={() => setJobMode("text")}>
              Metin
            </button>
          </div>
        </div>
        {jobMode === "url" ? (
          <>
            <input
              name="job_url"
              onChange={(event) => setJobUrl(event.target.value)}
              placeholder="https://example.com/jobs/backend-developer"
              type="url"
              value={jobUrl}
            />
            <label className="checkbox-inline">
              <input checked={useApify} disabled={busy} onChange={(event) => setUseApify(event.target.checked)} type="checkbox" />
              Apify ile çek (LinkedIn/Kariyer)
            </label>
          </>
        ) : (
          <textarea name="job_text" rows={12} placeholder="İş ilanı metnini buraya yapıştırın..." />
        )}
      </section>

      {showLlmToggle && (
        <section>
          <div className="section-title">
            <h2>Analiz</h2>
            <div className="section-title-actions">
              <LlmProviderSelect disabled={busy} onChange={onLlmProviderChange} value={llmProvider} />
              <LlmOptionToggle checked={deepAnalysis} disabled={busy} onChange={setDeepAnalysis} />
            </div>
          </div>
          <p className="hint">{llmHint}</p>
        </section>
      )}

      {!showLlmToggle && (
        <section>
          <div className="section-title">
            <h2>Analiz</h2>
            <LlmProviderSelect disabled={busy} onChange={onLlmProviderChange} value={llmProvider} />
          </div>
          <p className="hint">{llmHint}</p>
        </section>
      )}

      <button className="primary" disabled={busy} type="submit">
        {busy ? busyLabel : submitLabel}
      </button>
    </form>
  );
}

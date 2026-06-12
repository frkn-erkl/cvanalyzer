import { FormEvent, useState } from "react";
import { applyCvEdits, suggestCvEdits } from "../api";
import { isLlmTaskJob, supportsLiveLocalThinking, useLlmTaskPolling } from "../hooks/useLlmTaskPolling";
import type { CvEditApplyResult, CvEditSuggestionsResult, LlmProvider, LlmTaskJob } from "../types";
import LlmOptionToggle from "./LlmOptionToggle";
import LlmProviderSelect from "./LlmProviderSelect";
import LlmThinkingPanel from "./LlmThinkingPanel";
import OutputSourceBadge, { cvEditOutputSource } from "./OutputSourceBadge";
import SectionHeading from "./SectionHeading";

type CvMode = "text" | "file" | "url";

type Props = {
  llmProvider: LlmProvider;
  onLlmProviderChange: (provider: LlmProvider) => void;
};

const PRIORITY_LABELS: Record<CvEditSuggestionsResult["suggestions"][number]["priority"], string> = {
  high: "Yüksek",
  medium: "Orta",
  low: "Düşük",
};

function cloneFormData(source: FormData): FormData {
  const clone = new FormData();
  for (const [key, value] of source.entries()) {
    clone.append(key, value);
  }
  return clone;
}

function buildSubmissionData(form: HTMLFormElement, cvMode: CvMode, language: "tr" | "en", useLlm: boolean, llmProvider: LlmProvider) {
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

  return data;
}

export default function CvEditTab({ llmProvider, onLlmProviderChange }: Props) {
  const [cvMode, setCvMode] = useState<CvMode>("text");
  const [language, setLanguage] = useState<"tr" | "en">("tr");
  const [useLlm, setUseLlm] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CvEditSuggestionsResult | null>(null);
  const [task, setTask] = useState<LlmTaskJob | null>(null);
  const [lastSubmission, setLastSubmission] = useState<FormData | null>(null);
  const [applyBusy, setApplyBusy] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applyResult, setApplyResult] = useState<CvEditApplyResult | null>(null);
  const [applyTask, setApplyTask] = useState<LlmTaskJob | null>(null);
  const [copied, setCopied] = useState(false);

  const showLiveThinking = busy && supportsLiveLocalThinking(llmProvider, useLlm);
  const showApplyLiveThinking = applyBusy && supportsLiveLocalThinking(llmProvider, true);

  useLlmTaskPolling(task?.id, busy && Boolean(task), {
    onUpdate: setTask,
    onFailed: (message) => {
      setError(message);
      setBusy(false);
    },
    onComplete: (completedTask) => {
      setResult(completedTask.result as unknown as CvEditSuggestionsResult);
      setBusy(false);
    },
  });

  useLlmTaskPolling(applyTask?.id, applyBusy && Boolean(applyTask), {
    onUpdate: setApplyTask,
    onFailed: (message) => {
      setApplyError(message);
      setApplyBusy(false);
    },
    onComplete: (completedTask) => {
      setApplyResult(completedTask.result as unknown as CvEditApplyResult);
      setApplyBusy(false);
    },
  });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = buildSubmissionData(form, cvMode, language, useLlm, llmProvider);

    setBusy(true);
    setError(null);
    setTask(null);
    setApplyResult(null);
    setApplyError(null);
    setApplyTask(null);
    setCopied(false);
    setLastSubmission(cloneFormData(data));
    try {
      const response = await suggestCvEdits(data);
      if (isLlmTaskJob(response)) {
        setTask(response);
        return;
      }
      setResult(response);
      setBusy(false);
    } catch (submitError) {
      setResult(null);
      setLastSubmission(null);
      setError(submitError instanceof Error ? submitError.message : "CV düzenleme önerileri alınamadı.");
      setBusy(false);
    }
  }

  async function handleApplyEdits() {
    if (!result || !lastSubmission) {
      return;
    }

    const data = cloneFormData(lastSubmission);
    data.set("language", language);
    data.set("llm_provider", llmProvider);
    data.delete("use_llm");
    data.set("suggestions_json", JSON.stringify(result.suggestions));

    setApplyBusy(true);
    setApplyError(null);
    setApplyTask(null);
    setApplyResult(null);
    setCopied(false);
    try {
      const response = await applyCvEdits(data);
      if (isLlmTaskJob(response)) {
        setApplyTask(response);
        return;
      }
      setApplyResult(response);
      setApplyBusy(false);
    } catch (applyFailure) {
      setApplyError(applyFailure instanceof Error ? applyFailure.message : "CV düzenleme uygulanamadı.");
      setApplyBusy(false);
    }
  }

  async function copyToClipboard() {
    if (!applyResult?.updated_cv_text) {
      return;
    }
    await navigator.clipboard.writeText(applyResult.updated_cv_text);
    setCopied(true);
  }

  const outputSource = result ? cvEditOutputSource(result.llm_requested ?? useLlm, result.used_llm) : undefined;
  const applyOutputSource = applyResult
    ? cvEditOutputSource(applyResult.llm_requested ?? true, applyResult.used_llm)
    : undefined;

  return (
    <div className="cv-edit-tab">
      <form className="panel form" onSubmit={handleSubmit}>
        <section>
          <div className="section-title">
            <h2>CV</h2>
            <div className="section-title-actions">
              <LlmProviderSelect disabled={busy || applyBusy} onChange={onLlmProviderChange} value={llmProvider} />
              <LlmOptionToggle checked={useLlm} disabled={busy || applyBusy} onChange={setUseLlm} />
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

        <section className="guidance-field">
          <label>
            Yönlendirme
            <textarea
              name="guidance"
              rows={4}
              placeholder="Örn: İyi bir endüstri mühendisi CV görünümü için öneriler"
              required
            />
          </label>
          <p className="hint">
            CV&apos;nizi nasıl geliştirmek istediğinizi serbest metin olarak yazın. İlk adımda yalnızca öneri üretilir;
            isterseniz sonrasında önerileri tüm CV metnine uygulayabilirsiniz.
          </p>
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

        <button className="primary" disabled={busy || applyBusy} type="submit">
          {busy ? "Öneriler üretiliyor..." : "CV düzenleme önerileri al"}
        </button>
      </form>

      {showLiveThinking && (
        <LlmThinkingPanel
          live
          progress={task?.progress}
          waiting={!task?.progress?.thinking && !task?.progress?.response}
          waitingMessage="CV hazırlanıyor; Türkçe CV'ler önce İngilizceye çevrilir, ardından model önerileri üretir. Bu birkaç dakika sürebilir."
        />
      )}

      {error && <p className="error">{error}</p>}

      {result?.llm_thinking && !busy && <LlmThinkingPanel storedThinking={result.llm_thinking} />}

      {result && (
        <section className="results cv-edit-results">
          <article className="panel">
            <SectionHeading
              actions={<LlmOptionToggle checked={useLlm} disabled={busy || applyBusy} onChange={setUseLlm} />}
              hint={
                result.used_llm
                  ? "Seçilen LLM sağlayıcısı CV kanıtlarına dayalı düzenleme önerileri üretti."
                  : "Temel profil tabanlı deterministik öneriler kullanıldı."
              }
              source={outputSource}
              title="CV Düzenleme Önerileri"
            />

            <p className="cv-edit-assessment">{result.overall_assessment}</p>

            {(result.strengths.length > 0 || result.gaps.length > 0) && (
              <div className="cv-edit-summary-grid">
                {result.strengths.length > 0 && (
                  <div className="skill-group">
                    <h3>Güçlü yönler</h3>
                    <ul className="score-factors">
                      {result.strengths.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {result.gaps.length > 0 && (
                  <div className="skill-group">
                    <h3>Gelişim alanları</h3>
                    <ul className="score-factors">
                      {result.gaps.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            <div className="job-title-list">
              {result.suggestions.map((item) => (
                <article className="job-title-card cv-edit-card" key={`${item.category}-${item.title}`}>
                  <div className="job-title-card-header">
                    <div>
                      <h3>{item.title}</h3>
                      <div className="cv-edit-card-meta">
                        <span className="chip">{item.category}</span>
                        <span className={`priority-badge priority-${item.priority}`}>
                          {PRIORITY_LABELS[item.priority]}
                        </span>
                      </div>
                    </div>
                  </div>
                  <p>{item.recommendation}</p>
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

            <div className="cv-apply-actions">
              <button
                className="primary"
                disabled={!useLlm || applyBusy || busy || !lastSubmission}
                onClick={() => void handleApplyEdits()}
                type="button"
              >
                {applyBusy ? "CV metni düzenleniyor..." : "Tüm CV metnini düzenle"}
              </button>
              {!useLlm && (
                <p className="hint">Tam metin düzenleme için LLM açık olmalıdır.</p>
              )}
            </div>
          </article>

          {showApplyLiveThinking && (
            <LlmThinkingPanel
              live
              progress={applyTask?.progress}
              waiting={!applyTask?.progress?.thinking && !applyTask?.progress?.response}
              waitingMessage="Öneriler CV metnine uygulanıyor; bu adım birkaç dakika sürebilir."
            />
          )}

          {applyError && <p className="error">{applyError}</p>}

          {applyResult?.llm_thinking && !applyBusy && <LlmThinkingPanel storedThinking={applyResult.llm_thinking} />}

          {applyResult && (
            <article className="panel cv-apply-result rewrite-result">
              <div className="rewrite-result-header">
                <div className="section-heading-row">
                  <h3>Düzenlenmiş CV Metni</h3>
                  {applyOutputSource && <OutputSourceBadge source={applyOutputSource} />}
                </div>
                <button className="secondary" onClick={() => void copyToClipboard()} type="button">
                  {copied ? "Kopyalandı" : "Metni kopyala"}
                </button>
              </div>
              <textarea readOnly rows={18} value={applyResult.updated_cv_text} />

              {applyResult.changes.length > 0 && (
                <section className="rewrite-detail">
                  <h3>Uygulanan Değişiklikler</h3>
                  <ul>
                    {applyResult.changes.map((change) => (
                      <li key={`${change.section}-${change.reason}`}>
                        <strong>{change.section}:</strong> {change.reason}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {applyResult.warnings.length > 0 && (
                <section className="rewrite-detail">
                  <h3>Uyarılar</h3>
                  <ul>
                    {applyResult.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </section>
              )}
            </article>
          )}
        </section>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { getAnalysis, getApifyHealth, getLlmHealth, submitAnalysis, submitLlmAnalysis } from "./api";
import AnalysisForm from "./components/AnalysisForm";
import AnalysisResult from "./components/AnalysisResult";
import JobSearchTab from "./components/JobSearchTab";
import JobTitleSuggestionsTab from "./components/JobTitleSuggestionsTab";
import StatusPanel from "./components/StatusPanel";
import type { AnalysisJob, LlmProvider } from "./types";

type AppTab = "analysis" | "llm-analysis" | "job-titles" | "job-search";

export default function App() {
  const [activeTab, setActiveTab] = useState<AppTab>("analysis");
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [llmJob, setLlmJob] = useState<AnalysisJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [llmBusy, setLlmBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [llmHealth, setLlmHealth] = useState<Record<string, unknown> | null>(null);
  const [apifyHealth, setApifyHealth] = useState<Record<string, unknown> | null>(null);
  const [llmProvider, setLlmProvider] = useState<LlmProvider>("local");
  const [prefilledJobUrl, setPrefilledJobUrl] = useState("");

  useEffect(() => {
    getLlmHealth(llmProvider)
      .then(setLlmHealth)
      .catch((healthError) =>
        setLlmHealth({
          available: false,
          provider: llmProvider,
          error: healthError instanceof Error ? healthError.message : "Backend bağlantısı kurulamadı",
        }),
      );
  }, [llmProvider]);

  useEffect(() => {
    if (activeTab !== "job-search") {
      return;
    }
    getApifyHealth()
      .then(setApifyHealth)
      .catch((healthError) =>
        setApifyHealth({
          available: false,
          error: healthError instanceof Error ? healthError.message : "Apify durumu alınamadı",
        }),
      );
  }, [activeTab]);

  useEffect(() => {
    if (!job?.id || !["queued", "running"].includes(job.status)) {
      return;
    }
    const handle = window.setInterval(async () => {
      try {
        const next = await getAnalysis(job.id);
        setJob(next);
        if (next.status === "failed") {
          setError(next.error ?? "Analiz başarısız oldu.");
          setBusy(false);
        }
        if (next.status === "completed") {
          setBusy(false);
        }
      } catch (pollError) {
        setError(pollError instanceof Error ? pollError.message : "Analiz durumu alınamadı.");
        setBusy(false);
      }
    }, 1500);
    return () => window.clearInterval(handle);
  }, [job?.id, job?.status]);

  useEffect(() => {
    if (!llmJob?.id || !["queued", "running"].includes(llmJob.status)) {
      return;
    }
    const handle = window.setInterval(async () => {
      try {
        const next = await getAnalysis(llmJob.id);
        setLlmJob(next);
        if (next.status === "failed") {
          setLlmError(next.error ?? "LLM analizi başarısız oldu.");
          setLlmBusy(false);
        }
        if (next.status === "completed") {
          setLlmBusy(false);
        }
      } catch (pollError) {
        setLlmError(pollError instanceof Error ? pollError.message : "LLM analiz durumu alınamadı.");
        setLlmBusy(false);
      }
    }, 1500);
    return () => window.clearInterval(handle);
  }, [llmJob?.id, llmJob?.status]);

  async function handleSubmit(formData: FormData) {
    setBusy(true);
    setError(null);
    setJob({ id: "local", status: "running" });
    try {
      const response = await submitAnalysis(formData);
      setJob(response);
      if (response.status === "failed") {
        setError(response.error ?? "Analiz başarısız oldu.");
        setBusy(false);
      }
      if (response.status === "completed") {
        setBusy(false);
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Bilinmeyen hata");
      setJob(null);
      setBusy(false);
    }
  }

  async function handleLlmSubmit(formData: FormData) {
    setLlmBusy(true);
    setLlmError(null);
    setLlmJob({ id: "local", status: "running" });
    try {
      const response = await submitLlmAnalysis(formData);
      setLlmJob(response);
      if (response.status === "failed") {
        setLlmError(response.error ?? "LLM analizi başarısız oldu.");
        setLlmBusy(false);
      }
      if (response.status === "completed") {
        setLlmBusy(false);
      }
    } catch (submitError) {
      setLlmError(submitError instanceof Error ? submitError.message : "Bilinmeyen hata");
      setLlmJob(null);
      setLlmBusy(false);
    }
  }

  function handleAnalyzeListing(jobUrl: string) {
    setPrefilledJobUrl(jobUrl);
    setActiveTab("analysis");
  }

  return (
    <main className="app">
      <header className="hero">
        <div>
          <span className="eyebrow">Yerel LLM destekli</span>
          <h1>CV ve İş İlanı Uyum Analizi</h1>
          <p>
            CV metninizi ve iş ilanı linkini karşılaştırır; uygunluk skorunu, eksik alanları ve ilana özel CV geliştirme önerilerini üretir.
          </p>
        </div>
        <div className="toggle app-tabs">
          <button type="button" className={activeTab === "analysis" ? "active" : ""} onClick={() => setActiveTab("analysis")}>
            Uyum Analizi
          </button>
          <button type="button" className={activeTab === "llm-analysis" ? "active" : ""} onClick={() => setActiveTab("llm-analysis")}>
            LLM Analizi
          </button>
          <button type="button" className={activeTab === "job-titles" ? "active" : ""} onClick={() => setActiveTab("job-titles")}>
            İş Unvanı Önerileri
          </button>
          <button type="button" className={activeTab === "job-search" ? "active" : ""} onClick={() => setActiveTab("job-search")}>
            İlan Arama
          </button>
        </div>
      </header>

      <div className="layout">
        <div>
          {activeTab === "analysis" ? (
            <>
              <AnalysisForm
                initialJobUrl={prefilledJobUrl}
                llmProvider={llmProvider}
                onLlmProviderChange={setLlmProvider}
                onSubmit={handleSubmit}
                busy={busy}
              />
              {job?.result && <AnalysisResult llmProvider={llmProvider} result={job.result} />}
            </>
          ) : activeTab === "llm-analysis" ? (
            <>
              <AnalysisForm
                busy={llmBusy}
                busyLabel="LLM analizi yapılıyor..."
                initialJobUrl={prefilledJobUrl}
                llmHint="Bu sekmede skor, beceri eşleşmesi, öneriler ve yorumların tamamı seçilen LLM sağlayıcısı tarafından üretilir."
                llmProvider={llmProvider}
                onLlmProviderChange={setLlmProvider}
                onSubmit={handleLlmSubmit}
                showLlmToggle={false}
                submitLabel="LLM Analizini Başlat"
              />
              {llmJob?.result && <AnalysisResult llmProvider={llmProvider} result={llmJob.result} />}
            </>
          ) : activeTab === "job-search" ? (
            <JobSearchTab llmProvider={llmProvider} onAnalyzeJob={handleAnalyzeListing} onLlmProviderChange={setLlmProvider} />
          ) : (
            <JobTitleSuggestionsTab llmProvider={llmProvider} onLlmProviderChange={setLlmProvider} />
          )}
        </div>
        <StatusPanel
          apifyHealth={apifyHealth}
          llmProvider={llmProvider}
          mode={
            activeTab === "llm-analysis"
              ? "llm-only"
              : activeTab === "job-titles"
                ? "job-titles"
                : activeTab === "job-search"
                  ? "job-search"
                  : "hybrid"
          }
          showApify={activeTab === "job-search"}
          status={activeTab === "analysis" ? job?.status : activeTab === "llm-analysis" ? llmJob?.status : undefined}
          error={activeTab === "analysis" ? error : activeTab === "llm-analysis" ? llmError : null}
          llmHealth={llmHealth}
        />
      </div>
    </main>
  );
}

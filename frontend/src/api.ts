import type {
  AnalysisJob,
  CvEditApplyResult,
  CvEditSuggestionsResult,
  CvRewriteRequest,
  CvRewriteResult,
  JobSearchPreviewResult,
  JobSearchResult,
  JobTitleSuggestionsResult,
  SkillGapSummary,
  LlmProvider,
  LlmTaskJob,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const DEFAULT_FETCH_TIMEOUT_MS = 15_000;

async function fetchWithTimeout(input: string, init?: RequestInit, timeoutMs = DEFAULT_FETCH_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Backend yanıt vermedi (zaman aşımı). Analiz arka planda sürebilir; birkaç saniye sonra tekrar denenecek.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function submitAnalysis(formData: FormData): Promise<AnalysisJob> {
  const response = await fetch(`${API_BASE_URL}/api/analysis`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Analiz başlatılamadı.");
  }
  return response.json();
}

export async function submitLlmAnalysis(formData: FormData): Promise<AnalysisJob> {
  const response = await fetch(`${API_BASE_URL}/api/llm-analysis`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "LLM analizi başlatılamadı.");
  }
  return response.json();
}

export async function getAnalysis(id: string): Promise<AnalysisJob> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/analysis/${id}`);
  if (!response.ok) {
    throw new Error("Analiz durumu alınamadı.");
  }
  return response.json();
}

function backendUnreachableMessage(): string {
  return "Backend'e ulaşılamıyor. Proje kökünden .\\start-dev.ps1 çalıştırın veya backend'de uvicorn app.main:app --reload --port 8000 komutunu başlatın.";
}

export async function getLlmHealth(provider?: LlmProvider): Promise<Record<string, unknown>> {
  const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  try {
    const response = await fetch(`${API_BASE_URL}/api/llm/health${query}`);
    if (!response.ok) {
      if (response.status >= 500 || response.status === 502 || response.status === 503) {
        throw new Error(backendUnreachableMessage());
      }
      throw new Error("LLM durumu alınamadı.");
    }
    return response.json();
  } catch (error) {
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      throw new Error(backendUnreachableMessage());
    }
    throw error;
  }
}

export async function getLlmTask(taskId: string): Promise<LlmTaskJob> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/llm-tasks/${taskId}`, undefined, 30_000);
  if (!response.ok) {
    throw new Error("LLM görev durumu alınamadı.");
  }
  return response.json();
}

export async function rewriteCv(
  analysisId: string,
  request: CvRewriteRequest,
): Promise<CvRewriteResult | LlmTaskJob> {
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/api/analysis/${analysisId}/rewrite-cv`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    }, 30_000);
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || "CV güncelleme üretilemedi.");
    }
    return response.json();
  } catch (error) {
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      throw new Error("Backend'e bağlanılamadı. Backend'in çalıştığından emin olun.");
    }
    throw error;
  }
}

export function rewritePdfUrl(result: CvRewriteResult): string | null {
  if (!result.pdf_available || !result.pdf_download_url) {
    return null;
  }
  return `${API_BASE_URL}${result.pdf_download_url}`;
}

export async function suggestJobTitles(formData: FormData): Promise<JobTitleSuggestionsResult | LlmTaskJob> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/job-title-suggestions`, {
    method: "POST",
    body: formData,
  }, 30_000);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "İş unvanı önerileri alınamadı.");
  }
  return response.json();
}

export async function suggestCvEdits(formData: FormData): Promise<CvEditSuggestionsResult | LlmTaskJob> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/cv-edit-suggestions`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || "CV düzenleme önerileri alınamadı.");
    }
    return response.json();
  } catch (error) {
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      throw new Error("Backend'e bağlanılamadı. Backend'in çalıştığından emin olun.");
    }
    throw error;
  }
}

export async function applyCvEdits(formData: FormData): Promise<CvEditApplyResult | LlmTaskJob> {
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/api/cv-apply-edits`, {
      method: "POST",
      body: formData,
    }, 30_000);
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || "CV düzenleme uygulanamadı.");
    }
    return response.json();
  } catch (error) {
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      throw new Error(backendUnreachableMessage());
    }
    throw error;
  }
}

export async function getApifyHealth(): Promise<Record<string, unknown>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/apify/health`);
    if (!response.ok) {
      if (response.status >= 500 || response.status === 502 || response.status === 503) {
        throw new Error(backendUnreachableMessage());
      }
      throw new Error("Apify durumu alınamadı.");
    }
    return response.json();
  } catch (error) {
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      throw new Error(backendUnreachableMessage());
    }
    throw error;
  }
}

export async function previewJobSearch(formData: FormData): Promise<JobSearchPreviewResult> {
  const response = await fetch(`${API_BASE_URL}/api/job-search/preview`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Apify önizlemesi alınamadı.");
  }
  return response.json();
}

export async function searchJobs(formData: FormData): Promise<JobSearchResult> {
  const response = await fetch(`${API_BASE_URL}/api/job-search`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "İlan araması başarısız oldu.");
  }
  return response.json();
}

export async function getSkillGaps(): Promise<SkillGapSummary> {
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/api/skill-gaps`);
    if (!response.ok) {
      if (response.status >= 500 || response.status === 502 || response.status === 503) {
        throw new Error(backendUnreachableMessage());
      }
      throw new Error("Yetenek önerileri alınamadı.");
    }
    return response.json();
  } catch (error) {
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      throw new Error(backendUnreachableMessage());
    }
    throw error;
  }
}

export async function clearSkillGaps(): Promise<void> {
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/api/skill-gaps`, { method: "DELETE" });
    if (!response.ok) {
      if (response.status >= 500 || response.status === 502 || response.status === 503) {
        throw new Error(backendUnreachableMessage());
      }
      throw new Error("Yetenek önerileri temizlenemedi.");
    }
  } catch (error) {
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      throw new Error(backendUnreachableMessage());
    }
    throw error;
  }
}

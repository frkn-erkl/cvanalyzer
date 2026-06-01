import type { AnalysisJob, CvRewriteRequest, CvRewriteResult, JobSearchPreviewResult, JobSearchResult, JobTitleSuggestionsResult, LlmProvider } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

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
  const response = await fetch(`${API_BASE_URL}/api/analysis/${id}`);
  if (!response.ok) {
    throw new Error("Analiz durumu alınamadı.");
  }
  return response.json();
}

export async function getLlmHealth(provider?: LlmProvider): Promise<Record<string, unknown>> {
  const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  const response = await fetch(`${API_BASE_URL}/api/llm/health${query}`);
  if (!response.ok) {
    throw new Error("LLM durumu alınamadı.");
  }
  return response.json();
}

export async function rewriteCv(analysisId: string, request: CvRewriteRequest): Promise<CvRewriteResult> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/analysis/${analysisId}/rewrite-cv`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || "CV güncelleme üretilemedi.");
    }
    return response.json();
  } catch (error) {
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      throw new Error("Backend'e bağlanılamadı veya istek CORS/timed out. Backend'in çalıştığından emin olun ve sayfayı yenileyin.");
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

export async function suggestJobTitles(formData: FormData): Promise<JobTitleSuggestionsResult> {
  const response = await fetch(`${API_BASE_URL}/api/job-title-suggestions`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "İş unvanı önerileri alınamadı.");
  }
  return response.json();
}

export async function getApifyHealth(): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE_URL}/api/apify/health`);
  if (!response.ok) {
    throw new Error("Apify durumu alınamadı.");
  }
  return response.json();
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

import { FormEvent, useState } from "react";
import { previewJobSearch, searchJobs } from "../api";
import type { JobSearchPreviewResult, JobSearchResult, LlmProvider } from "../types";
import LlmOptionToggle from "./LlmOptionToggle";
import LlmProviderSelect from "./LlmProviderSelect";

type CvMode = "text" | "file" | "url";

type Props = {
  llmProvider: LlmProvider;
  onLlmProviderChange: (provider: LlmProvider) => void;
  onAnalyzeJob?: (jobUrl: string) => void;
};

function sourceLabel(source: "linkedin" | "kariyer"): string {
  return source === "linkedin" ? "LinkedIn" : "Kariyer.net";
}

export default function JobSearchTab({ llmProvider, onLlmProviderChange, onAnalyzeJob }: Props) {
  const [cvMode, setCvMode] = useState<CvMode>("text");
  const [useApify, setUseApify] = useState(false);
  const [useLlm, setUseLlm] = useState(false);
  const [searchLinkedIn, setSearchLinkedIn] = useState(true);
  const [searchKariyer, setSearchKariyer] = useState(true);
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<JobSearchPreviewResult | null>(null);
  const [pendingSearch, setPendingSearch] = useState<FormData | null>(null);
  const [result, setResult] = useState<JobSearchResult | null>(null);

  function buildFormData(form: HTMLFormElement): FormData {
    const data = new FormData(form);
    data.set("use_apify", useApify ? "true" : "false");
    data.set("use_llm", useLlm ? "true" : "false");
    data.set("llm_provider", llmProvider);

    const sources: string[] = [];
    if (searchLinkedIn) {
      sources.push("linkedin");
    }
    if (searchKariyer) {
      sources.push("kariyer");
    }
    data.set("sources", sources.length > 0 ? sources.join(",") : "linkedin,kariyer");

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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = buildFormData(form);

    setBusy(true);
    setError(null);
    setResult(null);

    try {
      if (useApify) {
        const previewResult = await previewJobSearch(data);
        setPreview(previewResult);
        setPendingSearch(data);
      } else {
        setPreview(null);
        setPendingSearch(null);
        const response = await searchJobs(data);
        setResult(response);
      }
    } catch (submitError) {
      setPreview(null);
      setPendingSearch(null);
      setResult(null);
      setError(submitError instanceof Error ? submitError.message : "İlan araması başarısız oldu.");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirmApifySearch() {
    if (!pendingSearch) {
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const response = await searchJobs(pendingSearch);
      setResult(response);
      setPreview(null);
      setPendingSearch(null);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Apify ilan araması başarısız oldu.");
    } finally {
      setBusy(false);
    }
  }

  function handleCancelPreview() {
    setPreview(null);
    setPendingSearch(null);
  }

  return (
    <div className="job-search-tab">
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

        <section>
          <div className="section-title">
            <h2>Arama</h2>
            <label className="checkbox-inline">
              <input checked={useApify} disabled={busy} onChange={(event) => setUseApify(event.target.checked)} type="checkbox" />
              Apify ile ara
            </label>
          </div>
          <div className="rewrite-controls">
            <label>
              Konum (opsiyonel)
              <input
                name="location"
                onChange={(event) => setLocation(event.target.value)}
                placeholder="İstanbul, Remote..."
                type="text"
                value={location}
              />
            </label>
          </div>
          <div className="checkbox-group">
            <label>
              <input checked={searchLinkedIn} disabled={busy} onChange={(event) => setSearchLinkedIn(event.target.checked)} type="checkbox" />
              LinkedIn
            </label>
            <label>
              <input checked={searchKariyer} disabled={busy} onChange={(event) => setSearchKariyer(event.target.checked)} type="checkbox" />
              Kariyer.net
            </label>
          </div>
          <p className="hint">
            Apify açıkken önce gönderilecek sorgular ve actor input&apos;ları listelenir; onayladıktan sonra arama başlar.
          </p>
        </section>

        <button className="primary" disabled={busy} type="submit">
          {busy ? "Hazırlanıyor..." : useApify ? "Apify gönderimini önizle" : "İlan ara"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {preview && (
        <section className="results job-search-preview">
          <article className="panel">
            <h2>Apify&apos;ye Gönderilecekler</h2>
            <p className="hint">
              Kaynak başına en fazla {preview.max_results_per_source} ilan istenecek
              {preview.location ? ` · Konum: ${preview.location}` : ""}.
            </p>

            {preview.title_suggestions.length > 0 && (
              <div className="skill-group">
                <h3>CV&apos;den üretilen unvan ipuçları</h3>
                <div className="chips">
                  {preview.title_suggestions.map((title) => (
                    <span className="chip" key={title}>
                      {title}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {preview.cv_skills.length > 0 && (
              <div className="skill-group">
                <h3>CV becerileri (sorguya eklenen)</h3>
                <div className="chips">
                  {preview.cv_skills.map((skill) => (
                    <span className="chip ok" key={skill}>
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="skill-group">
              <h3>Birleştirilmiş arama sorguları</h3>
              <div className="chips">
                {preview.search_queries.map((query) => (
                  <span className="chip" key={query}>
                    {query}
                  </span>
                ))}
              </div>
            </div>

            {preview.apify_actors.map((actor) => (
              <div className="skill-group" key={actor.source}>
                <h3>
                  {sourceLabel(actor.source)} actor
                  {!actor.configured && <span className="warn"> · yapılandırılmamış</span>}
                </h3>
                <p className="hint">Actor ID: {actor.actor_id}</p>
                <pre className="apify-payload">{JSON.stringify(actor.run_input, null, 2)}</pre>
              </div>
            ))}

            {preview.warnings.length > 0 && (
              <ul className="score-factors">
                {preview.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            )}

            <div className="job-search-actions">
              <button className="primary" disabled={busy || !preview.apify_ready} onClick={handleConfirmApifySearch} type="button">
                {busy ? "Apify aranıyor..." : "Apify aramasını başlat"}
              </button>
              <button className="secondary" disabled={busy} onClick={handleCancelPreview} type="button">
                İptal
              </button>
            </div>
          </article>
        </section>
      )}

      {result && (
        <section className="results job-search-results">
          <article className="panel">
            <h2>Uygun İlanlar</h2>
            {result.search_queries.length > 0 && (
              <div className="skill-group">
                <h3>Arama sorguları</h3>
                <div className="chips">
                  {result.search_queries.map((query) => (
                    <span className="chip" key={query}>
                      {query}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {result.listings.length === 0 ? (
              <p className="hint">Sonuç bulunamadı veya Apify devre dışı.</p>
            ) : (
              <div className="job-title-list">
                {result.listings.map((listing) => (
                  <article className="job-title-card" key={`${listing.source}-${listing.url}`}>
                    <div className="job-title-card-header">
                      <div>
                        <h3>{listing.title}</h3>
                        <p className="hint">
                          {listing.company ?? "Şirket belirtilmemiş"}
                          {listing.location ? ` · ${listing.location}` : ""}
                          {" · "}
                          {sourceLabel(listing.source)}
                        </p>
                        <span className="fit-score">Uyum: {listing.fit_score}/100</span>
                      </div>
                      <div className="job-search-actions">
                        <a className="secondary" href={listing.url} rel="noreferrer" target="_blank">
                          İlana git
                        </a>
                        {onAnalyzeJob && (
                          <button className="primary" onClick={() => onAnalyzeJob(listing.url)} type="button">
                            Bu ilanı analiz et
                          </button>
                        )}
                      </div>
                    </div>
                    {listing.matched_skills.length > 0 && (
                      <SkillChipGroup
                        skills={listing.matched_skills}
                        title="Eşleşen yetenekler"
                        tone="ok"
                        url={listing.url}
                      />
                    )}
                    {listing.missing_required_skills.length > 0 && (
                      <SkillChipGroup
                        skills={listing.missing_required_skills}
                        title="Eksik zorunlu yetenekler"
                        tone="danger"
                        url={listing.url}
                      />
                    )}
                    {listing.missing_preferred_skills.length > 0 && (
                      <SkillChipGroup
                        skills={listing.missing_preferred_skills}
                        title="Eksik tercih edilen yetenekler"
                        tone="warn"
                        url={listing.url}
                      />
                    )}
                    {listing.description_preview && <p>{listing.description_preview}</p>}
                  </article>
                ))}
              </div>
            )}

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

function SkillChipGroup({
  skills,
  title,
  tone,
  url,
}: {
  skills: string[];
  title: string;
  tone: "ok" | "warn" | "danger";
  url: string;
}) {
  return (
    <div className="skill-chip-group">
      <span className="skill-chip-title">{title}</span>
      <div className="chips">
        {skills.map((skill) => (
          <span className={`chip ${tone}`} key={`${url}-${title}-${skill}`}>
            {skill}
          </span>
        ))}
      </div>
    </div>
  );
}

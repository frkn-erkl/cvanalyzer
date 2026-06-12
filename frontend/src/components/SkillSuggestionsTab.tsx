import { useCallback, useEffect, useState } from "react";
import { clearSkillGaps, getSkillGaps } from "../api";
import type { SkillGapAggregate, SkillGapSource } from "../types";
import SectionHeading from "./SectionHeading";

function sourceLabel(source: SkillGapSource): string {
  if (source === "job_search") {
    return "İlan Arama";
  }
  if (source === "llm_analysis") {
    return "LLM Analizi";
  }
  return "Uyum Analizi";
}

function SkillGapSection({
  title,
  hint,
  items,
  tone,
}: {
  title: string;
  hint: string;
  items: SkillGapAggregate[];
  tone: "danger" | "warn";
}) {
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);

  if (items.length === 0) {
    return null;
  }

  return (
    <article className="panel skill-gap-section">
      <SectionHeading hint={hint} title={title} />
      <div className="skill-gap-list">
        {items.map((item) => {
          const key = `${item.gap_type}-${item.skill_name}`;
          const expanded = expandedSkill === key;
          return (
            <div className="skill-gap-row" key={key}>
              <button
                className="skill-gap-row-header"
                onClick={() => setExpandedSkill(expanded ? null : key)}
                type="button"
              >
                <div>
                  <strong>{item.skill_name}</strong>
                  <span className={`chip ${tone}`}>{item.listing_count} ilanda eksik</span>
                </div>
                <span className="skill-gap-toggle">{expanded ? "Gizle" : "İlanları göster"}</span>
              </button>
              {expanded && (
                <ul className="skill-gap-listings">
                  {item.listings.map((listing) => (
                    <li key={`${item.skill_name}-${listing.job_key}`}>
                      <div>
                        <strong>{listing.job_title}</strong>
                        {listing.company && <span className="hint"> · {listing.company}</span>}
                        <span className="chip">{sourceLabel(listing.source)}</span>
                      </div>
                      {listing.job_url && (
                        <a href={listing.job_url} rel="noreferrer" target="_blank">
                          İlana git
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </article>
  );
}

export default function SkillSuggestionsTab() {
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof getSkillGaps>> | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSummary = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const response = await getSkillGaps();
      setSummary(response);
    } catch (loadError) {
      setSummary(null);
      setError(loadError instanceof Error ? loadError.message : "Yetenek önerileri yüklenemedi.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  async function handleClear() {
    setBusy(true);
    setError(null);
    try {
      await clearSkillGaps();
      await loadSummary();
    } catch (clearError) {
      setError(clearError instanceof Error ? clearError.message : "Liste temizlenemedi.");
      setBusy(false);
    }
  }

  const required = summary?.aggregates.filter((item) => item.gap_type === "required") ?? [];
  const preferred = summary?.aggregates.filter((item) => item.gap_type === "preferred") ?? [];

  return (
    <div className="skill-suggestions-tab">
      <section className="panel skill-gap-toolbar">
        <div>
          <h2>Yetenek Önerileri</h2>
          <p className="hint">
            İlan Arama, Uyum Analizi ve LLM Analizi sonuçlarından biriken eksik yetenekler. Aynı ilan tekrar
            taranırsa sayaç artmaz; kayıt güncellenir.
          </p>
        </div>
        <div className="job-search-actions">
          <button className="secondary" disabled={busy} onClick={() => void loadSummary()} type="button">
            Yenile
          </button>
          <button className="secondary" disabled={busy || !summary?.total_skills} onClick={() => void handleClear()} type="button">
            Listeyi temizle
          </button>
        </div>
      </section>

      {busy && !summary && <p className="hint">Yetenek önerileri yükleniyor...</p>}
      {error && <p className="error">{error}</p>}

      {summary && summary.total_skills === 0 && !busy && (
        <article className="panel">
          <p className="hint">
            Henüz taranan ilan yok. İlan Arama veya Uyum Analizi yapın; eksik yetenekler burada toplanır.
          </p>
        </article>
      )}

      {summary && summary.total_skills > 0 && (
        <section className="results skill-gap-results">
          <p className="hint">
            {summary.total_listings} farklı ilan tarandı · {summary.total_skills} eksik yetenek kaydı
          </p>
          <SkillGapSection
            hint="Birden fazla ilanda tekrar eden zorunlu beceri açıkları."
            items={required}
            title="Zorunlu eksik yetenekler"
            tone="danger"
          />
          <SkillGapSection
            hint="Tercih edilen beceriler; birden fazla ilanda görülüyorsa önceliklendirin."
            items={preferred}
            title="Tercih edilen eksik yetenekler"
            tone="warn"
          />
        </section>
      )}
    </div>
  );
}

import { useState } from "react";
import { rewriteCv, rewritePdfUrl } from "../api";
import type { CvRewriteRequest, CvRewriteResult, LlmProvider } from "../types";
import LatexPreview from "./LatexPreview";
import LlmOptionToggle from "./LlmOptionToggle";
import OutputSourceBadge, { rewriteOutputSource } from "./OutputSourceBadge";
import SectionHeading from "./SectionHeading";

type Props = {
  analysisId: string;
  llmProvider: LlmProvider;
};

export default function CvRewritePanel({ analysisId, llmProvider }: Props) {
  const [tone, setTone] = useState<CvRewriteRequest["tone"]>("professional_ats");
  const [language, setLanguage] = useState<CvRewriteRequest["language"]>("en");
  const [deepRewrite, setDeepRewrite] = useState(true);
  const [preserveLatex, setPreserveLatex] = useState(true);
  const [compilePdf, setCompilePdf] = useState(true);
  const [result, setResult] = useState<CvRewriteResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleRewrite() {
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      const response = await rewriteCv(analysisId, {
        tone,
        language,
        deep_rewrite: deepRewrite,
        output_format: preserveLatex ? "auto" : "text",
        compile_pdf: compilePdf,
        llm_provider: llmProvider,
      });
      setResult(response);
    } catch (rewriteError) {
      setError(rewriteError instanceof Error ? rewriteError.message : "CV güncelleme üretilemedi.");
    } finally {
      setBusy(false);
    }
  }

  async function copyToClipboard() {
    if (!result?.updated_cv_text) {
      return;
    }
    await navigator.clipboard.writeText(result.updated_cv_text);
    setCopied(true);
  }

  async function copyLatexToClipboard() {
    if (!result?.updated_latex_text) {
      return;
    }
    await navigator.clipboard.writeText(result.updated_latex_text);
    setCopied(true);
  }

  const pdfUrl = result ? rewritePdfUrl(result) : null;
  const rewriteSource = result
    ? rewriteOutputSource(result.llm_requested ?? deepRewrite, result.used_llm)
    : undefined;

  return (
    <article className="panel rewrite-panel">
      <SectionHeading
        actions={<LlmOptionToggle checked={deepRewrite} disabled={busy} onChange={setDeepRewrite} />}
        hint="Sadece CV'de kanıtlanan bilgileri daha hedefli ifade eder; eksik becerileri CV'ye eklemez."
        source={rewriteSource}
        title="İlana Göre Gerçekçi CV Güncelleme"
      />

      <div className="rewrite-controls">
        <label>
          CV güncelleme stili
          <select value={tone} onChange={(event) => setTone(event.target.value as CvRewriteRequest["tone"])}>
            <option value="professional_ats">Profesyonel + ATS uyumlu</option>
            <option value="concise_professional_ats">Profesyonel + ATS uyumlu + kısa/net</option>
          </select>
        </label>
        <label>
          CV dili
          <select value={language} onChange={(event) => setLanguage(event.target.value as CvRewriteRequest["language"])}>
            <option value="en">English</option>
            <option value="tr">Türkçe</option>
          </select>
        </label>
        <label className="checkbox">
          <input checked={preserveLatex} onChange={(event) => setPreserveLatex(event.target.checked)} type="checkbox" />
          LaTeX formatını koru
        </label>
        <label className="checkbox">
          <input checked={compilePdf} onChange={(event) => setCompilePdf(event.target.checked)} type="checkbox" />
          PDF üretmeyi dene
        </label>
        <button className="primary" disabled={busy} onClick={handleRewrite} type="button">
          {busy ? "CV güncelleniyor..." : "Bu ilana göre CV'yi güncelle"}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {result && (
        <div className="rewrite-result">
          <div className="rewrite-result-header">
            <div className="section-heading-row">
              <h3>Güncellenmiş CV Metni</h3>
              {rewriteSource && <OutputSourceBadge source={rewriteSource} />}
            </div>
            <button className="secondary" onClick={copyToClipboard} type="button">
              {copied ? "Kopyalandı" : "Metni kopyala"}
            </button>
          </div>
          <textarea readOnly rows={18} value={result.updated_cv_text} />

          <LatexPreview
            compileWarnings={result.compile_warnings}
            formatPreserved={result.format_preserved}
            latexText={result.updated_latex_text}
            pdfUrl={pdfUrl}
            plainTextFallback={result.updated_cv_text}
          />

          {result.updated_latex_text && (
            <>
              <div className="rewrite-result-header">
                <h3>LaTeX Kaynak Metni</h3>
                <button className="secondary" onClick={copyLatexToClipboard} type="button">
                  {copied ? "Kopyalandı" : "LaTeX'i kopyala"}
                </button>
              </div>
              <textarea readOnly rows={18} value={result.updated_latex_text} />
            </>
          )}

          <div className="rewrite-actions">
            {pdfUrl ? (
              <a className="secondary link-button" href={pdfUrl} rel="noreferrer" target="_blank">
                PDF indir
              </a>
            ) : (
              <span className="hint">PDF çıktısı hazır değil. LaTeX motoru yoksa yalnızca kaynak metin verilir.</span>
            )}
            <span className="hint">
              {result.format_preserved ? "Orijinal LaTeX formatı korunmaya çalışıldı." : "Orijinal CV LaTeX değil; format birebir korunamadı."}
            </span>
          </div>

          <DetailList title="Yapılan Değişiklikler" items={result.changes.map((change) => `${change.section}: ${change.reason}`)} />
          <DetailList title="Korunan Gerçek Bilgiler" items={result.preserved_items} />
          <DetailList title="CV'ye Eklenmeyen Eksik Beceriler" items={result.omitted_missing_skills} />
          <DetailList title="Uyarılar" items={[...result.warnings, ...result.compile_warnings, ...result.unsupported_claims.map((claim) => `${claim.claim}: ${claim.reason}`)]} />
        </div>
      )}
    </article>
  );
}

function DetailList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <section className="rewrite-detail">
      <h3>{title}</h3>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

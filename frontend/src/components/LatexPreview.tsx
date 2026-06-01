type Props = {
  pdfUrl: string | null;
  latexText?: string | null;
  plainTextFallback?: string | null;
  compileWarnings: string[];
  formatPreserved: boolean;
};

export default function LatexPreview({
  pdfUrl,
  latexText,
  plainTextFallback,
  compileWarnings,
  formatPreserved,
}: Props) {
  const hasLatexFallback = !pdfUrl && Boolean(latexText);
  const hasPlainFallback = !pdfUrl && !latexText && Boolean(plainTextFallback);

  return (
    <article className="preview-panel">
      <div className="rewrite-result-header">
        <div>
          <h3>CV Önizleme</h3>
          <p className="hint">
            {pdfUrl
              ? "PDF çıktısı aşağıda tarayıcı içinde önizleniyor."
              : hasLatexFallback
                ? "PDF üretilemedi veya hazır değil; LaTeX kaynak önizlemesi gösteriliyor."
                : hasPlainFallback
                  ? "LaTeX kaynak veya PDF yok; güncellenmiş CV metni önizlemesi gösteriliyor."
                  : "PDF üretilemedi veya hazır değil; LaTeX kaynak önizlemesi gösteriliyor."}
          </p>
        </div>
        {pdfUrl && (
          <a className="secondary link-button" href={pdfUrl} rel="noreferrer" target="_blank">
            PDF indir
          </a>
        )}
      </div>

      {compileWarnings.length > 0 && (
        <div className="preview-warning">
          <strong>PDF/LaTeX uyarıları</strong>
          <ul>
            {compileWarnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="hint">
        {formatPreserved
          ? "Orijinal LaTeX formatı korunmaya çalışıldı."
          : "Orijinal CV LaTeX kaynak olmadığı için format birebir korunamadı."}
      </p>

      {pdfUrl ? (
        <object className="preview-frame" data={pdfUrl} type="application/pdf">
          <iframe className="preview-frame" src={pdfUrl} title="CV PDF önizleme" />
          <p>
            Tarayıcınız PDF önizlemeyi engelledi.{" "}
            <a href={pdfUrl} rel="noreferrer" target="_blank">
              PDF'i yeni sekmede açın.
            </a>
          </p>
        </object>
      ) : hasLatexFallback ? (
        <pre className="latex-preview-frame">{latexText}</pre>
      ) : hasPlainFallback ? (
        <pre className="plain-preview-frame">{plainTextFallback}</pre>
      ) : (
        <div className="preview-empty">Önizleme için PDF veya LaTeX kaynak metni yok.</div>
      )}
    </article>
  );
}

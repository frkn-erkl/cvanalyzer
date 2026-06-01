type Props = {
  status?: string;
  error?: string | null;
  llmHealth?: Record<string, unknown> | null;
  apifyHealth?: Record<string, unknown> | null;
  llmProvider?: "local" | "cursor";
  mode?: "hybrid" | "llm-only" | "job-titles" | "job-search";
  showApify?: boolean;
};

export default function StatusPanel({
  status,
  error,
  llmHealth,
  apifyHealth,
  llmProvider = "local",
  mode = "hybrid",
  showApify = false,
}: Props) {
  const llmAvailable = llmHealth?.available === true;
  const missingModels = Array.isArray(llmHealth?.missing_models)
    ? llmHealth.missing_models.filter((item): item is string => typeof item === "string")
    : [];
  const missingEmbedding = missingModels.filter((model) => model !== llmHealth?.model);
  const providerLabel = llmProvider === "cursor" ? "Cursor API" : "Yerel LLM";
  const cursorBaseUrl = typeof llmHealth?.base_url === "string" ? llmHealth.base_url : null;
  const cursorKeyConfigured = llmHealth?.key_configured === true;
  const apifyAvailable = apifyHealth?.available === true;
  const apifyKeyConfigured = apifyHealth?.key_configured === true;

  return (
    <aside className="panel status">
      <h2>Sistem Durumu</h2>
      <p>
        Analiz: <strong>{status ?? "hazır"}</strong>
      </p>
      <p>
        Seçili sağlayıcı: <strong>{providerLabel}</strong>
      </p>
      <p>
        {providerLabel}: <strong className={llmAvailable ? "ok" : "warn"}>{llmAvailable ? "bağlı" : "bağlı değil"}</strong>
      </p>
      {llmProvider === "cursor" && cursorBaseUrl && (
        <p>
          Proxy adresi: <strong>{cursorBaseUrl}</strong>
        </p>
      )}
      {llmProvider === "cursor" && (
        <p>
          API key: <strong className={cursorKeyConfigured ? "ok" : "warn"}>{cursorKeyConfigured ? "tanımlı" : "tanımlı değil"}</strong>
        </p>
      )}
      {typeof llmHealth?.model === "string" && <p>LLM modeli: {llmHealth.model}</p>}
      {llmProvider === "local" && typeof llmHealth?.embedding_model === "string" && (
        <p>
          Embedding modeli:{" "}
          <strong className={llmHealth.embedding_available === true ? "ok" : "warn"}>
            {llmHealth.embedding_model}
            {llmHealth.embedding_available === true ? " (yüklü)" : " (yüklü değil)"}
          </strong>
        </p>
      )}
      {llmProvider === "local" && llmAvailable && missingEmbedding.length > 0 && (
        <p className="hint">Embedding modeli yok ({missingEmbedding.join(", ")}); domain skoru anahtar kelime fallback kullanır.</p>
      )}
      {llmProvider === "local" && !llmAvailable && missingModels.length > 0 && (
        <p className="warn">Eksik model: {missingModels.join(", ")}</p>
      )}
      {typeof llmHealth?.error === "string" && !llmAvailable && (
        <p className="hint">{llmHealth.error}</p>
      )}
      {typeof llmHealth?.warning === "string" && (
        <p className="hint">{llmHealth.warning}</p>
      )}
      {showApify && (
        <>
          <p>
            Apify:{" "}
            <strong className={apifyAvailable ? "ok" : "warn"}>{apifyAvailable ? "bağlı" : "bağlı değil"}</strong>
          </p>
          <p>
            Apify token:{" "}
            <strong className={apifyKeyConfigured ? "ok" : "warn"}>{apifyKeyConfigured ? "tanımlı" : "tanımlı değil"}</strong>
          </p>
          {typeof apifyHealth?.error === "string" && !apifyAvailable && <p className="hint">{apifyHealth.error}</p>}
          {!apifyKeyConfigured && (
            <p className="hint">
              `backend/.env` dosyasına <code>APIFY_API_TOKEN=...</code>, <code>APIFY_ENABLED=true</code> ve actor ID&apos;lerini ekleyin.
            </p>
          )}
        </>
      )}
      {llmProvider === "cursor" && !cursorKeyConfigured && (
        <p className="hint">
          `backend/.env` dosyasına <code>CURSOR_API_KEY=...</code> ekleyin ve backend&apos;i yeniden başlatın.
        </p>
      )}
      {llmProvider === "cursor" && !llmAvailable && (
        <p className="hint">Cursor proxy&apos;yi başlatın, `backend/.env` içindeki ayarları kontrol edin veya Local LLM seçin.</p>
      )}
      {mode !== "job-titles" && llmProvider === "local" && (
        <p className="hint">LLM girdileri gerektiğinde otomatik olarak İngilizceye normalize edilir.</p>
      )}
      {error && <p className="error">{error}</p>}
      {mode === "llm-only" ? (
        <p className="hint">
          LLM Analizi sekmesinde skor, öneri ve yorumların tamamı seçilen LLM sağlayıcısı ile üretilir. Sağlayıcı kapalıysa analiz tamamlanmaz.
          Büyük CV/ilan metinlerinde analiz birkaç dakika sürebilir.
        </p>
      ) : mode === "hybrid" ? (
        <p className="hint">
          Uyum Analizi sekmesinde yerel LLM kapalıysa skor ve öneriler deterministik motorla yine üretilir.
        </p>
      ) : mode === "job-search" ? (
        <p className="hint">
          İlan Arama sekmesinde Apify açıkken LinkedIn ve Kariyer.net actor&apos;ları ile ilan toplanır; kapalıyken yalnızca arama sorguları üretilir.
        </p>
      ) : mode === "job-titles" ? (
        <p className="hint">İş unvanı önerileri LLM açıkken seçilen sağlayıcıdan, kapalıyken deterministik kurallardan üretilir.</p>
      ) : null}
    </aside>
  );
}

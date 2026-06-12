import { useEffect, useRef } from "react";
import type { LlmAnalysisProgress } from "../types";

type Props = {
  progress?: LlmAnalysisProgress | null;
  storedThinking?: string | null;
  live?: boolean;
  waiting?: boolean;
  waitingMessage?: string;
};

export default function LlmThinkingPanel({
  progress,
  storedThinking,
  live = false,
  waiting = false,
  waitingMessage = "CV ve iş ilanı hazırlanıyor; model kısa süre içinde düşünmeye başlayacak.",
}: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const thinking = (live ? progress?.thinking : storedThinking ?? progress?.thinking)?.trim() ?? "";
  const response = live ? progress?.response?.trim() ?? "" : "";
  const phase = progress?.phase ?? "thinking";

  useEffect(() => {
    if (!live || !bodyRef.current) {
      return;
    }
    bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [live, thinking, response]);

  if (!thinking && !response && !waiting) {
    return null;
  }

  return (
    <article className={`panel llm-thinking ${live ? "live" : ""}`}>
      <div className="llm-thinking-header">
        <h2>LLM Düşünme Süreci</h2>
        {live && (
          <span className={`llm-thinking-phase ${waiting && !thinking && !response ? "waiting" : phase}`}>
            {waiting && !thinking && !response
              ? "Hazırlanıyor"
              : phase === "responding"
                ? "Yanıt üretiliyor"
                : "Düşünüyor"}
          </span>
        )}
      </div>
      <div className="llm-thinking-body" ref={bodyRef}>
        {thinking && (
          <>
            {live && response && <p className="llm-thinking-section-label">Düşünme</p>}
            <pre>{thinking}</pre>
          </>
        )}
        {!thinking && !response && waiting && (
          <p className="llm-thinking-waiting">{waitingMessage}</p>
        )}
        {live && response && (
          <>
            <p className="llm-thinking-section-label">JSON yanıtı</p>
            <pre className="llm-thinking-response">{response}</pre>
          </>
        )}
      </div>
      {live && phase === "thinking" && thinking && (
        <p className="hint llm-thinking-hint">
          Düşünme metni bir süre sonra durabilir; model ardından JSON yanıtını üretmeye geçer.
        </p>
      )}
      {live && phase === "responding" && (
        <p className="hint llm-thinking-hint">Model analiz JSON&apos;unu yazıyor; bu aşama birkaç dakika sürebilir.</p>
      )}
    </article>
  );
}

export function thinkingFromMetadata(metadata: Record<string, unknown> | undefined): string | null {
  const value = metadata?.llm_thinking;
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

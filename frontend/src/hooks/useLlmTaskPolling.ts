import { useEffect, useRef } from "react";
import { getLlmTask } from "../api";
import type { LlmAnalysisProgress, LlmProvider, LlmTaskJob } from "../types";

export function supportsLiveLocalThinking(provider: LlmProvider, llmRequested: boolean): boolean {
  return llmRequested && provider === "local";
}

export function isLlmTaskJob(value: unknown): value is LlmTaskJob {
  return (
    typeof value === "object" &&
    value !== null &&
    "kind" in value &&
    "status" in value &&
    typeof (value as LlmTaskJob).id === "string"
  );
}

type TaskHandlers = {
  onUpdate: (task: LlmTaskJob) => void;
  onFailed: (message: string) => void;
  onComplete: (task: LlmTaskJob) => void;
};

const MAX_CONSECUTIVE_POLL_FAILURES = 20;

export function useLlmTaskPolling(
  taskId: string | null | undefined,
  busy: boolean,
  handlers: TaskHandlers,
) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    if (!taskId || !busy) {
      return;
    }
    let cancelled = false;
    let consecutiveFailures = 0;

    async function poll() {
      try {
        const next = await getLlmTask(taskId!);
        if (cancelled) {
          return;
        }
        consecutiveFailures = 0;
        handlersRef.current.onUpdate(next);
        if (next.status === "failed") {
          handlersRef.current.onFailed(next.error ?? "LLM görevi başarısız oldu.");
        }
        if (next.status === "completed") {
          handlersRef.current.onComplete(next);
        }
      } catch (pollError) {
        if (cancelled) {
          return;
        }
        consecutiveFailures += 1;
        if (consecutiveFailures >= MAX_CONSECUTIVE_POLL_FAILURES) {
          handlersRef.current.onFailed(
            pollError instanceof Error ? pollError.message : "LLM görev durumu alınamadı.",
          );
        }
      }
    }

    void poll();
    const handle = window.setInterval(() => {
      void poll();
    }, 800);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [taskId, busy]);
}

export function hasThinkingContent(progress?: LlmAnalysisProgress | null): boolean {
  return Boolean(progress?.thinking?.trim() || progress?.response?.trim());
}

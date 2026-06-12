from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from app import db

LlmProgressCallback = Callable[[str, str], None]

_THROTTLE_SECONDS = 0.35


def _save_progress(
    *,
    update: Callable[[dict[str, Any]], None],
    last_saved_at: float,
    last_thinking: str,
    last_response: str,
    thinking: str,
    response: str,
) -> tuple[float, str, str]:
    thinking = thinking.strip()
    response = response.strip()
    if thinking == last_thinking and response == last_response:
        return last_saved_at, last_thinking, last_response

    now = time.monotonic()
    is_final = bool(response)
    if not is_final and now - last_saved_at < _THROTTLE_SECONDS:
        return last_saved_at, last_thinking, last_response

    phase = "responding" if response else "thinking"
    update(
        {
            "thinking": thinking,
            "response": response,
            "phase": phase,
        }
    )
    return now, thinking, response


def analysis_progress_callback(analysis_id: str) -> LlmProgressCallback:
    last_saved_at = 0.0
    last_thinking = ""
    last_response = ""

    def on_progress(thinking: str, response: str) -> None:
        nonlocal last_saved_at, last_thinking, last_response
        last_saved_at, last_thinking, last_response = _save_progress(
            update=lambda progress: db.update_analysis_progress(analysis_id, progress),
            last_saved_at=last_saved_at,
            last_thinking=last_thinking,
            last_response=last_response,
            thinking=thinking,
            response=response,
        )

    return on_progress


def llm_task_progress_callback(task_id: str) -> LlmProgressCallback:
    last_saved_at = 0.0
    last_thinking = ""
    last_response = ""

    def on_progress(thinking: str, response: str) -> None:
        nonlocal last_saved_at, last_thinking, last_response
        last_saved_at, last_thinking, last_response = _save_progress(
            update=lambda progress: db.update_llm_task_progress(task_id, progress),
            last_saved_at=last_saved_at,
            last_thinking=last_thinking,
            last_response=last_response,
            thinking=thinking,
            response=response,
        )

    return on_progress


def merge_thinking_metadata(metadata: dict[str, Any], thinking: str | None) -> dict[str, Any]:
    if thinking and thinking.strip():
        metadata["llm_thinking"] = thinking.strip()
    return metadata


def set_llm_task_status_message(task_id: str, message: str) -> None:
    db.update_llm_task_progress(
        task_id,
        {
            "thinking": message.strip(),
            "response": "",
            "phase": "thinking",
        },
    )


def progress_callback_for_provider(
    provider: str,
    *,
    analysis_id: str | None = None,
    task_id: str | None = None,
) -> LlmProgressCallback | None:
    if provider != "local":
        return None
    if analysis_id:
        return analysis_progress_callback(analysis_id)
    if task_id:
        return llm_task_progress_callback(task_id)
    return None

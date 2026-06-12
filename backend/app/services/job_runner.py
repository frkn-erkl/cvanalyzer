from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cv-analysis")
T = TypeVar("T")


def _run_coro_in_thread(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def schedule_analysis_job(coro: Coroutine[Any, Any, Any]) -> None:
    """Run a long analysis coroutine off the API event loop so /health stays responsive."""
    _executor.submit(_run_coro_in_thread, coro)


def shutdown_job_runner() -> None:
    _executor.shutdown(wait=False, cancel_futures=True)

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.config import get_settings

APIFY_BASE_URL = "https://api.apify.com/v2"


class ApifyError(Exception):
    pass


class ApifyClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def token(self) -> str:
        return self.settings.apify_api_token.strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _actor_path(self, actor_id: str) -> str:
        return quote(actor_id.replace("/", "~"), safe="~")

    async def run_actor(self, actor_id: str, run_input: dict[str, Any]) -> list[dict[str, Any]]:
        if not actor_id.strip():
            raise ApifyError("Apify actor ID yapılandırılmamış.")
        if not self.is_configured:
            raise ApifyError("APIFY_API_TOKEN tanımlı değil.")

        timeout = self.settings.apify_timeout_seconds
        async with httpx.AsyncClient(timeout=30) as client:
            start = await client.post(
                f"{APIFY_BASE_URL}/acts/{self._actor_path(actor_id)}/runs",
                headers=self._headers(),
                json=run_input,
            )
            start.raise_for_status()
            run_data = start.json().get("data", {})
            run_id = run_data.get("id")
            if not isinstance(run_id, str):
                raise ApifyError("Apify run başlatılamadı.")

            deadline = time.monotonic() + timeout
            dataset_id: str | None = None
            while time.monotonic() < deadline:
                status_response = await client.get(
                    f"{APIFY_BASE_URL}/actor-runs/{run_id}",
                    headers=self._headers(),
                )
                status_response.raise_for_status()
                status_data = status_response.json().get("data", {})
                status = str(status_data.get("status", "")).upper()
                if status == "SUCCEEDED":
                    dataset_id = status_data.get("defaultDatasetId")
                    break
                if status in {"FAILED", "ABORTED", "TIMED-OUT"}:
                    raise ApifyError(f"Apify actor run başarısız: {status}")
                await asyncio.sleep(2)

            if not isinstance(dataset_id, str):
                raise ApifyError("Apify actor run zaman aşımına uğradı.")

            items: list[dict[str, Any]] = []
            offset = 0
            page_size = 250
            while True:
                items_response = await client.get(
                    f"{APIFY_BASE_URL}/datasets/{dataset_id}/items",
                    headers=self._headers(),
                    params={
                        "clean": "true",
                        "format": "json",
                        "offset": offset,
                        "limit": page_size,
                    },
                )
                items_response.raise_for_status()
                payload = items_response.json()
                if not isinstance(payload, list):
                    break
                batch = [item for item in payload if isinstance(item, dict)]
                items.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
            return items

    async def health(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "provider": "apify",
            "configured": True,
            "key_configured": self.is_configured,
            "available": False,
            "linkedin_search_actor": bool(self.settings.apify_linkedin_search_actor_id.strip()),
            "linkedin_job_actor": bool(self.settings.apify_linkedin_job_actor_id.strip()),
            "kariyer_search_actor": bool(self.settings.apify_kariyer_search_actor_id.strip()),
            "kariyer_job_actor": bool(self.settings.apify_kariyer_job_actor_id.strip()),
        }
        if not self.is_configured:
            result["error"] = "APIFY_API_TOKEN tanımlı değil."
            return result
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{APIFY_BASE_URL}/users/me", headers=self._headers())
                response.raise_for_status()
            result["available"] = True
            return result
        except Exception:  # noqa: BLE001
            result["error"] = "Apify API'ye bağlanılamadı."
            return result


async def apify_health() -> dict[str, Any]:
    return await ApifyClient().health()

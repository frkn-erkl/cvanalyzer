import math
from typing import Any, Protocol

import httpx
import numpy as np

from app.config import LlmProvider, get_settings, normalize_llm_provider
from app.services.language import ensure_english_for_llm


def _model_installed(configured: str, installed_names: list[str]) -> bool:
    return any(
        name == configured or name.startswith(f"{configured}:")
        for name in installed_names
    )


class LlmClient(Protocol):
    async def health(self) -> dict[str, Any]: ...

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        num_predict: int | None = None,
        num_ctx: int | None = None,
        max_chars: int | None = None,
        translate_input: bool = True,
        timeout_seconds: float | None = None,
    ) -> str | None: ...


class LocalLLM:
    provider: LlmProvider = "local"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.settings.ollama_base_url}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
            installed_models = [name for model in models if (name := model.get("name"))]
            llm_installed = _model_installed(self.settings.ollama_model, installed_models)
            embedding_installed = _model_installed(self.settings.ollama_embedding_model, installed_models)
            missing_models = [
                model_name
                for model_name, installed in (
                    (self.settings.ollama_model, llm_installed),
                    (self.settings.ollama_embedding_model, embedding_installed),
                )
                if not installed
            ]
            result: dict[str, Any] = {
                "provider": "local",
                "available": llm_installed,
                "embedding_available": embedding_installed,
                "model": self.settings.ollama_model,
                "embedding_model": self.settings.ollama_embedding_model,
                "installed_models": installed_models,
            }
            if missing_models:
                result["missing_models"] = missing_models
            if not llm_installed:
                result["error"] = (
                    f"Ollama is running but required model is not installed: {self.settings.ollama_model}"
                )
            elif not embedding_installed:
                result["warning"] = (
                    f"Embedding model is not installed: {self.settings.ollama_embedding_model}. "
                    "Domain similarity will use keyword fallback."
                )
            return result
        except Exception as exc:  # noqa: BLE001 - surfaced as service status, not swallowed silently
            return {"provider": "local", "available": False, "error": str(exc)}

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        num_predict: int | None = None,
        num_ctx: int | None = None,
        max_chars: int | None = None,
        translate_input: bool = True,
        timeout_seconds: float | None = None,
    ) -> str | None:
        max_chars = max_chars or self.settings.max_llm_context_chars
        if translate_input and self.settings.auto_translate_llm_input_to_english:
            prompt, _ = await ensure_english_for_llm(prompt, purpose="generate", provider="local")
        if system and translate_input and self.settings.auto_translate_llm_input_to_english:
            system, _ = await ensure_english_for_llm(system, purpose="generate_system", provider="local")
        payload = {
            "model": self.settings.ollama_model,
            "prompt": prompt[:max_chars],
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx or self.settings.ollama_num_ctx,
                "num_predict": num_predict or self.settings.llm_generate_num_predict,
            },
        }
        if system:
            payload["system"] = system[:max_chars]
        timeout = timeout_seconds or self.settings.llm_timeout_seconds
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{self.settings.ollama_base_url}/api/generate", json=payload)
                response.raise_for_status()
            data = response.json()
            text = str(data.get("response", "")).strip()
            if not text:
                text = str(data.get("thinking", "")).strip()
            return text or None
        except httpx.TimeoutException:
            return None
        except Exception:
            return None

    async def embed(self, text: str) -> list[float] | None:
        if self.settings.auto_translate_llm_input_to_english:
            text, _ = await ensure_english_for_llm(text, purpose="embed", provider="local")
        payload = {"model": self.settings.ollama_embedding_model, "prompt": text[:4096]}
        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(f"{self.settings.ollama_base_url}/api/embeddings", json=payload)
                response.raise_for_status()
            embedding = response.json().get("embedding")
            return embedding if isinstance(embedding, list) else None
        except Exception:
            return None


class CursorLLM:
    provider: LlmProvider = "cursor"

    def __init__(self) -> None:
        self.settings = get_settings()

    def _chat_completions_url(self) -> str:
        base = self.settings.cursor_api_base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _models_url(self) -> str:
        base = self.settings.cursor_api_base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            base = base[: -len("/chat/completions")]
        return f"{base}/models"

    def _proxy_root_health_url(self) -> str:
        base = self.settings.cursor_api_base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            base = base[: -len("/chat/completions")]
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        return f"{base}/health"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.cursor_api_key:
            headers["Authorization"] = f"Bearer {self.settings.cursor_api_key}"
        return headers

    async def health(self) -> dict[str, Any]:
        base_url = self.settings.cursor_api_base_url.strip()
        result: dict[str, Any] = {
            "provider": "cursor",
            "available": False,
            "configured": bool(base_url),
            "key_configured": bool(self.settings.cursor_api_key.strip()),
            "base_url": base_url or self.settings.cursor_api_base_url,
            "model": self.settings.cursor_model,
            "embedding_available": False,
        }
        if not base_url:
            result["error"] = "Cursor API base URL yapılandırılmamış."
            return result

        last_error: str | None = None
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                for url in (self._models_url(), self._proxy_root_health_url()):
                    try:
                        response = await client.get(url, headers=self._headers())
                        response.raise_for_status()
                        result["available"] = True
                        return result
                    except Exception as exc:  # noqa: BLE001
                        last_error = str(exc)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)

        if not result["key_configured"]:
            result["warning"] = "CURSOR_API_KEY tanımlı değil; bazı proxy'ler boş bearer token kabul eder."
        detail = last_error or "bilinmeyen hata"
        result["error"] = (
            f"Cursor proxy'ye bağlanılamadı ({detail}). "
            "Proxy'yi başlatın, CURSOR_API_BASE_URL değerini kontrol edin veya Local LLM seçin."
        )
        return result

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        num_predict: int | None = None,
        num_ctx: int | None = None,
        max_chars: int | None = None,
        translate_input: bool = True,
        timeout_seconds: float | None = None,
    ) -> str | None:
        del num_ctx  # OpenAI-compatible APIs do not expose Ollama num_ctx
        max_chars = max_chars or self.settings.max_llm_context_chars
        if translate_input and self.settings.auto_translate_llm_input_to_english:
            prompt, _ = await ensure_english_for_llm(prompt, purpose="generate", provider="cursor")
        if system and translate_input and self.settings.auto_translate_llm_input_to_english:
            system, _ = await ensure_english_for_llm(system, purpose="generate_system", provider="cursor")

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system[:max_chars]})
        messages.append({"role": "user", "content": prompt[:max_chars]})

        payload: dict[str, Any] = {
            "model": self.settings.cursor_model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
        }
        if num_predict is not None:
            payload["max_tokens"] = num_predict

        timeout = timeout_seconds or self.settings.llm_timeout_seconds
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self._chat_completions_url(),
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
            data = response.json()
            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                return None
            message = choices[0].get("message", {})
            if not isinstance(message, dict):
                return None
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            reasoning = message.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning.strip():
                return reasoning.strip()
            return None
        except httpx.TimeoutException:
            return None
        except Exception:
            return None


def get_llm_client(provider: LlmProvider | str | None = None) -> LlmClient:
    normalized = normalize_llm_provider(provider or get_settings().default_llm_provider)
    if normalized == "cursor":
        return CursorLLM()
    return LocalLLM()


async def llm_health(provider: LlmProvider | str | None = None) -> dict[str, Any]:
    client = get_llm_client(provider)
    return await client.health()


async def semantic_similarity(text_a: str, text_b: str) -> float | None:
    client = LocalLLM()
    embedding_a = await client.embed(text_a)
    embedding_b = await client.embed(text_b)
    if not embedding_a or not embedding_b:
        return None
    return cosine_similarity(embedding_a, embedding_b)


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    if len(vector_a) != len(vector_b) or not vector_a:
        return 0.0
    a = np.array(vector_a, dtype=np.float32)
    b = np.array(vector_b, dtype=np.float32)
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if math.isclose(denominator, 0.0):
        return 0.0
    return float(np.dot(a, b) / denominator)

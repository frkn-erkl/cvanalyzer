import asyncio

from app.services import llm
from app.services.llm import cosine_similarity


def test_model_installed_matches_exact_and_tagged_names() -> None:
    assert llm._model_installed("qwen3:8b", ["qwen3:8b"])
    assert llm._model_installed("qwen3:8b", ["qwen3:8b:latest"])
    assert not llm._model_installed("qwen3:8b", ["qwen3.5:9b-q4_K_M"])


def test_health_requires_configured_llm_model(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[dict[str, str]]]:
            return {"models": [{"name": "qwen3.5:9b-q4_K_M"}]}

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str):
            return FakeResponse()

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)
    settings = llm.get_settings()
    monkeypatch.setattr(settings, "ollama_model", "qwen3:8b")

    result = asyncio.run(llm.LocalLLM().health())

    assert result["available"] is False
    assert "qwen3:8b" in result["missing_models"]
    assert "error" in result


def test_health_available_without_embedding_model(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[dict[str, str]]]:
            return {"models": [{"name": "qwen3.5:9b-q4_K_M"}]}

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str):
            return FakeResponse()

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)
    settings = llm.get_settings()
    monkeypatch.setattr(settings, "ollama_model", "qwen3.5:9b-q4_K_M")

    result = asyncio.run(llm.LocalLLM().health())

    assert result["available"] is True
    assert result["embedding_available"] is False
    assert "nomic-embed-text" in result["missing_models"]
    assert "error" not in result
    assert "warning" in result


def test_health_available_when_models_installed(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[dict[str, str]]]:
            return {
                "models": [
                    {"name": "qwen3:8b"},
                    {"name": "nomic-embed-text:latest"},
                ]
            }

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str):
            return FakeResponse()

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)
    settings = llm.get_settings()
    monkeypatch.setattr(settings, "ollama_model", "qwen3:8b")

    result = asyncio.run(llm.LocalLLM().health())

    assert result["available"] is True
    assert result["embedding_available"] is True
    assert "missing_models" not in result


def test_cosine_similarity() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_generate_accepts_quality_options(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"response": "ok"}

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    async def fail_translate(prompt: str, *, purpose: str):
        raise AssertionError("generate should skip translation when translate_input=False")

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(llm, "ensure_english_for_llm", fail_translate)

    result = asyncio.run(
        llm.LocalLLM().generate(
            "abcdef",
            temperature=0.4,
            num_predict=123,
            num_ctx=2048,
            max_chars=3,
            translate_input=False,
        )
    )

    payload = captured["json"]
    assert result == "ok"
    assert payload["think"] is False
    assert payload["prompt"] == "abc"
    assert payload["options"]["temperature"] == 0.4
    assert payload["options"]["num_predict"] == 123
    assert payload["options"]["num_ctx"] == 2048


def test_generate_enables_thinking_when_progress_callback_provided(monkeypatch) -> None:
    captured: dict[str, object] = {}
    chunks = [
        '{"thinking":"Adım 1","response":"","done":false}',
        '{"thinking":"","response":"{\\"ok\\":true}","done":true}',
    ]

    class FakeStreamResponse:
        def raise_for_status(self) -> None:
            return None

        async def aiter_lines(self):
            for chunk in chunks:
                yield chunk

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        def stream(self, method: str, url: str, json: dict):
            captured["json"] = json
            captured["url"] = url

            class StreamContext:
                async def __aenter__(self_inner):
                    return FakeStreamResponse()

                async def __aexit__(self_inner, exc_type, exc, tb) -> None:
                    return None

            return StreamContext()

    progress_updates: list[tuple[str, str]] = []

    def on_progress(thinking: str, response: str) -> None:
        progress_updates.append((thinking, response))

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(llm, "ensure_english_for_llm", lambda text, **kwargs: (text, {}))
    settings = llm.get_settings()
    monkeypatch.setattr(settings, "ollama_enable_thinking", True)

    result = asyncio.run(
        llm.LocalLLM().generate_detailed(
            "prompt",
            translate_input=False,
            on_progress=on_progress,
        )
    )

    assert captured["json"]["think"] is True
    assert captured["json"]["stream"] is True
    assert result.text == '{"ok":true}'
    assert result.thinking == "Adım 1"
    assert progress_updates[-1] == ("Adım 1", '{"ok":true}')


def test_get_llm_client_defaults_to_local() -> None:
    client = llm.get_llm_client()
    assert isinstance(client, llm.LocalLLM)


def test_get_llm_client_returns_cursor() -> None:
    client = llm.get_llm_client("cursor")
    assert isinstance(client, llm.CursorLLM)


def test_cursor_generate_posts_openai_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "cursor ok"}}]}

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

    async def fail_translate(prompt: str, *, purpose: str, provider=None):
        raise AssertionError("cursor generate should skip translation")

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(llm, "ensure_english_for_llm", fail_translate)
    settings = llm.get_settings()
    monkeypatch.setattr(settings, "cursor_api_base_url", "http://127.0.0.1:8765/v1")
    monkeypatch.setattr(settings, "cursor_api_key", "test-key")
    monkeypatch.setattr(settings, "cursor_model", "auto")

    result = asyncio.run(
        llm.CursorLLM().generate(
            "hello",
            system="system prompt",
            num_predict=321,
            translate_input=False,
        )
    )

    payload = captured["json"]
    assert result == "cursor ok"
    assert captured["url"] == "http://127.0.0.1:8765/v1/chat/completions"
    assert payload["model"] == "auto"
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["content"] == "hello"
    assert payload["max_tokens"] == 321
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_cursor_health_available_when_models_endpoint_works(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[dict[str, str]]]:
            return {"data": [{"id": "auto"}]}

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict):
            return FakeResponse()

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)
    settings = llm.get_settings()
    monkeypatch.setattr(settings, "cursor_api_base_url", "http://127.0.0.1:8765/v1")
    monkeypatch.setattr(settings, "cursor_api_key", "test-key")
    monkeypatch.setattr(settings, "cursor_model", "auto")

    result = asyncio.run(llm.CursorLLM().health())

    assert result["provider"] == "cursor"
    assert result["available"] is True
    assert result["configured"] is True
    assert result["key_configured"] is True
    assert result["base_url"] == "http://127.0.0.1:8765/v1"
    assert result["model"] == "auto"


def test_cursor_health_available_when_health_fallback_works(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"status": "ok"}

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            self.calls: list[str] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict):
            self.calls.append(url)
            if url.endswith("/health"):
                return FakeResponse()
            raise ConnectionError("models unavailable")

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)
    settings = llm.get_settings()
    monkeypatch.setattr(settings, "cursor_api_base_url", "http://127.0.0.1:8765/v1")
    monkeypatch.setattr(settings, "cursor_api_key", "test-key")

    result = asyncio.run(llm.CursorLLM().health())

    assert result["available"] is True
    assert result["key_configured"] is True


def test_cursor_health_unavailable_when_endpoints_fail(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict):
            raise ConnectionError("connection refused")

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)
    settings = llm.get_settings()
    monkeypatch.setattr(settings, "cursor_api_base_url", "http://127.0.0.1:8765/v1")
    monkeypatch.setattr(settings, "cursor_api_key", "test-key")

    result = asyncio.run(llm.CursorLLM().health())

    assert result["available"] is False
    assert result["configured"] is True
    assert result["key_configured"] is True
    assert "Cursor proxy'ye bağlanılamadı" in str(result["error"])


def test_cursor_api_key_defaults_empty(monkeypatch) -> None:
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "cursor_api_key", "")

    assert settings.cursor_api_key == ""

import asyncio

from app import db
from app.config import get_settings
from app.services import language


def _setup_db(tmp_path, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "database_path", tmp_path / "test.db")
    monkeypatch.setattr(settings, "auto_translate_llm_input_to_english", True)
    db.init_db()


def test_detect_language_turkish() -> None:
    assert language.detect_language("6 yil Python deneyimi ve REST API gelistirme") == "tr"


def test_is_english_text_skips_translation_candidate() -> None:
    assert language.is_english_text("en", "Senior Backend Developer with Python and FastAPI experience.")


def test_ensure_english_for_llm_skips_english_text(tmp_path, monkeypatch) -> None:
    _setup_db(tmp_path, monkeypatch)

    async def fake_translate(_: str, *, purpose: str) -> str | None:
        raise AssertionError("translate should not be called")

    monkeypatch.setattr(language, "_translate_to_english", fake_translate)
    text = "Senior Backend Developer with Python, FastAPI, PostgreSQL, Docker, and AWS experience."
    result, metadata = asyncio.run(language.ensure_english_for_llm(text, purpose="embed"))

    assert result == text
    assert metadata["was_translated"] is False


def test_ensure_english_for_llm_translates_turkish_text(tmp_path, monkeypatch) -> None:
    _setup_db(tmp_path, monkeypatch)

    async def fake_translate(text: str, *, purpose: str) -> str | None:
        assert purpose == "cv"
        return "6 years of Python experience."

    monkeypatch.setattr(language, "_translate_to_english", fake_translate)
    turkish = "6 yil Python deneyimi ve REST API gelistirme."
    result, metadata = asyncio.run(language.ensure_english_for_llm(turkish, purpose="cv"))

    assert result == "6 years of Python experience."
    assert metadata["was_translated"] is True


def test_translation_cache_hit(tmp_path, monkeypatch) -> None:
    _setup_db(tmp_path, monkeypatch)
    calls = {"count": 0}

    async def fake_translate(_: str, *, purpose: str) -> str | None:
        calls["count"] += 1
        return "Translated text."

    monkeypatch.setattr(language, "_translate_to_english", fake_translate)
    turkish = "Deneyim: Python, FastAPI, PostgreSQL."

    first, first_meta = asyncio.run(language.ensure_english_for_llm(turkish, purpose="job"))
    second, second_meta = asyncio.run(language.ensure_english_for_llm(turkish, purpose="job"))

    assert first == "Translated text."
    assert second == "Translated text."
    assert first_meta["was_translated"] is True
    assert second_meta["cache_hit"] is True
    assert calls["count"] == 1


def test_ensure_english_for_llm_skips_translation_for_cursor_provider(tmp_path, monkeypatch) -> None:
    _setup_db(tmp_path, monkeypatch)

    async def fake_translate(_: str, *, purpose: str) -> str | None:
        raise AssertionError("translate should not be called for cursor provider")

    monkeypatch.setattr(language, "_translate_to_english", fake_translate)
    turkish = "6 yil Python deneyimi ve REST API gelistirme."
    result, metadata = asyncio.run(language.ensure_english_for_llm(turkish, purpose="cv", provider="cursor"))

    assert result == turkish
    assert metadata["was_translated"] is False
    assert metadata["provider"] == "cursor"


def test_chunk_text_splits_long_input() -> None:
    long_text = ("Paragraph one.\n\n" * 200).strip()
    chunks = language._chunk_text(long_text, 3000)
    assert len(chunks) > 1
    assert all(len(chunk) <= 3000 for chunk in chunks)

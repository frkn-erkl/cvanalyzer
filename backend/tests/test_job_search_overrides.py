import json

import pytest

from app.api.jobs import _parse_apify_run_inputs_override, _parse_search_queries_override
from app.services.job_search import _apply_search_queries_override


def test_parse_search_queries_override_from_json() -> None:
    assert _parse_search_queries_override('["Backend Developer", "Python"]') == [
        "Backend Developer",
        "Python",
    ]


def test_parse_search_queries_override_from_lines() -> None:
    assert _parse_search_queries_override("Backend Developer\n\nPython\n") == [
        "Backend Developer",
        "Python",
    ]


def test_parse_apify_run_inputs_override() -> None:
    raw = json.dumps({"linkedin": {"urls": ["https://example.com"]}, "kariyer": {"keyword": "test"}})
    parsed = _parse_apify_run_inputs_override(raw)
    assert parsed is not None
    assert parsed["linkedin"]["urls"] == ["https://example.com"]


def test_parse_apify_run_inputs_override_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="geçerli JSON"):
        _parse_apify_run_inputs_override("{bad")


def test_apply_search_queries_override_sanitizes() -> None:
    result = _apply_search_queries_override(
        ["generated"],
        [" MongoDB ", "MongoDB", "Backend Developer"],
    )
    assert result == ["MongoDB", "Backend Developer"]

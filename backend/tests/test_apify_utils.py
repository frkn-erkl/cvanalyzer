from app.services.apify_utils import effective_use_apify
from app.services.job_listings import detect_job_source


def test_detect_job_source_valid_domains() -> None:
    assert detect_job_source("https://www.linkedin.com/jobs/view/1") == "linkedin"
    assert detect_job_source("https://tr.linkedin.com/jobs/view/1") == "linkedin"
    assert detect_job_source("https://www.kariyer.net/is-ilani/1") == "kariyer"


def test_detect_job_source_rejects_spoofed_domains() -> None:
    assert detect_job_source("https://linkedin.com.evil.example/jobs/1") is None
    assert detect_job_source("https://notlinkedin.com/jobs/1") is None
    assert detect_job_source("https://kariyer.net.fake.example/job/1") is None


def test_effective_use_apify_requires_enabled_flag(monkeypatch) -> None:
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "apify_enabled", False)
    monkeypatch.setattr(settings, "apify_api_token", "token")

    active, warning = effective_use_apify(True)

    assert active is False
    assert warning is not None
    assert "APIFY_ENABLED" in warning


def test_effective_use_apify_requires_token(monkeypatch) -> None:
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "apify_enabled", True)
    monkeypatch.setattr(settings, "apify_api_token", "")

    active, warning = effective_use_apify(True)

    assert active is False
    assert warning is not None

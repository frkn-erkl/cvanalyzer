from urllib.parse import parse_qs, urlparse

from app.services.job_listings import (
    build_kariyer_listing_start_urls,
    build_kariyer_search_input,
    build_linkedin_jobs_search_url,
    build_linkedin_search_input,
    normalize_kariyer_items,
    normalize_linkedin_items,
)

SAMPLE_KARIYER_ITEM = {
    "id": 4385220,
    "title": "Harita Mühendisi",
    "company": "Alkazan İnş. End. Tic. Ltd. Şti",
    "url": "https://www.kariyer.net/is-ilani/alkazan-ins-end-tic-ltd-sti-harita-muhendisi-4385220",
    "location": "Bursa",
    "employment_type": "Tam Zamanlı",
    "work_model": "OnSite",
    "posting_date": "2026-02-18",
    "posted_relative": "1 saat",
    "description_text": "Alkazan; Sağlık, inşaat, gıda sektörlerinde faaliyet göstermektedir.",
}


SAMPLE_LINKEDIN_ITEM = {
    "id": "3692563200",
    "link": "https://www.linkedin.com/jobs/view/english-data-labeling-analyst-at-facebook-3692563200",
    "title": "English Data Labeling Analyst",
    "companyName": "Facebook",
    "location": "Los Angeles Metropolitan Area",
    "postedAt": "2023-08-16",
    "descriptionText": "The main function of a data labeling analyst is to create and manage labeling processes.",
}


def test_build_linkedin_jobs_search_url() -> None:
    url = build_linkedin_jobs_search_url("Backend Developer", "Istanbul")
    assert url.startswith("https://www.linkedin.com/jobs/search/?")
    assert "keywords=Backend+Developer" in url or "keywords=Backend%20Developer" in url
    assert "location=istanbul" in url


def test_build_linkedin_jobs_search_url_ascii_folds_turkish_location() -> None:
    url = build_linkedin_jobs_search_url("Yazılım Mühendisi", "İzmir")
    query = parse_qs(urlparse(url).query)

    assert query["keywords"] == ["Yazılım Mühendisi"]
    assert query["location"] == ["izmir"]


def test_build_linkedin_search_input() -> None:
    payload = build_linkedin_search_input(
        queries=["Backend Developer", "Python Developer"],
        location="İzmir, İstanbul, remote",
        max_results=5,
    )

    assert len(payload["urls"]) == 6
    assert all(url.startswith("https://www.linkedin.com/jobs/search/?") for url in payload["urls"])
    assert any("location=izmir" in url for url in payload["urls"])
    assert any("location=istanbul" in url for url in payload["urls"])
    assert any("location=remote" in url for url in payload["urls"])
    assert payload["scrapeCompany"] is True
    assert payload["count"] == 10
    assert payload["splitByLocation"] is False


def test_normalize_linkedin_items_maps_actor_output() -> None:
    candidates = normalize_linkedin_items([SAMPLE_LINKEDIN_ITEM])

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source == "linkedin"
    assert candidate.title == "English Data Labeling Analyst"
    assert candidate.company == "Facebook"
    assert candidate.location == "Los Angeles Metropolitan Area"
    assert candidate.posted_at == "2023-08-16"
    assert "data labeling analyst" in candidate.description


def test_normalize_linkedin_items_without_description() -> None:
    item = {
        "link": "https://www.linkedin.com/jobs/view/example-123",
        "title": "Backend Developer",
        "companyName": "Acme",
    }
    candidates = normalize_linkedin_items([item])

    assert len(candidates) == 1
    assert candidates[0].description == "Backend Developer"


def test_build_linkedin_search_input_skips_invalid_queries() -> None:
    payload = build_linkedin_search_input(
        queries=["Backend Developer", None, "  ", "Python"],  # type: ignore[list-item]
        location="Istanbul",
        max_results=10,
    )

    assert len(payload["urls"]) == 2


def test_build_kariyer_listing_start_urls() -> None:
    assert build_kariyer_listing_start_urls(None) == ["https://www.kariyer.net/is-ilanlari"]
    assert build_kariyer_listing_start_urls("İstanbul") == ["https://www.kariyer.net/is-ilanlari/istanbul"]
    assert build_kariyer_listing_start_urls("İzmir, İstanbul, remote") == [
        "https://www.kariyer.net/is-ilanlari/izmir",
        "https://www.kariyer.net/is-ilanlari/istanbul",
    ]


def test_build_kariyer_search_input_keyword_with_city_start_urls() -> None:
    payload = build_kariyer_search_input(
        queries=["yazılım mühendisi"],
        location="Kayseri",
        max_results=10,
    )

    assert payload == {
        "keyword": "yazılım mühendisi",
        "startUrls": ["https://www.kariyer.net/is-ilanlari/kayseri"],
        "results_wanted": 10,
        "max_pages": 3,
        "max_job_age": "all",
        "proxyConfiguration": {"useApifyProxy": False},
    }
    assert "location" not in payload


def test_build_kariyer_search_input_multi_url_mode() -> None:
    payload = build_kariyer_search_input(
        queries=["yazılım mühendisi", "python developer"],
        location="Ankara, İzmir",
        max_results=150,
    )

    assert payload == {
        "keyword": "yazılım mühendisi",
        "startUrls": [
            "https://www.kariyer.net/is-ilanlari/ankara",
            "https://www.kariyer.net/is-ilanlari/izmir",
        ],
        "results_wanted": 150,
        "max_pages": 15,
        "max_job_age": "all",
        "proxyConfiguration": {"useApifyProxy": False},
    }
    assert "location" not in payload


def test_build_kariyer_search_input_single_city_start_urls() -> None:
    payload = build_kariyer_search_input(
        queries=["yazılım mühendisi"],
        location="İstanbul",
        max_results=50,
    )

    assert payload["keyword"] == "yazılım mühendisi"
    assert payload["startUrls"] == ["https://www.kariyer.net/is-ilanlari/istanbul"]
    assert payload["results_wanted"] == 50
    assert payload["max_pages"] == 5
    assert "location" not in payload


def test_build_kariyer_search_input_keyword_only_without_location() -> None:
    payload = build_kariyer_search_input(
        queries=["yazılım mühendisi"],
        location="remote",
        max_results=20,
    )

    assert payload["keyword"] == "yazılım mühendisi"
    assert payload["results_wanted"] == 20
    assert "location" not in payload
    assert "startUrls" not in payload


def test_normalize_kariyer_items_maps_actor_output() -> None:
    candidates = normalize_kariyer_items([SAMPLE_KARIYER_ITEM])

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source == "kariyer"
    assert candidate.title == "Harita Mühendisi"
    assert candidate.company == "Alkazan İnş. End. Tic. Ltd. Şti"
    assert candidate.location == "Bursa"
    assert candidate.posted_at == "2026-02-18"
    assert "Alkazan" in candidate.description

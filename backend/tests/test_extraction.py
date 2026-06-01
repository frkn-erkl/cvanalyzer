from app.services.extraction import clean_text, extract_text_from_bytes


def test_plain_text_extraction_cleans_whitespace() -> None:
    extracted = extract_text_from_bytes(b"Python   React\n\n\nDocker", filename="cv.txt", content_type="text/plain")

    assert extracted.text == "Python React\n\nDocker"
    assert extracted.metadata["format"] == "text"


def test_clean_text_removes_null_bytes() -> None:
    assert clean_text("A\x00  B") == "A B"

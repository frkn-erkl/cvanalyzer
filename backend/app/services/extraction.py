import io
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup
from docx import Document
from pypdf import PdfReader


@dataclass(frozen=True)
class ExtractedText:
    text: str
    metadata: dict[str, str | int | bool]


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_bytes(
    content: bytes,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> ExtractedText:
    lowered = (filename or "").lower()
    content_type = (content_type or "").lower()

    if lowered.endswith(".pdf") or "pdf" in content_type:
        return _extract_pdf(content)
    if lowered.endswith(".docx") or "wordprocessingml" in content_type:
        return _extract_docx(content)
    if lowered.endswith((".html", ".htm")) or "html" in content_type:
        return _extract_html(content)

    if lowered.endswith(".tex"):
        decoded = _decode_text(content)
        return ExtractedText(clean_text(decoded), {"format": "latex", "bytes": len(content)})

    decoded = _decode_text(content)
    return ExtractedText(clean_text(decoded), {"format": "text", "bytes": len(content)})


def extract_text_from_html(html: str) -> ExtractedText:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = soup.get_text("\n", strip=True)
    return ExtractedText(clean_text(f"{title}\n\n{text}"), {"format": "html", "title": title})


def _extract_html(content: bytes) -> ExtractedText:
    return extract_text_from_html(_decode_text(content))


def _extract_pdf(content: bytes) -> ExtractedText:
    reader = PdfReader(io.BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    return ExtractedText(
        clean_text("\n\n".join(pages)),
        {"format": "pdf", "pages": len(reader.pages), "bytes": len(content)},
    )


def _extract_docx(content: bytes) -> ExtractedText:
    document = Document(io.BytesIO(content))
    paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    return ExtractedText(
        clean_text("\n".join(paragraphs)),
        {"format": "docx", "paragraphs": len(paragraphs), "bytes": len(content)},
    )


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "cp1254", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")

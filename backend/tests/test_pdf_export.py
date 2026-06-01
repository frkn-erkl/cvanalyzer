from pathlib import Path

from app.config import get_settings
from app.services import pdf_export


def test_compile_latex_to_pdf_warns_when_engine_missing(monkeypatch) -> None:
    monkeypatch.setattr(pdf_export, "find_latex_engine", lambda: None)

    pdf_path, warnings = pdf_export.compile_latex_to_pdf("\\documentclass{article}", "rewrite-1")

    assert pdf_path is None
    assert "No local LaTeX engine" in warnings[0]


def test_compile_latex_to_pdf_copies_generated_file(tmp_path, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "export_dir", tmp_path / "exports")
    monkeypatch.setattr(pdf_export, "find_latex_engine", lambda: "pdflatex")

    def fake_run(command, cwd, capture_output, text, timeout, check):
        Path(cwd, "cv.pdf").write_bytes(b"%PDF-1.4")

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        return Completed()

    monkeypatch.setattr(pdf_export.subprocess, "run", fake_run)

    pdf_path, warnings = pdf_export.compile_latex_to_pdf("\\documentclass{article}", "rewrite-2")

    assert warnings == []
    assert pdf_path is not None
    assert pdf_path.exists()
    assert pdf_path.read_bytes() == b"%PDF-1.4"

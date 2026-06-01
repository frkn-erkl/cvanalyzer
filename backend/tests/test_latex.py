from app.models import CvRewriteRequest
from app.services.latex import (
    build_latex_rewrite_prompt,
    extract_latex_structure,
    is_latex_source,
    sanitize_latex_output,
)
from tests.test_cv_rewrite import _analysis


LATEX_CV = r"""
\documentclass{article}
\newcommand{\resumeItem}[1]{\item #1}
\begin{document}
\section{Experience}
\resumeItem{Built REST APIs with Python and FastAPI.}
\end{document}
"""


def test_is_latex_source_detects_resume_template() -> None:
    assert is_latex_source(LATEX_CV)
    assert not is_latex_source("Plain CV text with Python and FastAPI.")


def test_extract_latex_structure_reads_sections_and_commands() -> None:
    structure = extract_latex_structure(LATEX_CV)

    assert "Experience" in structure.sections
    assert "resumeItem" in structure.custom_commands
    assert "\\documentclass" in structure.preamble


def test_sanitize_latex_output_removes_code_fences() -> None:
    output, warnings = sanitize_latex_output(f"```latex\n{LATEX_CV}\n```")

    assert output.startswith("\\documentclass")
    assert "\\begin{document}" in output
    assert warnings == []


def test_build_latex_rewrite_prompt_mentions_preserving_template() -> None:
    prompt = build_latex_rewrite_prompt(
        LATEX_CV,
        "Python FastAPI backend role.",
        _analysis(),
        CvRewriteRequest(output_format="latex"),
    )

    assert "preserving the original LaTeX template" in prompt
    assert "Output valid LaTeX source only" in prompt

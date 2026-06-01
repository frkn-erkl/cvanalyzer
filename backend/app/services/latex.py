import re
from dataclasses import dataclass

from app.config import get_settings
from app.models import AnalysisResult, CvRewriteRequest


LATEX_MARKERS = (
    "\\documentclass",
    "\\begin{document}",
    "\\end{document}",
    "\\section",
    "\\subsection",
    "\\resumeItem",
    "\\resumeSubheading",
    "\\cventry",
    "\\cvitem",
)


@dataclass(frozen=True)
class LatexStructure:
    preamble: str
    body: str
    sections: list[str]
    custom_commands: list[str]


def is_latex_source(text: str) -> bool:
    if not text.strip():
        return False
    marker_count = sum(1 for marker in LATEX_MARKERS if marker in text)
    return "\\documentclass" in text or ("\\begin{document}" in text and marker_count >= 2) or marker_count >= 3


def extract_latex_structure(text: str) -> LatexStructure:
    begin_match = re.search(r"\\begin\{document\}", text)
    if begin_match:
        preamble = text[: begin_match.start()]
        body = text[begin_match.start() :]
    else:
        preamble = ""
        body = text
    sections = re.findall(r"\\(?:section|subsection)\*?\{([^}]+)\}", text)
    custom_commands = re.findall(r"\\newcommand\{\\([^}]+)\}", text)
    return LatexStructure(preamble=preamble, body=body, sections=sections, custom_commands=custom_commands)


def build_latex_rewrite_prompt(
    original_latex: str,
    job_text: str,
    analysis: AnalysisResult,
    request: CvRewriteRequest,
) -> str:
    settings = get_settings()
    structure = extract_latex_structure(original_latex)
    matched = ", ".join(match.name for match in analysis.matched_required_skills) or "none"
    omitted = ", ".join(match.name for match in [*analysis.missing_required_skills, *analysis.missing_preferred_skills]) or "none"
    evidence = "\n".join(f"- {item[:260]}" for item in analysis.cv_profile.highlights[:5]) or "- none"
    job_focus = "\n".join(f"- {item[:260]}" for item in (analysis.job_profile.responsibilities[:5] or analysis.job_profile.keywords[:8])) or "- none"
    output_language = "English" if request.language == "en" else "Turkish"
    tone = "professional, ATS-friendly"
    if request.tone == "concise_professional_ats":
        tone = "professional, ATS-friendly, concise"

    return f"""
You are an evidence-based LaTeX CV editing assistant.
Rewrite the CV below for the job posting while preserving the original LaTeX template.

Hard rules:
- Output valid LaTeX source only. Do not wrap it in Markdown fences.
- Preserve the original preamble, document class, packages, custom commands, spacing commands, and section structure whenever possible.
- Change only human-readable CV content. Do not rename LaTeX commands or environments.
- Do not add skills, certifications, education, years of experience, seniority, projects, or metrics not supported by the original CV.
- Keep missing skills out of the CV text: {omitted}.
- Use a {tone} tone and write human-readable CV content in {output_language}.
- Improve the profile/summary content when a matching section exists; keep it factual, role-specific, and concise.
- Reword existing experience bullets as technology + responsibility + outcome only when the original CV supports the outcome.

Known CV sections: {", ".join(structure.sections) or "unknown"}
Custom commands: {", ".join(structure.custom_commands) or "none"}
Matched required skills that may be highlighted if present in the CV: {matched}
CV seniority: {analysis.cv_profile.seniority}
Job seniority: {analysis.job_profile.seniority}

Strong CV evidence to preserve:
{evidence}

Job focus:
{job_focus}

Original LaTeX CV:
{original_latex[: settings.latex_rewrite_cv_chars]}

Job posting:
{job_text[: settings.latex_rewrite_job_chars]}
"""


def sanitize_latex_output(output: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    cleaned = output.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:latex|tex)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    if "\\documentclass" in cleaned:
        first_docclass = cleaned.find("\\documentclass")
        if first_docclass > 0:
            cleaned = cleaned[first_docclass:]
            warnings.append("Removed non-LaTeX text before \\documentclass.")
    if cleaned.count("\\documentclass") > 1:
        warnings.append("Multiple \\documentclass entries detected; output may need manual review.")
    if "\\begin{document}" not in cleaned:
        warnings.append("LaTeX output does not contain \\begin{document}.")
    if "\\end{document}" not in cleaned:
        warnings.append("LaTeX output does not contain \\end{document}.")
    return cleaned, warnings


def latex_to_plain_text(latex_text: str) -> str:
    text = re.sub(r"%.*", "", latex_text)
    text = re.sub(r"\\(?:documentclass|usepackage)(?:\[[^\]]+\])?\{[^}]+\}", " ", text)
    text = re.sub(r"\\begin\{[^}]+\}|\\end\{[^}]+\}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]+\])?", " ", text)
    text = re.sub(r"[{}$&_#^~]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

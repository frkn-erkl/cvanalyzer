import shutil
import subprocess
import tempfile
from pathlib import Path

from app.config import get_settings


def find_latex_engine() -> str | None:
    for engine in ("xelatex", "pdflatex", "tectonic"):
        if shutil.which(engine):
            return engine
    return None


def pdf_path_for_rewrite(rewrite_id: str) -> Path:
    return get_settings().export_dir / f"{rewrite_id}.pdf"


def compile_latex_to_pdf(latex_text: str, rewrite_id: str) -> tuple[Path | None, list[str]]:
    engine = find_latex_engine()
    if engine is None:
        return None, ["No local LaTeX engine found. Install xelatex, pdflatex, or tectonic to generate PDF output."]

    export_dir = get_settings().export_dir
    export_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"cv_rewrite_{rewrite_id}_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        tex_path = temp_dir / "cv.tex"
        tex_path.write_text(latex_text, encoding="utf-8")

        command = _compile_command(engine, tex_path)
        try:
            completed = subprocess.run(
                command,
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None, ["PDF compilation timed out after 30 seconds."]

        if completed.returncode != 0:
            output = (completed.stderr or completed.stdout or "Unknown LaTeX compile error").strip()
            return None, [f"PDF compilation failed: {output[-1200:]}"]

        generated_pdf = temp_dir / "cv.pdf"
        if not generated_pdf.exists():
            return None, ["PDF compilation finished but no PDF file was produced."]

        final_path = pdf_path_for_rewrite(rewrite_id)
        shutil.copyfile(generated_pdf, final_path)
        return final_path, []


def _compile_command(engine: str, tex_path: Path) -> list[str]:
    if engine == "tectonic":
        return [engine, str(tex_path), "--outdir", str(tex_path.parent)]
    return [
        engine,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-no-shell-escape",
        str(tex_path),
    ]

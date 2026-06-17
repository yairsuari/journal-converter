from __future__ import annotations
from pathlib import Path
from typing import Optional
import re
import shutil
import subprocess
import tempfile

from .config import JournalConfig
from .csl_manager import get_csl

_PANDOC_SEARCH_PATHS = [
    Path.home() / "AppData" / "Local" / "Pandoc" / "pandoc.exe",  # Windows user install
    Path("/usr/local/bin/pandoc"),
    Path("/usr/bin/pandoc"),
    Path("/opt/homebrew/bin/pandoc"),
]


def _find_pandoc() -> str:
    on_path = shutil.which("pandoc")
    if on_path:
        return on_path
    for candidate in _PANDOC_SEARCH_PATHS:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError(
        "Pandoc not found. Install it from https://pandoc.org/installing.html"
    )


def count_words(path: Path) -> int:
    """Return an approximate word count for a .docx or .tex file."""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        from docx import Document
        doc = Document(path)
        text = " ".join(p.text for p in doc.paragraphs)
    elif suffix == ".tex":
        import re
        text = path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'\\begin\{document\}', text)
        if m:
            text = text[m.end():]
        text = re.sub(r'%[^\n]*', '', text)
        text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])*(?:\{[^}]*\})*', ' ', text)
        text = re.sub(r'[\\{}\[\]]', ' ', text)
    else:
        return 0
    return len(text.split())


_UNICODE_TO_LATEX: dict[str, str] = {
    # Math / science symbols
    '∼': r'$\sim$',       '≈': r'$\approx$',    '≤': r'$\leq$',
    '≥': r'$\geq$',       '≠': r'$\neq$',        '±': r'$\pm$',
    '×': r'$\times$',     '÷': r'$\div$',         '°': r'$^{\circ}$',
    '−': r'$-$',           '∞': r'$\infty$',       '·': r'$\cdot$',
    '∝': r'$\propto$',    '≡': r'$\equiv$',       '∂': r'$\partial$',
    '∑': r'$\sum$',       '∏': r'$\prod$',        '∫': r'$\int$',
    '√': r'$\sqrt{}$',    '²': r'$^{2}$',         '³': r'$^{3}$',
    '¹': r'$^{1}$',       'µ': r'$\mu$',
    # Greek lowercase
    'α': r'$\alpha$',     'β': r'$\beta$',        'γ': r'$\gamma$',
    'δ': r'$\delta$',     'ε': r'$\varepsilon$',  'ζ': r'$\zeta$',
    'η': r'$\eta$',       'θ': r'$\theta$',        'ι': r'$\iota$',
    'κ': r'$\kappa$',     'λ': r'$\lambda$',       'μ': r'$\mu$',
    'ν': r'$\nu$',        'ξ': r'$\xi$',           'π': r'$\pi$',
    'ρ': r'$\rho$',       'σ': r'$\sigma$',        'τ': r'$\tau$',
    'υ': r'$\upsilon$',   'φ': r'$\varphi$',       'χ': r'$\chi$',
    'ψ': r'$\psi$',       'ω': r'$\omega$',
    # Greek uppercase
    'Γ': r'$\Gamma$',     'Δ': r'$\Delta$',       'Θ': r'$\Theta$',
    'Λ': r'$\Lambda$',    'Ξ': r'$\Xi$',           'Π': r'$\Pi$',
    'Σ': r'$\Sigma$',     'Υ': r'$\Upsilon$',     'Φ': r'$\Phi$',
    'Ψ': r'$\Psi$',       'Ω': r'$\Omega$',
    # Typography
    '–': '--',        '—': '---',
    '‘': '`',         '’': "'",
    '“': '``',        '”': "''",
    '…': r'\ldots{}', '†': r'\dag{}',
    '‡': r'\ddag{}',  ' ': '~',
    # Ligatures Word sometimes embeds
    'ﬁ': 'fi',        'ﬂ': 'fl',
    'ﬀ': 'ff',        'ﬃ': 'ffi',        'ﬄ': 'ffl',
    # Misc
    '©': r'\textcopyright{}', '®': r'\textregistered{}',
    '™': r'\texttrademark{}',
}

def _sanitize_unicode(tex_path: Path) -> None:
    """Replace Unicode chars and bare ^ outside math that pdflatex can't handle."""
    text = tex_path.read_text(encoding="utf-8")
    for char, latex in _UNICODE_TO_LATEX.items():
        text = text.replace(char, latex)
    # Wrap bare superscripts like R^2 that Pandoc leaves outside math mode
    text = re.sub(r'(?<!\$)(?<![\{\\])(\b\w+)\^(\w+)(?!\})', r'$\1^\2$', text)
    # Center all figures
    text = re.compile(r'(\\includegraphics(?:\[[^\]]*\])?\{[^}]+\})').sub(
        lambda m: '\\begin{center}\n' + m.group(1) + '\n\\end{center}', text
    )
    tex_path.write_text(text, encoding="utf-8")


def _ensure_utf8_inputenc(tex_path: Path) -> None:
    """Inject \\usepackage[utf8]{inputenc} if the preamble doesn't already have it."""
    text = tex_path.read_text(encoding="utf-8")
    if "inputenc" in text:
        return
    # Insert after \documentclass line if present, otherwise at the very top
    import re
    injected = "\\usepackage[utf8]{inputenc}\n"
    m = re.search(r"\\documentclass[^\n]*\n", text)
    if m:
        text = text[: m.end()] + injected + text[m.end() :]
    else:
        text = injected + text
    tex_path.write_text(text, encoding="utf-8")


def convert(
    source: Path,
    target_journal: JournalConfig,
    output: Path,
    bib: Optional[Path] = None,
    bib_encoding: str = "utf-8",
    preserve_citations: bool = False,
) -> list[str]:
    """
    Convert source document to target journal format.
    Returns a list of warnings for the user to review.

    preserve_citations: when True and both source and output are .docx, re-inject
    live Paperpile ADDIN field codes that Pandoc discards during conversion.
    """
    warnings: list[str] = []

    pandoc = _find_pandoc()

    suffix = output.suffix.lower()
    if suffix not in (".docx", ".tex", ".pdf"):
        raise ValueError(f"Unsupported output format: {suffix}")

    # Pre-extract Paperpile field map before Pandoc discards the field codes.
    # Used for DOCX→DOCX citation injection and DOCX→LaTeX \citep{} revival.
    pp_field_map: dict = {}
    if source.suffix.lower() == '.docx':
        from .paperpile import extract_field_map
        pp_field_map = extract_field_map(source)

    if bib is None:
        msg = (
            "No .bib file supplied — citation reformatting skipped. "
            "Provide a BibTeX file with --bib to reformat citations."
        )
        if suffix == ".tex":
            msg = (
                "No .bib file supplied — citations will be rendered as plain text. "
                "For LaTeX output, always provide --bib so citations stay as \\cite{} commands."
            )
        warnings.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        out_tmp  = tmp_path / output.name

        cmd = [pandoc, str(source), "-o", str(out_tmp)]

        if suffix == ".tex":
            cmd += ["--standalone", "--extract-media", "."]
            if bib is not None:
                # --natbib keeps citations as \citep{}/\citet{}; do NOT pass --bibliography
                # here — Pandoc would write the full path into \bibliography{}, mangling
                # backslashes on Windows. cite_revive adds \bibliography{stem} instead.
                cmd += ["--natbib"]

            templates_dir = Path(__file__).parent.parent / "templates"

            # Full Pandoc template takes priority — gives complete control over preamble
            if target_journal.template.pandoc_template:
                tmpl_path = templates_dir / target_journal.template.pandoc_template
                if tmpl_path.exists():
                    cmd += ["--template", str(tmpl_path)]
                    if target_journal.latex_journal_abbrev:
                        cmd += ["-V", f"journal-abbrev={target_journal.latex_journal_abbrev}"]
                    # Copy cls + all companion files into the working dir
                    if target_journal.template.latex_cls:
                        cls_path = templates_dir / target_journal.template.latex_cls
                        if cls_path.exists():
                            for f in templates_dir.iterdir():
                                if f.suffix in (".cls", ".bst", ".cfg", ".sty", ".pdf") and f.is_file():
                                    shutil.copy(f, tmp_path / f.name)
                        else:
                            warnings.append(
                                f"LaTeX class '{target_journal.template.latex_cls}' not found in templates/ — "
                                "the Pandoc template references it; download it from the journal's author "
                                "guidelines page and place it in templates/."
                            )
                else:
                    warnings.append(
                        f"Pandoc template '{target_journal.template.pandoc_template}' not found in templates/ — "
                        "using default Pandoc preamble."
                    )
                    # Fall back to cls-only if template missing
                    if target_journal.template.latex_cls:
                        cls_path = templates_dir / target_journal.template.latex_cls
                        if cls_path.exists():
                            shutil.copy(cls_path, tmp_path / target_journal.template.latex_cls)
                            cmd += ["-V", f"documentclass={cls_path.stem}"]

            # No Pandoc template — just override the document class
            elif target_journal.template.latex_cls:
                cls_path = templates_dir / target_journal.template.latex_cls
                if cls_path.exists():
                    shutil.copy(cls_path, tmp_path / target_journal.template.latex_cls)
                    cmd += ["-V", f"documentclass={cls_path.stem}"]
                else:
                    warnings.append(
                        f"LaTeX class '{target_journal.template.latex_cls}' not found in templates/ — "
                        "using default article class. Download it from the journal's author guidelines page "
                        f"and place it in templates/."
                    )

        else:
            if bib is not None:
                csl_path = get_csl(target_journal.citation.style)
                cmd += ["--bibliography", str(bib), "--citeproc", "--csl", str(csl_path)]

            if suffix == ".docx" and target_journal.template.word:
                template_path = Path(__file__).parent.parent / "templates" / target_journal.template.word
                if template_path.exists():
                    cmd += ["--reference-doc", str(template_path)]
                else:
                    warnings.append(
                        f"Word template '{target_journal.template.word}' not found in templates/ — "
                        "using default Pandoc styling."
                    )

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(tmp_path))
        if result.returncode != 0:
            raise RuntimeError(f"Pandoc conversion failed:\n{result.stderr}")

        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(out_tmp, output)

        # Copy extracted media into a per-document subfolder to avoid collisions
        # when main + supplementary share the same output directory.
        media_tmp = tmp_path / "media"
        if media_tmp.exists():
            media_dest = output.parent / "media" / output.stem
            if media_dest.exists():
                shutil.rmtree(media_dest)
            shutil.copytree(media_tmp, media_dest)
            if suffix == ".tex":
                tex = output.read_text(encoding="utf-8")
                tex = re.sub(r'\./media/', f'./media/{output.stem}/', tex)
                output.write_text(tex, encoding="utf-8")
            warnings.append(
                f"Figures extracted to media/{output.stem}/ — "
                "replace with high-resolution originals before submission."
            )

    if suffix == ".tex":
        _ensure_utf8_inputenc(output)
        _sanitize_unicode(output)

    if suffix == ".tex" and bib is not None:
        # Build citekey map from field data (already extracted above as pp_field_map).
        # extract_citation_map decodes the JSON to get citekeys; re-use the same
        # DOCX read but via the dedicated function to keep concerns separate.
        from .paperpile import extract_citation_map
        from .cite_revive import revive
        pp_cite_map = extract_citation_map(source) if source.suffix.lower() == '.docx' else {}
        n_replaced, unmatched = revive(output, bib, bib_encoding=bib_encoding,
                                       paperpile_map=pp_cite_map or None)
        if n_replaced > 0:
            method = "Paperpile field data" if pp_cite_map else "author/year matching"
            warnings.append(
                f"Revived {n_replaced} citation(s) as \\citep{{}} commands ({method}). "
                "Add \\bibliographystyle{} to your preamble to match the target journal."
            )
        for u in unmatched:
            warnings.append(f"Could not match to a BibTeX key — check manually: '{u}'")

    if suffix == ".docx" and preserve_citations and pp_field_map:
        from .paperpile import inject_paperpile_fields
        n_injected = inject_paperpile_fields(output, pp_field_map)
        if n_injected > 0:
            warnings.append(
                f"Re-injected {n_injected} Paperpile citation field(s) — "
                "citations are live in Word. Refresh fields (Ctrl+A, then F9) after opening."
            )
        else:
            warnings.append(
                "Preserve citations was enabled but no Paperpile fields were matched "
                "in the output — citations remain as plain text."
            )

    return warnings

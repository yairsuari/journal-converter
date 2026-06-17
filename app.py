"""Streamlit GUI for the journal conversion tool."""
import io
import shutil
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

from converter import convert, count_words, JournalConfig, validate
from converter.wizard import load_publisher_data, slugify, write_journal_config

JOURNALS_DIR = Path(__file__).parent / "journals"

DISCLAIMER = (
    "This tool performs automated reformatting and does not guarantee compliance "
    "with a journal's current submission requirements. Output must be reviewed "
    "manually before submission. Supported journal configurations are community-"
    "maintained and may not reflect the most recent author guidelines. Always "
    "verify against the target journal's current instructions for authors."
)


@st.cache_data
def _load_journals() -> list[tuple[str, str]]:
    """Return sorted list of (journal_id, display_name) from journals/ folder."""
    journals = []
    for path in JOURNALS_DIR.glob("*.yaml"):
        try:
            config = JournalConfig.load(path.stem, JOURNALS_DIR)
            journals.append((path.stem, config.name))
        except Exception:
            pass
    return sorted(journals, key=lambda x: x[1])


def _mime(suffix: str) -> str:
    return (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if suffix == ".docx"
        else "text/plain"
    )


# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="Journal Converter", page_icon="📄", layout="centered")
st.title("Journal Conversion Tool")
st.caption("Reformat academic manuscripts between journals — open source, runs in your browser")

# ── Journal selectors ─────────────────────────────────────────────────────────

journals = _load_journals()
ids = [j[0] for j in journals]
names = [j[1] for j in journals]

col1, col2 = st.columns(2)
with col1:
    from_idx = st.selectbox("From journal", range(len(journals)), format_func=lambda i: names[i])
with col2:
    to_idx = st.selectbox("To journal", range(len(journals)), format_func=lambda i: names[i],
                          index=min(1, len(journals) - 1))

if from_idx == to_idx:
    st.warning("Source and target journals are the same — nothing to convert.")

# ── Add a new journal ────────────────────────────────────────────────────────

with st.expander("➕ Don't see your journal? Add it here"):
    new_name = st.text_input("Journal name", key="nj_name")
    new_id = st.text_input("Journal ID (short, lowercase, used internally)",
                            value=slugify(new_name) if new_name else "", key="nj_id")

    publishers_dir = JOURNALS_DIR / "publishers"
    available_publishers = sorted(p.stem for p in publishers_dir.glob("*.yaml")) if publishers_dir.exists() else []
    publisher_choice = st.selectbox("Publisher", ["None / not listed"] + available_publishers, key="nj_publisher")
    new_publisher = None if publisher_choice == "None / not listed" else publisher_choice
    pub_data = load_publisher_data(JOURNALS_DIR, new_publisher)

    new_style = new_format = None
    if "citation" not in pub_data:
        st.caption("Find the CSL filename at "
                   "[citation-style-language/styles](https://github.com/citation-style-language/styles)")
        new_style = st.text_input("CSL style name (without .csl)", key="nj_style")
        new_format = st.selectbox("Citation format", ["author-year", "numeric", "footnote"], key="nj_format")

    new_abstract_type = None
    new_headings: list[str] = []
    if "abstract" not in pub_data:
        new_abstract_type = st.selectbox("Abstract type", ["unstructured", "structured"], key="nj_abstype")
        if new_abstract_type == "structured":
            headings_raw = st.text_input("Structured abstract headings (comma-separated)", key="nj_headings")
            new_headings = [h.strip() for h in headings_raw.split(",") if h.strip()]

    has_word_limit = st.checkbox("Has a word limit", key="nj_haswl")
    new_word_limit = st.number_input("Word limit", min_value=0, step=500, value=8000,
                                      key="nj_wl") if has_word_limit else None

    new_template_word = new_template_cls = None
    if "template" not in pub_data:
        new_template_word = st.text_input("Word reference .docx filename (optional, place file in templates/)",
                                           key="nj_tword") or None
        new_template_cls = st.text_input("LaTeX .cls filename (optional, place file in templates/)",
                                          key="nj_tcls") or None

    if st.button("Save journal config"):
        if not new_name or not new_id:
            st.error("Journal name and ID are required.")
        elif not new_publisher and not new_style:
            st.error("Citation style is required when no publisher is selected.")
        else:
            try:
                new_path = write_journal_config(
                    JOURNALS_DIR, name=new_name, journal_id=new_id, publisher=new_publisher,
                    citation_style=new_style, citation_format=new_format,
                    abstract_type=new_abstract_type, abstract_headings=new_headings,
                    word_limit=int(new_word_limit) if new_word_limit else None,
                    template_word=new_template_word, template_latex_cls=new_template_cls,
                )
                new_config = JournalConfig.load(new_path.stem, JOURNALS_DIR)
                config_issues = validate(new_config)
                st.success(f"Saved {new_path.name} — it now appears in the journal dropdowns above.")
                for issue in config_issues:
                    st.warning(issue)
                st.info("Consider contributing this back via a pull request — see CONTRIBUTING.md.")
                _load_journals.clear()
                st.rerun()
            except FileExistsError:
                st.error(f"A config for '{slugify(new_id)}' already exists.")

# ── File uploaders ────────────────────────────────────────────────────────────

source_file = st.file_uploader("Source document", type=["docx", "tex"],
                                help="Upload the manuscript you want to convert")
bib_file = st.file_uploader("BibTeX file (optional)",  type=["bib"],
                              help="Required for citation reformatting. Export from Paperpile or your reference manager")

fmt_options = ["Same as source", "Word (.docx)", "LaTeX (.tex)"]
fmt_choice = st.selectbox("Output format", fmt_options,
                           help="LaTeX output keeps citations alive as \\citep{} commands "
                                "if you supply a BibTeX file")

# ── Citation preservation ─────────────────────────────────────────────────────

_source_is_docx = source_file is not None and source_file.name.lower().endswith(".docx")
_output_is_docx = (
    fmt_choice == "Word (.docx)" or
    (fmt_choice == "Same as source" and _source_is_docx)
)
preserve_citations = False
if _source_is_docx and _output_is_docx:
    preserve_citations = st.checkbox(
        "Preserve citations (Paperpile)",
        value=True,
        help="Re-inject live Paperpile ADDIN field codes that Pandoc discards, "
             "so citations remain interactive in the converted Word document. "
             "Currently only Paperpile citations are supported.",
    )

# ── Conversion ────────────────────────────────────────────────────────────────

ready = source_file is not None and from_idx != to_idx
if st.button("Convert", type="primary", disabled=not ready):

    target_config = JournalConfig.load(ids[to_idx], JOURNALS_DIR)

    # Determine output suffix before validate() so we can suppress format-irrelevant warnings
    if fmt_choice == "Word (.docx)":
        out_suffix = ".docx"
    elif fmt_choice == "LaTeX (.tex)":
        out_suffix = ".tex"
    else:
        out_suffix = Path(source_file.name).suffix

    config_issues = validate(target_config)
    if config_issues:
        for issue in config_issues:
            if out_suffix != ".tex" and "LaTeX class" in issue:
                continue  # LaTeX template warnings are irrelevant for DOCX output
            st.warning(f"Config note: {issue}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        source_path = tmp_path / source_file.name
        source_path.write_bytes(source_file.getvalue())

        bib_path = None
        if bib_file:
            bib_path = tmp_path / bib_file.name
            bib_path.write_bytes(bib_file.getvalue())

        suffix = out_suffix
        output_name = f"{source_path.stem}_{ids[to_idx]}{suffix}"
        output_path = tmp_path / output_name

        if not shutil.which("pandoc"):
            st.error(
                "Pandoc is not installed on this server. "
                "If running locally, install it from https://pandoc.org/installing.html"
            )
            st.stop()

        try:
            with st.spinner("Converting…"):
                warnings = convert(source_path, target_config, output_path,
                                   bib=bib_path, preserve_citations=preserve_citations)

            st.success("Conversion complete.")

            # ── Conversion report ─────────────────────────────────────────────
            with st.expander("Conversion notes", expanded=bool(warnings)):
                if warnings:
                    for w in warnings:
                        st.info(w)
                else:
                    st.write("No issues detected.")

                if target_config.word_limit:
                    wc = count_words(output_path)
                    over = wc - target_config.word_limit
                    if over > 0:
                        st.warning(
                            f"Word count: {wc:,} / {target_config.word_limit:,} — "
                            f"**over limit by {over:,} words.** Trim before submission."
                        )
                    else:
                        st.caption(
                            f"Word count: {wc:,} / {target_config.word_limit:,} — "
                            f"within limit ({-over:,} words to spare)."
                        )

            # ── Download ──────────────────────────────────────────────────────
            media_dir = output_path.parent / "media"
            if suffix == ".tex" and media_dir.exists():
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(output_path, output_name)
                    for fig in sorted(media_dir.rglob("*")):
                        if fig.is_file():
                            zf.write(fig, Path("media") / fig.relative_to(media_dir))
                zip_name = output_path.stem + ".zip"
                st.download_button(
                    label=f"Download {zip_name} (LaTeX + figures)",
                    data=buf.getvalue(),
                    file_name=zip_name,
                    mime="application/zip",
                    type="primary",
                )
            else:
                st.download_button(
                    label=f"Download {output_name}",
                    data=output_path.read_bytes(),
                    file_name=output_name,
                    mime=_mime(suffix),
                    type="primary",
                )

        except RuntimeError as exc:
            st.error(f"Conversion failed:\n\n{exc}")

# ── Footer ───────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    "**Citation support** — Citation field preservation currently supports "
    "**Paperpile** only. Zotero, Mendeley, and other reference managers are not yet "
    "supported. [Request support or report a bug]"
    "(https://github.com/yairsuari/journal-converter/issues)"
)
st.caption(f"**Disclaimer** — {DISCLAIMER}")

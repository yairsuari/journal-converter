"""Streamlit GUI for the journal conversion tool."""
import io
import shutil
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

from converter import convert, count_words, JournalConfig, validate

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

# ── File uploaders ────────────────────────────────────────────────────────────

source_file = st.file_uploader("Source document", type=["docx", "tex"],
                                help="Upload the manuscript you want to convert")
bib_file = st.file_uploader("BibTeX file (optional)",  type=["bib"],
                              help="Required for citation reformatting. Export from Paperpile or your reference manager")

# ── Conversion ────────────────────────────────────────────────────────────────

ready = source_file is not None and from_idx != to_idx
if st.button("Convert", type="primary", disabled=not ready):

    target_config = JournalConfig.load(ids[to_idx], JOURNALS_DIR)

    config_issues = validate(target_config)
    if config_issues:
        for issue in config_issues:
            st.warning(f"Config note: {issue}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        source_path = tmp_path / source_file.name
        source_path.write_bytes(source_file.getvalue())

        bib_path = None
        if bib_file:
            bib_path = tmp_path / bib_file.name
            bib_path.write_bytes(bib_file.getvalue())

        suffix = source_path.suffix
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
                warnings = convert(source_path, target_config, output_path, bib=bib_path)

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

# ── Disclaimer ────────────────────────────────────────────────────────────────

st.divider()
st.caption(f"**Disclaimer** — {DISCLAIMER}")

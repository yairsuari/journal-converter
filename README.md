# Journal Converter

Reformat an academic manuscript from one journal's house style to another — citations,
reference list, abstract structure, and (where configured) the document template —
without doing it by hand.

Works on `.docx` and `.tex` manuscripts, plus supplementary material, and is built around
[Pandoc](https://pandoc.org/). Journal support is defined entirely in YAML configs under
[`journals/`](journals/), so adding a new journal doesn't require touching any code.

## Supported journals

| Journal | Publisher | Citation style | Last verified |
|---|---|---|---|
| Hydrology and Earth System Sciences (HESS) | Copernicus | author-year | 2026-06-11 |
| Frontiers in Marine Science | Frontiers | author-year | 2026-06-11 |

Don't see your target journal? See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add one —
it's just a YAML file.

## Install

1. Install [Pandoc](https://pandoc.org/installing.html)
2. Clone this repo and install Python dependencies:
   ```
   git clone https://github.com/yairsuari/journal-converter.git
   cd journal-converter
   pip install -r requirements.txt
   ```

## Usage

### CLI

```
python cli.py source.docx --from hess --to frontiers-marine-science --bib refs.bib
```

Common options:

| Flag | Purpose |
|---|---|
| `--bib FILE` | BibTeX file for citation reformatting |
| `--supplementary, -s FILE` | Convert a supplementary document alongside the manuscript |
| `--format {docx,tex}` | Output format (default: same as source) |
| `--output-dir DIR` | Where to write output files (default: next to the source) |
| `--bib-encoding` | Encoding of the `.bib` file (auto-falls back to `cp1255` on error) |

Output includes the converted document(s) plus a `.conversion-report.txt` listing anything
that needs manual review (missing templates, unmatched citations, figures to replace with
high-resolution originals, word count vs. the target journal's limit).

### GUI

```
streamlit run app.py
```

Upload a manuscript, optional `.bib` file, pick source/target journals, convert, and
download — no command line needed. Also deployable to
[Streamlit Community Cloud](https://streamlit.io/cloud) for sharing with collaborators who
don't want to install anything.

## How it works

- **Core engine** (`converter/core.py`) drives Pandoc for the actual format conversion,
  reformats citations via CSL, extracts figures, and patches LaTeX output (Unicode
  characters Pandoc leaves un-escaped, bare superscripts, figure centering).
- **Journal configs** (`journals/*.yaml`) declare citation style, abstract format, template
  files, and word limits. Publisher-level configs (`journals/publishers/`) hold shared
  defaults so e.g. all Frontiers journals don't repeat the same settings.
- **Citation revival** (`converter/cite_revive.py`) — Pandoc can't read Paperpile's Word
  field codes, so citations land as plain "(Author, Year)" text; this matches them back to
  BibTeX keys and restores live `\citep{}` commands in LaTeX output.
- **CSL manager** (`converter/csl_manager.py`) fetches the latest citation style from the
  CSL registry at runtime, falling back to a bundled pinned version if offline.

## Disclaimer

This tool performs automated reformatting and does not guarantee compliance with a
journal's current submission requirements. **Output must be reviewed manually before
submission.** Journal configurations are community-maintained and may not reflect the most
recent author guidelines — always verify against the target journal's current instructions
for authors.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — adding a new journal is usually just a YAML file
and a pull request.

## License

MIT — see [LICENSE](LICENSE).

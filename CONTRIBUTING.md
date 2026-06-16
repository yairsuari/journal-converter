# Contributing

The main extension point for this project is the `journals/` folder. Adding support for a
new journal should never require touching the core conversion code — it's just a YAML file.

## Adding a new journal

**Fastest path:** run `python add_journal.py` and answer the prompts — it writes the YAML,
runs the validator, and tells you what (if anything) is missing. The CLI also triggers this
automatically if you run a conversion with `--to <unknown-journal-id>`.

To do it by hand instead:

1. Create `journals/<journal-id>.yaml`. Use a short, lowercase, hyphenated ID (e.g.
   `journal-of-hydrology.yaml`).

2. If the journal's publisher already has a base config in `journals/publishers/`, just
   reference it and override what's journal-specific:

   ```yaml
   name: Journal of Hydrology
   publisher: elsevier
   last_verified: "2026-06-16"

   word_limit: 8000
   ```

   If the publisher doesn't have a base config yet, create one (see below) or write the
   full config directly on the journal:

   ```yaml
   name: Some Journal
   last_verified: "2026-06-16"

   citation:
     style: some-csl-style-name
     format: author-year   # author-year | numeric | footnote

   abstract:
     type: unstructured     # or: structured
     # headings: [Background, Methods, Results, Conclusions]  # required if structured

   template:
     word: some-journal-template.docx   # optional, place file in templates/
     latex_cls: some-journal.cls        # optional, place file in templates/

   word_limit: 8000   # optional
   ```

3. Finding the CSL style name: search the
   [CSL style repository](https://github.com/citation-style-language/styles) for the
   journal or publisher. Use the filename without `.csl` as `citation.style`.

4. Run the validator before opening a PR:
   ```
   python -c "from converter import JournalConfig, validate; c = JournalConfig.load('your-journal-id', __import__('pathlib').Path('journals')); print(validate(c) or 'OK')"
   ```

5. Test it against a real (or sample) manuscript with `cli.py` to confirm citations and
   structure come out as expected.

## Adding a publisher base config

If you're adding several journals from the same publisher, create
`journals/publishers/<publisher-id>.yaml` with the shared `citation`, `abstract`, and
`template` settings. Individual journal configs reference it via `publisher: <publisher-id>`
and only need to override what differs.

## Bundling template files

Word reference docs and LaTeX class files go in `templates/`. Only commit a file if its
license is permissive (LPPL, MIT, or equivalent) — check the license header in `.cls`
files. If the license is unclear or restrictive, leave the file out; the converter will
fall back to default styling and warn the user, and your journal config should note where
to download the file from.

## Reporting a problem

Open a GitHub issue using the bug report template. Please anonymise any manuscript excerpt
you attach — replace author names with placeholders, include only the relevant excerpt
(not the full manuscript), and redact unpublished references.

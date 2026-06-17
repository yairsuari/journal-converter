"""Command-line interface for the journal conversion tool."""
import sys
import shutil
import click
from pathlib import Path
from datetime import datetime

from converter import convert, count_words, JournalConfig, validate

JOURNALS_DIR = Path(__file__).parent / "journals"


@click.command()
@click.argument("source", type=click.Path(exists=True, path_type=Path))
@click.option("--from", "from_journal", required=True, metavar="JOURNAL",
              help="Source journal ID (e.g. hess)")
@click.option("--to", "to_journal", required=True, metavar="JOURNAL",
              help="Target journal ID (e.g. frontiers-marine-science)")
@click.option("--bib", type=click.Path(exists=True, path_type=Path), default=None,
              help="BibTeX file for citation reformatting")
@click.option("--supplementary", "-s", type=click.Path(exists=True, path_type=Path), default=None,
              help="Supplementary material document to convert alongside the main manuscript")
@click.option("--bib-encoding", default="utf-8", show_default=True,
              help="Encoding of the .bib file (e.g. utf-8, cp1255). Auto-falls back to cp1255 on error.")
@click.option("--format", "fmt", type=click.Choice(["docx", "tex"]), default=None,
              help="Output format (default: same as source)")
@click.option("--preserve-citations/--no-preserve-citations", default=False,
              help="Re-inject live Paperpile citation fields into the output .docx "
                   "(only applies to .docx -> .docx conversions)")
@click.option("--output-dir", type=click.Path(path_type=Path), default=None,
              help="Directory for output files (default: same folder as source)")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Output path for main document (default: <source>_<to-journal><ext>)")
def main(source: Path, from_journal: str, to_journal: str,
         bib: Path | None, supplementary: Path | None,
         bib_encoding: str, fmt: str | None, preserve_citations: bool,
         output_dir: Path | None, output: Path | None):
    """Convert an academic manuscript from one journal format to another."""
    _check_pandoc()

    try:
        target_config = JournalConfig.load(to_journal, JOURNALS_DIR)
    except FileNotFoundError:
        click.echo(f"No config found for journal '{to_journal}'.")
        if not click.confirm("Create one now?", default=True):
            sys.exit(1)
        from converter.wizard import run_wizard
        new_path = run_wizard(JOURNALS_DIR, suggested_id=to_journal)
        target_config = JournalConfig.load(new_path.stem, JOURNALS_DIR)
        to_journal = new_path.stem

    issues = validate(target_config)
    if issues:
        click.echo("Config warnings for target journal:")
        for issue in issues:
            click.echo(f"  ! {issue}")
        click.echo()

    out_suffix = f".{fmt}" if fmt else source.suffix
    out_dir = output_dir if output_dir else source.parent
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    if output is None:
        output = out_dir / f"{source.stem}_{to_journal}{out_suffix}"

    click.echo(f"Converting  : {source.name}  ->  {output.name}")
    click.echo(f"From        : {from_journal}")
    click.echo(f"To          : {target_config.name}")
    if bib:
        click.echo(f"BibTeX      : {bib.name}")
    if preserve_citations:
        click.echo(f"Citations   : preserve Paperpile fields")
    if supplementary:
        click.echo(f"Supplementary: {supplementary.name}")
    click.echo()

    warnings = convert(source, target_config, output, bib=bib, bib_encoding=bib_encoding,
                       preserve_citations=preserve_citations)

    supp_warnings: list[str] = []
    if supplementary:
        supp_output = output.parent / f"{supplementary.stem}_{to_journal}{output.suffix}"
        supp_warnings = convert(supplementary, target_config, supp_output,
                                bib=bib, bib_encoding=bib_encoding,
                                preserve_citations=preserve_citations)
        click.echo(f"Supplementary : {supp_output}")

    report_path = _write_report(output, from_journal, target_config,
                                warnings, supp_warnings, supplementary)

    click.echo(f"Done. Output  : {output}")
    if warnings or supp_warnings:
        click.echo(f"      Report : {report_path}")


def _check_pandoc():
    from converter.core import _find_pandoc
    try:
        _find_pandoc()
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


def _write_report(output: Path, from_journal: str, target: JournalConfig,
                  warnings: list[str], supp_warnings: list[str] | None = None,
                  supplementary: Path | None = None) -> Path:
    report_path = output.with_name(output.stem + ".conversion-report.txt")
    lines = [
        "Conversion Report",
        f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"From      : {from_journal}",
        f"To        : {target.name}",
        f"Output    : {output.name}",
        "",
    ]
    if warnings:
        lines.append("Main manuscript — items requiring manual review:")
        for w in warnings:
            lines.append(f"  - {w}")
    else:
        lines.append("Main manuscript: no issues detected.")

    if supplementary and supp_warnings is not None:
        lines.append("")
        if supp_warnings:
            lines.append("Supplementary material — items requiring manual review:")
            for w in supp_warnings:
                lines.append(f"  - {w}")
        else:
            lines.append("Supplementary material: no issues detected.")

    if target.word_limit:
        wc = count_words(output)
        over = wc - target.word_limit
        if over > 0:
            status = f"OVER LIMIT by {over:,} words — trim before submission."
        else:
            status = f"within limit ({-over:,} words to spare)."
        lines += [
            "",
            f"Word count: {wc:,} / {target.word_limit:,} words — {status}",
        ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


if __name__ == "__main__":
    main()

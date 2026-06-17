"""Interactive wizard for creating a new journal YAML config.

Lets a user add support for a journal that isn't in journals/ yet, instead
of hitting a dead end. See the "Structural Differences" resolved decision
in docs/journal_conversion_roadmap.html.

`write_journal_config` holds the actual data-assembly logic and is shared
by the CLI wizard (`run_wizard`, prompt-driven) and the Streamlit GUI
(which collects the same fields via widgets).
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import re

import yaml

from .config import JournalConfig
from .validate import validate


def slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug


def load_publisher_data(journals_dir: Path, publisher: str | None) -> dict:
    """Return the raw YAML dict for a publisher base config, or {} if none/missing."""
    if not publisher:
        return {}
    pub_path = journals_dir / "publishers" / f"{publisher}.yaml"
    if not pub_path.exists():
        return {}
    return yaml.safe_load(pub_path.read_text(encoding="utf-8")) or {}


def write_journal_config(
    journals_dir: Path,
    name: str,
    journal_id: str,
    publisher: str | None = None,
    citation_style: str | None = None,
    citation_format: str | None = None,
    abstract_type: str | None = None,
    abstract_headings: list[str] | None = None,
    word_limit: int | None = None,
    template_word: str | None = None,
    template_latex_cls: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Assemble and write a journal config YAML. No prompts — pure data in, file out.

    Raises FileExistsError if the target file exists and overwrite is False.
    """
    journal_id = slugify(journal_id)
    out_path = journals_dir / f"{journal_id}.yaml"
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"'{journal_id}.yaml' already exists")

    data: dict = {"name": name, "last_verified": date.today().isoformat()}
    if publisher:
        data["publisher"] = publisher

    if citation_style:
        data["citation"] = {"style": citation_style, "format": citation_format or "author-year"}

    if abstract_type:
        abstract: dict = {"type": abstract_type}
        if abstract_type == "structured" and abstract_headings:
            abstract["headings"] = abstract_headings
        data["abstract"] = abstract

    if word_limit:
        data["word_limit"] = word_limit

    template: dict = {}
    if template_word:
        template["word"] = template_word
    if template_latex_cls:
        template["latex_cls"] = template_latex_cls
    if template:
        data["template"] = template

    journals_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return out_path


def run_wizard(journals_dir: Path, suggested_id: str | None = None) -> Path:
    """Interactively build a new journal config YAML via terminal prompts."""
    import click

    click.echo()
    click.echo("Let's add this journal to the database.")
    name = click.prompt("Journal name (as it appears on the journal's website)")

    default_id = suggested_id or slugify(name)
    journal_id = slugify(click.prompt("Journal ID (short, lowercase, used with --to)", default=default_id))

    out_path = journals_dir / f"{journal_id}.yaml"
    overwrite = False
    if out_path.exists():
        if not click.confirm(f"'{journal_id}.yaml' already exists. Overwrite?", default=False):
            raise click.Abort()
        overwrite = True

    publishers_dir = journals_dir / "publishers"
    available_publishers = sorted(p.stem for p in publishers_dir.glob("*.yaml")) if publishers_dir.exists() else []
    publisher = None
    if available_publishers:
        click.echo(f"Known publishers: {', '.join(available_publishers)}")
        publisher = click.prompt(
            "Publisher ID (blank if none / not listed)", default="", show_default=False
        ).strip() or None

    pub_data = load_publisher_data(journals_dir, publisher)

    citation_style = citation_format = None
    if "citation" not in pub_data:
        click.echo()
        click.echo("Citation style — find the CSL filename at "
                    "https://github.com/citation-style-language/styles")
        citation_style = click.prompt("CSL style name (filename without .csl)")
        citation_format = click.prompt("Citation format", type=click.Choice(["author-year", "numeric", "footnote"]),
                                        default="author-year")

    abstract_type = None
    abstract_headings: list[str] = []
    if "abstract" not in pub_data:
        click.echo()
        abstract_type = click.prompt("Abstract type", type=click.Choice(["unstructured", "structured"]),
                                      default="unstructured")
        if abstract_type == "structured":
            headings_raw = click.prompt("Structured abstract headings (comma-separated)")
            abstract_headings = [h.strip() for h in headings_raw.split(",") if h.strip()]

    word_limit = None
    if click.confirm("Does this journal have a word limit?", default=False):
        word_limit = click.prompt("Word limit", type=int)

    template_word = template_latex_cls = None
    if "template" not in pub_data and click.confirm("Add a template file reference now?", default=False):
        template_word = click.prompt("Word reference .docx filename (blank to skip)",
                                      default="", show_default=False).strip() or None
        template_latex_cls = click.prompt("LaTeX .cls filename (blank to skip)",
                                           default="", show_default=False).strip() or None

    out_path = write_journal_config(
        journals_dir, name=name, journal_id=journal_id, publisher=publisher,
        citation_style=citation_style, citation_format=citation_format,
        abstract_type=abstract_type, abstract_headings=abstract_headings,
        word_limit=word_limit, template_word=template_word,
        template_latex_cls=template_latex_cls, overwrite=overwrite,
    )

    click.echo()
    click.echo(f"Wrote {out_path}")

    config = JournalConfig.load(journal_id, journals_dir)
    issues = validate(config)
    if issues:
        click.echo("Validation notes:")
        for issue in issues:
            click.echo(f"  ! {issue}")
    else:
        click.echo("Config validated cleanly.")

    click.echo()
    click.echo(
        f"Consider contributing this back: open a pull request adding {out_path.name} "
        "to journals/ on GitHub — see CONTRIBUTING.md for details."
    )

    return out_path

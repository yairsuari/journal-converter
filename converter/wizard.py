"""Interactive wizard for creating a new journal YAML config.

Lets a user add support for a journal that isn't in journals/ yet, instead
of hitting a dead end. See the "Structural Differences" resolved decision
in docs/journal_conversion_roadmap.html.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import re

import click
import yaml

from .config import JournalConfig
from .validate import validate


def _slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug


def run_wizard(journals_dir: Path, suggested_id: str | None = None) -> Path:
    """Interactively build a new journal config YAML. Returns the path written."""
    click.echo()
    click.echo("Let's add this journal to the database.")
    name = click.prompt("Journal name (as it appears on the journal's website)")

    default_id = suggested_id or _slugify(name)
    journal_id = _slugify(click.prompt("Journal ID (short, lowercase, used with --to)", default=default_id))

    out_path = journals_dir / f"{journal_id}.yaml"
    if out_path.exists() and not click.confirm(f"'{journal_id}.yaml' already exists. Overwrite?", default=False):
        raise click.Abort()

    publishers_dir = journals_dir / "publishers"
    available_publishers = sorted(p.stem for p in publishers_dir.glob("*.yaml")) if publishers_dir.exists() else []
    publisher = None
    if available_publishers:
        click.echo(f"Known publishers: {', '.join(available_publishers)}")
        publisher = click.prompt(
            "Publisher ID (blank if none / not listed)", default="", show_default=False
        ).strip() or None

    pub_data: dict = {}
    if publisher and (publishers_dir / f"{publisher}.yaml").exists():
        pub_data = yaml.safe_load((publishers_dir / f"{publisher}.yaml").read_text(encoding="utf-8")) or {}

    data: dict = {"name": name, "last_verified": date.today().isoformat()}
    if publisher:
        data["publisher"] = publisher

    if "citation" not in pub_data:
        click.echo()
        click.echo("Citation style — find the CSL filename at "
                    "https://github.com/citation-style-language/styles")
        style = click.prompt("CSL style name (filename without .csl)")
        fmt = click.prompt("Citation format", type=click.Choice(["author-year", "numeric", "footnote"]),
                            default="author-year")
        data["citation"] = {"style": style, "format": fmt}

    if "abstract" not in pub_data:
        click.echo()
        abstract_type = click.prompt("Abstract type", type=click.Choice(["unstructured", "structured"]),
                                      default="unstructured")
        abstract: dict = {"type": abstract_type}
        if abstract_type == "structured":
            headings_raw = click.prompt("Structured abstract headings (comma-separated)")
            abstract["headings"] = [h.strip() for h in headings_raw.split(",") if h.strip()]
        data["abstract"] = abstract

    if click.confirm("Does this journal have a word limit?", default=False):
        data["word_limit"] = click.prompt("Word limit", type=int)

    if "template" not in pub_data and click.confirm("Add a template file reference now?", default=False):
        template: dict = {}
        word = click.prompt("Word reference .docx filename (blank to skip)",
                             default="", show_default=False).strip()
        if word:
            template["word"] = word
        cls_file = click.prompt("LaTeX .cls filename (blank to skip)",
                                 default="", show_default=False).strip()
        if cls_file:
            template["latex_cls"] = cls_file
        if template:
            data["template"] = template

    journals_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

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

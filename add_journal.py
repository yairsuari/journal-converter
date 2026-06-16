"""Interactively add a new journal to journals/ without doing a conversion.

    python add_journal.py
"""
from pathlib import Path

import click

from converter.wizard import run_wizard

JOURNALS_DIR = Path(__file__).parent / "journals"


@click.command()
def main():
    """Create a new journal YAML config via an interactive wizard."""
    run_wizard(JOURNALS_DIR)


if __name__ == "__main__":
    main()

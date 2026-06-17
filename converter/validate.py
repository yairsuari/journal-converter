from pathlib import Path
from datetime import date
from .config import JournalConfig

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_KNOWN_FORMATS = {"author-year", "numeric", "footnote"}
_KNOWN_ABSTRACT_TYPES = {"unstructured", "structured"}
_STALE_DAYS = 365


def validate(config: JournalConfig) -> list[str]:
    """Return validation issues for a journal config. Empty list means clean."""
    issues = []

    if not config.citation.style:
        issues.append("citation.style is required")

    if config.citation.format not in _KNOWN_FORMATS:
        issues.append(
            f"citation.format '{config.citation.format}' must be one of: "
            + ", ".join(sorted(_KNOWN_FORMATS))
        )

    if config.abstract.type not in _KNOWN_ABSTRACT_TYPES:
        issues.append(
            f"abstract.type '{config.abstract.type}' must be one of: "
            + ", ".join(sorted(_KNOWN_ABSTRACT_TYPES))
        )

    if config.abstract.type == "structured" and not config.abstract.headings:
        issues.append("abstract.headings must be set when abstract.type is 'structured'")

    if config.template.word:
        if not (_TEMPLATES_DIR / config.template.word).exists():
            issues.append(
                f"Word template '{config.template.word}' not found in templates/ — "
                "download it from the journal website and place it there"
            )

    if config.template.pandoc_template:
        if not (_TEMPLATES_DIR / config.template.pandoc_template).exists():
            issues.append(
                f"Pandoc template '{config.template.pandoc_template}' not found in templates/"
            )

    if config.template.latex_cls:
        if not (_TEMPLATES_DIR / config.template.latex_cls).exists():
            issues.append(
                f"LaTeX class '{config.template.latex_cls}' not found in templates/ — "
                "check its license and place it there if redistributable"
            )

    if config.last_verified:
        try:
            verified = date.fromisoformat(config.last_verified)
            age = (date.today() - verified).days
            if age > _STALE_DAYS:
                issues.append(
                    f"Config last verified {age} days ago ({config.last_verified}) — "
                    "check against current journal author guidelines"
                )
        except ValueError:
            issues.append(
                f"last_verified '{config.last_verified}' is not a valid ISO date (YYYY-MM-DD)"
            )

    return issues

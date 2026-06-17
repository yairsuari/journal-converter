from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml


@dataclass
class CitationConfig:
    style: str
    format: str  # author-year | numeric | footnote


@dataclass
class AbstractConfig:
    type: str  # unstructured | structured
    headings: list[str] = field(default_factory=list)


@dataclass
class TemplateConfig:
    word: Optional[str] = None
    latex_cls: Optional[str] = None
    pandoc_template: Optional[str] = None  # full Pandoc .tex template; overrides latex_cls preamble


@dataclass
class JournalConfig:
    name: str
    publisher: str
    citation: CitationConfig
    abstract: AbstractConfig
    template: TemplateConfig
    last_verified: Optional[str] = None
    word_limit: Optional[int] = None
    latex_journal_abbrev: Optional[str] = None  # e.g. "hess" for Copernicus class option

    @classmethod
    def load(cls, journal_id: str, journals_dir: Path) -> JournalConfig:
        journal_path = journals_dir / f"{journal_id}.yaml"
        if not journal_path.exists():
            raise FileNotFoundError(f"No config found for journal '{journal_id}' at {journal_path}")

        data = yaml.safe_load(journal_path.read_text(encoding="utf-8"))

        publisher_id = data.get("publisher")
        if publisher_id:
            pub_path = journals_dir / "publishers" / f"{publisher_id}.yaml"
            if pub_path.exists():
                pub_data = yaml.safe_load(pub_path.read_text(encoding="utf-8"))
                data = _deep_merge(pub_data, data)

        citation_raw = data.get("citation", {})
        abstract_raw = data.get("abstract", {})
        template_raw = data.get("template", {})

        return cls(
            name=data["name"],
            publisher=data.get("publisher", ""),
            citation=CitationConfig(
                style=citation_raw["style"],
                format=citation_raw["format"],
            ),
            abstract=AbstractConfig(
                type=abstract_raw.get("type", "unstructured"),
                headings=abstract_raw.get("headings", []),
            ),
            template=TemplateConfig(
                word=template_raw.get("word"),
                latex_cls=template_raw.get("latex_cls"),
                pandoc_template=template_raw.get("pandoc_template"),
            ),
            last_verified=data.get("last_verified"),
            word_limit=data.get("word_limit"),
            latex_journal_abbrev=data.get("latex_journal_abbrev"),
        )


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result

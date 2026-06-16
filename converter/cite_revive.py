"""
Post-process a pandoc-generated .tex file to replace rendered (Author, Year)
citations with live \\citep{key} commands, using the source .bib file as the key map.

Pandoc cannot read Paperpile's Word field codes, so citations arrive as plain
author-year text.  This module maps them back to BibTeX keys.
"""
import re
from pathlib import Path


# ── BibTeX parsing ────────────────────────────────────────────────────────────

_ENTRY_RE = re.compile(r'@\w+\s*\{([^,]+),(.*?)(?=\n@|\Z)', re.DOTALL)
_AUTHOR_RE = re.compile(r'\bauthor\s*=\s*[{"]([^}"]+)[}"]', re.IGNORECASE)
_YEAR_RE   = re.compile(r'\byear\s*=\s*[{"]?(\d{4})[}"]?', re.IGNORECASE)
_DATE_RE   = re.compile(r'\bdate\s*=\s*[{"]?(\d{4})', re.IGNORECASE)


def _first_author_lastname(author_field: str) -> str:
    first = re.split(r'\s+and\s+', author_field, flags=re.IGNORECASE)[0].strip()
    first = first.replace('{', '').replace('}', '').replace('\\', '')
    if ',' in first:
        return first.split(',')[0].strip()
    parts = first.split()
    return parts[-1].strip() if parts else first


def _parse_bib(bib_text: str) -> dict[tuple[str, str], list[str]]:
    """Return {(lastname_lower, year): [bibtex_key, ...]}."""
    lookup: dict[tuple[str, str], list[str]] = {}
    for m in _ENTRY_RE.finditer(bib_text):
        key  = m.group(1).strip()
        body = m.group(2)
        am = _AUTHOR_RE.search(body)
        ym = _YEAR_RE.search(body) or _DATE_RE.search(body)
        if not am or not ym:
            continue
        lastname = _first_author_lastname(am.group(1)).lower()
        year     = ym.group(1)
        lookup.setdefault((lastname, year), []).append(key)
    return lookup


# ── Citation matching ─────────────────────────────────────────────────────────

# A parenthetical block that contains at least one 4-digit year (DOTALL so \n is matched)
_BLOCK_RE = re.compile(r'\(([^()]*\d{4}[^()]*)\)', re.DOTALL)

# Year at the end of a single citation unit: ", YYYY[a-z]?"
_YEAR_TAIL_RE = re.compile(r',\s*(\d{4})([a-z]?)\s*$')


def _normalize(text: str) -> str:
    """Collapse whitespace (including line breaks) and unescape LaTeX ampersand."""
    text = re.sub(r'\s+', ' ', text)
    text = text.replace(r'\&', 'and')
    return text.strip()


def _lastname_from_namepart(name_part: str) -> str:
    """Extract first author lastname from a name phrase like 'Smith et al.' or 'van Maren'."""
    # Split on ' et al.' (no \b — period ends the token) or ' and ' (word boundary safe)
    first = re.split(r'\s+et\s+al\.|\s+and\b', name_part, flags=re.IGNORECASE)[0].strip()
    words = first.split()
    return words[-1].lower() if words else first.lower()


def _resolve_part(part: str, lookup: dict) -> str | None:
    """Resolve one citation unit (e.g. 'Smith et al., 2020') to a BibTeX key."""
    part = _normalize(part)
    m = _YEAR_TAIL_RE.search(part)
    if not m:
        return None
    year      = m.group(1)
    suffix    = m.group(2)
    name_part = part[:m.start()].strip()
    if not name_part:
        return None
    lastname = _lastname_from_namepart(name_part)
    for y in ([year + suffix, year] if suffix else [year]):
        keys = lookup.get((lastname, y))
        if keys:
            return keys[0] if len(keys) == 1 else None  # None = ambiguous
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def revive(tex_path: Path, bib_path: Path,
           bib_encoding: str = "utf-8") -> tuple[int, list[str]]:
    """
    Replace rendered (Author, Year) citations in tex_path with \\citep{key}.
    Appends \\bibliography{bib_stem} if at least one citation was replaced.
    Returns (n_replaced, unmatched_citation_strings).
    Modifies tex_path in place.
    """
    try:
        bib_text = bib_path.read_text(encoding=bib_encoding)
    except (UnicodeDecodeError, LookupError):
        bib_text = bib_path.read_text(encoding="cp1255")
    lookup = _parse_bib(bib_text)
    text   = tex_path.read_text(encoding='utf-8')

    replaced = 0
    unmatched: list[str] = []

    def replace_block(m: re.Match) -> str:
        nonlocal replaced
        raw_content = _normalize(m.group(1))
        parts = [p.strip() for p in raw_content.split(';')]
        keys: list[str] = []

        for part in parts:
            key = _resolve_part(part, lookup)
            if key is None:
                unmatched.append(_normalize(part))
                return m.group(0)  # leave whole block unchanged if any part fails
            keys.append(key)

        replaced += len(keys)
        return r'\citep{' + ', '.join(keys) + '}'

    new_text = _BLOCK_RE.sub(replace_block, text)

    bib_stem = bib_path.stem
    bib_cmd  = f'\\bibliography{{{bib_stem}}}'
    # Replace any \bibliography{...} Pandoc may have written (often a mangled full path)
    new_text, n_subs = re.subn(r'\\bibliography\{[^}]*\}', bib_cmd, new_text)
    if replaced > 0 and n_subs == 0:
        new_text = new_text.rstrip() + f'\n\n{bib_cmd}\n'

    tex_path.write_text(new_text, encoding='utf-8')
    return replaced, list(dict.fromkeys(unmatched))

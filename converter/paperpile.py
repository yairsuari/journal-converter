"""
Extract Paperpile citation fields from .docx files.

Paperpile stores citation data as Word ADDIN fields with a base64+zlib-compressed
JSON payload containing BibTeX citekeys.  This module decodes those fields to build
a direct rendered-text → citekey map, which cite_revive uses instead of fuzzy
author/year matching against the .bib file.
"""
from __future__ import annotations
import base64
import json
import re
import zlib
from pathlib import Path

_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def _decode_data(b64: str) -> list[dict]:
    padded = b64 + '=' * (4 - len(b64) % 4)
    return json.loads(zlib.decompress(base64.b64decode(padded)))


def _iter_fields(para_elem):
    """Yield (instr_text, rendered_text) for each field in a paragraph element."""
    in_f = past_sep = False
    instr: list[str] = []
    render: list[str] = []
    for child in para_elem.iter():
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag == 'fldChar':
            ft = child.get(f'{{{_NS}}}fldCharType')
            if ft == 'begin':
                in_f, past_sep, instr, render = True, False, [], []
            elif ft == 'separate':
                past_sep = True
            elif ft == 'end' and in_f:
                yield ''.join(instr), ''.join(render)
                in_f = False
        elif tag == 'instrText' and in_f and not past_sep:
            instr.append(child.text or '')
        elif tag == 't' and in_f and past_sep:
            render.append(child.text or '')


def _normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def extract_citation_map(docx_path: Path) -> dict[str, list[str]]:
    """
    Return {normalized_rendered_text: [citekey, ...]} for every Paperpile field.

    Keys include outer parentheses, e.g. '(Smith, 2020)' -> ['Smith2020-ab'].
    Multi-citation fields produce a single entry:
      '(Smith, 2020; Jones, 2021)' -> ['Smith2020-ab', 'Jones2021-xy']
    Returns {} when the source is not a .docx or has no Paperpile fields.
    """
    if docx_path.suffix.lower() != '.docx':
        return {}
    try:
        from docx import Document  # noqa: PLC0415
    except ImportError:
        return {}
    try:
        doc = Document(docx_path)
    except Exception:
        return {}

    result: dict[str, list[str]] = {}
    for para in doc.paragraphs:
        for instr, rendered in _iter_fields(para._p):
            if 'ADDIN paperpile_citation' not in instr:
                continue
            m = re.search(r'<data>(.*?)</data>', instr, re.DOTALL)
            if not m:
                continue
            try:
                citations = _decode_data(m.group(1))
            except Exception:
                continue
            keys = [c.get('citekey') for c in citations if c.get('citekey')]
            if keys and rendered.strip():
                result[_normalize(rendered)] = keys
    return result

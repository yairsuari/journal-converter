"""
Direct paragraph injection from a source .docx into a target journal template.

Instead of using Pandoc's --reference-doc (which rebuilds the document body and
loses logos/images embedded in the template body), this module:
  1. Copies the template verbatim to the output path
  2. Removes template sample content from a configurable cut point
  3. Injects all source body elements (paragraphs, tables, images) in their place
  4. Applies a style map (source style name -> target style name)
"""
from __future__ import annotations
import shutil
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Optional

_W_NS  = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R_NS  = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_W     = f"{{{_W_NS}}}"
_R     = f"{{{_R_NS}}}"

_IMG_RELTYPE   = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
_HYPER_RELTYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"

_EXT_TO_CT: dict[str, str] = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "gif": "image/gif", "tif": "image/tiff", "tiff": "image/tiff",
    "svg": "image/svg+xml", "emf": "image/x-emf", "wmf": "image/x-wmf",
    "bmp": "image/bmp",
}


# ── Public API ────────────────────────────────────────────────────────────────

def build_docx(
    source: Path,
    template: Path,
    output: Path,
    style_map: dict[str, str],
    cut_at_style: Optional[str],
) -> list[str]:
    """
    Build output.docx by injecting source content into the template.

    Returns a list of user-facing warning strings.
    """
    from docx import Document

    warnings: list[str] = []

    shutil.copy(template, output)

    src_doc  = Document(source)
    out_doc  = Document(output)

    # Build relationship map before modifying out_doc
    with zipfile.ZipFile(source, "r") as src_zip:
        rId_map = _build_source_rId_map(src_doc, out_doc, src_zip, warnings)

    out_body = out_doc.element.body
    out_children = list(out_body)

    # The last child of w:body is always w:sectPr (section/page layout).
    # Keep it — it defines margins, page size, headers/footers for the output.
    sect_pr = out_children[-1]
    body_children = out_children[:-1]  # everything except sectPr

    # Find where to cut the template body
    cut_idx = _find_cut_index(body_children, cut_at_style)
    if cut_at_style and cut_idx == len(body_children):
        warnings.append(
            f"word_cut_at_style '{cut_at_style}' not found in template body — "
            "template sample content was not removed. Check the style name in the YAML config."
        )

    # Remove template paragraphs/tables from cut_idx onward
    for child in body_children[cut_idx:]:
        out_body.remove(child)

    # Warn about elements that are not fully handled in v1
    src_body_elems = list(src_doc.element.body)
    if any(e.tag == f"{_W}sectPr" for e in src_body_elems):
        src_body_elems = [e for e in src_body_elems if e.tag != f"{_W}sectPr"]

    has_footnotes = any(
        child.tag in (f"{_W}footnoteReference", f"{_W}endnoteReference")
        for elem in src_body_elems
        for child in elem.iter()
    )
    if has_footnotes:
        warnings.append(
            "Source document contains footnotes/endnotes — these are not carried over "
            "in the direct template injection path. Review the output manually."
        )

    has_num_ids = any(
        child.tag == f"{_W}numId"
        for elem in src_body_elems
        for child in elem.iter()
    )
    if has_num_ids:
        warnings.append(
            "Source document contains numbered lists — list numbering definitions are not "
            "merged in the direct template injection path. Lists may appear without numbers."
        )

    # Inject source elements before sectPr
    for elem in src_body_elems:
        new_elem = deepcopy(elem)
        _apply_style_map(new_elem, style_map)
        _remap_rids(new_elem, rId_map)
        sect_pr.addprevious(new_elem)

    out_doc.save(output)
    return warnings


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_cut_index(body_children: list, cut_at_style: Optional[str]) -> int:
    """Return index of first w:p with pStyle == cut_at_style, or 0 if None, or len if not found."""
    if cut_at_style is None:
        return 0
    for i, child in enumerate(body_children):
        if child.tag != f"{_W}p":
            continue
        p_pr = child.find(f"{_W}pPr")
        if p_pr is None:
            continue
        p_style = p_pr.find(f"{_W}pStyle")
        if p_style is not None and p_style.get(f"{_W}val") == cut_at_style:
            return i
    return len(body_children)


def _apply_style_map(elem, style_map: dict[str, str]) -> None:
    """Remap w:pStyle w:val on every w:p descendant (and the element itself if it's a w:p)."""
    if not style_map:
        return
    targets = [elem] if elem.tag == f"{_W}p" else []
    targets += list(elem.iter(f"{_W}p"))
    for p in targets:
        p_pr = p.find(f"{_W}pPr")
        if p_pr is None:
            continue
        p_style = p_pr.find(f"{_W}pStyle")
        if p_style is None:
            continue
        val = p_style.get(f"{_W}val")
        if val and val in style_map:
            p_style.set(f"{_W}val", style_map[val])


def _remap_rids(elem, rId_map: dict[str, str]) -> None:
    """Replace r:embed / r:id / r:link attribute values using rId_map."""
    if not rId_map:
        return
    attrs = (f"{_R}embed", f"{_R}id", f"{_R}link")
    for node in elem.iter():
        for attr in attrs:
            val = node.get(attr)
            if val and val in rId_map:
                node.set(attr, rId_map[val])


def _build_source_rId_map(
    src_doc,
    out_doc,
    src_zip: zipfile.ZipFile,
    warnings: list[str],
) -> dict[str, str]:
    """
    For every image and external hyperlink in the source document's relationships,
    register a corresponding relationship in the output document.
    Returns {src_rId: out_rId}.
    """
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    rId_map: dict[str, str] = {}
    used_names: set[str] = set()

    for src_rId, rel in src_doc.part.rels.items():
        if rel.reltype == _IMG_RELTYPE and not rel.is_external:
            # e.g. rel.target_ref = "media/image1.png"
            zip_path = "word/" + rel.target_ref
            try:
                img_bytes = src_zip.read(zip_path)
            except KeyError:
                warnings.append(
                    f"Image '{rel.target_ref}' referenced in source but not found in zip — skipped."
                )
                continue

            ext = rel.target_ref.rsplit(".", 1)[-1].lower()
            ct = _EXT_TO_CT.get(ext, f"image/{ext}")

            # Build a unique partname that won't collide with template's images
            stem = Path(rel.target_ref).stem
            candidate = f"/word/media/src_{stem}.{ext}"
            counter = 1
            while candidate in used_names:
                candidate = f"/word/media/src_{stem}_{counter}.{ext}"
                counter += 1
            used_names.add(candidate)

            try:
                from docx.parts.image import ImagePart
                from docx.opc.packuri import PackURI
                new_part = ImagePart(PackURI(candidate), ct, img_bytes)
                new_rId = out_doc.part.relate_to(new_part, RT.IMAGE)
                rId_map[src_rId] = new_rId
            except Exception as exc:
                warnings.append(f"Could not copy image '{rel.target_ref}': {exc}")

        elif rel.reltype == _HYPER_RELTYPE and rel.is_external:
            try:
                new_rId = out_doc.part.relate_to(rel.target_ref, RT.HYPERLINK, is_external=True)
                rId_map[src_rId] = new_rId
            except Exception as exc:
                warnings.append(f"Could not copy hyperlink '{rel.target_ref}': {exc}")

    return rId_map

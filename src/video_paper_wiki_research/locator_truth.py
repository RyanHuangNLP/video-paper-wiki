"""Independent locator truth for staged Docling text nodes.

This is not the engine shape-only locator validator. It checks node/span/
geometry against retained PDF page boxes and prospective source bindings.
"""

from __future__ import annotations

import hashlib
import math
import re
from io import BytesIO
from typing import Any

from video_paper_wiki.ledger_locator import decode_ledger_locator, encode_ledger_locator

from video_paper_wiki_research.contracts import (
    INVENTORY_LIMIT,
    SOURCE_CONTEXT_INVALID,
    SOURCE_CONTEXT_LIMIT,
    ResearchError,
    sha256_bytes,
)

_PAGE_KEY = re.compile(r"^[1-9][0-9]*$")
_TEXT_REF = re.compile(r"^#/texts/(0|[1-9][0-9]*)$")
_ORIGINS = {"TOPLEFT", "BOTTOMLEFT"}


def _fail(message: str, *, code: str = SOURCE_CONTEXT_INVALID) -> None:
    raise ResearchError(code, message)


def _is_int(value: object) -> bool:
    return type(value) is int


def _is_finite_number(value: object) -> bool:
    if type(value) is int:
        return True
    if type(value) is float:
        return math.isfinite(value)
    return False


def as_ratio(value: object) -> tuple[int, int]:
    if type(value) is int:
        return (value, 1)
    if type(value) is float:
        if not math.isfinite(value):
            _fail("coordinate is not a finite number")
        numerator, denominator = value.as_integer_ratio()
        reconstructed = numerator / denominator
        if not math.isfinite(reconstructed) or reconstructed.as_integer_ratio() != (numerator, denominator):
            _fail("coordinate is not exactly representable as binary64")
        return (numerator, denominator)
    _fail("coordinate is not a finite number")
    raise AssertionError("unreachable")


def ratio_le(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] * right[1] <= right[0] * left[1]


def ratio_eq(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] * right[1] == right[0] * left[1]


def pdf_page_geometry(data: bytes, page_count: int) -> dict[int, dict[str, Any]]:
    try:
        from pypdf import PdfReader
        from pypdf.errors import FileNotDecryptedError, PdfReadError, PdfStreamError
    except ImportError as exc:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "PDF parser is unavailable") from exc
    try:
        reader = PdfReader(BytesIO(data))
    except (PdfReadError, PdfStreamError, OSError, ValueError) as exc:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "PDF is not parseable") from exc
    if bool(getattr(reader, "is_encrypted", False)):
        raise ResearchError(SOURCE_CONTEXT_INVALID, "PDF is encrypted")
    try:
        pages = list(reader.pages)
    except FileNotDecryptedError as exc:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "PDF is encrypted") from exc
    if len(pages) != page_count:
        _fail("PDF page count differs from intake")
    geometry: dict[int, dict[str, Any]] = {}
    for index, page in enumerate(pages, start=1):
        rotation = int(getattr(page, "rotation", 0) or 0) % 360
        if rotation != 0:
            _fail("rotated PDF pages are unsupported")
        mediabox = page.mediabox
        cropbox = page.cropbox
        edges = []
        for box in (mediabox, cropbox):
            left = float(box.left)
            bottom = float(box.bottom)
            right = float(box.right)
            top = float(box.top)
            if not all(math.isfinite(item) for item in (left, bottom, right, top)):
                _fail("PDF page box is not finite")
            edges.append((as_ratio(left), as_ratio(bottom), as_ratio(right), as_ratio(top)))
        if edges[0] != edges[1]:
            _fail("CropBox must equal MediaBox")
        left, bottom, right, top = edges[0]
        if not ratio_eq(left, (0, 1)) or not ratio_eq(bottom, (0, 1)):
            _fail("only zero-origin PDF pages are supported")
        width = (right[0] * left[1] - left[0] * right[1], right[1] * left[1])
        height = (top[0] * bottom[1] - bottom[0] * top[1], top[1] * bottom[1])
        # Reduce by converting through float identity of the page size.
        width_f = float(page.mediabox.width)
        height_f = float(page.mediabox.height)
        if not math.isfinite(width_f) or not math.isfinite(height_f) or width_f <= 0 or height_f <= 0:
            _fail("PDF page size is not a positive finite size")
        geometry[index] = {"width": as_ratio(width_f), "height": as_ratio(height_f), "width_f": width_f, "height_f": height_f}
        del width, height
    return geometry


def validate_export_profile(document: object) -> dict[str, Any]:
    if type(document) is not dict:
        _fail("Docling document must be an object")
    texts = document.get("texts")
    pages = document.get("pages")
    if type(texts) is not list:
        _fail("document texts must be a list")
    if type(pages) is not dict:
        _fail("document pages must be an object")
    for key, page in pages.items():
        if type(key) is not str or _PAGE_KEY.fullmatch(key) is None:
            _fail("page keys must be canonical positive decimal strings")
        if type(page) is not dict:
            _fail("page entry must be an object")
        page_no = page.get("page_no")
        size = page.get("size")
        if not _is_int(page_no) or page_no < 1 or str(page_no) != key:
            _fail("page_no must match its canonical page key")
        if type(size) is not dict:
            _fail("page size must be an object")
        width = size.get("width")
        height = size.get("height")
        if not _is_finite_number(width) or not _is_finite_number(height):
            _fail("page size must be finite numbers")
        if type(width) is int and width <= 0 or type(height) is int and height <= 0:
            _fail("page size must be positive")
        if type(width) is float and width <= 0 or type(height) is float and height <= 0:
            _fail("page size must be positive")
    return document


def _bbox_object(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        _fail("bbox must be an object")
    origin = value.get("coord_origin")
    if origin not in _ORIGINS:
        _fail("coord_origin must be TOPLEFT or BOTTOMLEFT")
    out = {}
    for key in ("l", "t", "r", "b"):
        item = value.get(key)
        if not _is_finite_number(item):
            _fail("bbox coordinates must be finite numbers")
        out[key] = item
    out["coord_origin"] = origin
    return out


def external_bbox(bbox: dict[str, Any], height: tuple[int, int], height_f: float) -> list[float | int]:
    origin = bbox["coord_origin"]
    l, t, r, b = bbox["l"], bbox["t"], bbox["r"], bbox["b"]
    if origin == "TOPLEFT":
        return [l, t, r, b]
    # BOTTOMLEFT: [l, H-t, r, H-b]
    h_t = height_f - (t if type(t) is float else float(t))
    h_b = height_f - (b if type(b) is float else float(b))
    if not math.isfinite(h_t) or not math.isfinite(h_b):
        _fail("BOTTOMLEFT bbox is not finite")
    if as_ratio(h_t) != as_ratio(height_f - float(t)) or as_ratio(h_b) != as_ratio(height_f - float(b)):
        _fail("BOTTOMLEFT bbox is not exactly representable")
    return [l, h_t, r, h_b]


def check_bbox(bbox: dict[str, Any], width: tuple[int, int], height: tuple[int, int], width_f: float, height_f: float) -> None:
    l, t, r, b = (as_ratio(bbox[key]) for key in ("l", "t", "r", "b"))
    zero = (0, 1)
    if not (ratio_le(zero, l) and ratio_le(l, r) and ratio_le(r, width)):
        _fail("bbox is outside the page width")
    origin = bbox["coord_origin"]
    if origin == "TOPLEFT":
        if not (ratio_le(zero, t) and ratio_le(t, b) and ratio_le(b, height)):
            _fail("TOPLEFT bbox is outside the page height")
        return
    if not (ratio_le(zero, b) and ratio_le(b, t) and ratio_le(t, height)):
        _fail("BOTTOMLEFT bbox is outside the page height")
    del width_f, height_f


def text_node(document: dict[str, Any], index: int) -> tuple[str, str, list[Any]]:
    texts = document["texts"]
    if index < 0 or index >= len(texts):
        _fail("text node index is out of range")
    node = texts[index]
    if type(node) is not dict:
        _fail("text node must be an object")
    text = node.get("text")
    if type(text) is not str:
        _fail("text node text must be a scalar string")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "text node contains a surrogate") from exc
    ref = f"#/texts/{index}"
    stated = node.get("self_ref")
    if stated is not None:
        if type(stated) is not str or stated != ref:
            _fail("self_ref must match #/texts/N")
    prov = node.get("prov")
    if prov is None:
        return text, ref, []
    if type(prov) is not list:
        _fail("prov must be a list")
    return text, ref, prov


def parse_supported_prov(item: object, *, ref: str) -> dict[str, Any] | None:
    if type(item) is not dict:
        _fail("provenance item must be an object")
    has_supported = any(key in item for key in ("page_no", "charspan", "bbox"))
    if not has_supported:
        return None
    page_no = item.get("page_no")
    charspan = item.get("charspan")
    bbox = item.get("bbox")
    if not _is_int(page_no) or page_no < 1:
        _fail("page_no must be an exact 1-based integer")
    if type(charspan) is not list or len(charspan) != 2 or not all(_is_int(part) for part in charspan):
        _fail("charspan must be two exact integers")
    start, end = charspan
    if not 0 <= start < end:
        _fail("charspan must be a half-open ordered interval")
    box = _bbox_object(bbox)
    return {"page_no": page_no, "charspan": [start, end], "bbox": box, "ref": ref}


def encode_block_locator(
    *,
    source_id: str,
    page: int,
    ref: str,
    bbox: list[float | int],
    charspan: list[int],
    artifact_path: str,
    artifact_sha256: str,
    text: str,
) -> str:
    locator = {
        "kind": "pdf",
        "source_id": source_id,
        "page": page,
        "ref": ref,
        "bbox": bbox,
        "charspan": charspan,
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha256,
        "text_sha256": sha256_bytes(text.encode("utf-8")),
    }
    wire = encode_ledger_locator(locator)
    decoded = decode_ledger_locator(wire)
    if decoded["source_id"] != source_id or decoded["page"] != page or decoded["ref"] != ref:
        _fail("locator wire does not round-trip identity fields")
    if decoded["artifact_path"] != artifact_path or decoded["artifact_sha256"] != artifact_sha256:
        _fail("locator wire does not round-trip artifact bindings")
    if decoded["text_sha256"] != locator["text_sha256"]:
        _fail("locator wire text hash differs")
    return wire


def block_id_for(wire: str) -> str:
    return "mp1-block-" + hashlib.sha256(wire.encode("utf-8")).hexdigest()


def charge_inventory(count: list[int]) -> None:
    count[0] += 1
    if count[0] > INVENTORY_LIMIT:
        raise ResearchError(SOURCE_CONTEXT_LIMIT, "exported node/provenance/omitted inventory exceeds 20000")

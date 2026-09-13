"""Build the small synthetic PDF samples in a process-owned temporary folder."""
from __future__ import annotations

import atexit
import os
from pathlib import Path
import shutil
import tempfile


def _document(objects: list[bytes], marker: bytes) -> bytes:
    data = bytearray(b"%PDF-1.4\n%" + marker + b"\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    xref = len(data)
    count = len(objects) + 1
    data.extend(f"xref\n0 {count}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(
        f"trailer\n<< /Size {count} /Root 1 0 R /Info {len(objects)} 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(data)


def _stream(commands: list[str], *, legacy_length: int | None = None) -> bytes:
    content = ("\n".join(commands) + "\n").encode("ascii")
    length = len(content) if legacy_length is None else legacy_length
    return f"<< /Length {length} >>\nstream\n".encode("ascii") + content + b"endstream"


def sample_pdf_bytes(name: str) -> bytes:
    """Construct a named sample, preserving its historical parser input bytes."""
    if name == "tiny":
        return _document(
            [
                b"<< /Type /Catalog /Pages 2 0 R >>",
                b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
                # The old sample declares 46 bytes for its 47-byte stream.
                # Preserve this parser-recovery input instead of silently fixing it.
                _stream(["BT", "/F1 12 Tf", "72 720 Td", "(Tiny VPKB paper) Tj", "ET"], legacy_length=46),
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
                b"<< /Title (Tiny VPKB paper) >>",
            ],
            marker=bytes((0xE2, 0xE3, 0xCF, 0xD3)),
        )
    if name == "sectioned":
        return _document(
            [
                b"<< /Type /Catalog /Pages 2 0 R >>",
                b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources << /Font << /F1 7 0 R >> >> >>",
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 6 0 R /Resources << /Font << /F1 7 0 R >> >> >>",
                _stream([
                    "BT", "/F1 12 Tf", "18 TL", "72 720 Td",
                    "(Sectioned VPKB Paper) Tj", "T*", "(Abstract) Tj", "T*",
                    "(This abstract sentence is the conclusion claim. Further abstract text remains here.) Tj",
                    "T*", "(1 Introduction) Tj", "T*",
                    "(We study whether a frozen tokenizer is enough.) Tj", "ET",
                ]),
                _stream([
                    "BT", "/F1 12 Tf", "18 TL", "72 720 Td", "(2. Method) Tj", "T*",
                    "(We train a diffusion transformer on video latents.) Tj", "ET",
                ]),
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
                b"<< /Title (Sectioned VPKB Paper) >>",
            ],
            marker=bytes((0x80,)) * 4,
        )
    raise ValueError(f"unknown PDF sample: {name!r}")


_roots: dict[int, Path] = {}


def _cleanup(root: Path, owner_pid: int) -> None:
    # A forked child must never clean up its parent's sample directory.
    if os.getpid() == owner_pid:
        shutil.rmtree(root)


def sample_pdf_path(name: str) -> Path:
    """Return a stable sample path for this process, removed on normal exit."""
    data = sample_pdf_bytes(name)  # Validate before creating any files.
    pid = os.getpid()
    if pid not in _roots:
        root = Path(tempfile.mkdtemp(prefix="vpdf-", dir=Path("/tmp").resolve()))
        _roots[pid] = root
        atexit.register(_cleanup, root, pid)
    path = _roots[pid] / f"{name}.pdf"
    if not path.exists():
        with path.open("xb") as output:
            output.write(data)
    return path

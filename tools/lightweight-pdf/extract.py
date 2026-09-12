#!/usr/bin/env python3
"""Extract a text-based PDF into page-numbered Markdown without model downloads."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import unicodedata

from pypdf import PdfReader


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.pdf.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    targets = (output / "source.md", output / "source.json")
    if any(path.exists() for path in targets):
        raise SystemExit("Source output already exists; select a fresh output directory.")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    reader = PdfReader(source)
    if reader.is_encrypted:
        raise SystemExit("Encrypted PDF: provide an unlocked source file.")
    pages = []
    for number, page in enumerate(reader.pages, 1):
        text = unicodedata.normalize("NFC", page.extract_text() or "")
        text = text.replace("\x00", "").replace("\r\n", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        pages.append((number, text))
    if not any(text for _, text in pages):
        raise SystemExit("No native text found. This lightweight path does not run OCR or download models.")
    lines = [
        f"# {source.stem}", "",
        f"原始 PDF：[本机文件](<{source}>)", "",
        f"SHA-256：`{digest}`", "",
        "按 PDF 文件页码保留原生文本。未运行 OCR、版面模型或表格重建；图中内容可能缺失，多栏、公式和表格的文字顺序需对照原 PDF。", "",
    ]
    for number, text in pages:
        lines.extend([f'<a id="page-{number}"></a>', "", f"## PDF 第 {number} 页", "", text or "（本页无可提取的原生文本）", ""])
    targets[0].write_text("\n".join(lines), encoding="utf-8")
    metadata = {
        "source_path": str(source), "source_sha256": digest,
        "source_bytes": source.stat().st_size,
        "parser": "pypdf-native-text", "parser_version": importlib.metadata.version("pypdf"),
        "page_count": len(pages), "pages_with_text": sum(bool(text) for _, text in pages),
        "models_downloaded": False, "pdf_copied": False, "ocr": False,
        "output": targets[0].name, "output_bytes": targets[0].stat().st_size,
        "output_sha256": hashlib.sha256(targets[0].read_bytes()).hexdigest(),
        "pages": [{"page": number, "characters": len(text), "text_sha256": hashlib.sha256(text.encode()).hexdigest()} for number, text in pages],
    }
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise SystemExit("Source PDF changed during extraction.")
    targets[1].write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: metadata[key] for key in ("page_count", "pages_with_text", "output_bytes", "models_downloaded", "pdf_copied")}, ensure_ascii=False))
    print(targets[0])


if __name__ == "__main__":
    main()

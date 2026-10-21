"""UTF-8 note reads that fail closed. No network."""

from __future__ import annotations

from pathlib import Path


class InvalidEncoding(UnicodeError):
    """Raised when a notes file is not valid UTF-8."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        super().__init__(f"file is not valid UTF-8: {self.path.as_posix()}")


def read_utf8(path: Path) -> str:
    """Read *path* as UTF-8, or raise InvalidEncoding. Does not rewrite the file."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidEncoding(path) from exc

"""Scanning, filename validation, and recoverable rename transactions."""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

SUPPORTED = {".pdf", ".txt", ".md", ".py"}
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TEXT_BYTES = 64 * 1024
MAX_CONTENT_CHARS = 4500
MAX_PDF_PAGES = 3
DEFAULT_LOG = Path.home() / ".lazyrename" / "transactions.json"
INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])$", re.I)


class RenameError(Exception):
    """A safe operation cannot be completed."""


def scan(folder: Path, recursive: bool = False) -> list[Path]:
    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        raise RenameError("Choose an existing folder.")
    try:
        iterator = folder.rglob("*") if recursive else folder.iterdir()
        return sorted(
            (p for p in iterator if p.is_file() and not p.is_symlink() and p.suffix.lower() in SUPPORTED),
            key=lambda p: str(p).casefold(),
        )
    except OSError as exc:
        raise RenameError(f"Cannot scan folder: {exc}") from exc


def extract_content(path: Path) -> str:
    """Read a bounded sample. Never import or execute scanned content."""
    try:
        size = path.stat().st_size
        if size == 0:
            raise RenameError("Empty file")
        if size > MAX_FILE_BYTES:
            raise RenameError("File exceeds the 25 MB safety limit")
        if path.suffix.lower() == ".pdf":
            import pymupdf

            with pymupdf.open(path) as document:
                if document.is_encrypted:
                    raise RenameError("Encrypted PDF")
                chunks = []
                for page_index in range(min(len(document), MAX_PDF_PAGES)):
                    chunks.append(document[page_index].get_text()[:MAX_CONTENT_CHARS])
                    if sum(map(len, chunks)) >= MAX_CONTENT_CHARS:
                        break
                content = "\n".join(chunks)[:MAX_CONTENT_CHARS]
        else:
            with path.open("rb") as stream:
                raw = stream.read(MAX_TEXT_BYTES)
            if b"\x00" in raw:
                raise RenameError("Binary content")
            content = raw.decode("utf-8", errors="replace")[:MAX_CONTENT_CHARS]
        content = " ".join(content.split())
        if not content:
            raise RenameError("No extractable text")
        return content
    except RenameError:
        raise
    except Exception as exc:
        raise RenameError(f"Cannot read file: {exc}") from exc


def sanitize_stem(value: str) -> str:
    """Turn a model title into a safe Windows-compatible filename stem."""
    value = value.strip().strip("`\"'")
    if not value:
        raise RenameError("Model returned an empty filename")
    value = re.sub(r"(?i)^filename\s*:\s*", "", value).splitlines()[0]
    value = INVALID.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    value = value[:90].rstrip(" .")
    if not value or value in {".", ".."} or _reserved_windows_name(value):
        raise RenameError("Model returned an unusable filename")
    return value


def _reserved_windows_name(name: str) -> bool:
    return bool(RESERVED.fullmatch(name.split(".", 1)[0].rstrip(" .")))


def validate_target_name(source: Path, target_name: str) -> str:
    if not isinstance(target_name, str) or not target_name:
        raise RenameError("Filename is empty")
    if target_name != target_name.strip() or target_name.endswith((" ", ".")):
        raise RenameError("Filename has leading/trailing spaces or a trailing dot")
    if INVALID.search(target_name) or target_name in {".", ".."}:
        raise RenameError("Filename contains invalid Windows characters")
    if _reserved_windows_name(target_name):
        raise RenameError("Filename is reserved on Windows")
    if len(target_name) > 180:
        raise RenameError("Filename is too long")
    if Path(target_name).suffix != source.suffix or not source.suffix:
        raise RenameError("Keep the original extension")
    return target_name


def _key(path: Path) -> str:
    return str(path).casefold()


def _existing_casefold(directory: Path) -> set[str]:
    return {p.name.casefold() for p in directory.iterdir()}


def prepare_plan(rows: list[dict]) -> list[dict]:
    """Validate every selected move before any file is touched."""
    plan = []
    destinations = set()
    existing_by_dir = {}
    for row in rows:
        source = Path(row["source"])
        if source.is_symlink() or not source.is_file():
            raise RenameError(f"Source is missing or a symlink: {source}")
        target_name = validate_target_name(source, row["target_name"])
        if source.name == target_name:
            continue
        directory = source.parent
        if directory not in existing_by_dir:
            existing_by_dir[directory] = _existing_casefold(directory)
        target = directory / target_name
        if target_name.casefold() in existing_by_dir[directory]:
            raise RenameError(f"Destination already exists: {target}")
        if _key(target) in destinations:
            raise RenameError(f"Two files would have the same destination: {target}")
        destinations.add(_key(target))
        stat = source.stat()
        if "size" in row and (stat.st_size != row["size"] or stat.st_mtime_ns != row["mtime_ns"]):
            raise RenameError(f"Source changed since preview: {source}")
        plan.append({"source": str(source), "target": str(target), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    return plan


def _save_log(log_path: Path, data: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = log_path.with_name(log_path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, log_path)


def load_log(log_path: Path = DEFAULT_LOG) -> dict:
    if not log_path.exists():
        return {"version": 1, "batches": []}
    try:
        data = json.loads(log_path.read_text(encoding="utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("batches"), list):
            raise ValueError("Unsupported transaction log")
        return data
    except (OSError, ValueError) as exc:
        raise RenameError(f"Cannot read transaction log: {exc}") from exc


def _move_no_overwrite(source: Path, target: Path) -> None:
    """Rename without replacing an existing destination on any platform."""
    if target.exists() or target.is_symlink():
        raise RenameError(f"Destination already exists: {target}")
    if sys.platform == "win32":
        # Windows os.rename fails when target exists, including a concurrent arrival.
        os.rename(source, target)
    else:
        # Hard-link creation is atomic and fails if target exists. Both paths share a directory.
        os.link(source, target, follow_symlinks=False)
        try:
            os.unlink(source)
        except OSError:
            os.unlink(target)
            raise


def apply_batch(rows: list[dict], log_path: Path = DEFAULT_LOG) -> dict:
    plan = prepare_plan(rows)
    if not plan:
        raise RenameError("No changes selected")
    data = load_log(log_path)
    batch = {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
             "state": "in_progress", "moves": [dict(move, state="pending") for move in plan]}
    data["batches"].append(batch)
    _save_log(log_path, data)
    try:
        for move in batch["moves"]:
            source, target = Path(move["source"]), Path(move["target"])
            if source.is_symlink() or not source.is_file():
                raise RenameError(f"Source disappeared: {source}")
            stat = source.stat()
            if stat.st_size != move["size"] or stat.st_mtime_ns != move["mtime_ns"]:
                raise RenameError(f"Source changed: {source}")
            _move_no_overwrite(source, target)
            move["state"] = "done"
            _save_log(log_path, data)
        batch["state"] = "applied"
        _save_log(log_path, data)
        return batch
    except (OSError, RenameError) as exc:
        batch["state"] = "interrupted"
        _save_log(log_path, data)
        raise RenameError(f"Batch stopped: {exc}. Completed moves remain in the log for undo.") from exc


def latest_undoable(log_path: Path = DEFAULT_LOG) -> dict | None:
    for batch in reversed(load_log(log_path)["batches"]):
        if batch["state"] in {"applied", "interrupted", "in_progress"}:
            return batch
    return None


def undo_latest(log_path: Path = DEFAULT_LOG) -> dict:
    data = load_log(log_path)
    batch = next((b for b in reversed(data["batches"]) if b["state"] in
                  {"applied", "interrupted", "in_progress"}), None)
    if batch is None:
        raise RenameError("No rename batch is available to undo")
    # An interrupted process may have moved a file before it could update the log.
    for move in batch["moves"]:
        if move["state"] == "pending" and Path(move["source"]).exists() and Path(move["target"]).exists():
            raise RenameError(f"Cannot resolve interrupted move; both paths exist: {move['source']} and {move['target']}")
    moves = [m for m in batch["moves"] if m["state"] == "done" or
             (m["state"] == "pending" and not Path(m["source"]).exists() and Path(m["target"]).exists())]
    for move in moves:
        original, current = Path(move["source"]), Path(move["target"])
        if not current.is_file() or current.is_symlink():
            raise RenameError(f"Renamed file is missing: {current}")
        if original.exists() or original.is_symlink() or original.name.casefold() in _existing_casefold(original.parent):
            raise RenameError(f"Cannot undo; original name is occupied: {original}")
        stat = current.stat()
        if stat.st_size != move["size"] or stat.st_mtime_ns != move["mtime_ns"]:
            raise RenameError(f"Cannot undo; renamed file changed: {current}")
    try:
        for move in reversed(moves):
            _move_no_overwrite(Path(move["target"]), Path(move["source"]))
            move["state"] = "undone"
            _save_log(log_path, data)
        batch["state"] = "undone"
        _save_log(log_path, data)
        return batch
    except OSError as exc:
        _save_log(log_path, data)
        raise RenameError(f"Undo stopped: {exc}. Retry after resolving the issue.") from exc

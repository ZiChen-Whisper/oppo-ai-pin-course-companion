"""Build a centralized, metadata-only index of one course's materials."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


LOCK_NAME = ".registry.lock"
LOCK_TIMEOUT_SECONDS = 15.0
LOCK_POLL_SECONDS = 0.05
MAX_MARKDOWN_BYTES = 512 * 1024
PROTECTED_MARKERS = (
    "do not read without permission",
    "do not read without premission",
)
IGNORED_DIRECTORY_NAMES = {".git", "node_modules", ".venv", "oppo-ai-pin"}
SUPPORTED_EXTENSIONS = {
    ".md", ".markdown", ".pdf", ".ppt", ".pptx", ".key",
    ".doc", ".docx", ".odt", ".rtf", ".txt", ".html", ".htm",
    ".xls", ".xlsx", ".ods", ".csv", ".ipynb", ".py", ".java",
    ".c", ".cpp", ".h", ".cs", ".js", ".ts", ".sql", ".r",
    ".m", ".sh", ".ps1", ".zip",
}
LAB_HINTS = ("lab", "实验", "作业", "assignment", "homework", "实验报告")
SLIDE_HINTS = ("slide", "slides", "课件", "演示", "presentation", "lecture")
SLIDE_EXTENSIONS = {".ppt", ".pptx", ".key"}
COURSE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
ATX_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
TEXTBOOK_HINTS = ("textbook", "课本", "教材", "电子书")


class IndexingError(RuntimeError):
    """Raised when the registry or course roots cannot be indexed safely."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _is_protected_name(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in PROTECTED_MARKERS)


def _safe_course_id(course_id: str) -> str:
    if not isinstance(course_id, str) or not COURSE_ID_RE.fullmatch(course_id):
        raise IndexingError(f"Invalid course id: {course_id!r}")
    return course_id


def _read_registry(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            registry = json.load(stream)
    except FileNotFoundError as exc:
        raise IndexingError(f"Registry not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise IndexingError(f"Cannot read registry {path}: {exc}") from exc
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise IndexingError("registry.json must be an object with schema_version: 1")
    if not isinstance(registry.get("revision"), int) or not isinstance(registry.get("courses"), list):
        raise IndexingError("registry.json must contain integer revision and courses array")
    return registry


def _atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class _RegistryLock:
    """Cross-process lock shared with the service through O_EXCL creation."""

    def __init__(self, path: Path, timeout: float = LOCK_TIMEOUT_SECONDS):
        self.path = path
        self.timeout = timeout
        self.owned = False

    def __enter__(self) -> "_RegistryLock":
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                self.owned = True
                with os.fdopen(fd, "w", encoding="ascii") as stream:
                    stream.write(f"pid={os.getpid()}\n")
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise IndexingError(f"Timed out waiting for registry lock: {self.path}")
                time.sleep(LOCK_POLL_SECONDS)
            except OSError as exc:
                raise IndexingError(f"Cannot create registry lock {self.path}: {exc}") from exc

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.owned:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


def _resolve_roots(data_root: Path, course: dict[str, Any]) -> list[Path]:
    root_values = [course.get("root"), *(course.get("extra_roots") or [])]
    roots: list[Path] = []
    seen: set[str] = set()
    for value in root_values:
        if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
            if value is None and roots:
                continue
            raise IndexingError(f"Course {course.get('id')} has an invalid root")
        raw = Path(value).expanduser()
        if raw.is_symlink():
            raise IndexingError(f"Course root cannot be a symbolic link: {raw}")
        resolved = (data_root / raw).resolve() if not raw.is_absolute() else raw.resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise IndexingError(f"Course root does not exist or is not a directory: {resolved}")
        if resolved.is_symlink():
            raise IndexingError(f"Course root cannot be a symbolic link: {resolved}")
        key = os.path.normcase(str(resolved))
        if key not in seen:
            roots.append(resolved)
            seen.add(key)
    if not roots:
        raise IndexingError(f"Course {course.get('id')} has no valid roots")
    return roots


def _walk_files(roots: list[Path]) -> Iterator[Path]:
    for root in roots:
        if _is_protected_name(root.name):
            continue
        for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            kept_dirs = []
            for dirname in dirs:
                directory = current_path / dirname
                if dirname.casefold() in IGNORED_DIRECTORY_NAMES or _is_protected_name(dirname):
                    continue
                if directory.is_symlink():
                    continue
                kept_dirs.append(dirname)
            dirs[:] = kept_dirs
            for filename in files:
                candidate = current_path / filename
                if _is_protected_name(filename) or candidate.is_symlink():
                    continue
                if candidate.suffix.casefold() in SUPPORTED_EXTENSIONS:
                    yield candidate


def _classify(path: Path) -> str:
    pieces = [part.casefold() for part in path.parts]
    joined = "/".join(pieces)
    if any(hint in joined for hint in LAB_HINTS):
        return "lab"
    if path.suffix.casefold() in {".md", ".markdown"}:
        return "textbook-markdown" if any(hint in joined for hint in TEXTBOOK_HINTS) else "other"
    if path.suffix.casefold() in SLIDE_EXTENSIONS or any(hint in joined for hint in SLIDE_HINTS):
        return "slides"
    return "other"


def _markdown_details(path: Path) -> tuple[str, list[str], str | None]:
    headings: list[str] = []
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_MARKDOWN_BYTES + 1)
        truncated = len(raw) > MAX_MARKDOWN_BYTES
        text = raw[:MAX_MARKDOWN_BYTES].decode("utf-8-sig", errors="replace")
    except OSError as exc:
        return path.stem, headings, f"Could not read Markdown headings from {path}: {exc}"
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```") or line.lstrip().startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = ATX_HEADING_RE.match(line)
        if match:
            heading = match.group(2).strip()
            if heading:
                headings.append(heading)
    title = next((h for h in headings if h), path.stem)
    warning = f"Markdown heading scan limited to first {MAX_MARKDOWN_BYTES} bytes: {path}" if truncated else None
    return title, headings, warning


def _load_existing_index(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
        if isinstance(value, dict) and isinstance(value.get("files"), list):
            return value
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        pass
    return {}


def _existing_notes(index: dict[str, Any]) -> dict[str, Any]:
    notes: dict[str, Any] = {}
    for item in index.get("files", []):
        if not isinstance(item, dict) or "notes" not in item or not item.get("path"):
            continue
        try:
            key = os.path.normcase(str(Path(item["path"]).resolve()))
        except (OSError, TypeError, ValueError):
            continue
        notes[key] = item["notes"]
    return notes


def index_course(data_root: Path, course_id: str) -> dict[str, Any]:
    """Index supported files for a single course, updating registry revision.

    Roots are read only from the selected course's registry entry. Registry
    ``materials`` entries are deliberately left untouched; only file metadata
    and Markdown headings are stored in the generated course index.
    """
    course_id = _safe_course_id(course_id)
    data_root = Path(data_root).expanduser().resolve()
    registry_path = data_root / "registry.json"
    indexes_dir = data_root / "indexes"
    index_path = indexes_dir / f"{course_id}.json"

    # Validate roots before changing any generated data. This preserves a prior
    # index and timestamp when the configured course directory has gone away.
    initial_registry = _read_registry(registry_path)
    matches = [course for course in initial_registry["courses"] if isinstance(course, dict) and course.get("id") == course_id]
    if len(matches) != 1:
        raise IndexingError(f"Expected exactly one registry course with id {course_id!r}, found {len(matches)}")
    roots = _resolve_roots(data_root, matches[0])

    with _RegistryLock(data_root / LOCK_NAME):
        # Reload under the shared lock to avoid losing concurrent registry edits.
        registry = _read_registry(registry_path)
        matches = [course for course in registry["courses"] if isinstance(course, dict) and course.get("id") == course_id]
        if len(matches) != 1:
            raise IndexingError(f"Expected exactly one registry course with id {course_id!r}, found {len(matches)}")
        course = matches[0]
        roots = _resolve_roots(data_root, course)
        old_index = _load_existing_index(index_path)
        notes_by_path = _existing_notes(old_index)
        files: list[dict[str, Any]] = []
        warnings: list[str] = []

        for file_path in _walk_files(roots):
            absolute_path = file_path.resolve()
            stat = file_path.stat()
            relative_root = next((root for root in roots if absolute_path.is_relative_to(root)), roots[0])
            relative_path = absolute_path.relative_to(relative_root).as_posix()
            title = file_path.stem
            headings: list[str] = []
            if file_path.suffix.casefold() in {".md", ".markdown"}:
                title, headings, warning = _markdown_details(file_path)
                if warning:
                    warnings.append(warning)
            item: dict[str, Any] = {
                "path": str(absolute_path),
                "relative_path": relative_path,
                "name": file_path.name,
                "type": _classify(file_path),
                "title": title,
                "headings": headings,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
            note_key = os.path.normcase(str(absolute_path))
            if note_key in notes_by_path:
                item["notes"] = notes_by_path[note_key]
            files.append(item)

        files.sort(key=lambda item: (item["path"].casefold(), item["path"]))
        indexed_at = _now_iso()
        result = {
            "course_id": course_id,
            "indexed_at": indexed_at,
            "roots": [str(root) for root in roots],
            "files": files,
            "warnings": warnings,
        }
        _atomic_json_write(index_path, result)
        course["last_indexed_at"] = indexed_at
        registry["revision"] += 1
        _atomic_json_write(registry_path, registry)
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only index for one course")
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--course-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = index_course(args.data_root, args.course_id)
    except IndexingError as exc:
        parser.error(str(exc))
    print(json.dumps({"course_id": result["course_id"], "indexed_at": result["indexed_at"], "file_count": len(result["files"]), "warnings": result["warnings"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

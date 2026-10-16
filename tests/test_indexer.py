from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


INDEXER_PATH = Path(__file__).parents[1] / "runtime" / "indexer.py"
SPEC = importlib.util.spec_from_file_location("oppo_course_indexer", INDEXER_PATH)
indexer = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(indexer)


class CourseIndexerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.data_root = self.base / "data"
        self.course_root = self.base / "course"
        self.data_root.mkdir()
        self.course_root.mkdir()
        self.registry_path = self.data_root / "registry.json"
        self.registry = {
            "schema_version": 1,
            "revision": 4,
            "courses": [{
                "id": "cs101", "name": "CS101", "aliases": [], "semester": "2026 Fall",
                "teacher": "", "notes": "", "root": str(self.course_root), "extra_roots": [],
                "schedule": [], "materials": [{"path": "manually-selected.pdf", "label": "hand picked"}],
                "last_indexed_at": None,
            }],
        }
        self.registry_path.write_text(json.dumps(self.registry, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_indexes_metadata_headings_and_preserves_manual_data_and_notes(self) -> None:
        chapter = self.course_root / "Textbook.md"
        chapter.write_text("# Main Title\n\n## First Chapter\nBody must not be copied.\n", encoding="utf-8")
        ordinary_markdown = self.course_root / "notes.md"
        ordinary_markdown.write_text("# Meeting Notes\n", encoding="utf-8")
        (self.course_root / "教材").mkdir()
        (self.course_root / "教材" / "chapter.md").write_text("# Chapter\n", encoding="utf-8")
        (self.course_root / "slides.pptx").write_bytes(b"not parsed")
        (self.course_root / "misc.pdf").write_bytes(b"pdf bytes are not parsed")

        first = indexer.index_course(self.data_root, "cs101")
        self.assertRegex(first["indexed_at"], r"^\d{4}-\d\d-\d\dT.*\.\d{6}Z$")
        self.assertEqual({"textbook-markdown", "slides", "other"}, {item["type"] for item in first["files"]})
        markdown = next(item for item in first["files"] if item["name"] == "Textbook.md")
        self.assertEqual("other", next(item for item in first["files"] if item["name"] == "notes.md")["type"])
        self.assertEqual("textbook-markdown", next(item for item in first["files"] if item["name"] == "chapter.md")["type"])
        self.assertEqual("Main Title", markdown["title"])
        self.assertEqual(["Main Title", "First Chapter"], markdown["headings"])
        self.assertNotIn("Body must not be copied", json.dumps(first, ensure_ascii=False))

        old_index_path = self.data_root / "indexes" / "cs101.json"
        old_index = json.loads(old_index_path.read_text(encoding="utf-8"))
        markdown_old = next(item for item in old_index["files"] if item["name"] == "Textbook.md")
        markdown_old["notes"] = "review later"
        old_index_path.write_text(json.dumps(old_index), encoding="utf-8")
        second = indexer.index_course(self.data_root, "cs101")
        markdown = next(item for item in second["files"] if item["name"] == "Textbook.md")
        self.assertEqual("review later", markdown["notes"])
        saved_registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(6, saved_registry["revision"])
        self.assertEqual(self.registry["courses"][0]["materials"], saved_registry["courses"][0]["materials"])
        self.assertEqual(second["indexed_at"], saved_registry["courses"][0]["last_indexed_at"])

    def test_skips_protected_generated_and_dependency_paths(self) -> None:
        (self.course_root / "DO NOT READ WITHOUT PERMISSION").mkdir()
        (self.course_root / "DO NOT READ WITHOUT PERMISSION" / "secret.md").write_text("# secret", encoding="utf-8")
        (self.course_root / "OPPO-AI-Pin").mkdir()
        (self.course_root / "OPPO-AI-Pin" / "generated.md").write_text("# generated", encoding="utf-8")
        (self.course_root / "node_modules").mkdir()
        (self.course_root / "node_modules" / "pkg.md").write_text("# dep", encoding="utf-8")
        (self.course_root / "DO NOT READ WITHOUT PREMISSION.md").write_text("secret", encoding="utf-8")
        (self.course_root / "ok.md").write_text("# allowed", encoding="utf-8")
        result = indexer.index_course(self.data_root, "cs101")
        self.assertEqual(["ok.md"], [item["name"] for item in result["files"]])

    def test_missing_root_fails_without_changing_prior_index_or_timestamp(self) -> None:
        old_index_path = self.data_root / "indexes" / "cs101.json"
        old_index_path.parent.mkdir()
        old_index_path.write_text('{"course_id":"cs101","files":[],"indexed_at":"old"}', encoding="utf-8")
        original_registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        original_registry["courses"][0]["last_indexed_at"] = "old"
        self.registry_path.write_text(json.dumps(original_registry), encoding="utf-8")
        original_index = old_index_path.read_text(encoding="utf-8")
        self.course_root.rmdir()
        with self.assertRaises(indexer.IndexingError):
            indexer.index_course(self.data_root, "cs101")
        self.assertEqual(original_index, old_index_path.read_text(encoding="utf-8"))
        current = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual("old", current["courses"][0]["last_indexed_at"])

    def test_rejects_unknown_course_and_invalid_id(self) -> None:
        with self.assertRaises(indexer.IndexingError):
            indexer.index_course(self.data_root, "../escape")
        with self.assertRaises(indexer.IndexingError):
            indexer.index_course(self.data_root, "a.b")
        with self.assertRaises(indexer.IndexingError):
            indexer.index_course(self.data_root, "x" * 81)
        self.assertEqual("_valid-1", indexer._safe_course_id("_valid-1"))
        with self.assertRaises(indexer.IndexingError):
            indexer.index_course(self.data_root, "missing")


if __name__ == "__main__":
    unittest.main()

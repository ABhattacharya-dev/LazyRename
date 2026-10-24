import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lazyrename.core import (RenameError, apply_batch, extract_content, load_log,
                             prepare_plan, sanitize_stem, undo_latest, validate_target_name)


class FilenameTests(unittest.TestCase):
    def test_sanitizes_model_output(self):
        self.assertEqual(sanitize_stem('Filename: "Quarterly: sales / forecast?"'),
                         "Quarterly sales forecast")
        with self.assertRaises(RenameError):
            sanitize_stem("CON")
        with self.assertRaises(RenameError):
            sanitize_stem("")
        with self.assertRaises(RenameError):
            sanitize_stem("... ")

    def test_rejects_invalid_target_and_extension_change(self):
        source = Path("a.pdf")
        for value in ["bad?.pdf", "CON.pdf", "CON .pdf", "report.txt", "report.PDF",
                      "report.pdf ", "folder/report.pdf"]:
            with self.subTest(value=value), self.assertRaises(RenameError):
                validate_target_name(source, value)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / "log.json"
        self.first = self.root / "a.txt"
        self.first.write_text("A meaningful note", encoding="utf-8")

    def row(self, path, target):
        stat = path.stat()
        return {"source": str(path), "target_name": target,
                "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}

    def test_collision_with_existing_file_never_overwrites(self):
        occupied = self.root / "Taken.txt"
        occupied.write_text("keep me", encoding="utf-8")
        with self.assertRaises(RenameError):
            apply_batch([self.row(self.first, "taken.txt")], self.log)
        self.assertEqual(occupied.read_text(), "keep me")
        self.assertTrue(self.first.exists())
        self.assertFalse(self.log.exists())

    def test_duplicate_destination_rejected_before_move(self):
        other = self.root / "b.txt"
        other.write_text("Other", encoding="utf-8")
        with self.assertRaises(RenameError):
            prepare_plan([self.row(self.first, "same.txt"), self.row(other, "SAME.txt")])
        self.assertTrue(self.first.exists())
        self.assertTrue(other.exists())

    def test_apply_and_undo_latest_batch(self):
        batch = apply_batch([self.row(self.first, "Meaningful note.txt")], self.log)
        renamed = self.root / "Meaningful note.txt"
        self.assertFalse(self.first.exists())
        self.assertEqual(renamed.read_text(), "A meaningful note")
        self.assertEqual(batch["state"], "applied")
        undone = undo_latest(self.log)
        self.assertEqual(undone["state"], "undone")
        self.assertTrue(self.first.exists())
        self.assertFalse(renamed.exists())
        self.assertEqual(load_log(self.log)["batches"][-1]["state"], "undone")

    def test_undo_collision_keeps_both_files(self):
        apply_batch([self.row(self.first, "Meaningful note.txt")], self.log)
        self.first.write_text("new arrival", encoding="utf-8")
        with self.assertRaises(RenameError):
            undo_latest(self.log)
        self.assertEqual(self.first.read_text(), "new arrival")
        self.assertEqual((self.root / "Meaningful note.txt").read_text(), "A meaningful note")

    def test_interrupted_batch_can_undo_completed_move(self):
        other = self.root / "b.txt"
        other.write_text("Other", encoding="utf-8")
        from lazyrename import core

        actual_move = core._move_no_overwrite
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated move failure")
            actual_move(source, target)

        with patch.object(core, "_move_no_overwrite", side_effect=fail_second):
            with self.assertRaises(RenameError):
                apply_batch([self.row(self.first, "First note.txt"),
                             self.row(other, "Second note.txt")], self.log)
        self.assertTrue((self.root / "First note.txt").exists())
        self.assertTrue(other.exists())
        undo_latest(self.log)
        self.assertTrue(self.first.exists())
        self.assertFalse((self.root / "First note.txt").exists())

    def test_changed_source_since_preview_rejected(self):
        row = self.row(self.first, "Renamed.txt")
        self.first.write_text("Modified content", encoding="utf-8")
        with self.assertRaises(RenameError):
            apply_batch([row], self.log)
        self.assertTrue(self.first.exists())

    def test_empty_and_binary_content(self):
        empty = self.root / "empty.txt"
        empty.touch()
        binary = self.root / "binary.txt"
        binary.write_bytes(b"hello\x00world")
        for path in (empty, binary):
            with self.subTest(path=path), self.assertRaises(RenameError):
                extract_content(path)

    def test_pdf_text_and_encryption(self):
        import pymupdf

        document = pymupdf.open()
        document.new_page().insert_text((72, 72), "Readable local PDF content")
        plain = self.root / "plain.pdf"
        encrypted = self.root / "encrypted.pdf"
        document.save(plain)
        document.save(encrypted, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                      owner_pw="owner-secret", user_pw="user-secret")
        document.close()
        self.assertIn("Readable local PDF content", extract_content(plain))
        with self.assertRaisesRegex(RenameError, "Encrypted PDF"):
            extract_content(encrypted)


if __name__ == "__main__":
    unittest.main()

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("update_catalog", Path(__file__).with_name("update_catalog.py"))
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def file(fid, name, mime="application/pdf"):
    return {"id": fid, "name": name, "mimeType": mime,
            "webViewLink": "https://drive.google.com/file/d/" + fid + "/view"}


def catalog():
    return {"updated_at": "2026-11-18", "whats_new": [{"date": "2026-11-18", "title": "履歴", "description": "残す"}],
            "courses": [{"name": "薬剤学2", "term": "2026年度 後期", "lessons": [
                {"name": "第2回", "files": ["講義.pdf"], "file_links": {
                    "講義.pdf": "https://drive.google.com/file/d/old_doc/view?usp=drivesdk"}}]}]}


class FakeDrive:
    def __init__(self, tree, failure=None):
        self.tree = tree
        self.failure = failure

    def get(self, fid):
        if fid not in self.tree:
            raise PermissionError("folder unavailable")
        return {"id": fid, "mimeType": updater.FOLDER}

    def children(self, fid):
        if fid == self.failure:
            raise PermissionError("folder unavailable")
        yield from self.tree[fid]


class CatalogUpdateTests(unittest.TestCase):
    def test_nested_scan_preserves_links_and_finds_practice_files(self):
        tree = {
            "term": [file("course", "薬剤学2", updater.FOLDER)],
            "course": [file("lesson", "第2回", updater.FOLDER)],
            "lesson": [file("old_doc", "講義.pdf"), file("new_doc", "補足.pdf")],
            "practice": [file("guide", "00_案内.txt", "text/plain"), file("p", "物理化学", updater.FOLDER)],
            "p": [file("p1", "項目1", updater.FOLDER)],
            "p1": [file("data", "測定.xlsx")],
        }
        result = updater.scan_drive(FakeDrive(tree), catalog(), (
            ("term", "2026年度 後期", None), ("practice", "2026年度 後期", "実習データ")))
        output, diff = updater.build_catalog(catalog(), result)
        self.assertEqual(len(diff["added"]), 3)
        self.assertEqual(len(diff["removed"]), 0)
        self.assertEqual(len(updater.validate(output)), 4)
        lesson = output["courses"][0]["lessons"][0]
        self.assertEqual(lesson["files"][0], "講義.pdf")
        self.assertEqual(lesson["file_links"]["講義.pdf"], catalog()["courses"][0]["lessons"][0]["file_links"]["講義.pdf"])
        self.assertIn("物理化学：項目1", [l["name"] for l in output["courses"][1]["lessons"]])

    def test_unchanged_scan_preserves_date_history_and_order(self):
        original = catalog()
        courses = copy.deepcopy(original["courses"])
        output, diff = updater.build_catalog(original, courses)
        self.assertIs(output, original)
        self.assertEqual(diff, {"added": [], "removed": [], "changed": []})

    def test_rename_move_and_removal_are_reported(self):
        previous = catalog()
        extra = previous["courses"][0]["lessons"][0]
        extra["files"].append("削除.pdf")
        extra["file_links"]["削除.pdf"] = "https://drive.google.com/file/d/remove_doc/view"
        courses = [{"name": "薬剤学2", "term": "2026年度 後期", "lessons": [{
            "name": "第3回", "files": ["改名.pdf"], "file_links": {
                "改名.pdf": "https://drive.google.com/file/d/old_doc/view?usp=drivesdk"}}]}]
        output, diff = updater.build_catalog(previous, courses)
        self.assertEqual(len(diff["changed"]), 1)
        self.assertEqual(len(diff["removed"]), 1)
        self.assertEqual(output["whats_new"][1:], previous["whats_new"])

    def test_failed_scan_does_not_return_partial_results(self):
        tree = {"term": [file("course", "薬剤学2", updater.FOLDER)], "course": [file("old_doc", "講義.pdf")]}
        with self.assertRaises(PermissionError):
            updater.scan_drive(FakeDrive(tree, "course"), catalog(), (("term", "2026年度 後期", None),))

    def test_same_named_files_in_one_lesson_fail_instead_of_losing_a_link(self):
        tree = {"root": [file("one", "同名.pdf"), file("two", "同名.pdf")]}
        with self.assertRaisesRegex(ValueError, "同名"):
            updater.scan_drive(FakeDrive(tree), catalog(), (("root", "2026年度 後期", "実習データ"),))

    def test_shortcut_uses_its_own_id(self):
        shortcut = file("shortcut", "教科書", updater.SHORTCUT)
        shortcut["webViewLink"] = "https://drive.google.com/file/d/target/view"
        courses = updater.scan_drive(FakeDrive({"root": [shortcut]}), catalog(), (("root", "2026年度 後期", "実習データ"),))
        self.assertEqual(updater.file_id(courses[0]["lessons"][0]["file_links"]["教科書"]), "shortcut")

    def test_empty_or_duplicate_catalog_is_rejected(self):
        with self.assertRaises(ValueError):
            updater.validate(dict(catalog(), courses=[]))
        broken = catalog()
        broken["courses"].append(copy.deepcopy(broken["courses"][0]))
        with self.assertRaises(ValueError):
            updater.validate(broken)

    def test_success_creates_backup_log_and_updates_dist(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, state = Path(directory) / "repo", Path(directory) / "state"
            (repo / "data").mkdir(parents=True)
            (repo / "dist" / "data").mkdir(parents=True)
            expected = json.dumps(catalog()).encode()
            (repo / "data" / "catalog.json").write_bytes(expected)
            (repo / "dist" / "data" / "catalog.json").write_bytes(b"old dist")
            backup = updater.save_catalog(repo, catalog(), {"added": [], "removed": [], "changed": []}, state, expected)
            self.assertEqual((backup / "data" / "catalog.json").read_bytes(), expected)
            self.assertEqual((repo / "data" / "catalog.json").read_bytes(), (repo / "dist" / "data" / "catalog.json").read_bytes())
            self.assertEqual(len(list((state / "logs").glob("*.json"))), 1)

    def test_dist_write_failure_restores_both_catalogs(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, state = Path(directory) / "repo", Path(directory) / "state"
            (repo / "data").mkdir(parents=True)
            (repo / "dist" / "data").mkdir(parents=True)
            expected = json.dumps(catalog()).encode()
            target, dist = repo / "data" / "catalog.json", repo / "dist" / "data" / "catalog.json"
            target.write_bytes(expected)
            dist.write_bytes(b"old dist")
            candidate = copy.deepcopy(catalog())
            candidate["updated_at"] = "2026-11-19"
            real_write = updater.atomic_write
            failed = False
            def fail_dist(path, content):
                nonlocal failed
                if Path(path) == dist and not failed:
                    failed = True
                    raise OSError("simulated failure")
                return real_write(path, content)
            with patch.object(updater, "atomic_write", side_effect=fail_dist):
                with self.assertRaises(OSError):
                    updater.save_catalog(repo, candidate, {}, state, expected)
            self.assertEqual(target.read_bytes(), expected)
            self.assertEqual(dist.read_bytes(), b"old dist")

    def test_concurrent_catalog_edit_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "data").mkdir()
            target = repo / "data" / "catalog.json"
            target.write_bytes(b"user edit")
            with self.assertRaisesRegex(ValueError, "スキャン中"):
                updater.save_catalog(repo, catalog(), {}, repo / "state", b"previous")
            self.assertEqual(target.read_bytes(), b"user edit")

    def test_retry_discards_partial_page_yields(self):
        class Transient(Exception):
            transient = True
        attempts = []
        def operation():
            attempts.append(1)
            if len(attempts) == 1:
                raise Transient()
            return ["complete"]
        with patch.object(updater.time, "sleep"):
            self.assertEqual(updater.read_retry(operation), ["complete"])
        self.assertEqual(len(attempts), 2)


if __name__ == "__main__":
    unittest.main()

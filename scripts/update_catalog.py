"""Read Drive metadata using Arg_Sys_Desk's existing Google authentication.

Python 3.11+, standard library only. This utility never mutates Drive files.
It writes only the site's catalogs and private local backups/logs.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlsplit

FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"
JST = timezone(timedelta(hours=9))
ROOTS = (
    ("1sPR5GZXzGD5pQfhOMu2HjP2fC77FofFG", "2026年度 後期", None),
    ("1Ie9yN0zG2yOC7OgO9a4jlF7YcJjdvOdW", "2026年度 前期", None),
    ("1mNaJYSltQtf2aP3hGkt5Qsvwqloj0F0A", "2026年度 後期", "実習データ"),
)
_run_state = None


def natural(value):
    return [(1, int(x)) if x.isdecimal() else (0, x.casefold())
            for x in re.split(r"(\d+)", value)]


def file_id(url):
    parts = urlsplit(url)
    match = re.search(r"/d/([A-Za-z0-9_-]+)(?:/|$)", parts.path)
    if match:
        return match.group(1)
    return parse_qs(parts.query).get("id", [None])[0]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def catalog_files(catalog):
    result = {}
    for course in catalog["courses"]:
        for lesson in course["lessons"]:
            for name in lesson["files"]:
                url = lesson["file_links"][name]
                fid = file_id(url)
                if not fid or fid in result:
                    raise ValueError("一覧のファイルIDが不明、または重複しています: " + name)
                result[fid] = (course["name"], course["term"], lesson["name"], name, url)
    return result


def validate(catalog):
    if not isinstance(catalog, dict) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", catalog.get("updated_at", "")):
        raise ValueError("更新日が不正です")
    if not isinstance(catalog.get("whats_new"), list) or not isinstance(catalog.get("courses"), list):
        raise ValueError("catalog の構造が不正です")
    course_keys = set()
    for course in catalog["courses"]:
        key = (course["name"], course["term"])
        if not all(key) or key in course_keys or not course["lessons"]:
            raise ValueError("科目が空、または重複しています")
        course_keys.add(key)
        lessons = set()
        for lesson in course["lessons"]:
            if not lesson["name"] or lesson["name"] in lessons:
                raise ValueError("項目名が空、または重複しています")
            lessons.add(lesson["name"])
            names = lesson["files"]
            if not isinstance(names, list) or any(not isinstance(n, str) or not n for n in names):
                raise ValueError("ファイル名の構造が不正です")
            if len(names) != len(set(names)) or set(names) != set(lesson["file_links"]):
                raise ValueError("同じ項目のファイル名が重複、またはリンクが不一致です")
            for url in lesson["file_links"].values():
                parts = urlsplit(url)
                if parts.scheme != "https" or parts.hostname not in {"drive.google.com", "docs.google.com"}:
                    raise ValueError("Google Drive 以外のリンクが含まれています")
    result = catalog_files(catalog)
    if not result:
        raise ValueError("空の一覧で既存データを上書きしません")
    return result


def read_retry(function):
    """Only read requests are retried. Authentication is handled by the manager."""
    for attempt in range(4):
        try:
            return function()
        except Exception as error:
            if attempt == 3 or not getattr(error, "transient", False):
                raise
            time.sleep(2 ** attempt)


def scan_drive(api, previous, roots=ROOTS):
    old_files = catalog_files(previous)
    seen_folders, seen_files = set(), set()
    courses = []
    scanned = 0

    def children(folder_id):
        nonlocal scanned
        if folder_id in seen_folders:
            raise ValueError("フォルダの循環・重複を検出しました")
        seen_folders.add(folder_id)
        scanned += 1
        # Materialize inside the retry so an interrupted page iteration restarts cleanly.
        return sorted(read_retry(lambda: list(api.children(folder_id))), key=lambda f: natural(f["name"]))

    def walk(course, folder_id, parts):
        items = children(folder_id)
        files = [f for f in items if f["mimeType"] != FOLDER and not f.get("trashed")]
        if files:
            label = "：".join(parts) if parts else ("案内・ファイル一覧・log" if course["name"] == "実習データ" else "共通")
            lesson = {"name": label, "files": [], "file_links": {}}
            for item in files:
                fid, name = item["id"], item["name"]
                if fid in seen_files:
                    raise ValueError("複数箇所に同一ファイルが含まれています: " + name)
                seen_files.add(fid)
                if name in lesson["file_links"]:
                    raise ValueError("同じ項目に同名ファイルがあります。Driveで名前を区別してください: " + name)
                # Keep stable existing links. Shortcut links use their own ID, not their target.
                url = old_files[fid][4] if fid in old_files else (
                    item.get("webViewLink") if item["mimeType"] != SHORTCUT else None)
                url = url or ("https://drive.google.com/file/d/" + fid + "/view")
                lesson["files"].append(name)
                lesson["file_links"][name] = url
            course["lessons"].append(lesson)
        for item in items:
            if item["mimeType"] == FOLDER and not item.get("trashed"):
                walk(course, item["id"], parts + [item["name"]])

    for root_id, term, course_name in roots:
        metadata = read_retry(lambda: api.get(root_id))
        if metadata.get("mimeType") != FOLDER or metadata.get("trashed"):
            raise ValueError("対象フォルダを読み取れません: " + root_id)
        if course_name:
            course = {"name": course_name, "term": term, "lessons": []}
            walk(course, root_id, [])
            if course["lessons"]:
                courses.append(course)
        else:
            for item in children(root_id):
                if item["mimeType"] == FOLDER and not item.get("trashed"):
                    course = {"name": item["name"], "term": term, "lessons": []}
                    walk(course, item["id"], [])
                    if course["lessons"]:
                        courses.append(course)
    print(f"読み取り完了: {scanned}フォルダ")
    return courses


def build_catalog(previous, courses, now=None):
    # Preserve established display order; append newly discovered entries naturally.
    courses = json.loads(json.dumps(courses, ensure_ascii=False))
    old_order = {(c["name"], c["term"]): i for i, c in enumerate(previous["courses"])}
    old_courses = {(c["name"], c["term"]): c for c in previous["courses"]}
    courses.sort(key=lambda c: (old_order.get((c["name"], c["term"]), len(old_order)), natural(c["name"]), c["term"]))
    for course in courses:
        old = old_courses.get((course["name"], course["term"]), {"lessons": []})
        lesson_order = {l["name"]: i for i, l in enumerate(old["lessons"])}
        old_lessons = {l["name"]: l for l in old["lessons"]}
        course["lessons"].sort(key=lambda l: (lesson_order.get(l["name"], len(lesson_order)), natural(l["name"])))
        for lesson in course["lessons"]:
            order = {n: i for i, n in enumerate(old_lessons.get(lesson["name"], {}).get("files", []))}
            lesson["files"].sort(key=lambda n: (order.get(n, len(order)), natural(n)))
            lesson["file_links"] = {n: lesson["file_links"][n] for n in lesson["files"]}
    candidate = dict(previous, courses=courses)
    before, after = validate(previous), validate(candidate)
    added, removed = sorted(after.keys() - before.keys()), sorted(before.keys() - after.keys())
    changed = sorted(fid for fid in before.keys() & after.keys() if before[fid] != after[fid])
    difference = {"added": [after[k] for k in added], "removed": [before[k] for k in removed],
                  "changed": [{"before": before[k], "after": after[k]} for k in changed]}
    if added or removed or changed:
        date = (now or datetime.now(JST)).strftime("%Y-%m-%d")
        candidate["updated_at"] = date
        candidate["whats_new"] = [{
            "date": date, "title": "資料一覧を更新しました",
            "description": f"追加{len(added)}件、削除{len(removed)}件、名称・分類・リンク変更{len(changed)}件を反映しました。{len(courses)}分類・{len(after)}件を掲載しています。"
        }] + previous["whats_new"]
    else:
        # A repeated scan is a true no-op; preserve date/history and JSON ordering.
        candidate = previous
    validate(candidate)
    return candidate, difference


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save_catalog(repo, catalog, difference, state, expected):
    """Back up every replaced file. Roll back both catalogs if an update fails."""
    repo, state = Path(repo), Path(state)
    target = repo / "data" / "catalog.json"
    if target.read_bytes() != expected:
        raise ValueError("スキャン中にcatalog.jsonが変更されました。再実行してください")
    payload = (json.dumps(catalog, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if json.loads(expected.decode("utf-8-sig")) == catalog:
        payload = expected
    stamp = datetime.now(JST).strftime("%Y%m%d-%H%M%S-%f")
    targets = [target]
    if (repo / "dist").is_dir():
        targets.append(repo / "dist" / "data" / "catalog.json")
    state.mkdir(parents=True, exist_ok=True)
    backup = state / "backups" / stamp
    backup.mkdir(parents=True)
    old = {p: p.read_bytes() if p.exists() else None for p in targets}
    for p, data in old.items():
        if data is not None:
            atomic_write(backup / p.relative_to(repo), data)
    modified = []
    try:
        for p in targets:
            if old[p] != payload:
                modified.append(p)
                atomic_write(p, payload)
        entry = {"timestamp": datetime.now(JST).isoformat(), "status": "updated" if modified else "unchanged",
                 "courses": len(catalog["courses"]), "files": len(catalog_files(catalog)),
                 "backup": str(backup), **difference}
        # One file per execution avoids corrupting another process's append operation.
        atomic_write(state / "logs" / (stamp + ".json"),
                     (json.dumps(entry, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    except BaseException:
        for p in reversed(modified):
            if old[p] is None:
                p.unlink(missing_ok=True)
            else:
                atomic_write(p, old[p])
        raise
    return backup


@contextmanager
def manager_lock(directory):
    # Use the desktop manager's own lock so token refresh cannot race its login.
    import msvcrt
    path = directory / "app.lock"
    with path.open("a+b") as lock:
        lock.seek(0)
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise ValueError("Arg_Sys_Desk が起動しています。閉じてから再実行してください") from error
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def main(argv=None):
    global _run_state
    parser = argparse.ArgumentParser(description="DriveからArg_Sys_pagesのcatalog.jsonを更新")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manager", type=Path, help="Arg_Sys_Deskのフォルダ（既定：サイトの隣）")
    parser.add_argument("--state-dir", type=Path, help="バックアップ・logの保存先")
    parser.add_argument("--dry-run", action="store_true", help="読み取り・差分表示のみ")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    identifier = hashlib.sha256(str(repo).casefold().encode()).hexdigest()[:12]
    state = args.state_dir or Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ArgSysPages" / identifier
    _run_state = state
    manager = (args.manager or repo.parent / "Arg_Sys_Desk").resolve()
    local = manager / "local"
    auth = local / "data"
    if not (repo / "data" / "catalog.json").is_file():
        raise ValueError("Arg_Sys_pagesの直下に解凍して実行してください。data/catalog.jsonが見つかりません")
    if not (local / "arglocal" / "google_api.py").is_file() or not (auth / "token.bin").is_file() or not (auth / "client_secret.json").is_file():
        raise ValueError("Arg_Sys_Deskの認証が見つかりません。先にArg_Sys_DeskでGoogle認証を完了してください。別の場所の場合は --manager で指定できます")
    if os.name != "nt":
        raise ValueError("この認証連携はWindows用です")
    expected = (repo / "data" / "catalog.json").read_bytes()
    previous = json.loads(expected.decode("utf-8-sig"))
    validate(previous)
    # Import only the authentication/HTTP adapter. No manager UI or database is started.
    sys.path.insert(0, str(local))
    from arglocal.google_api import Google, OAuth
    with manager_lock(auth):
        oauth = OAuth(auth)
        if not oauth.token:
            raise ValueError("保存済みGoogle認証を読み取れません。同じWindowsユーザーでArg_Sys_DeskのGoogle認証をやり直してください")
        courses = scan_drive(Google(oauth), previous)
        candidate, difference = build_catalog(previous, courses)
        print(f"追加 {len(difference['added'])} / 削除 {len(difference['removed'])} / 変更 {len(difference['changed'])}")
        print(f"合計 {len(candidate['courses'])}分類 / {len(catalog_files(candidate))}件")
        if args.dry_run:
            print("確認のみ。JSONは変更していません。")
            return 0
        backup = save_catalog(repo, candidate, difference, state, expected)
        print("更新完了: " + str(repo / "data" / "catalog.json"))
        print("バックアップ: " + str(backup))
        print("実行log: " + str(state / "logs"))
        print("GitHubへの反映は通常どおりcommit/pushしてください。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        if _run_state is not None:
            try:
                stamp = datetime.now(JST).strftime("%Y%m%d-%H%M%S-%f")
                entry = {"timestamp": datetime.now(JST).isoformat(), "status": "failed", "error": str(error)}
                atomic_write(_run_state / "logs" / (stamp + ".json"),
                             (json.dumps(entry, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            except OSError:
                print("実行logの保存先にも書き込めませんでした。", file=sys.stderr)
        print("エラー: " + str(error), file=sys.stderr)
        raise SystemExit(1)

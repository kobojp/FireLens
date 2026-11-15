"""Launcher failures and the identified schema-14 root exclusion migration."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.app import db
from backend.app.settings import get_setting


def test_root_scoped_exclusions_isolate_scan_tree_and_write_guards(tmp_path, monkeypatch):
    from backend.app.scanner import scan_root
    from backend.app.settings import SettingsError, excluded_root_folders, save_root_exclusions
    from backend.app.storage import StorageError, create_year_folder
    from backend.app.tree import build_tree

    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "data"))
    path = tmp_path / "data" / "firelens.sqlite3"
    db.initialize_database(path)
    with db.connect(path) as conn:
        roots = []
        for name in ["A", "B"]:
            source = tmp_path / name
            (source / "水帶" / "設備").mkdir(parents=True)
            with conn:
                roots.append(
                    conn.execute(
                        "INSERT INTO root(label,path) VALUES (?,?)", (name, str(source))
                    ).lastrowid
                )
        save_root_exclusions(conn, roots[0], ["水帶"])
        assert "水帶" in excluded_root_folders(conn, roots[0])
        assert "水帶" not in excluded_root_folders(conn, roots[1])
        scan_root(conn, roots[0])
        scan_root(conn, roots[1])
        assert not build_tree(conn, roots[0])
        assert build_tree(conn, roots[1])[0]["label"] == "水帶"
        code = conn.execute("SELECT code FROM category WHERE name='水帶'").fetchone()[0]
        with pytest.raises(StorageError, match="排除"):
            create_year_folder(conn, roots[0], code, "2027年")
        before = get_setting(conn, "excluded_root_folders_by_root")
        with pytest.raises(SettingsError):
            save_root_exclusions(conn, roots[0], ["../outside"])
        assert get_setting(conn, "excluded_root_folders_by_root") == before
        assert (tmp_path / "A" / "水帶" / "設備").is_dir()


def test_root_exclusion_api_preserves_other_roots_and_does_not_inherit(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app.config import get_database_path
    from backend.app.main import create_app

    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "api"))
    with TestClient(create_app()) as client:
        with db.connect(get_database_path()) as conn:
            for i in range(1, 3):
                conn.execute(
                    "INSERT INTO root(id,label,path) VALUES (?,?,?)",
                    (i, str(i), str(tmp_path / str(i))),
                )
        assert (
            client.put("/api/roots/1/excluded-folders", json={"names": ["水帶"]}).status_code == 200
        )
        assert client.get("/api/roots/2/excluded-folder-names").json()["names"] == []
        assert (
            client.put("/api/roots/2/excluded-folders", json={"names": ["備份"]}).status_code == 200
        )
        assert client.get("/api/roots/1/excluded-folder-names").json()["names"] == ["水帶"]
        assert (
            client.put("/api/roots/1/excluded-folders", json={"names": ["../bad"]}).status_code
            == 400
        )
        assert client.get("/api/roots/1/excluded-folder-names").json()["names"] == ["水帶"]
        assert client.get("/api/roots/999/excluded-folder-names").status_code == 404


def test_known_schema14_opens_without_downgrading_or_changing_saved_exclusions(tmp_path):
    path = tmp_path / "known.sqlite3"
    db.initialize_database(path)
    mapping = {"1": ["合成排除"]}
    with db.connect(path) as conn:
        conn.execute("PRAGMA user_version=14")
        conn.execute(
            "INSERT OR REPLACE INTO setting(key,value_json) VALUES (?,?)",
            ("excluded_root_folders_by_root", json.dumps(mapping)),
        )
    db.initialize_database(path)
    with db.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 14
        assert get_setting(conn, "excluded_root_folders_by_root") == mapping


def test_migration14_freezes_old_exclusions_only_for_existing_roots(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    db.initialize_database(path)
    with db.connect(path) as conn:
        first = conn.execute(
            "INSERT INTO root(label,path) VALUES ('A',?)", (str(tmp_path / "A"),)
        ).lastrowid
        conn.execute(
            "INSERT OR REPLACE INTO setting(key,value_json) VALUES (?,?)",
            ("excluded_root_folders", '["不掃描"]'),
        )
        conn.execute("DELETE FROM setting WHERE key='excluded_root_folders_by_root'")
        conn.execute("PRAGMA user_version=13")
    db.initialize_database(path)
    with db.connect(path) as conn:
        assert get_setting(conn, "excluded_root_folders_by_root") == {str(first): ["不掃描"]}
        assert get_setting(conn, "excluded_root_folders") == ["不掃描"]
        conn.execute("INSERT INTO root(label,path) VALUES ('B',?)", (str(tmp_path / "B"),))
    db.initialize_database(path)
    with db.connect(path) as conn:
        assert get_setting(conn, "excluded_root_folders_by_root") == {str(first): ["不掃描"]}


def test_unknown_future_schema_still_rejected_without_mutating_db(tmp_path):
    path = tmp_path / "future.sqlite3"
    db.initialize_database(path)
    with db.connect(path) as conn:
        conn.execute("PRAGMA user_version=15")
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="15"):
        db.initialize_database(path)
    assert path.read_bytes() == before


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell launcher")
@pytest.mark.parametrize("stage", ["npm_ci", "npm_build", "uv_sync", "uv_run", "success"])
def test_right_click_launcher_reports_failure_and_stops_at_failed_command(tmp_path, stage):
    project = tmp_path / "合成 專案"
    project.mkdir()
    (project / "frontend").mkdir()
    source = Path(__file__).resolve().parents[1] / "run-desktop.ps1"
    launcher = project / source.name
    shutil.copyfile(source, launcher)
    commands = tmp_path / "commands"
    commands.mkdir()
    for name, matches in {
        "npm": [("ci", "npm_ci"), ("run", "npm_build")],
        "uv": [("sync", "uv_sync"), ("run", "uv_run")],
    }.items():
        script = "@echo off\necho " + name + ' %*>>"%FIRELENS_LAUNCH_CALL_LOG%"\n'
        for argument, failure in matches:
            script += f'if "%FIRELENS_FAIL_STAGE%"=="{failure}" if "%~1"=="{argument}" exit /b 37\n'
        script += "exit /b 0\n"
        (commands / f"{name}.cmd").write_text(script, encoding="ascii")
    calls = tmp_path / "calls.txt"
    data = tmp_path / "data"
    env = dict(
        os.environ,
        PATH=str(commands) + os.pathsep + os.environ["PATH"],
        FIRELENS_FAIL_STAGE=stage,
        FIRELENS_LAUNCH_CALL_LOG=str(calls),
        FIRELENS_DATA_DIR=str(data),
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(launcher),
            "-NoPause",
        ],
        env=env,
        capture_output=True,
        timeout=20,
    )
    actual = calls.read_text().splitlines()
    expected = [
        "npm ci",
        "npm run build",
        "uv sync --locked",
        "uv run --locked python -m desktop.main",
    ]
    if stage == "success":
        assert result.returncode == 0
        assert actual == expected
    else:
        assert result.returncode == 37, result.stdout + result.stderr
        assert actual == expected[: ["npm_ci", "npm_build", "uv_sync", "uv_run"].index(stage) + 1]
        assert list((data / "logs").glob("desktop-launch-*.log"))

from __future__ import annotations

from pathlib import Path

import backend.app.config as config
from backend.app.config import DB_FILENAME, get_database_path
from backend.app.db import connect, initialize_database


def _set_installed_environment(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    install_dir = tmp_path / "installed" / "FireLens"
    local_app_data = tmp_path / "localappdata"
    monkeypatch.delenv("FIRELENS_DATA_DIR", raising=False)
    monkeypatch.setenv("FIRELENS_INSTALL_DIR", str(install_dir))
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    return install_dir, local_app_data


def test_installed_database_lives_under_install_directory(monkeypatch, tmp_path: Path) -> None:
    install_dir, _ = _set_installed_environment(monkeypatch, tmp_path)
    assert get_database_path() == install_dir / "data" / DB_FILENAME


def test_data_dir_override_still_wins(monkeypatch, tmp_path: Path) -> None:
    install_dir, _ = _set_installed_environment(monkeypatch, tmp_path)
    override = tmp_path / "self-test-data"
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(override))
    assert get_database_path() == override / DB_FILENAME
    assert get_database_path() != install_dir / "data" / DB_FILENAME


def test_pre_installer_portable_exe_keeps_legacy_database_location(
    monkeypatch, tmp_path: Path
) -> None:
    portable_dir = tmp_path / "downloads"
    portable_dir.mkdir()
    local_app_data = tmp_path / "localappdata"
    monkeypatch.delenv("FIRELENS_DATA_DIR", raising=False)
    monkeypatch.delenv("FIRELENS_INSTALL_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(config.os, "name", "nt")
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "executable", str(portable_dir / "FireLens.exe"))

    assert config.get_install_dir() is None
    assert get_database_path() == local_app_data / "FireLens" / DB_FILENAME


def test_installer_marker_enables_install_directory_database(monkeypatch, tmp_path: Path) -> None:
    install_dir = tmp_path / "installed" / "FireLens"
    install_dir.mkdir(parents=True)
    (install_dir / config.INSTALL_MARKER_FILENAME).write_text("installed", encoding="utf-8")
    monkeypatch.delenv("FIRELENS_DATA_DIR", raising=False)
    monkeypatch.delenv("FIRELENS_INSTALL_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.setattr(config.os, "name", "nt")
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "executable", str(install_dir / "FireLens.exe"))

    assert config.get_install_dir() == install_dir
    assert get_database_path() == install_dir / "data" / DB_FILENAME


def test_legacy_database_is_copied_safely_on_first_installed_launch(
    monkeypatch, tmp_path: Path
) -> None:
    install_dir, local_app_data = _set_installed_environment(monkeypatch, tmp_path)
    legacy = local_app_data / "FireLens" / DB_FILENAME
    initialize_database(legacy)
    conn = connect(legacy)
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO setting(key, value_json) "
                "VALUES ('migration-proof', '\"kept\"')"
            )
    finally:
        conn.close()

    target = initialize_database()
    assert target == install_dir / "data" / DB_FILENAME
    assert legacy.is_file(), "舊版資料庫必須保留，作為搬遷失敗時的回復來源"
    migrated = connect(target)
    try:
        row = migrated.execute(
            "SELECT value_json FROM setting WHERE key='migration-proof'"
        ).fetchone()
        assert row is not None
        assert row[0] == '"kept"'
        assert migrated.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        migrated.close()


def test_existing_install_database_is_never_overwritten_by_legacy(
    monkeypatch, tmp_path: Path
) -> None:
    install_dir, local_app_data = _set_installed_environment(monkeypatch, tmp_path)
    target = install_dir / "data" / DB_FILENAME
    legacy = local_app_data / "FireLens" / DB_FILENAME
    initialize_database(target)
    initialize_database(legacy)

    target_conn = connect(target)
    legacy_conn = connect(legacy)
    try:
        with target_conn:
            target_conn.execute(
                "INSERT OR REPLACE INTO setting(key, value_json) VALUES ('owner', '\"installed\"')"
            )
        with legacy_conn:
            legacy_conn.execute(
                "INSERT OR REPLACE INTO setting(key, value_json) VALUES ('owner', '\"legacy\"')"
            )
    finally:
        target_conn.close()
        legacy_conn.close()

    initialize_database()
    check = connect(target)
    try:
        row = check.execute("SELECT value_json FROM setting WHERE key='owner'").fetchone()
        assert row is not None
        assert row[0] == '"installed"'
    finally:
        check.close()


def test_inno_setup_defines_wizard_and_data_directory() -> None:
    text = (Path(__file__).parents[1] / "packaging" / "FireLens.iss").read_text(encoding="utf-8")
    assert "WizardStyle=modern" in text
    assert "DefaultDirName={localappdata}\\Programs\\FireLens" in text
    assert 'Name: "{app}\\data"' in text
    assert 'DestName: ".firelens-installed"' in text
    assert "PrivilegesRequired=lowest" in text


def test_build_self_test_waits_and_uses_isolated_data_dir() -> None:
    text = (Path(__file__).parents[1] / "packaging" / "build.ps1").read_text(encoding="utf-8")
    assert "$env:FIRELENS_DATA_DIR = $SelfTestDir" in text
    assert "Start-Process -FilePath $Exe" in text
    assert "-Wait -PassThru" in text

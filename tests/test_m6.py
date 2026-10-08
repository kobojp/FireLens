from __future__ import annotations

import http.cookiejar
import importlib.util
import sys
import tomllib
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from desktop.server import start_server
from desktop.single_instance import AlreadyRunning, SingleInstance
from desktop.update import update_capability
from desktop.version import __version__


def test_version_source_matches_project_metadata() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == __version__


def test_single_instance_lock(tmp_path: Path) -> None:
    lock = tmp_path / "firelens.lock"
    first = SingleInstance(lock)
    second = SingleInstance(lock)
    first.acquire()
    try:
        with pytest.raises(AlreadyRunning):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_desktop_server_serves_api_and_frontend(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setenv("FIRELENS_DESKTOP_SECURE", "1")
    handle = start_server(create_app())
    try:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        with opener.open(f"{handle.url}/api/health", timeout=5) as response:
            assert response.status == 200
            assert b'"ok"' in response.read()
        with opener.open(handle.url, timeout=5) as response:
            assert response.status == 200
            assert b"FireLens" in response.read()
    finally:
        handle.stop()
    assert not handle.thread.is_alive()


def test_desktop_server_starts_without_console_streams(monkeypatch, tmp_path: Path) -> None:
    """PyInstaller windowed mode has no stdout/stderr console streams."""
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setenv("FIRELENS_DESKTOP_SECURE", "1")
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    handle = start_server(create_app())
    try:
        with urllib.request.urlopen(f"{handle.url}/api/health", timeout=5) as response:
            assert response.status == 200
            assert b'"ok"' in response.read()
    finally:
        handle.stop()
    assert not handle.thread.is_alive()


def test_desktop_security_requires_session_and_blocks_foreign_origin(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setenv("FIRELENS_DESKTOP_SECURE", "1")
    app = create_app()
    with TestClient(app) as client:
        fresh = TestClient(create_app())
        try:
            denied = fresh.post("/api/roots", json={"path": str(tmp_path)})
            assert denied.status_code == 403
        finally:
            fresh.close()
        assert client.get("/api/health").status_code == 200
        hostile = client.post(
            "/api/roots",
            json={"path": str(tmp_path)},
            headers={"Origin": "https://example.com"},
        )
        assert hostile.status_code == 403
        allowed = client.post(
            "/api/roots",
            json={"path": str(tmp_path), "label": "本機"},
            headers={"Origin": "http://127.0.0.1:12345"},
        )
        assert allowed.status_code == 201


def test_isolated_upgrade_and_online_update_policy() -> None:
    script = Path("packaging/upgrade_selftest.py").resolve()
    spec = importlib.util.spec_from_file_location("firelens_upgrade_selftest", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.run() == 0
    capability = update_capability()
    assert capability["enabled"] is True
    assert "Ed25519" in str(capability["reason"])
    assert capability["repository"] == "kobojp/FireLens"

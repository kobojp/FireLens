from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_wait(path: Path, args: list[str], env: dict[str, str], timeout: float = 90) -> int:
    result = subprocess.run(
        [str(path), *args],
        check=False,
        timeout=timeout,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode


def update_root(env: dict[str, str]) -> Path:
    return Path(env["LOCALAPPDATA"]) / "FireLens" / "updates"


def latest_state(env: dict[str, str]) -> dict[str, object] | None:
    pointer = update_root(env) / "latest-transaction.json"
    if not pointer.is_file():
        return None
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    state_path = Path(str(payload["state_path"]))
    if not state_path.is_file():
        return None
    return json.loads(state_path.read_text(encoding="utf-8"))


def wait_phase(
    env: dict[str, str],
    phases: set[str],
    timeout: float = 35,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last: dict[str, object] | None = None
    while time.monotonic() < deadline:
        last = latest_state(env)
        if last and str(last.get("phase")) in phases:
            return last
        time.sleep(0.2)
    raise RuntimeError(f"updater state timeout, wanted={sorted(phases)}, last={last}")


def insert_probe(db: Path, value: str) -> None:
    conn = sqlite3.connect(db)
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO setting(key, value_json) VALUES (?, ?)",
                ("update_e2e_probe", json.dumps(value)),
            )
    finally:
        conn.close()


def read_probe(db: Path) -> str:
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT value_json FROM setting WHERE key = 'update_e2e_probe'"
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise RuntimeError("update E2E probe disappeared")
    return str(json.loads(row[0]))


def base_env(localappdata: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(localappdata)
    env["FIRELENS_UPDATE_E2E"] = "1"
    env["FIRELENS_UPDATE_E2E_AUTO_CLOSE"] = "1"
    env.pop("FIRELENS_DATA_DIR", None)
    env.pop("FIRELENS_INSTALL_DIR", None)
    env.pop("FIRELENS_UPDATER_FAULT", None)
    return env


def prepare_portable(root: Path, source_exe: Path, env: dict[str, str]) -> tuple[Path, Path]:
    install = root / "可攜 更新 測試"
    install.mkdir(parents=True)
    current = install / "FireLens.exe"
    shutil.copy2(source_exe, current)
    if run_wait(current, ["--self-test"], env) != 0:
        raise RuntimeError("portable baseline self-test failed")
    db = Path(env["LOCALAPPDATA"]) / "FireLens" / "firelens.sqlite3"
    if not db.is_file():
        raise RuntimeError("portable DB was not created in LocalAppData")
    insert_probe(db, "portable-kept")
    return current, db


def trigger_update(
    current: Path,
    staged: Path,
    env: dict[str, str],
    *,
    expected_exit: int = 0,
) -> None:
    exit_code = run_wait(current, ["--update-e2e-trigger", str(staged)], env, timeout=40)
    if exit_code != expected_exit:
        raise RuntimeError(
            f"packaged FireLens update trigger exit={exit_code}, expected={expected_exit}"
        )


def assert_success_chain(current: Path, source_exe: Path, env: dict[str, str]) -> dict[str, object]:
    state = wait_phase(env, {"success"})
    if sha256(current) != sha256(source_exe):
        raise RuntimeError("successful update did not install pristine packaged FireLens.exe")
    log = Path(str(state["log_file"])).read_text(encoding="utf-8")
    for marker in (
        "started updater_pid=",
        "ready handshake written",
        "parent exited",
        "replace complete target_hash=",
        "new launch pid=",
        "healthy handshake received",
    ):
        if marker not in log:
            raise RuntimeError(f"successful update log missing marker: {marker}")
    return state


def portable_success(root: Path, source_exe: Path) -> None:
    env = base_env(root / "portable-localappdata")
    current, db = prepare_portable(root / "portable", source_exe, env)
    db_before = sha256(db)
    old_file_id = current.stat().st_ino
    staged = root / "portable-staged" / "FireLens 乾淨新版.exe"
    staged.parent.mkdir(parents=True)
    shutil.copy2(source_exe, staged)
    trigger_update(current, staged, env)
    assert_success_chain(current, source_exe, env)
    if current.stat().st_ino == old_file_id:
        raise RuntimeError("portable target file identity did not change after replacement")
    if not db.is_file() or read_probe(db) != "portable-kept" or sha256(db) != db_before:
        raise RuntimeError("portable update changed LocalAppData database")
    if (current.parent / ".firelens-installed").exists():
        raise RuntimeError("portable update created installer marker")


def install_silent(setup: Path, install: Path, env: dict[str, str]) -> None:
    result = subprocess.run(
        [
            str(setup),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/SP-",
            f"/DIR={install}",
        ],
        check=False,
        timeout=120,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise RuntimeError(f"silent installer failed: {result.returncode}")


def installed_success(root: Path, source_exe: Path, setup: Path) -> None:
    env = base_env(root / "installed-localappdata")
    install = root / "安裝 路徑 FireLens"
    install_silent(setup, install, env)
    current = install / "FireLens.exe"
    helper = install / "FireLensUpdater.exe"
    marker = install / ".firelens-installed"
    if not current.is_file() or not helper.is_file() or not marker.is_file():
        raise RuntimeError("installer did not deploy FireLens, helper, and marker")
    if run_wait(current, ["--self-test"], env) != 0:
        raise RuntimeError("installed baseline self-test failed")
    db = install / "data" / "firelens.sqlite3"
    insert_probe(db, "installed-kept")
    db_before = sha256(db)
    marker_before = sha256(marker)
    helper_before = sha256(helper)
    staged = root / "installed-staged" / "FireLens 新版.exe"
    staged.parent.mkdir(parents=True)
    shutil.copy2(source_exe, staged)
    trigger_update(current, staged, env)
    assert_success_chain(current, source_exe, env)
    if read_probe(db) != "installed-kept" or sha256(db) != db_before:
        raise RuntimeError("installed update modified {app}\\data database")
    if sha256(marker) != marker_before or sha256(helper) != helper_before:
        raise RuntimeError("installed update modified marker or installed updater helper")
    uninstaller = install / "unins000.exe"
    if uninstaller.is_file():
        subprocess.run(
            [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
            check=False,
            timeout=90,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def failure_case(root: Path, source_exe: Path, fault: str) -> None:
    env = base_env(root / f"failure-{fault}-localappdata")
    env["FIRELENS_UPDATER_FAULT"] = fault
    current, db = prepare_portable(root / f"failure-{fault}", source_exe, env)
    db_before = sha256(db)
    staged = root / f"failure-{fault}-staged" / "FireLens.exe"
    staged.parent.mkdir(parents=True)
    shutil.copy2(source_exe, staged)

    if fault == "startup_failure":
        trigger_update(current, staged, env, expected_exit=20)
        wait_phase(env, {"helper_start_failed"})
        if not current.is_file() or sha256(current) != sha256(source_exe):
            raise RuntimeError("helper startup failure changed current FireLens.exe")
    else:
        trigger_update(current, staged, env)
        if fault == "die_after_ready":
            terminal = {"error"}
        elif fault == "rollback_fail":
            terminal = {"rollback_failed"}
        else:
            terminal = {"rolled_back"}
        state = wait_phase(env, terminal, timeout=35)
        if fault != "rollback_fail" and sha256(current) != sha256(source_exe):
            raise RuntimeError(f"{fault} did not leave a valid rollback executable")
        if fault == "rollback_fail":
            backup = Path(str(state.get("backup_path") or ""))
            if not backup.is_file():
                raise RuntimeError("rollback failure did not preserve backup")

    if read_probe(db) != "portable-kept" or sha256(db) != db_before:
        raise RuntimeError(f"{fault} changed user database")
    clean_env = dict(env)
    clean_env.pop("FIRELENS_UPDATER_FAULT", None)
    if run_wait(current, ["--self-test"], clean_env) != 0:
        raise RuntimeError(f"{fault} left FireLens unable to self-test")


def run(source_exe: Path, setup: Path) -> int:
    source_exe = source_exe.resolve()
    setup = setup.resolve()
    if os.name != "nt" or not source_exe.is_file() or not setup.is_file():
        raise RuntimeError(
            "real updater E2E requires packaged FireLens.exe and setup.exe on Windows"
        )

    with tempfile.TemporaryDirectory(prefix="FireLens-real-update-e2e-") as temp:
        root = Path(temp)
        portable_success(root, source_exe)
        installed_success(root, source_exe, setup)
        for fault in (
            "startup_failure",
            "die_after_ready",
            "lock_timeout",
            "replace_fail",
            "new_crash",
            "healthy_timeout",
            "rollback_fail",
        ):
            failure_case(root, source_exe, fault)
    print(
        "FireLens real packaged update E2E passed: portable, installer, READY/HEALTHY, "
        "rollback and injected failures"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--setup", required=True, type=Path)
    args = parser.parse_args()
    return run(args.exe, args.setup)


if __name__ == "__main__":
    raise SystemExit(main())

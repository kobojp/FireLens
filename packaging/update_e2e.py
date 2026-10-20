from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db import connect, initialize_database  # noqa: E402
from desktop.update import _APPLY_SCRIPT  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_apply(
    *,
    script: Path,
    current: Path,
    new: Path,
    backup: Path,
    log: Path,
    env: dict[str, str],
    launch_argument: str,
    rollback_launch_argument: str = "--self-test",
) -> None:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-PidToWait",
            "2147483000",
            "-CurrentExe",
            str(current),
            "-NewExe",
            str(new),
            "-BackupExe",
            str(backup),
            "-LogFile",
            str(log),
            "-LaunchArgument",
            launch_argument,
            "-RollbackLaunchArgument",
            rollback_launch_argument,
            "-HealthCheckSeconds",
            "1",
        ],
        check=False,
        timeout=45,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"apply-update.ps1 failed ({result.returncode}): {result.stdout}\n{result.stderr}"
        )


def prepare_isolated_install(root: Path, source_exe: Path) -> tuple[Path, Path, Path, str, str]:
    install = root / "installed" / "FireLens"
    install.mkdir(parents=True)
    current = install / "FireLens.exe"
    shutil.copy2(source_exe, current)
    with current.open("ab") as stream:
        stream.write(b"FIRELENS-OLD-VERSION-PROBE")
    backup = root / "FireLens-old-backup.exe"
    shutil.copy2(current, backup)

    marker = install / ".firelens-installed"
    marker.write_text("installed\n", encoding="utf-8")
    db = install / "data" / "firelens.sqlite3"
    initialize_database(db)
    conn = connect(db)
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO setting(key, value_json) "
                "VALUES ('update_e2e_probe', '\"kept\"')"
            )
    finally:
        conn.close()
    return current, backup, db, sha256(db), sha256(marker)


def run(source_exe: Path) -> int:
    source_exe = source_exe.resolve()
    if os.name != "nt" or not source_exe.is_file():
        raise RuntimeError("update E2E requires an existing packaged Windows FireLens.exe")

    with tempfile.TemporaryDirectory(prefix="FireLens-update-e2e-") as temp:
        root = Path(temp)
        script = root / "apply-update.ps1"
        script.write_text(_APPLY_SCRIPT, encoding="utf-8-sig")
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(root / "localappdata")
        env["FIRELENS_DATA_DIR"] = str(root / "selftest-data")

        success_root = root / "success"
        current, backup, db, db_before, marker_before = prepare_isolated_install(
            success_root, source_exe
        )
        new_exe = success_root / "FireLens-new.exe"
        shutil.copy2(source_exe, new_exe)
        log = success_root / "update.log"
        run_apply(
            script=script,
            current=current,
            new=new_exe,
            backup=backup,
            log=log,
            env=env,
            launch_argument="--self-test",
        )
        if sha256(current) != sha256(source_exe):
            raise RuntimeError("success path did not replace the old EXE")
        if (
            sha256(db) != db_before
            or sha256(current.parent / ".firelens-installed") != marker_before
        ):
            raise RuntimeError("success path modified installed user data or marker")
        if "new FireLens launched successfully" not in log.read_text(encoding="utf-8-sig"):
            raise RuntimeError("success path did not complete launch health check")

        rollback_root = root / "rollback"
        current, backup, db, db_before, marker_before = prepare_isolated_install(
            rollback_root, source_exe
        )
        old_hash = sha256(current)
        bad_new = rollback_root / "FireLens-bad.exe"
        shutil.copy2(Path(os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")), bad_new)
        log = rollback_root / "update.log"
        run_apply(
            script=script,
            current=current,
            new=bad_new,
            backup=backup,
            log=log,
            env=env,
            launch_argument="/c exit 7",
        )
        if sha256(current) != old_hash:
            raise RuntimeError("rollback path did not restore the old EXE")
        if (
            sha256(db) != db_before
            or sha256(current.parent / ".firelens-installed") != marker_before
        ):
            raise RuntimeError("rollback path modified installed user data or marker")
        if "rollback completed" not in log.read_text(encoding="utf-8-sig"):
            raise RuntimeError("rollback path did not report a completed rollback")
    print("FireLens packaged update E2E passed: replace/restart, rollback, DB and marker unchanged")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    args = parser.parse_args()
    return run(args.exe)


if __name__ == "__main__":
    raise SystemExit(main())

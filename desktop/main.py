from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import threading
import urllib.request
from pathlib import Path

from backend.app.config import get_app_data_dir, get_install_dir
from backend.app.db import initialize_database
from backend.app.logging_config import configure_logging, get_logger
from desktop.server import start_server
from desktop.single_instance import AlreadyRunning, SingleInstance
from desktop.update import UpdateError, mark_update_healthy, schedule_local_update_e2e
from desktop.version import __version__


def self_test() -> int:
    database_path = initialize_database()
    report_path = os.environ.get("FIRELENS_SELFTEST_REPORT")
    if report_path:
        install_dir = get_install_dir()
        Path(report_path).write_text(
            json.dumps(
                {
                    "sys_executable": str(Path(sys.executable).resolve()),
                    "frozen": bool(getattr(sys, "frozen", False)),
                    "install_dir": str(install_dir) if install_dir is not None else None,
                    "database_path": str(database_path),
                    "app_data_dir": str(get_app_data_dir()),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    os.environ["FIRELENS_DESKTOP_SECURE"] = "1"
    handle = start_server()
    try:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        with opener.open(f"{handle.url}/api/health", timeout=5) as response:
            if response.status != 200 or b'"ok"' not in response.read():
                return 2
        with opener.open(handle.url, timeout=5) as response:
            body = response.read(4096)
            if response.status != 200 or b"FireLens" not in body:
                return 3
        return 0
    finally:
        handle.stop()


def run_desktop(update_transaction: str | None = None, update_state: str | None = None) -> int:
    configure_logging()
    logger = get_logger("firelens.desktop")
    logger.info("desktop launch version=%s", __version__)
    lock_path = get_app_data_dir() / "firelens.lock"
    try:
        with SingleInstance(lock_path):
            os.environ["FIRELENS_DESKTOP_SECURE"] = "1"
            handle = start_server()
            try:
                import webview

                window = webview.create_window(
                    f"FireLens {__version__}",
                    handle.url,
                    width=1440,
                    height=900,
                    min_size=(1100, 700),
                )
                if update_transaction and update_state:

                    def on_loaded(_window=None) -> None:
                        fault = os.environ.get("FIRELENS_UPDATER_FAULT", "")
                        if fault != "healthy_timeout":
                            try:
                                mark_update_healthy(update_transaction, update_state)
                                logger.info(
                                    "update healthy transaction=%s version=%s",
                                    update_transaction,
                                    __version__,
                                )
                            except UpdateError as exc:
                                logger.error(
                                    "update healthy handshake failed transaction=%s error=%s",
                                    update_transaction,
                                    exc,
                                )
                        if os.environ.get("FIRELENS_UPDATE_E2E_AUTO_CLOSE") == "1":
                            threading.Timer(0.5, window.destroy).start()

                    window.events.loaded += on_loaded
                elif os.environ.get("FIRELENS_UPDATE_E2E_AUTO_CLOSE") == "1":

                    def close_e2e_window(_window=None) -> None:
                        threading.Timer(0.5, window.destroy).start()

                    window.events.loaded += close_e2e_window
                webview.start()
            finally:
                handle.stop()
    except AlreadyRunning:
        get_logger("firelens.desktop").warning("FireLens duplicate launch blocked")
        return 4
    logger.info("desktop exit version=%s", __version__)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="FireLens")
    parser.add_argument("--self-test", action="store_true", help="run packaged headless self-test")
    parser.add_argument("--version", action="store_true", help="print application version")
    parser.add_argument("--update-transaction", help=argparse.SUPPRESS)
    parser.add_argument("--update-state", help=argparse.SUPPRESS)
    parser.add_argument("--update-e2e-trigger", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--update-e2e-crash", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if args.self_test:
        configure_logging()
        return self_test()
    if args.update_e2e_crash:
        return 23
    if args.update_e2e_trigger is not None:
        configure_logging()
        try:
            schedule_local_update_e2e(args.update_e2e_trigger)
        except UpdateError:
            return 20
        return 0
    if bool(args.update_transaction) != bool(args.update_state):
        return 24
    return run_desktop(args.update_transaction, args.update_state)


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
import http.cookiejar
import os
import sys
import urllib.request

from backend.app.config import get_app_data_dir
from backend.app.db import initialize_database
from backend.app.logging_config import configure_logging, get_logger
from desktop.server import start_server
from desktop.single_instance import AlreadyRunning, SingleInstance
from desktop.version import __version__


def self_test() -> int:
    initialize_database()
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


def run_desktop() -> int:
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

                webview.create_window(
                    f"FireLens {__version__}",
                    handle.url,
                    width=1440,
                    height=900,
                    min_size=(1100, 700),
                )
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
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if args.self_test:
        configure_logging()
        return self_test()
    return run_desktop()


if __name__ == "__main__":
    sys.exit(main())

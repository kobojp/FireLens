from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "FireLens"
DB_FILENAME = "firelens.sqlite3"
INSTALL_MARKER_FILENAME = ".firelens-installed"


def get_install_dir() -> Path | None:
    override = os.environ.get("FIRELENS_INSTALL_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt" and getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent
        if (candidate / INSTALL_MARKER_FILENAME).is_file():
            return candidate
    return None


def get_app_data_dir() -> Path:
    override = os.environ.get("FIRELENS_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / APP_NAME

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def get_database_path() -> Path:
    if not os.environ.get("FIRELENS_DATA_DIR"):
        install_dir = get_install_dir()
        if install_dir is not None:
            return install_dir / "data" / DB_FILENAME
    return get_app_data_dir() / DB_FILENAME


def get_legacy_database_path() -> Path | None:
    if os.environ.get("FIRELENS_DATA_DIR") or get_install_dir() is None or os.name != "nt":
        return None
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    return Path(local_app_data) / APP_NAME / DB_FILENAME


def get_cache_dir() -> Path:
    return get_app_data_dir() / "cache"


def get_thumbnail_dir() -> Path:
    return get_cache_dir() / "thumbnails"


def get_offline_dir() -> Path:
    return get_cache_dir() / "offline"


def get_log_dir() -> Path:
    return get_app_data_dir() / "logs"


def get_backup_dir() -> Path:
    return get_app_data_dir() / "backups"

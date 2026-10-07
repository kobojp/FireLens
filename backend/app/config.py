from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "FireLens"
DB_FILENAME = "firelens.sqlite3"


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
    return get_app_data_dir() / DB_FILENAME


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

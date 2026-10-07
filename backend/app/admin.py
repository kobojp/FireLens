from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from desktop.version import __version__

from .backup import MAX_BACKUP_BYTES, BackupError, export_backup, restore_backup
from .config import (
    get_app_data_dir,
    get_backup_dir,
    get_cache_dir,
    get_database_path,
    get_log_dir,
    get_offline_dir,
    get_thumbnail_dir,
)
from .db import SCHEMA_VERSION, database
from .logging_config import configure_logging
from .settings import (
    SettingsError,
    get_settings,
    save_settings,
    update_category_aliases,
    update_root_settings,
)

router = APIRouter(prefix="/api")


class SettingsUpdate(BaseModel):
    theme: str | None = None
    thumbnail_quality: int | None = None
    slot_order: dict[str, list[str]] | None = None
    custom_slots: dict[str, list[str]] | None = None


class RootSettingsUpdate(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    is_cloud_stream: bool


class CategoryAliasesUpdate(BaseModel):
    aliases: dict[str, str]


def _directory_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file() and not child.is_symlink():
                total += child.stat().st_size
        except OSError:
            continue
    return total


@router.get("/app-info")
def app_info() -> dict[str, object]:
    log_path = configure_logging()
    return {
        "version": __version__,
        "schema_version": SCHEMA_VERSION,
        "data_dir": str(get_app_data_dir()),
        "database_path": str(get_database_path()),
        "cache_dir": str(get_cache_dir()),
        "thumbnail_dir": str(get_thumbnail_dir()),
        "offline_dir": str(get_offline_dir()),
        "backup_dir": str(get_backup_dir()),
        "log_dir": str(get_log_dir()),
        "log_file": str(log_path),
        "log_size_bytes": log_path.stat().st_size if log_path.is_file() else 0,
        "cache_size_bytes": _directory_size(get_cache_dir()),
        "online_update_enabled": False,
        "online_update_reason": "尚未設定簽章更新來源與公鑰，因此安全停用。",
    }


@router.get("/settings")
def settings() -> dict[str, object]:
    with database() as conn:
        return get_settings(conn)


@router.put("/settings")
def update_settings(payload: SettingsUpdate) -> dict[str, object]:
    values: dict[str, Any] = {
        key: value for key, value in payload.model_dump().items() if value is not None
    }
    with database() as conn:
        try:
            return save_settings(conn, values)
        except SettingsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/roots/{root_id}/settings")
def root_settings(root_id: int, payload: RootSettingsUpdate) -> dict[str, object]:
    with database() as conn:
        try:
            return update_root_settings(
                conn,
                root_id,
                label=payload.label,
                is_cloud_stream=payload.is_cloud_stream,
            )
        except SettingsError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/categories/{category_code}/aliases")
def category_alias_settings(
    category_code: str, payload: CategoryAliasesUpdate
) -> dict[str, object]:
    with database() as conn:
        try:
            return update_category_aliases(conn, category_code, payload.aliases)
        except SettingsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/settings/backup")
def download_backup() -> Response:
    with database() as conn:
        try:
            content, filename = export_backup(conn)
        except BackupError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/settings/restore")
async def upload_backup(file: Annotated[UploadFile, File()]) -> dict[str, object]:
    content = await file.read(MAX_BACKUP_BYTES + 1)
    if len(content) > MAX_BACKUP_BYTES:
        raise HTTPException(status_code=413, detail="備份檔不可超過 256 MB")
    with database() as conn:
        try:
            return restore_backup(conn, content)
        except BackupError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

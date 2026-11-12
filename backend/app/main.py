from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from desktop.version import __version__

from .admin import router as admin_router
from .cache import (
    CacheError,
    CacheUnavailable,
    content_file,
    list_offline_queue,
    prime_thumbnail_cache,
    queue_offline_import,
    root_status,
    sync_offline_queue,
    thumbnail_file,
)
from .db import database, initialize_database
from .export_files import ExportActionError, ExportRegistry, export_issue_rows
from .issues import (
    IssueConflict,
    IssueError,
    create_label,
    issue_statistics,
    item_issue,
    list_labels,
    set_item_issue,
    update_label,
)
from .item_folders import rename_item_folder
from .logging_config import RequestLoggingMiddleware, configure_logging, get_logger
from .organizer import (
    OrganizerConflict,
    OrganizerError,
    analyze_root,
    execute_renames,
    preview_photo_rename,
    preview_renames,
    rename_existing_photo,
    rename_history,
    undo_rename,
)
from .photo_quality import (
    QualityError,
    cancel_quality,
    export_quality,
    review_photo,
    save_sensitivity,
    scan_quality,
    sensitivity_for,
)
from .photo_quality import (
    gallery as quality_gallery,
)
from .photo_quality import (
    job_status as quality_job_status,
)
from .photo_transfer import execute_slot_transfer, preview_slot_transfer, undo_slot_transfer
from .private_drive import PrivateDriveError, PrivateDriveService
from .reconcile import (
    ReconcileError,
    build_reconciliation,
    delete_ledger,
    export_reconciliation,
    get_ledger_detail,
    import_ledger,
    list_aliases,
    list_ledgers,
    parse_excel_bytes,
    parse_text_rows,
    preview_excel_bytes,
    preview_text_rows,
    rename_ledger,
    reshoot_text,
    save_alias,
    seed_default_aliases,
    set_reshoot_mark,
)
from .scan_jobs import (
    ScanAlreadyRunning,
    ScanJobError,
    cancel_scan_job,
    scan_job_status,
    start_scan_job,
)
from .security import DesktopSecurityMiddleware
from .settings import custom_slots_for
from .shared_issues import (
    SyncError,
    backup_preview,
    recover_missing_shared_events,
    resume_after_restore,
)
from .shared_issues import (
    backups as sync_backups,
)
from .shared_issues import (
    configure as configure_shared_issues,
)
from .shared_issues import (
    conflicts as sync_conflicts,
)
from .shared_issues import (
    enabled_roots as enabled_shared_issue_roots,
)
from .shared_issues import (
    record_item as sync_record_item,
)
from .shared_issues import (
    record_label as sync_record_label,
)
from .shared_issues import (
    record_renamed_item as sync_record_renamed_item,
)
from .shared_issues import (
    resolve as resolve_shared_issue,
)
from .shared_issues import (
    restore as restore_shared_issue,
)
from .shared_issues import (
    status as shared_status,
)
from .shared_issues import (
    synchronize as synchronize_shared_issues,
)
from .storage import (
    StorageConflict,
    StorageError,
    create_building_folder,
    create_item_folder,
    create_period_folder,
    create_year_folder,
    delete_item_folder,
    delete_photo,
    import_photo,
    reorder_photos,
)
from .tree import build_tree


def _frontend_dist_dir() -> Path:
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "frontend_dist"
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


class RootCreate(BaseModel):
    path: str = Field(min_length=1)
    label: str | None = None
    is_cloud_stream: bool = False


class ItemFolderCreate(BaseModel):
    root_id: int
    category_code: str = Field(min_length=1)
    year: str = Field(min_length=1)
    period: str = Field(min_length=1)
    building: str = Field(min_length=1)
    code: str = Field(min_length=1)


class ItemFolderRename(BaseModel):
    new_name: str = Field(min_length=1, max_length=120)


class IssueLabelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class IssueLabelUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None
    sort_order: int | None = None


class SharedIssueConfigure(BaseModel):
    enabled: bool


class SharedIssueResolution(BaseModel):
    key: str = Field(min_length=1, max_length=1024)
    event_id: str = Field(min_length=32, max_length=32)


class SharedIssueConfirm(BaseModel):
    confirm: bool = False


class ItemIssueUpdate(BaseModel):
    label_id: int | None


class PhotoQualityScan(BaseModel):
    full: bool = False
    category: str = ""
    period: str = ""


class PhotoQualityExportSave(BaseModel):
    format: str = "xlsx"
    category: str = ""
    period: str = ""
    building: str = ""
    query: str = ""
    problem_only: bool = True
    status_filter: str = ""
    review_filter: str = ""
    sort_by: str = "latest"


class PhotoQualityReview(BaseModel):
    review: str


class PhotoQualitySetting(BaseModel):
    sensitivity: float = Field(ge=0.5, le=1.5)


class ReconcileExportSave(BaseModel):
    root_id: int
    ledger_id: int
    format: str = "xlsx"
    period: str | None = None
    category_code: str = "extinguisher"


class IssueExportSave(BaseModel):
    format: str = "xlsx"
    root_id: int | None = None
    label_id: int | None = None
    building: str = ""
    query: str = Field(default="", max_length=200)
    expected_row_count: int | None = Field(default=None, ge=0, le=1000000)


class OpenExportRequest(BaseModel):
    open_token: str = Field(min_length=12, max_length=100)
    mode: str


class YearFolderCreate(BaseModel):
    root_id: int
    category_code: str = Field(min_length=1)
    year: str = Field(min_length=1)


class PeriodFolderCreate(BaseModel):
    root_id: int
    category_code: str = Field(min_length=1)
    year: str = Field(min_length=1)
    period: str = Field(min_length=1)


class BuildingFolderCreate(PeriodFolderCreate):
    building: str = Field(min_length=1)


class LedgerTextImport(BaseModel):
    name: str = Field(min_length=1)
    text: str = Field(min_length=1)


class LedgerRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class AliasUpsert(BaseModel):
    source_value: str = Field(min_length=1)
    target_value: str = Field(min_length=1)
    confirmed: bool = True


class ReconcileRequest(BaseModel):
    root_id: int
    ledger_id: int
    period: str | None = None
    category_code: str = "extinguisher"


class ReshootMarkUpdate(BaseModel):
    root_id: int
    ledger_id: int
    category_code: str = Field(min_length=1)
    device_no: str = Field(min_length=1)
    marked: bool


class RenameSelection(BaseModel):
    candidate_ids: list[str] = Field(min_length=1)


class ReorderPhotos(BaseModel):
    photo_ids: list[int]


class GoogleOpenSheetRequest(BaseModel):
    tab_id: int | None = Field(default=None, ge=0, le=2147483647)


class GoogleCellUpdateRequest(BaseModel):
    tab: str = Field(min_length=1, max_length=200)
    row: int = Field(ge=1, le=100000)
    column: int = Field(ge=1, le=30)
    expected: str = Field(max_length=2000)
    value: str = Field(max_length=2000)


class OAuthSecretSettingsRequest(BaseModel):
    client_secret: str = Field(min_length=1, max_length=2048)


class SlotTransferRequest(BaseModel):
    target_slot: str = Field(min_length=1, max_length=100)
    target_photo_id: int | None = None
    expected_source_sha256: str | None = None
    expected_target_sha256: str | None = None


class PhotoRenameRequest(BaseModel):
    target_filename: str = Field(min_length=1, max_length=255)
    expected_sha256: str | None = None
    reason: str = Field(default="人工重新命名", max_length=100)


def _item_detail(conn: sqlite3.Connection, item_id: int) -> dict[str, object]:
    row = conn.execute(
        """
        SELECT i.*, c.code AS category_code, c.name AS category_name,
               c.slots_json, c.filename_aliases_json
        FROM item AS i
        JOIN category AS c ON c.id = i.category_id
        WHERE i.id = ?
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="找不到指定項目")
    result = dict(row)
    result["slots"] = json.loads(result.pop("slots_json"))
    result["custom_slots"] = list(custom_slots_for(conn, str(result["category_code"])))
    result["filename_aliases"] = json.loads(result.pop("filename_aliases_json"))
    result["photos"] = [
        dict(photo)
        for photo in conn.execute(
            """
            SELECT id, filename, relative_path, extension, slot, size_bytes,
                   mtime_ns, sha256, cloud_placeholder
            FROM photo WHERE item_id = ? ORDER BY filename COLLATE NOCASE
            """,
            (item_id,),
        )
    ]
    return result


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        configure_logging()
        logger = get_logger("firelens.app")
        logger.info("application startup version=%s", __version__)
        initialize_database()
        with database() as conn:
            seed_default_aliases(conn)

        def auto_sync_once() -> None:
            with database() as sync_conn:
                for sync_root_id in enabled_shared_issue_roots(sync_conn):
                    try:
                        synchronize_shared_issues(sync_conn, sync_root_id)
                    except (SyncError, OSError, sqlite3.Error):
                        # Never delete or rewrite local records when a Drive
                        # folder is missing, partially synced or conflicted.
                        logger.warning("共享異常同步暫停，需查看狀態或人工處理")

        async def auto_sync_loop() -> None:
            while True:
                await asyncio.to_thread(auto_sync_once)
                await asyncio.sleep(120)

        sync_task = asyncio.create_task(auto_sync_loop())
        try:
            yield
        finally:
            sync_task.cancel()
            with suppress(asyncio.CancelledError):
                await sync_task
            logger.info("application shutdown version=%s", __version__)

    app = FastAPI(title="FireLens API", version=__version__, lifespan=lifespan)
    export_registry = ExportRegistry()
    private_drive = PrivateDriveService()
    app.add_middleware(DesktopSecurityMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
    )

    app.include_router(admin_router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/google-oauth-settings")
    def google_oauth_settings() -> dict[str, object]:
        try:
            return private_drive.client_settings()
        except PrivateDriveError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/google-oauth-settings")
    def save_google_oauth_settings(payload: OAuthSecretSettingsRequest) -> dict[str, object]:
        try:
            return private_drive.save_client_secret(payload.client_secret)
        except PrivateDriveError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.delete("/api/google-oauth-settings")
    def clear_google_oauth_settings() -> dict[str, object]:
        try:
            return private_drive.clear_client_secret()
        except PrivateDriveError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/api/private-drive/status")
    def drive_auth_status() -> dict[str, object]:
        return private_drive.status()

    @app.post("/api/private-drive/login")
    def drive_auth_login(edit: bool = Query(default=False)) -> dict[str, object]:
        try:
            return private_drive.login(edit=edit)
        except PrivateDriveError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/private-drive/logout")
    def drive_auth_logout() -> dict[str, object]:
        return private_drive.logout()

    @app.get("/api/private-drive/sheets")
    def drive_private_sheets() -> list[dict[str, str]]:
        try:
            return private_drive.sheets()
        except PrivateDriveError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/api/private-drive/sheets/{sheet_id}/tabs")
    def drive_private_sheet_tabs(sheet_id: str) -> list[dict[str, str | int]]:
        try:
            return private_drive.sheet_tabs(sheet_id)
        except PrivateDriveError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/api/private-drive/sheets/{sheet_id}/values")
    def drive_private_sheet_values(
        sheet_id: str,
        tab: str = Query(min_length=1, max_length=200),
        start_row: int = Query(default=1, ge=1, le=100000),
    ) -> dict[str, object]:
        try:
            return private_drive.values(sheet_id, tab, start_row)
        except PrivateDriveError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/api/private-drive/sheets/{sheet_id}/copy-info")
    def drive_copy_info(
        sheet_id: str, tab: str = Query(min_length=1, max_length=200)
    ) -> dict[str, int]:
        try:
            return private_drive.copy_info(sheet_id, tab)
        except PrivateDriveError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/api/private-drive/sheets/{sheet_id}/copy-chunk")
    def drive_copy_chunk(
        sheet_id: str,
        tab: str = Query(min_length=1, max_length=200),
        start_row: int = Query(ge=1, le=20000),
        end_row: int = Query(ge=1, le=20000),
        start_column: int = Query(ge=1, le=30),
        end_column: int = Query(ge=1, le=30),
    ) -> dict[str, object]:
        try:
            return private_drive.copy_chunk(
                sheet_id, tab, start_row, end_row, start_column, end_column
            )
        except PrivateDriveError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/private-drive/sheets/{sheet_id}/open")
    def open_private_sheet_in_browser(
        sheet_id: str, payload: GoogleOpenSheetRequest
    ) -> dict[str, bool]:
        try:
            return private_drive.open_sheet_in_browser(sheet_id, payload.tab_id)
        except PrivateDriveError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.put("/api/private-drive/sheets/{sheet_id}/cell")
    def update_private_sheet_cell(
        sheet_id: str, payload: GoogleCellUpdateRequest
    ) -> dict[str, object]:
        try:
            return private_drive.edit_cell(
                sheet_id,
                payload.tab,
                payload.row,
                payload.column,
                payload.expected,
                payload.value,
            )
        except PrivateDriveError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/api/roots")
    def list_roots() -> list[dict[str, object]]:
        with database() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM root ORDER BY id")]

    @app.post("/api/roots", status_code=201)
    def add_root(payload: RootCreate) -> dict[str, object]:
        source = Path(payload.path).expanduser()
        if not source.is_dir():
            raise HTTPException(status_code=400, detail="指定的根目錄不存在或無法讀取")
        resolved = str(source.resolve())
        label = payload.label or source.name or resolved
        with database() as conn, conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO root(label, path, is_cloud_stream) VALUES (?, ?, ?)",
                    (label, resolved, int(payload.is_cloud_stream)),
                )
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=409, detail="此根目錄已存在") from exc
            row = conn.execute("SELECT * FROM root WHERE id = ?", (cursor.lastrowid,)).fetchone()
            assert row is not None
            return dict(row)

    @app.get("/api/categories")
    def categories() -> list[dict[str, object]]:
        with database() as conn:
            return [
                {
                    "code": row["code"],
                    "name": row["name"],
                    "slots": json.loads(row["slots_json"]),
                    "filename_aliases": json.loads(row["filename_aliases_json"]),
                }
                for row in conn.execute(
                    "SELECT code, name, slots_json, filename_aliases_json FROM category ORDER BY id"
                )
            ]

    @app.post("/api/roots/{root_id}/scan", status_code=202)
    def scan(root_id: int) -> dict[str, object]:
        try:
            return start_scan_job(root_id)
        except ScanAlreadyRunning as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ScanJobError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/roots/{root_id}/scan")
    def scan_status(root_id: int) -> dict[str, object]:
        return scan_job_status(root_id)

    @app.post("/api/roots/{root_id}/scan/cancel")
    def cancel_scan(root_id: int) -> dict[str, object]:
        return cancel_scan_job(root_id)

    @app.get("/api/roots/{root_id}/tree")
    def tree(root_id: int) -> list[dict[str, object]]:
        with database() as conn:
            exists = conn.execute("SELECT 1 FROM root WHERE id = ?", (root_id,)).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail="找不到指定的根目錄")
            return build_tree(conn, root_id)

    @app.get("/api/quality/{root_id}")
    def photo_quality_gallery(
        root_id: int,
        category: str = "",
        period: str = "",
        building: str = "",
        query: str = "",
        problem_only: bool = True,
        status_filter: str = "",
        review_filter: str = "",
        sort_by: str = "latest",
        limit: int = Query(default=40, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        with database() as conn:
            try:
                return quality_gallery(
                    conn,
                    root_id,
                    category=category,
                    period=period,
                    building=building,
                    query=query,
                    problem_only=problem_only,
                    status_filter=status_filter,
                    review_filter=review_filter,
                    sort_by=sort_by,
                    limit=limit,
                    offset=offset,
                )
            except QualityError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/quality/{root_id}/settings")
    def quality_settings(root_id: int) -> dict:
        with database() as conn:
            if not conn.execute("SELECT 1 FROM root WHERE id=?", (root_id,)).fetchone():
                raise HTTPException(status_code=404, detail="根目錄不存在")
            return {"root_id": root_id, "sensitivity": sensitivity_for(conn, root_id)}

    @app.post("/api/quality/{root_id}/settings")
    def set_quality_settings(root_id: int, payload: PhotoQualitySetting) -> dict:
        with database() as conn:
            try:
                return save_sensitivity(conn, root_id, payload.sensitivity)
            except QualityError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/quality/{root_id}/scan", status_code=202)
    def start_photo_quality(root_id: int, payload: PhotoQualityScan) -> dict:
        try:
            return scan_quality(
                root_id,
                full=payload.full,
                category=payload.category,
                period=payload.period,
            )
        except QualityError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/quality/{root_id}/scan")
    def photo_quality_status(root_id: int) -> dict:
        return quality_job_status(root_id)

    @app.post("/api/quality/{root_id}/scan/cancel")
    def stop_photo_quality(root_id: int) -> dict:
        return cancel_quality(root_id)

    @app.post("/api/quality/photos/{photo_id}/review")
    def set_photo_quality_review(photo_id: int, payload: PhotoQualityReview) -> dict:
        with database() as conn:
            try:
                return review_photo(conn, photo_id, payload.review)
            except QualityError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/quality/{root_id}/export/save")
    def save_photo_quality_export(root_id: int, payload: PhotoQualityExportSave) -> dict:
        fmt = payload.format.casefold()
        if fmt not in ("csv", "xlsx"):
            raise HTTPException(status_code=400, detail="只允許 CSV／Excel 匯出")
        with database() as conn:
            try:
                rows = quality_gallery(
                    conn,
                    root_id,
                    category=payload.category,
                    period=payload.period,
                    building=payload.building,
                    query=payload.query,
                    problem_only=payload.problem_only,
                    status_filter=payload.status_filter,
                    review_filter=payload.review_filter,
                    sort_by=payload.sort_by,
                    limit=1000000,
                    offset=0,
                )
                content, _ = export_quality(rows["items"], fmt)
            except QualityError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            return export_registry.save(prefix="照片品質檢查", content=content, extension=fmt)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"照片品質匯出失敗：{exc}") from exc

    @app.get("/api/quality/{root_id}/export")
    def download_photo_quality(
        root_id: int,
        fmt: str = "csv",
        category: str = "",
        period: str = "",
        building: str = "",
        query: str = "",
        problem_only: bool = True,
        status_filter: str = "",
        review_filter: str = "",
        sort_by: str = "latest",
    ) -> Response:
        if fmt not in ("csv", "xlsx"):
            raise HTTPException(status_code=400, detail="只允許 CSV／Excel 匯出")
        with database() as conn:
            try:
                rows = quality_gallery(
                    conn,
                    root_id,
                    category=category,
                    period=period,
                    building=building,
                    query=query,
                    problem_only=problem_only,
                    status_filter=status_filter,
                    review_filter=review_filter,
                    sort_by=sort_by,
                    limit=1000000,
                    offset=0,
                )
                content, content_type = export_quality(rows["items"], fmt)
            except QualityError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="FireLens-photo-quality.{fmt}"'},
        )

    @app.get("/api/items/{item_id}/photos")
    def item_photos(item_id: int) -> list[dict[str, object]]:
        with database() as conn:
            exists = conn.execute("SELECT 1 FROM item WHERE id = ?", (item_id,)).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail="找不到指定項目")
            rows = conn.execute(
                """
                SELECT id, filename, relative_path, extension, slot, size_bytes,
                       mtime_ns, cloud_placeholder
                FROM photo WHERE item_id = ? ORDER BY filename COLLATE NOCASE
                """,
                (item_id,),
            )
            return [dict(row) for row in rows]

    @app.get("/api/items/{item_id}")
    def item_detail(item_id: int) -> dict[str, object]:
        with database() as conn:
            return _item_detail(conn, item_id)

    @app.delete("/api/items/{item_id}")
    def remove_item(item_id: int) -> dict[str, object]:
        with database() as conn:
            try:
                return delete_item_folder(conn, item_id)
            except StorageError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/items/{item_id}/rename")
    def rename_folder(item_id: int, payload: ItemFolderRename) -> dict[str, object]:
        with database() as conn:
            try:
                changed = rename_item_folder(conn, item_id, payload.new_name)
                sync_record_renamed_item(
                    conn, item_id, str(changed["old_relative_path"]), str(changed["old_name"])
                )
                return changed
            except SyncError as exc:
                raise HTTPException(
                    status_code=503,
                    detail="資料夾更名已完成，但共享異常事件暫時未寫入：" + str(exc),
                ) from exc
            except StorageConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except StorageError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/issues/labels")
    def issue_labels() -> list[dict[str, object]]:
        with database() as conn:
            return list_labels(conn)

    @app.post("/api/issues/labels", status_code=201)
    def add_issue_label(payload: IssueLabelCreate) -> dict[str, object]:
        with database() as conn:
            try:
                created = create_label(conn, payload.name)
                sync_record_label(conn, int(created["id"]))
                return created
            except SyncError as exc:
                raise HTTPException(
                    status_code=503, detail="已寫入本機，但共享事件暫無法保存：" + str(exc)
                ) from exc
            except IssueConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except IssueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/api/issues/labels/{label_id}")
    def edit_issue_label(label_id: int, payload: IssueLabelUpdate) -> dict[str, object]:
        with database() as conn:
            try:
                updated = update_label(
                    conn,
                    label_id,
                    name=payload.name,
                    active=payload.active,
                    sort_order=payload.sort_order,
                )
                sync_record_label(conn, label_id)
                return updated
            except SyncError as exc:
                raise HTTPException(
                    status_code=503, detail="已寫入本機，但共享事件暫無法保存：" + str(exc)
                ) from exc
            except IssueConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except IssueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/issues/sync/{root_id}")
    def get_shared_issue_sync(root_id: int) -> dict[str, object]:
        with database() as conn:
            try:
                return shared_status(conn, root_id)
            except SyncError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/issues/sync/{root_id}/configure")
    def configure_issue_sync(root_id: int, payload: SharedIssueConfigure) -> dict[str, object]:
        with database() as conn:
            try:
                return configure_shared_issues(conn, root_id, payload.enabled)
            except (SyncError, OSError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/issues/sync/{root_id}/run")
    def run_issue_sync(root_id: int) -> dict[str, object]:
        with database() as conn:
            try:
                return synchronize_shared_issues(conn, root_id)
            except (SyncError, OSError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/issues/sync/{root_id}/conflicts")
    def get_issue_sync_conflicts(root_id: int) -> list[dict]:
        with database() as conn:
            try:
                return sync_conflicts(conn, root_id)
            except (SyncError, OSError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/issues/sync/{root_id}/resolve")
    def resolve_issue_sync(root_id: int, payload: SharedIssueResolution) -> dict[str, object]:
        with database() as conn:
            try:
                return resolve_shared_issue(conn, root_id, payload.key, payload.event_id)
            except (SyncError, OSError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/issues/sync/{root_id}/backups")
    def list_issue_sync_backups(root_id: int) -> list[dict]:
        with database() as conn:
            try:
                return sync_backups(conn, root_id)
            except SyncError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/issues/sync/{root_id}/backups/{backup_id}")
    def preview_issue_backup(root_id: int, backup_id: str) -> dict:
        with database() as conn:
            try:
                preview = backup_preview(conn, root_id, backup_id)
                preview.pop("_data", None)
                return preview
            except (SyncError, OSError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/issues/sync/{root_id}/backups/{backup_id}/restore")
    def restore_issue_backup(root_id: int, backup_id: str, payload: SharedIssueConfirm) -> dict:
        with database() as conn:
            try:
                return restore_shared_issue(conn, root_id, backup_id, payload.confirm)
            except (SyncError, OSError, sqlite3.Error) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/issues/sync/{root_id}/recover-shared")
    def recover_shared_issue_events(root_id: int, payload: SharedIssueConfirm) -> dict:
        with database() as conn:
            try:
                return recover_missing_shared_events(conn, root_id, payload.confirm)
            except (SyncError, OSError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/issues/sync/{root_id}/resume")
    def resume_shared_issue_sync(root_id: int, payload: SharedIssueConfirm) -> dict:
        with database() as conn:
            try:
                return resume_after_restore(conn, root_id, payload.confirm)
            except (SyncError, OSError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/issues/statistics")
    def issues_stats(root_id: int | None = None) -> dict[str, object]:
        with database() as conn:
            return issue_statistics(conn, root_id)

    @app.post("/api/issues/export/save")
    def issue_export_save(payload: IssueExportSave) -> dict[str, object]:
        with database() as conn:
            stats = issue_statistics(conn, payload.root_id)
        try:
            content, count = export_issue_rows(
                stats,
                label_id=payload.label_id,
                building=payload.building,
                query=payload.query.strip(),
                file_format=payload.format.casefold(),
            )
            if payload.expected_row_count is not None and count != payload.expected_row_count:
                raise HTTPException(
                    status_code=409,
                    detail="異常統計資料或篩選筆數已變更，請重新整理後再次匯出",
                )
            return {
                **export_registry.save(
                    prefix="異常設備清單", content=content, extension=payload.format.casefold()
                ),
                "row_count": count,
            }
        except ExportActionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"檔案儲存失敗：{exc}") from exc

    @app.post("/api/exports/open")
    def open_export(payload: OpenExportRequest) -> dict[str, bool]:
        try:
            export_registry.open(token=payload.open_token, mode=payload.mode)
        except ExportActionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"開啟檔案失敗：{exc}") from exc
        return {"opened": True}

    @app.get("/api/items/{item_id}/issue")
    def get_item_issue(item_id: int) -> dict[str, object]:
        with database() as conn:
            try:
                return item_issue(conn, item_id)
            except IssueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/api/items/{item_id}/issue")
    def update_item_issue(item_id: int, payload: ItemIssueUpdate) -> dict[str, object]:
        with database() as conn:
            try:
                updated = set_item_issue(conn, item_id, payload.label_id)
                sync_record_item(conn, item_id, payload.label_id)
                return updated
            except SyncError as exc:
                raise HTTPException(
                    status_code=503, detail="已寫入本機，但共享事件暫無法保存：" + str(exc)
                ) from exc
            except IssueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/items/{item_id}/slots/{slot}/photos")
    async def upload_photo(
        item_id: int,
        slot: str,
        file: Annotated[UploadFile, File()],
        replace_photo_id: Annotated[int | None, Query()] = None,
        allow_duplicate: Annotated[bool, Query()] = False,
    ) -> dict[str, object]:
        data = await file.read()
        with database() as conn:
            root_row = conn.execute(
                """
                SELECT r.id, r.path FROM item i JOIN root r ON r.id=i.root_id WHERE i.id=?
                """,
                (item_id,),
            ).fetchone()
            if root_row is None:
                raise HTTPException(status_code=404, detail="找不到指定項目")
            if not Path(root_row["path"]).expanduser().is_dir():
                try:
                    queued = queue_offline_import(
                        conn,
                        item_id=item_id,
                        slot=slot,
                        source_name=file.filename or "upload",
                        data=data,
                        replace_photo_id=replace_photo_id,
                    )
                except CacheError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                result = _item_detail(conn, item_id)
                result["offline_queued"] = True
                result["offline_queue_entry"] = queued
                return result
            try:
                import_photo(
                    conn,
                    item_id,
                    slot,
                    file.filename or "upload",
                    data,
                    replace_photo_id=replace_photo_id,
                    allow_duplicate=allow_duplicate,
                )
            except StorageConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except StorageError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            result = _item_detail(conn, item_id)
            result["offline_queued"] = False
            return result

    @app.get("/api/photos/{photo_id}/content")
    def photo_content(photo_id: int) -> FileResponse:
        with database() as conn:
            try:
                path, cached = content_file(conn, photo_id)
            except (CacheError, StorageError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        headers = {"X-FireLens-Cached-Thumbnail": "1"} if cached else None
        return FileResponse(path, headers=headers)

    @app.get("/api/photos/{photo_id}/thumbnail")
    def photo_thumbnail(photo_id: int) -> FileResponse:
        with database() as conn:
            try:
                path = thumbnail_file(conn, photo_id)
            except CacheUnavailable as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except CacheError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse(path, media_type="image/jpeg")

    @app.delete("/api/photos/{photo_id}")
    def remove_photo(photo_id: int) -> dict[str, object]:
        with database() as conn:
            try:
                item_id = delete_photo(conn, photo_id)
            except StorageError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return _item_detail(conn, item_id)

    @app.post("/api/photos/{photo_id}/rename/preview")
    def preview_existing_photo_rename(
        photo_id: int, payload: PhotoRenameRequest
    ) -> dict[str, object]:
        with database() as conn:
            root = conn.execute(
                "SELECT i.root_id FROM photo p JOIN item i ON i.id=p.item_id WHERE p.id=?",
                (photo_id,),
            ).fetchone()
            if root is None:
                raise HTTPException(status_code=404, detail="找不到指定照片")
            if scan_job_status(int(root["root_id"]))["state"] == "running":
                raise HTTPException(
                    status_code=409, detail="掃描進行中，請等待完成或先取消掃描再改名"
                )
            try:
                return preview_photo_rename(conn, photo_id, payload.target_filename)
            except OrganizerConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except OrganizerError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/photos/{photo_id}/rename")
    def execute_existing_photo_rename(
        photo_id: int, payload: PhotoRenameRequest
    ) -> dict[str, object]:
        if not payload.expected_sha256:
            raise HTTPException(status_code=400, detail="缺少預覽時的 SHA-256，請先預覽再改名")
        with database() as conn:
            root = conn.execute(
                "SELECT i.root_id FROM photo p JOIN item i ON i.id=p.item_id WHERE p.id=?",
                (photo_id,),
            ).fetchone()
            if root is None:
                raise HTTPException(status_code=404, detail="找不到指定照片")
            if scan_job_status(int(root["root_id"]))["state"] == "running":
                raise HTTPException(
                    status_code=409, detail="掃描進行中，請等待完成或先取消掃描再改名"
                )
            try:
                result = rename_existing_photo(
                    conn,
                    photo_id,
                    payload.target_filename,
                    expected_sha256=payload.expected_sha256,
                    reason=payload.reason,
                )
                result["item"] = _item_detail(conn, int(result["item_id"]))
                return result
            except OrganizerConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except OrganizerError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/photos/{photo_id}/transfer/preview")
    def preview_photo_transfer(photo_id: int, payload: SlotTransferRequest) -> dict[str, object]:
        with database() as conn:
            root = conn.execute(
                "SELECT i.root_id FROM photo p JOIN item i ON i.id=p.item_id WHERE p.id=?",
                (photo_id,),
            ).fetchone()
            if root is None:
                raise HTTPException(status_code=404, detail="找不到指定照片")
            if scan_job_status(int(root["root_id"]))["state"] == "running":
                raise HTTPException(status_code=409, detail="掃描進行中，請稍後再交換")
            try:
                return preview_slot_transfer(
                    conn, photo_id, payload.target_slot, payload.target_photo_id
                )
            except OrganizerConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except OrganizerError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/photos/{photo_id}/transfer")
    def transfer_photo(photo_id: int, payload: SlotTransferRequest) -> dict[str, object]:
        if not payload.expected_source_sha256:
            raise HTTPException(status_code=400, detail="請先確認預覽中的照片 SHA-256")
        with database() as conn:
            root = conn.execute(
                "SELECT i.root_id FROM photo p JOIN item i ON i.id=p.item_id WHERE p.id=?",
                (photo_id,),
            ).fetchone()
            if root is None:
                raise HTTPException(status_code=404, detail="找不到指定照片")
            if scan_job_status(int(root["root_id"]))["state"] == "running":
                raise HTTPException(status_code=409, detail="掃描進行中，請稍後再交換")
            try:
                result = execute_slot_transfer(
                    conn,
                    photo_id,
                    payload.target_slot,
                    payload.target_photo_id,
                    payload.expected_source_sha256,
                    payload.expected_target_sha256,
                )
                result["item"] = _item_detail(conn, int(result["item_id"]))
                return result
            except OrganizerConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except OrganizerError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/items/{item_id}/slot-transfers")
    def recent_slot_transfers(item_id: int) -> list[dict[str, object]]:
        with database() as conn:
            item = conn.execute(
                "SELECT root_id, relative_path FROM item WHERE id=?", (item_id,)
            ).fetchone()
            if item is None:
                raise HTTPException(status_code=404, detail="找不到指定設備")
            return [
                dict(row)
                for row in conn.execute(
                    """SELECT id, root_id, created_at, source_before, source_after,
                              target_before, target_after, reverted_at
                       FROM slot_transfer_log WHERE root_id=? AND item_relative_path=?
                       ORDER BY id DESC LIMIT 20""",
                    (item["root_id"], item["relative_path"]),
                )
            ]

    @app.post("/api/slot-transfers/{root_id}/undo/{transfer_log_id}")
    def undo_photo_slot_transfer(root_id: int, transfer_log_id: int) -> dict[str, object]:
        if scan_job_status(root_id)["state"] == "running":
            raise HTTPException(status_code=409, detail="掃描進行中，請稍後再復原")
        with database() as conn:
            try:
                result = undo_slot_transfer(conn, root_id, transfer_log_id)
                result["item"] = _item_detail(conn, int(result["item_id"]))
                return result
            except OrganizerConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except OrganizerError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/items/{item_id}/slots/{slot}/reorder")
    def adjust_photo_order(item_id: int, slot: str, payload: ReorderPhotos) -> dict[str, object]:
        with database() as conn:
            try:
                reorder_photos(conn, item_id, slot, payload.photo_ids)
            except StorageError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return _item_detail(conn, item_id)

    @app.post("/api/items", status_code=201)
    def add_item_folder(payload: ItemFolderCreate) -> dict[str, object]:
        with database() as conn:
            try:
                item_id = create_item_folder(
                    conn,
                    payload.root_id,
                    payload.category_code,
                    payload.year,
                    payload.period,
                    payload.building,
                    payload.code,
                )
            except StorageConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except StorageError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return _item_detail(conn, item_id)

    @app.post("/api/folders/year", status_code=201)
    def add_year_folder(payload: YearFolderCreate) -> dict[str, object]:
        with database() as conn:
            try:
                return create_year_folder(
                    conn, payload.root_id, payload.category_code, payload.year
                )
            except StorageConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except StorageError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/folders/period", status_code=201)
    def add_period_folder(payload: PeriodFolderCreate) -> dict[str, object]:
        with database() as conn:
            try:
                return create_period_folder(
                    conn,
                    payload.root_id,
                    payload.category_code,
                    payload.year,
                    payload.period,
                )
            except StorageConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except StorageError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/folders/building", status_code=201)
    def add_building_folder(payload: BuildingFolderCreate) -> dict[str, object]:
        with database() as conn:
            try:
                return create_building_folder(
                    conn,
                    payload.root_id,
                    payload.category_code,
                    payload.year,
                    payload.period,
                    payload.building,
                )
            except StorageConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except StorageError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/roots/{root_id}/status")
    def cached_root_status(root_id: int) -> dict[str, object]:
        with database() as conn:
            try:
                return root_status(conn, root_id)
            except CacheError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/roots/{root_id}/cache/thumbnails")
    def cache_thumbnails(root_id: int, limit: int | None = None) -> dict[str, object]:
        with database() as conn:
            try:
                status = root_status(conn, root_id)
                if not status["connected"]:
                    raise CacheUnavailable("照片根目錄目前離線，無法新增縮圖快取")
                result = prime_thumbnail_cache(conn, root_id, limit=limit)
                result["root_id"] = root_id
                return result
            except CacheUnavailable as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except CacheError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/roots/{root_id}/offline-queue")
    def offline_queue(root_id: int) -> list[dict[str, object]]:
        with database() as conn:
            try:
                return list_offline_queue(conn, root_id)
            except CacheError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/roots/{root_id}/offline-queue/sync")
    def sync_offline(root_id: int) -> dict[str, object]:
        with database() as conn:
            try:
                return sync_offline_queue(conn, root_id)
            except CacheUnavailable as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except CacheError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/ledgers")
    def ledgers() -> list[dict[str, object]]:
        with database() as conn:
            return list_ledgers(conn)

    @app.post("/api/ledgers/excel", status_code=201)
    async def import_excel_ledger(
        file: Annotated[UploadFile, File()],
        name: Annotated[str | None, Query()] = None,
    ) -> dict[str, object]:
        data = await file.read()
        try:
            rows = parse_excel_bytes(data)
        except ReconcileError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        with database() as conn:
            ledger_id = import_ledger(
                conn,
                name=name or file.filename or "Excel 清冊",
                source_type="xlsx",
                rows=rows,
                source_bytes=data,
                source_filename=file.filename,
            )
            return next(row for row in list_ledgers(conn) if row["id"] == ledger_id)

    @app.post("/api/ledgers/excel/preview")
    async def preview_excel_ledger(
        file: Annotated[UploadFile, File()],
    ) -> dict[str, object]:
        data = await file.read()
        try:
            preview = preview_excel_bytes(data)
        except ReconcileError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        preview["source_filename"] = file.filename
        return preview

    @app.post("/api/ledgers/text", status_code=201)
    def import_text_ledger(payload: LedgerTextImport) -> dict[str, object]:
        try:
            rows = parse_text_rows(payload.text)
        except ReconcileError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        with database() as conn:
            ledger_id = import_ledger(
                conn,
                name=payload.name,
                source_type="text",
                rows=rows,
                source_bytes=payload.text.encode("utf-8"),
                source_text=payload.text,
            )
            return next(row for row in list_ledgers(conn) if row["id"] == ledger_id)

    @app.post("/api/ledgers/text/preview")
    def preview_text_ledger(payload: LedgerTextImport) -> dict[str, object]:
        try:
            return preview_text_rows(payload.text)
        except ReconcileError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/ledgers/{ledger_id}")
    def ledger_detail(ledger_id: int) -> dict[str, object]:
        with database() as conn:
            try:
                return get_ledger_detail(conn, ledger_id)
            except ReconcileError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/api/ledgers/{ledger_id}")
    def update_ledger_name(ledger_id: int, payload: LedgerRename) -> dict[str, object]:
        with database() as conn:
            try:
                return rename_ledger(conn, ledger_id, payload.name)
            except ReconcileError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/ledgers/{ledger_id}")
    def remove_ledger(ledger_id: int) -> dict[str, object]:
        with database() as conn:
            try:
                return delete_ledger(conn, ledger_id)
            except ReconcileError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/aliases")
    def aliases() -> list[dict[str, object]]:
        with database() as conn:
            seed_default_aliases(conn)
            return list_aliases(conn)

    @app.post("/api/aliases")
    def upsert_alias(payload: AliasUpsert) -> dict[str, object]:
        with database() as conn:
            try:
                return save_alias(
                    conn,
                    payload.source_value,
                    payload.target_value,
                    confirmed=payload.confirmed,
                )
            except ReconcileError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/reconcile")
    def reconcile(payload: ReconcileRequest) -> dict[str, object]:
        with database() as conn:
            try:
                result = build_reconciliation(
                    conn,
                    root_id=payload.root_id,
                    ledger_id=payload.ledger_id,
                    period=payload.period.strip() if payload.period else None,
                    category_code=payload.category_code,
                )
            except ReconcileError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            result["reshoot_text"] = reshoot_text(result)
            return result

    @app.post("/api/reconcile/reshot")
    def update_reshot_mark(payload: ReshootMarkUpdate) -> dict[str, object]:
        with database() as conn:
            try:
                set_reshoot_mark(
                    conn,
                    root_id=payload.root_id,
                    ledger_id=payload.ledger_id,
                    category_code=payload.category_code,
                    device_no=payload.device_no,
                    marked=payload.marked,
                )
            except ReconcileError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"marked": payload.marked}

    @app.get("/api/organizer/{root_id}")
    def organizer_analysis(root_id: int) -> dict[str, object]:
        with database() as conn:
            try:
                return analyze_root(conn, root_id)
            except OrganizerError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organizer/{root_id}/rename/preview")
    def organizer_rename_preview(root_id: int, payload: RenameSelection) -> dict[str, object]:
        with database() as conn:
            try:
                return preview_renames(conn, root_id, payload.candidate_ids)
            except OrganizerError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organizer/{root_id}/rename")
    def organizer_rename(root_id: int, payload: RenameSelection) -> dict[str, object]:
        with database() as conn:
            try:
                return execute_renames(conn, root_id, payload.candidate_ids)
            except OrganizerConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except OrganizerError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/organizer/{root_id}/history")
    def organizer_history(root_id: int) -> list[dict[str, object]]:
        with database() as conn:
            try:
                return rename_history(conn, root_id)
            except OrganizerError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organizer/{root_id}/undo/{log_id}")
    def organizer_undo(root_id: int, log_id: int) -> dict[str, object]:
        with database() as conn:
            try:
                return undo_rename(conn, root_id, log_id)
            except OrganizerConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except OrganizerError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/reconcile/export")
    def reconcile_export(
        root_id: int,
        ledger_id: int,
        format: str = "csv",
        period: str | None = None,
        category_code: str = "extinguisher",
    ) -> Response:
        with database() as conn:
            try:
                result = build_reconciliation(
                    conn,
                    root_id=root_id,
                    ledger_id=ledger_id,
                    period=period.strip() if period else None,
                    category_code=category_code,
                )
                content, media_type, filename = export_reconciliation(result, format.casefold())
            except ReconcileError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        safe_filename = (
            "firelens-reshoot.csv" if format.casefold() == "csv" else "firelens-reshoot.xlsx"
        )
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
        )

    @app.post("/api/reconcile/export/save")
    def reconcile_export_save(payload: ReconcileExportSave) -> dict[str, object]:
        file_format = payload.format.casefold()
        if file_format not in {"csv", "xlsx"}:
            raise HTTPException(status_code=400, detail="僅支援匯出 CSV 或 Excel")
        with database() as conn:
            try:
                result = build_reconciliation(
                    conn,
                    root_id=payload.root_id,
                    ledger_id=payload.ledger_id,
                    period=payload.period.strip() if payload.period else None,
                    category_code=payload.category_code,
                )
                content, _, _ = export_reconciliation(result, file_format)
            except ReconcileError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            return export_registry.save(prefix="缺失清單", content=content, extension=file_format)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"檔案儲存失敗：{exc}") from exc

    frontend_dist = _frontend_dist_dir()
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


app = create_app()

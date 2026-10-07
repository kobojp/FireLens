from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import asynccontextmanager
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
from .logging_config import RequestLoggingMiddleware, configure_logging, get_logger
from .organizer import (
    OrganizerConflict,
    OrganizerError,
    analyze_root,
    execute_renames,
    preview_renames,
    rename_history,
    undo_rename,
)
from .reconcile import (
    ReconcileError,
    build_reconciliation,
    export_reconciliation,
    import_ledger,
    list_aliases,
    list_ledgers,
    parse_excel_bytes,
    parse_text_rows,
    reshoot_text,
    save_alias,
    seed_default_aliases,
    set_reshoot_mark,
)
from .scanner import scan_root
from .security import DesktopSecurityMiddleware
from .settings import custom_slots_for
from .storage import (
    StorageConflict,
    StorageError,
    create_building_folder,
    create_item_folder,
    create_period_folder,
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


class AliasUpsert(BaseModel):
    source_value: str = Field(min_length=1)
    target_value: str = Field(min_length=1)
    confirmed: bool = True


class ReconcileRequest(BaseModel):
    root_id: int
    ledger_id: int
    period: str | None = None


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
        try:
            yield
        finally:
            logger.info("application shutdown version=%s", __version__)

    app = FastAPI(title="FireLens API", version=__version__, lifespan=lifespan)
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

    @app.post("/api/roots/{root_id}/scan")
    def scan(root_id: int) -> dict[str, object]:
        with database() as conn:
            try:
                result = scan_root(conn, root_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except FileNotFoundError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return {
                "root_id": result.root_id,
                "items": result.items,
                "photos": result.photos,
                "categories": result.categories,
            }

    @app.get("/api/roots/{root_id}/tree")
    def tree(root_id: int) -> list[dict[str, object]]:
        with database() as conn:
            exists = conn.execute("SELECT 1 FROM root WHERE id = ?", (root_id,)).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail="找不到指定的根目錄")
            return build_tree(conn, root_id)

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

    @app.post("/api/items/{item_id}/slots/{slot}/photos")
    async def upload_photo(
        item_id: int,
        slot: str,
        file: Annotated[UploadFile, File()],
        replace_photo_id: Annotated[int | None, Query()] = None,
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
            )
            return next(row for row in list_ledgers(conn) if row["id"] == ledger_id)

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
            )
            return next(row for row in list_ledgers(conn) if row["id"] == ledger_id)

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
    ) -> Response:
        with database() as conn:
            try:
                result = build_reconciliation(
                    conn,
                    root_id=root_id,
                    ledger_id=ledger_id,
                    period=period.strip() if period else None,
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

    frontend_dist = _frontend_dist_dir()
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


app = create_app()

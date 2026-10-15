from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .db import database
from .scanner import ScanCancelled, ScanSummary, scan_root


class ScanJobError(ValueError):
    pass


class ScanAlreadyRunning(ScanJobError):
    pass


@dataclass
class _ScanJob:
    root_id: int
    cancel_event: threading.Event
    state: str = "running"
    started_at: str = ""
    finished_at: str | None = None
    summary: ScanSummary | None = None
    error: str | None = None
    cancel_requested: bool = False


_jobs: dict[int, _ScanJob] = {}
_jobs_lock = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _payload(job: _ScanJob | None, root_id: int) -> dict[str, object]:
    if job is None:
        return {
            "root_id": root_id,
            "state": "idle",
            "started_at": None,
            "finished_at": None,
            "cancel_requested": False,
            "summary": None,
            "error": None,
        }
    return {
        "root_id": root_id,
        "state": job.state,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "cancel_requested": job.cancel_requested,
        "summary": asdict(job.summary) if job.summary is not None else None,
        "error": job.error,
    }


def scan_job_status(root_id: int) -> dict[str, object]:
    with _jobs_lock:
        return _payload(_jobs.get(root_id), root_id)


def _run_scan(job: _ScanJob) -> None:
    try:
        with database() as conn:
            summary = scan_root(conn, job.root_id, cancel_check=job.cancel_event.is_set)
        with _jobs_lock:
            job.summary = summary
            job.state = "completed"
            job.finished_at = _now()
    except ScanCancelled:
        with _jobs_lock:
            job.state = "cancelled"
            job.finished_at = _now()
    except Exception as exc:  # noqa: BLE001 - surfaced as a bounded background-job error
        with _jobs_lock:
            job.state = "error"
            job.error = str(exc) or exc.__class__.__name__
            job.finished_at = _now()


def start_scan_job(root_id: int) -> dict[str, object]:
    with database() as conn:
        row = conn.execute("SELECT path FROM root WHERE id=?", (root_id,)).fetchone()
    if row is None:
        raise ScanJobError("找不到指定的根目錄")
    root_path = Path(str(row["path"])).expanduser()
    if not root_path.is_dir():
        raise FileNotFoundError(f"根目錄不存在或無法讀取：{root_path}")

    with _jobs_lock:
        current = _jobs.get(root_id)
        if current is not None and current.state == "running":
            raise ScanAlreadyRunning("掃描進行中")
        job = _ScanJob(
            root_id=root_id,
            cancel_event=threading.Event(),
            started_at=_now(),
        )
        _jobs[root_id] = job
        payload = _payload(job, root_id)

    worker = threading.Thread(
        target=_run_scan,
        args=(job,),
        name=f"firelens-scan-{root_id}",
        daemon=True,
    )
    worker.start()
    return payload


def cancel_scan_job(root_id: int) -> dict[str, object]:
    with _jobs_lock:
        job = _jobs.get(root_id)
        if job is None or job.state != "running":
            return _payload(job, root_id)
        job.cancel_requested = True
        job.cancel_event.set()
        return _payload(job, root_id)

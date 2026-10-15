from __future__ import annotations

import time

from fastapi.testclient import TestClient


def run_scan(client: TestClient, root_id: int, timeout: float = 5.0) -> dict[str, object]:
    started = client.post(f"/api/roots/{root_id}/scan")
    assert started.status_code == 202, started.text
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/roots/{root_id}/scan")
        assert response.status_code == 200, response.text
        status = response.json()
        if status["state"] == "completed":
            summary = status.get("summary")
            assert isinstance(summary, dict)
            return summary
        if status["state"] in {"cancelled", "error"}:
            raise AssertionError(f"scan ended as {status['state']}: {status.get('error')}")
        time.sleep(0.02)
    raise AssertionError("scan did not finish before timeout")

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_health_and_tree_smoke(monkeypatch, tmp_path: Path, sample_source: Path) -> None:
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
    app = create_app()

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        created = client.post(
            "/api/roots",
            json={"path": str(sample_source), "label": "合成測試"},
        )
        assert created.status_code == 201
        root_id = created.json()["id"]

        scan = client.post(f"/api/roots/{root_id}/scan")
        assert scan.status_code == 200
        assert scan.json()["items"] == 4

        tree = client.get(f"/api/roots/{root_id}/tree")
        assert tree.status_code == 200
        labels = {node["label"] for node in tree.json()}
        assert labels == {"滅火器", "放置盒", "燈具"}

        extinguisher = next(node for node in tree.json() if node["label"] == "滅火器")
        item = extinguisher["children"][0]["children"][0]["children"][0]["children"][0]
        photos = client.get(f"/api/items/{item['id']}/photos")
        assert photos.status_code == 200
        assert {photo["filename"] for photo in photos.json()} == {
            "完成.jpg",
            "有效日期.jpg",
            "編號.JPG",
        }

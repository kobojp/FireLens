from __future__ import annotations

from pathlib import Path

from backend.app.db import connect
from backend.app.scanner import _slot_for, _status_for
from tests.test_m2 import find_item, jpeg_bytes, setup_client


def test_slot_for_numbered_and_custom() -> None:
    assert _slot_for("extinguisher", "藥劑.jpg") == "藥劑"
    assert _slot_for("extinguisher", "藥劑-2.jpg") == "藥劑"
    assert _slot_for("extinguisher", "有效日期-1.jpg") == "藥劑"
    assert _slot_for("extinguisher", "瓶身.jpg") is None
    assert _slot_for("extinguisher", "瓶身.jpg", ("瓶身",)) == "瓶身"
    assert _slot_for("extinguisher", "瓶身-3.jpg", ("瓶身",)) == "瓶身"
    assert _slot_for("extinguisher", "編號 (2).jpg") is None


def test_status_ignores_photo_count_and_custom_slots() -> None:
    names = ["編號.jpg", "藥劑.jpg", "藥劑-1.jpg", "藥劑-2.jpg", "完成.jpg", "瓶身.jpg"]
    assert _status_for("extinguisher", names) == "complete"
    assert _status_for("extinguisher", ["編號.jpg", "藥劑-1.jpg"]) == "partial"


def test_multi_photo_and_custom_slot_import(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    client, root_id, db_path = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        tree = client.get(f"/api/roots/{root_id}/tree").json()
        item_id = int(find_item(tree, "中-01-02")["id"])
        item_dir = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02"

        saved = client.put("/api/settings", json={"custom_slots": {"extinguisher": ["瓶身"]}})
        assert saved.status_code == 200, saved.text
        assert saved.json()["custom_slots"]["extinguisher"] == ["瓶身"]

        for index in range(3):
            response = client.post(
                f"/api/items/{item_id}/slots/藥劑/photos",
                files={"file": (f"p{index}.jpg", jpeg_bytes((index * 40, 10, 10)), "image/jpeg")},
            )
            assert response.status_code == 200
        for name in ("藥劑.jpg", "藥劑-1.jpg", "藥劑-2.jpg"):
            assert (item_dir / name).is_file()

        custom = client.post(
            f"/api/items/{item_id}/slots/瓶身/photos",
            files={"file": ("c.jpg", jpeg_bytes((9, 9, 9)), "image/jpeg")},
        )
        assert custom.status_code == 200
        detail = custom.json()
        assert detail["custom_slots"] == ["瓶身"]
        slots = {photo["filename"]: photo["slot"] for photo in detail["photos"]}
        assert slots["瓶身.jpg"] == "瓶身"
        assert slots["藥劑-2.jpg"] == "藥劑"
        # 缺漏判定仍只看必要槽位
        assert detail["status"] == "partial"

        unknown = client.post(
            f"/api/items/{item_id}/slots/不存在/photos",
            files={"file": ("x.jpg", jpeg_bytes((1, 2, 3)), "image/jpeg")},
        )
        assert unknown.status_code == 400

        conn = connect(db_path)
        try:
            actions = [row["action"] for row in conn.execute("SELECT action FROM audit_log")]
        finally:
            conn.close()
        assert actions.count("import_photo") == 4
    finally:
        client.__exit__(None, None, None)


def test_custom_slot_validation(monkeypatch, tmp_path: Path, sample_source: Path) -> None:
    client, _, _ = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        for bad in (["藥劑"], ["有效日期"], ["a/b"], ["瓶-1"], [""], ["x", "X"], ["尾."]):
            response = client.put("/api/settings", json={"custom_slots": {"extinguisher": bad}})
            assert response.status_code == 400, bad
        missing = client.put("/api/settings", json={"custom_slots": {"nope": ["a"]}})
        assert missing.status_code == 400
    finally:
        client.__exit__(None, None, None)

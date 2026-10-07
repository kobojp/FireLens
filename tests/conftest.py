from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.db import initialize_database


@pytest.fixture
def sample_source(tmp_path: Path) -> Path:
    root = tmp_path / "source"

    extinguisher = root / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-01"
    extinguisher.mkdir(parents=True)
    (extinguisher / "編號.JPG").write_bytes(b"number")
    (extinguisher / "有效日期.jpg").write_bytes(b"date")
    (extinguisher / "完成.jpg").write_bytes(b"done")
    (extinguisher / "desktop.ini").write_text("[ViewState]", encoding="utf-8")

    empty_item = root / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02"
    empty_item.mkdir(parents=True)

    box = root / "放置盒" / "2026年" / "新增5P 二氧化碳(含放置盒)" / "中-02-C124"
    box.mkdir(parents=True)
    (box / "新增1.jpg").write_bytes(b"legacy-1")
    (box / "完成.jpg").write_bytes(b"legacy-done")

    lamp = root / "燈具" / "2026年" / "9月份更換" / "立體停車場" / "立體5樓" / "D-05-04"
    lamp.mkdir(parents=True)
    (lamp / "1.jpg").write_bytes(b"lamp-1")
    (lamp / "2.PNG").write_bytes(b"lamp-2")

    return root


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "firelens.sqlite3"
    initialize_database(path)
    return path

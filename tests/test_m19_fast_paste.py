"""M19-E: fast indexed paste, candidate safety, and synthetic performance checks."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest

import backend.app.duplicates as duplicates
from backend.app.scanner import scan_root
from backend.app.storage import DuplicatePhotoConflict, delete_photo, import_photo
from tests.test_m19_dynamic_folders import _jpeg_bytes, _setup


def _existing(tmp_path: Path):
    conn, root_id, root = _setup(tmp_path)
    scan_root(conn, root_id)
    item_id = int(conn.execute("SELECT id FROM item WHERE code='水-01'").fetchone()[0])
    assert duplicates.index_photos(conn, root_id)["analyzed"] == 2
    return conn, root_id, root, item_id


def test_indexed_upload_never_scans_or_stats_unrelated_photos(tmp_path, monkeypatch):
    conn, root_id, _, item_id = _existing(tmp_path)
    try:
        calls: list[str] = []
        real_safe_stat = duplicates._safe_stat

        def track(root: Path, relative: str):
            calls.append(relative)
            return real_safe_stat(root, relative)

        monkeypatch.setattr(duplicates, "_safe_stat", track)
        monkeypatch.setattr(duplicates, "_photos", lambda *_: pytest.fail("full photo traversal"))
        monkeypatch.setattr(
            duplicates, "index_photos", lambda *_a, **_kw: pytest.fail("full root indexing")
        )
        new_hash = hashlib.sha256(_jpeg_bytes("green")).hexdigest()
        assert duplicates.preflight(conn, root_id, new_hash) == []
        assert calls == []
        original_hash = hashlib.sha256(_jpeg_bytes("red")).hexdigest()
        red_matches = duplicates.preflight(conn, root_id, original_hash)
        assert len(red_matches) == 1
        assert len(calls) == 1 and calls[0].endswith("前.jpg")
        calls.clear()
        blue_hash = hashlib.sha256(_jpeg_bytes("blue")).hexdigest()
        blue_matches = duplicates.preflight(conn, root_id, blue_hash)
        assert len(blue_matches) == 1
        assert len(calls) == 1 and calls[0].endswith("照片.jpg")
        original = conn.execute(
            "SELECT relative_path FROM photo WHERE item_id=?", (item_id,)
        ).fetchone()[0]
        assert original
    finally:
        conn.close()


def test_new_import_immediately_fingerprinted_and_reused(tmp_path, monkeypatch):
    conn, root_id, root, item_id = _existing(tmp_path)
    try:
        monkeypatch.setattr(
            duplicates, "index_photos", lambda *_a, **_kw: pytest.fail("unexpected rescan")
        )
        first = import_photo(conn, item_id, "中", "green.jpg", _jpeg_bytes("green"))
        assert "timing_ms" in first
        assert first["timing_ms"]["total"] >= first["timing_ms"]["duplicate_check"]
        row = conn.execute(
            """SELECT f.sha256,p.filename FROM photo_fingerprint f
               JOIN photo p ON p.relative_path=f.relative_path
               JOIN item i ON i.id=p.item_id AND i.root_id=f.root_id
               WHERE f.root_id=? AND i.id=? AND p.filename='中.jpg'""",
            (root_id, item_id),
        ).fetchone()
        assert row is not None and row["sha256"] == first["sha256"]
        with pytest.raises(DuplicatePhotoConflict) as exc:
            import_photo(conn, item_id, "後", "green.jpg", _jpeg_bytes("green"))
        assert exc.value.matches[0]["filename"] == "中.jpg"
        new_photo = conn.execute(
            "SELECT id FROM photo WHERE item_id=? AND filename='中.jpg'",
            (item_id,),
        ).fetchone()
        assert new_photo is not None
        delete_photo(conn, int(new_photo[0]))
        assert not conn.execute(
            "SELECT 1 FROM photo_fingerprint WHERE root_id=? AND relative_path LIKE ?",
            (root_id, "%/中.jpg"),
        ).fetchone()
        assert duplicates.preflight(conn, root_id, first["sha256"]) == []
    finally:
        conn.close()


def test_invalid_digest_candidate_blocks_instead_of_false_clean(tmp_path, monkeypatch):
    conn, root_id, root, _ = _existing(tmp_path)
    try:
        source = root / "水帶" / "倉庫" / "水-01" / "前.jpg"
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        original_safe_stat = duplicates._safe_stat

        def altered_stat(root_dir: Path, relative: str):
            entry = original_safe_stat(root_dir, relative)
            if entry and relative.endswith("前.jpg"):
                return None
            return entry

        monkeypatch.setattr(duplicates, "_safe_stat", altered_stat)
        with pytest.raises(duplicates.DuplicateIndexRequired, match="無法安全讀取"):
            duplicates.preflight(conn, root_id, original_hash)
    finally:
        conn.close()


def test_large_synthetic_indexed_root_is_fast_and_uses_digest_index(tmp_path, monkeypatch):
    conn, root_id, root, item_id = _existing(tmp_path)
    try:
        count = 4000
        prefix = "水帶/倉庫/水-01"
        synthetic = [
            (item_id, f"synthetic-{n}.jpg", f"{prefix}/synthetic-{n}.jpg", ".jpg", "前", 1512, 1)
            for n in range(count)
        ]
        with conn:
            conn.executemany(
                """INSERT INTO photo(
                     item_id,filename,relative_path,extension,slot,size_bytes,mtime_ns
                   ) VALUES (?,?,?,?,?,?,?)""",
                synthetic,
            )
            conn.executemany(
                """INSERT INTO photo_fingerprint(
                     root_id,relative_path,size_bytes,mtime_ns,algorithm,sha256
                   ) VALUES (?,?,?,?,?,?)""",
                [
                    (
                        root_id,
                        path,
                        1512,
                        1,
                        duplicates.ALGORITHM,
                        hashlib.sha256(f"synthetic-{n}".encode()).hexdigest(),
                    )
                    for n, (_, _, path, _, _, _, _) in enumerate(synthetic)
                ],
            )
        explanation = conn.execute(
            """EXPLAIN QUERY PLAN SELECT f.sha256 FROM photo_fingerprint f
               INDEXED BY idx_photo_fingerprint_digest WHERE f.root_id=? AND f.sha256=?""",
            (root_id, hashlib.sha256(b"miss").hexdigest()),
        ).fetchall()
        assert any("idx_photo_fingerprint_digest" in row[3] for row in explanation)
        joined_plan = conn.execute(
            """EXPLAIN QUERY PLAN
                SELECT p.id FROM photo_fingerprint f INDEXED BY idx_photo_fingerprint_digest
                JOIN photo p INDEXED BY idx_photo_relative_path
                  ON p.relative_path=f.relative_path
                JOIN item i ON i.id=p.item_id AND i.root_id=f.root_id
               WHERE f.root_id=? AND f.sha256=?""",
            (root_id, hashlib.sha256(b"miss").hexdigest()),
        ).fetchall()
        plan_text = " | ".join(str(row[3]) for row in joined_plan)
        assert "idx_photo_fingerprint_digest" in plan_text
        assert "idx_photo_relative_path" in plan_text
        # Read-only approximation of the old per-upload metadata traversal.
        # The synthetic files are absent, so this measures local filesystem
        # metadata calls only, NOT an actual Google Drive paste benchmark.
        real_safe_stat = duplicates._safe_stat
        legacy_samples = []
        for _ in range(3):
            started = time.perf_counter()
            for record in duplicates._photos(conn, root_id):
                real_safe_stat(root.resolve(), str(record["relative_path"]))
            legacy_samples.append((time.perf_counter() - started) * 1000)
        monkeypatch.setattr(
            duplicates, "_safe_stat", lambda *_: pytest.fail("disk touched with no matches")
        )
        monkeypatch.setattr(
            duplicates, "index_photos", lambda *_a, **_kw: pytest.fail("disk-wide scan")
        )
        digest = hashlib.sha256(b"miss").hexdigest()
        samples = []
        for _ in range(7):
            started = time.perf_counter()
            assert duplicates.preflight(conn, root_id, digest) == []
            samples.append((time.perf_counter() - started) * 1000)
        assert min(samples) >= 0
        print(
            f"\nM19-E Windows synthetic indexed lookup: {count + 2} entries; "
            f"median={sorted(samples)[len(samples) // 2]:.3f} ms; "
            f"range={min(samples):.3f}–{max(samples):.3f} ms"
        )
        print(
            f"Legacy-style metadata traversal approximation: {count + 2} entries; "
            f"median={sorted(legacy_samples)[1]:.3f} ms; "
            "synthetic local filesystem only"
        )
    finally:
        conn.close()

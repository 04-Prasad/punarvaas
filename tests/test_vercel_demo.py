import gzip
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from core.store import demo


def test_snapshot_restored_once_and_source_is_unchanged(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE district (name TEXT)")
        conn.execute("INSERT INTO district VALUES ('chamoli')")
    snapshot = tmp_path / "demo.db.gz"
    snapshot.write_bytes(gzip.compress(source.read_bytes()))
    original = snapshot.read_bytes()
    monkeypatch.setattr(demo, "SNAPSHOT", snapshot)
    monkeypatch.setattr(demo, "_database", None)
    monkeypatch.setattr(demo.tempfile, "tempdir", str(tmp_path))
    with ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(lambda _: demo.demo_database(), range(8)))
    assert len(set(paths)) == 1
    with sqlite3.connect(paths[0]) as conn:
        assert conn.execute("SELECT name FROM district").fetchone()[0] == "chamoli"
        conn.execute("INSERT INTO district VALUES ('kendrapara')")
    assert snapshot.read_bytes() == original

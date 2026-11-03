"""Restore the demo snapshot to serverless scratch space, once per process."""
from __future__ import annotations

import gzip
import logging
import shutil
import tempfile
from pathlib import Path
from threading import Lock

SNAPSHOT = Path(__file__).resolve().parents[2] / "deployment-data" / "demo.db.gz"
_lock = Lock()
_database: Path | None = None


def demo_database() -> Path:
    global _database
    with _lock:
        if _database is None:
            if not SNAPSHOT.is_file():
                raise RuntimeError("Demo snapshot missing. Run scripts/prepare_vercel.py before deploying.")
            directory = Path(tempfile.mkdtemp(prefix="punarvaas-demo-"))
            target = directory / "demo.db"
            try:
                with gzip.open(SNAPSHOT, "rb") as source, target.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
            except Exception:
                logging.getLogger(__name__).exception("Could not restore the bundled demo database")
                target.unlink(missing_ok=True)
                directory.rmdir()
                raise
            _database = target
        return _database

"""Package a consistent copy of the local demo database for Vercel CLI upload."""
from pathlib import Path
import gzip
import shutil
import sqlite3
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / "data" / "punarvaas.db"
    destination = ROOT / "deployment-data" / "demo.db.gz"
    destination.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        snapshot = Path(staging) / "demo.db"
        src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        dst = sqlite3.connect(snapshot)
        try:
            src.backup(dst)
            districts = [r[0] for r in dst.execute("SELECT district FROM district")]
            if not districts:
                raise RuntimeError("Cannot deploy an empty demo database")
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Demo database failed integrity check")
        finally:
            src.close()
            dst.close()
        with snapshot.open("rb") as inp, gzip.open(destination, "wb", compresslevel=6) as out:
            shutil.copyfileobj(inp, out)
    print(f"Packaged {', '.join(districts)}: {destination.stat().st_size / 1024**2:.1f} MiB")


if __name__ == "__main__":
    main()

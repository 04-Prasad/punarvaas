"""
Load Engine 1/2 output into the store.

    python -m tools.ingest                    # every district found
    python -m tools.ingest --district chamoli
    PUNARVAAS_DB=postgresql://... python -m tools.ingest
"""
from __future__ import annotations

import argparse

from core.config import DATA, DISTRICTS
from core.store import open_store


def main(argv=None):
    ap = argparse.ArgumentParser(description="Load processed snapshots into the store")
    ap.add_argument("--district", default="all", choices=list(DISTRICTS) + ["all"])
    ap.add_argument("--db", default=None, help="override PUNARVAAS_DB")
    a = ap.parse_args(argv)

    keys = list(DISTRICTS) if a.district == "all" else [a.district]
    keys = [k for k in keys if (DATA / "processed" / k / "cells.parquet").exists()]
    if not keys:
        raise SystemExit("nothing to ingest — run  python -m pipelines.engine1 "
                         "--district all  first")
    st = open_store(a.db)
    for k in keys:
        r = st.ingest_district(k)
        print(f"  {r['district']:<12} {r['cells']:>7,} cells  "
              f"{r.get('villages', 0):>3} villages  {r.get('sites', 0):>4} sites  "
              f"{r.get('plan_rows', 0):>3} plan rows")
    print(f"  → {type(st).__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

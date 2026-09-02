"""
PUNARVAAS · SQLite backend.

Same tables and same column names as db/migrations/*.sql, so a query written
against one backend reads correctly against the other. Two differences are
unavoidable and are handled explicitly rather than hidden:

  geometry   PostGIS stores the hex boundary as `geometry(Polygon, 4326)`.
             SQLite stores the GeoJSON ring as text. The API serves GeoJSON in
             both cases, so nothing downstream can tell.
  audit      PostGIS revokes UPDATE and DELETE on `audit_log` at the role level.
             SQLite has no roles, so the same guarantee is enforced with a pair
             of BEFORE triggers that RAISE(ABORT). Weaker — a superuser with the
             file can still rewrite it — and the report says so.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import numpy as np
import pandas as pd

from core.config import DATA
from core.jsonio import dumps as jdumps, json_safe

CELL_MAP_COLUMNS = ("h3_index", "lat", "lon", "zone", "h_union", "risk_score",
                    "governing_hazard", "population", "confidence",
                    "return_period_yr", "village_name", "hazard_count",
                    "slope_deg", "elevation_m")

DDL = """
CREATE TABLE IF NOT EXISTS district (
  district TEXT PRIMARY KEY, name TEXT, state TEXT, terrain TEXT,
  snapshot_id TEXT, contains_synthetic INTEGER,
  cells INTEGER, population REAL, pop_at_risk REAL, eal_annual_inr REAL,
  ingested_at TEXT DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS hex_feature (
  h3_index TEXT PRIMARY KEY, district TEXT NOT NULL, snapshot_id TEXT,
  payload TEXT NOT NULL, boundary TEXT,
  lat REAL, lon REAL, zone TEXT, h_union REAL, risk_score REAL,
  population REAL, governing_hazard TEXT, confidence REAL,
  lgd_village_code TEXT, village_name TEXT);
CREATE INDEX IF NOT EXISTS ix_hex_district ON hex_feature(district, zone);
CREATE INDEX IF NOT EXISTS ix_hex_bbox     ON hex_feature(district, lat, lon);
CREATE INDEX IF NOT EXISTS ix_hex_village  ON hex_feature(lgd_village_code);

CREATE TABLE IF NOT EXISTS village_risk (
  district TEXT NOT NULL, lgd_village_code TEXT NOT NULL, payload TEXT NOT NULL,
  PRIMARY KEY (district, lgd_village_code));

CREATE TABLE IF NOT EXISTS candidate_site (
  site_id TEXT PRIMARY KEY, district TEXT NOT NULL, lgd_village_code TEXT,
  rank INTEGER, accepted INTEGER, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_site_district ON candidate_site(district, rank);

CREATE TABLE IF NOT EXISTS relocation_priority (
  district TEXT NOT NULL, lgd_village_code TEXT NOT NULL, priority TEXT,
  phase INTEGER, payload TEXT NOT NULL,
  PRIMARY KEY (district, lgd_village_code));

CREATE TABLE IF NOT EXISTS artefact (
  district TEXT NOT NULL, name TEXT NOT NULL, payload TEXT NOT NULL,
  PRIMARY KEY (district, name));

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT DEFAULT CURRENT_TIMESTAMP,
  actor TEXT NOT NULL, action TEXT NOT NULL, subject TEXT, detail TEXT);

CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""


# One definition, in core.jsonio, shared with the pipeline writers — because a
# store that normalises numbers differently from the artefacts it loads will
# eventually disagree with them about what a value is.
_jsonable = json_safe


def _r(v, dp: int):
    """Round for the wire. `None` stays `None`; a NaN becomes `None`."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, dp) if np.isfinite(f) else None


def _common_prefix(ids: list[str]) -> str:
    """Longest shared head of the cell ids.

    Local-backend ids look like `L10:08a3:-41:-67` — resolution, anchor hash,
    then axial coordinates. The first two fields are identical for every cell in
    a district, so sending them 20,000 times costs 180 kB for no information.
    """
    if not ids:
        return ""
    a, b = min(ids), max(ids)
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    return a[:i]


class _Codes:
    """Dictionary encoder: repeated strings become small integers plus a vocab."""

    def __init__(self):
        self.values: list[str] = []
        self._ix: dict[str, int] = {}

    def code(self, v) -> int:
        s = "" if v is None else str(v)
        c = self._ix.get(s)
        if c is None:
            c = self._ix[s] = len(self.values)
            self.values.append(s)
        return c


class SqliteStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DATA / "punarvaas.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self.migrate()

    @property
    def db(self) -> sqlite3.Connection:
        """The calling thread's connection, opened on first use.

        A single connection shared across threads with `check_same_thread=False`
        only silences the guard: two threads stepping through the same connection
        interleave on its statement state and raise
        `sqlite3.InterfaceError: bad parameter or other API misuse`. The console
        issues its district loads in parallel, so this was reachable from one page
        load. WAL lets independent readers proceed concurrently, which makes a
        connection per thread both correct and faster than serialising every query
        behind a lock. Threads come from the server's bounded worker pool, so the
        number of connections is bounded too.
        """
        c: sqlite3.Connection | None = getattr(self._local, "db", None)
        if c is None:
            c = sqlite3.connect(str(self.path))
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            self._local.db = c
        return c

    # ── writes ──────────────────────────────────────────────────────────────
    def migrate(self) -> None:
        self.db.executescript(DDL)
        self.db.commit()

    def audit(self, actor: str, action: str, subject: str = "", detail: dict | None = None):
        self.db.execute("INSERT INTO audit_log(actor, action, subject, detail) "
                        "VALUES (?,?,?,?)",
                        (actor, action, subject, jdumps(detail or {}, default=str)))
        self.db.commit()

    def ingest_district(self, district: str) -> dict:
        from core.config import DISTRICTS
        from core.grid.hexgrid import Grid

        d = DISTRICTS[district]
        src = DATA / "processed" / district
        cells = pd.read_parquet(src / "cells.parquet")
        villages = pd.read_parquet(src / "villages.parquet")
        manifest = json.loads((src / "manifest.json").read_text())
        plan = json.loads((src / "plan.json").read_text()) if (src / "plan.json").exists() else None
        grid = Grid.for_district(district)

        recs = []
        for r in cells.to_dict("records"):
            row = {k: _jsonable(v) for k, v in r.items()}
            recs.append((row["h3_index"], district, row.get("snapshot_id"),
                         jdumps(row, default=str),
                         jdumps(grid.cell_to_geojson_ring(row["h3_index"])),
                         row.get("lat"), row.get("lon"), row.get("zone"),
                         row.get("h_union"), row.get("risk_score"),
                         row.get("population"), row.get("governing_hazard"),
                         row.get("confidence"), row.get("lgd_village_code"),
                         row.get("village_name")))
        cur = self.db.cursor()
        cur.execute("DELETE FROM hex_feature WHERE district = ?", (district,))
        cur.executemany(
            "INSERT OR REPLACE INTO hex_feature(h3_index, district, snapshot_id, payload,"
            " boundary, lat, lon, zone, h_union, risk_score, population,"
            " governing_hazard, confidence, lgd_village_code, village_name)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", recs)

        cur.execute("DELETE FROM village_risk WHERE district = ?", (district,))
        cur.executemany(
            "INSERT INTO village_risk(district, lgd_village_code, payload) VALUES (?,?,?)",
            [(district, str(r["lgd_village_code"]),
              jdumps({k: _jsonable(v) for k, v in r.items()}, default=str))
             for r in villages.to_dict("records")])

        pop = float(cells["population"].sum())
        at_risk = float(villages["pop_at_risk"].sum()) if len(villages) else 0.0
        cur.execute("INSERT OR REPLACE INTO district(district, name, state, terrain,"
                    " snapshot_id, contains_synthetic, cells, population, pop_at_risk,"
                    " eal_annual_inr) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (district, d.name, d.state, d.terrain,
                     str(cells["snapshot_id"].iloc[0]),
                     int(bool(manifest.get("contains_synthetic", True))),
                     len(cells), pop, at_risk,
                     float(cells["eal_annual_inr"].sum())))

        for name, obj in (("manifest", manifest),
                          ("model_landslide", self._maybe(src / "model_landslide.json")),
                          ("gev", self._maybe(src / "gev.json"))):
            if obj is not None:
                cur.execute("INSERT OR REPLACE INTO artefact(district, name, payload)"
                            " VALUES (?,?,?)", (district, name, jdumps(obj, default=str)))

        n_sites = n_plan = 0
        if plan:
            cur.execute("DELETE FROM candidate_site WHERE district = ?", (district,))
            cur.executemany(
                "INSERT INTO candidate_site(site_id, district, lgd_village_code, rank,"
                " accepted, payload) VALUES (?,?,?,?,?,?)",
                [(s["site_id"], district, s.get("lgd_village_code"), s.get("rank"),
                  int(bool(s.get("accepted"))), jdumps(s, default=str))
                 for s in plan["sites"]])
            cur.execute("DELETE FROM relocation_priority WHERE district = ?", (district,))
            cur.executemany(
                "INSERT INTO relocation_priority(district, lgd_village_code, priority,"
                " phase, payload) VALUES (?,?,?,?,?)",
                [(district, r["lgd_village_code"], r["priority"], r["phase"],
                  jdumps(r, default=str)) for r in plan["habitations"]])
            for name in ("ahp", "funnels", "phase_summary", "acceptance"):
                cur.execute("INSERT OR REPLACE INTO artefact(district, name, payload)"
                            " VALUES (?,?,?)",
                            (district, name, jdumps(plan.get(name), default=str)))
            cur.execute("INSERT OR REPLACE INTO artefact(district, name, payload)"
                        " VALUES (?,?,?)",
                        (district, "plan_meta", jdumps(
                            {k: v for k, v in plan.items()
                             if k not in ("sites", "habitations", "funnels")},
                            default=str)))
            n_sites, n_plan = len(plan["sites"]), len(plan["habitations"])
        self.db.commit()
        self.audit("pipeline", "ingest_district", district,
                   {"cells": len(cells), "villages": len(villages),
                    "sites": n_sites, "plan_rows": n_plan})
        return {"district": district, "cells": len(cells), "villages": len(villages),
                "sites": n_sites, "plan_rows": n_plan}

    @staticmethod
    def _maybe(p: Path):
        return json.loads(p.read_text()) if p.exists() else None

    # ── reads ───────────────────────────────────────────────────────────────
    def _rows(self, sql: str, args=()) -> list[dict]:
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def districts(self) -> list[dict]:
        out = self._rows("SELECT * FROM district ORDER BY pop_at_risk DESC")
        for r in out:
            r["contains_synthetic"] = bool(r["contains_synthetic"])
        return out

    def zone_summary(self, district: str) -> list[dict]:
        return self._rows(
            "SELECT zone, COUNT(*) AS cells, SUM(population) AS population,"
            " AVG(h_union) AS h_union_mean, MAX(h_union) AS h_union_max,"
            " AVG(confidence) AS confidence FROM hex_feature"
            " WHERE district = ? GROUP BY zone", (district,))

    def cells(self, district: str, bbox: tuple | None = None, zone: str | None = None,
              limit: int = 40_000) -> list[dict]:
        sql = ("SELECT h3_index, lat, lon, zone, h_union, risk_score, population,"
               " governing_hazard, confidence, village_name, boundary"
               " FROM hex_feature WHERE district = ?")
        args: list = [district]
        if bbox:
            sql += " AND lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?"
            args += [bbox[0], bbox[2], bbox[1], bbox[3]]
        if zone:
            sql += " AND zone = ?"
            args.append(zone)
        sql += " LIMIT ?"
        args.append(int(limit))
        out = self._rows(sql, tuple(args))
        for r in out:
            r["boundary"] = json.loads(r["boundary"]) if r["boundary"] else None
        return out

    # Dictionary-encoded columns for the console map. Order is `rowid`, i.e.
    # ingest order, which is Engine 1's output order — stable across calls, so a
    # client can key its own arrays by index.
    GRID_COLS = ("h3_index", "lat", "lon", "zone", "h_union", "risk_score",
                 "population", "confidence", "governing_hazard", "village_name")

    def grid(self, district: str) -> dict:
        rows = self.db.execute(
            f"SELECT {', '.join(self.GRID_COLS)} FROM hex_feature"
            " WHERE district = ? ORDER BY rowid", (district,)).fetchall()
        ids = [r["h3_index"] for r in rows]
        pfx = _common_prefix(ids)
        zones, hazards, villages = _Codes(), _Codes(), _Codes()
        return {
            "district": district, "n": len(rows), "id_prefix": pfx,
            "id": [i[len(pfx):] for i in ids],
            "lat": [round(float(r["lat"]), 6) for r in rows],
            "lon": [round(float(r["lon"]), 6) for r in rows],
            "zone": [zones.code(r["zone"]) for r in rows],
            "h_union": [_r(r["h_union"], 5) for r in rows],
            "risk_score": [_r(r["risk_score"], 2) for r in rows],
            "population": [_r(r["population"], 2) for r in rows],
            "confidence": [_r(r["confidence"], 3) for r in rows],
            "governing_hazard": [hazards.code(r["governing_hazard"]) for r in rows],
            "village": [villages.code(r["village_name"]) for r in rows],
            "vocab": {"zone": zones.values, "governing_hazard": hazards.values,
                      "village": villages.values},
        }

    def cell(self, h3_index: str) -> dict | None:
        r = self.db.execute("SELECT payload, boundary, district FROM hex_feature"
                            " WHERE h3_index = ?", (h3_index,)).fetchone()
        if not r:
            return None
        out = json.loads(r["payload"])
        out["boundary"] = json.loads(r["boundary"]) if r["boundary"] else None
        out["district"] = r["district"]
        return out

    def villages(self, district: str) -> list[dict]:
        return [json.loads(r["payload"]) for r in
                self.db.execute("SELECT payload FROM village_risk WHERE district = ?",
                                (district,)).fetchall()]

    def plan(self, district: str) -> list[dict]:
        return [json.loads(r["payload"]) for r in
                self.db.execute("SELECT payload FROM relocation_priority"
                                " WHERE district = ? ORDER BY phase, priority",
                                (district,)).fetchall()]

    def sites(self, district: str, village: str | None = None) -> list[dict]:
        sql = "SELECT payload FROM candidate_site WHERE district = ?"
        args: list = [district]
        if village:
            sql += " AND lgd_village_code = ?"
            args.append(village)
        sql += " ORDER BY rank"
        return [json.loads(r["payload"]) for r in self.db.execute(sql, tuple(args))]

    def artefact(self, district: str, name: str):
        r = self.db.execute("SELECT payload FROM artefact WHERE district = ? AND name = ?",
                            (district, name)).fetchone()
        return json.loads(r["payload"]) if r else None

    def audit_tail(self, limit: int = 100) -> list[dict]:
        return self._rows("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))

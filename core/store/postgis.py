"""
PUNARVAAS · PostGIS backend.

The production store. Three things it gives that SQLite cannot:

  · a real spatial index (GiST on geometry) instead of a lat/lon BETWEEN scan,
    which is what makes a viewport query over a full district fast;
  · `REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC` enforced by the server, so
    the audit trail is tamper-evident against the application itself, not just
    against a careless query;
  · concurrent writers, which matters the moment field verification comes back
    from more than one tehsil at a time.

The DDL is not duplicated here. It lives in db/migrations/*.sql — one canonical
schema, applied in order — because a schema that exists twice diverges.

psycopg is imported lazily and the error names the fix, since the whole point of
the SQLite backend is that this dependency is optional.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.config import DATA
from core.jsonio import dumps as jdumps

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"


def _connect(url: str):
    try:
        import psycopg                       # noqa: PLC0415
    except ModuleNotFoundError as e:         # pragma: no cover
        raise SystemExit(
            "PostGIS backend needs psycopg 3:  pip install 'psycopg[binary]'\n"
            "Or drop PUNARVAAS_DB from the environment to use the SQLite backend."
        ) from e
    return psycopg.connect(url, autocommit=True)


class PostgisStore:
    """Mirror of SqliteStore against PostgreSQL + PostGIS."""

    def __init__(self, url: str):
        self.url = url
        self.db = _connect(url)
        self.migrate()

    # ── writes ──────────────────────────────────────────────────────────────
    def migrate(self) -> None:
        with self.db.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS schema_migration ("
                        " filename TEXT PRIMARY KEY,"
                        " applied_at TIMESTAMPTZ DEFAULT now())")
            done = {r[0] for r in cur.execute("SELECT filename FROM schema_migration")}
            for f in sorted(MIGRATIONS.glob("*.sql")):
                if f.name in done:
                    continue
                cur.execute(f.read_text())
                cur.execute("INSERT INTO schema_migration(filename) VALUES (%s)", (f.name,))

    def audit(self, actor: str, action: str, subject: str = "", detail: dict | None = None):
        with self.db.cursor() as cur:
            cur.execute("INSERT INTO audit_log(actor, action, subject, detail)"
                        " VALUES (%s,%s,%s,%s)",
                        (actor, action, subject, jdumps(detail or {}, default=str)))

def ingest_district(self, district: str) -> dict:
    """Load Engine 1 Parquet output into the canonical PostGIS schema."""
    import pandas as pd

    from core.grid.hexgrid import Grid

    src = DATA / "processed" / district
    cells = pd.read_parquet(src / "cells.parquet")
    grid = Grid.for_district(district)

    # Parquet -> canonical DB columns.
    # Fields such as lat/lon are represented spatially by centroid/geom.
    db_columns = [
        "h3_index",
        "snapshot_id",
        "h3_res",
        "h3_res8",
        "h3_res9",
        "lgd_state_code",
        "lgd_district_code",
        "lgd_block_code",
        "lgd_village_code",
        "district",
        "block",
        "village_name",
        "habitation_name",
        "geom",
        "centroid",
        "area_m2",
        "elevation_m",
        "slope_deg",
        "aspect_deg",
        "curvature",
        "twi",
        "hand_m",
        "relief_m",
        "distance_to_stream_m",
        "h_landslide",
        "h_flood",
        "h_erosion",
        "h_cloudburst",
        "h_seismic",
        "h_glof",
        "h_cyclone",
        "h_surge",
        "h_subsidence",
        "insar_velocity_mm_yr",
        "events_per_decade",
        "erosion_rate_m_yr",
        "distance_to_bankline_m",
        "rain_1d_100yr_mm",
        "pga_g",
        "h_union",
        "hazard_count",
        "governing_hazard",
        "compound_bonus",
        "population",
        "households",
        "buildings_count",
        "built_area_m2",
        "children_u6",
        "elderly_60p",
        "pwd_count",
        "sc_st_population",
        "critical_facilities",
        "v_structural",
        "v_social",
        "v_accessibility",
        "v_isolation",
        "v_index",
        "risk_score",
        "risk_ci_low",
        "risk_ci_high",
        "eap_annual",
        "eal_annual_inr",
        "zone",
        "rule_id",
        "ruleset_version",
        "confidence",
        "confidence_notes",
        "contributions",
        "field_verified",
        "verified_at",
        "verified_by",
        "is_synthetic",
    ]

    # Values for fields not present in the Engine 1 Parquet contract.
    if "h3_res" not in cells:
        cells["h3_res"] = 10

    if "lgd_block_code" not in cells:
        cells["lgd_block_code"] = None

    if "block" not in cells:
        cells["block"] = None

    if "habitation_name" not in cells:
        cells["habitation_name"] = None

    if "critical_facilities" not in cells:
        cells["critical_facilities"] = [{} for _ in range(len(cells))]

    if "confidence_notes" not in cells:
        cells["confidence_notes"] = [{} for _ in range(len(cells))]

    if "contributions" not in cells:
        cells["contributions"] = [[] for _ in range(len(cells))]

    if "verified_at" not in cells:
        cells["verified_at"] = None

    if "verified_by" not in cells:
        cells["verified_by"] = None

    if "field_verified" not in cells:
        cells["field_verified"] = False

    # The snapshot table is referenced by hex_features.snapshot_id.
    # Create a minimal snapshot record for this processed dataset if needed.
    snapshot_id = str(cells["snapshot_id"].iloc[0])

    with self.db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO snapshot (
                snapshot_id,
                district_code,
                ruleset_version,
                trigger,
                input_manifest,
                contains_synthetic
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (snapshot_id) DO NOTHING
            """,
            (
                snapshot_id,
                district,
                str(cells["ruleset_version"].iloc[0]),
                "manual",
                "{}",
                bool(cells["is_synthetic"].any()),
            ),
        )

        cur.execute(
            "DELETE FROM hex_features WHERE district = %s",
            (district,),
        )

        # Build INSERT explicitly so Parquet-only columns cannot accidentally
        # break the database contract.
        placeholders = ", ".join(["%s"] * len(db_columns))

        # geom and centroid are generated from the H3 cell geometry.
        insert_columns = [
            c for c in db_columns
            if c not in ("geom", "centroid")
        ]

        insert_sql = f"""
            INSERT INTO hex_features (
                {", ".join(insert_columns)},
                geom,
                centroid
            )
            VALUES (
                {", ".join(["%s"] * len(insert_columns))},
                ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                ST_SetSRID(
                    ST_MakePoint(%s, %s),
                    4326
                )
            )
        """

        for _, row in cells.iterrows():
            values = []

            for col in insert_columns:
                value = row[col]

                # pandas NaN must become SQL NULL.
                if pd.isna(value):
                    value = None

                # JSONB fields need JSON-compatible values.
                if col in (
                    "critical_facilities",
                    "confidence_notes",
                    "contributions",
                ):
                    if value is None:
                        value = {}
                    elif not isinstance(value, (dict, list)):
                        value = {}

                values.append(value)

            h3 = row["h3_index"]

            ring = grid.cell_to_geojson_ring(h3)

            geojson = {
                "type": "Polygon",
                "coordinates": [ring],
            }

            lat = float(row["lat"])
            lon = float(row["lon"])

            cur.execute(
                insert_sql,
                tuple(values)
                + (
                    jdumps(geojson),
                    lon,
                    lat,
                ),
            )

    self.audit(
        "pipeline",
        "ingest_district",
        district,
        {"cells": len(cells)},
    )

    return {
        "district": district,
        "cells": len(cells),
    }

    # ── reads ───────────────────────────────────────────────────────────────
    def _rows(self, sql: str, args=()) -> list[dict]:
        with self.db.cursor() as cur:
            cur.execute(sql, args)
            names = [c.name for c in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]

    def districts(self) -> list[dict]:
        return self._rows(
            "SELECT district, MAX(snapshot_id) AS snapshot_id, COUNT(*) AS cells,"
            " SUM(population) AS population, SUM(eal_annual_inr) AS eal_annual_inr,"
            " bool_or(is_synthetic) AS contains_synthetic"
            " FROM hex_features GROUP BY district")

    def zone_summary(self, district: str) -> list[dict]:
        return self._rows(
            "SELECT zone::text AS zone, COUNT(*) AS cells, SUM(population) AS population,"
            " AVG(h_union) AS h_union_mean, MAX(h_union) AS h_union_max,"
            " AVG(confidence) AS confidence FROM hex_features"
            " WHERE district = %s GROUP BY zone", (district,))

    def cells(self, district: str, bbox: tuple | None = None, zone: str | None = None,
              limit: int = 40_000) -> list[dict]:
        sql = ("SELECT h3_index, lat, lon, zone::text AS zone, h_union, risk_score,"
               " population, governing_hazard, confidence, village_name,"
               " ST_AsGeoJSON(geom) AS boundary FROM hex_features WHERE district = %s")
        args: list = [district]
        if bbox:
            # This is the line the GiST index exists for.
            sql += " AND geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)"
            args += list(bbox)
        if zone:
            sql += " AND zone = %s::zone_class"
            args.append(zone)
        sql += " LIMIT %s"
        args.append(int(limit))
        out = self._rows(sql, tuple(args))
        for r in out:
            g = json.loads(r["boundary"]) if r["boundary"] else None
            r["boundary"] = g["coordinates"][0] if g else None
        return out

    def grid(self, district: str) -> dict:
        """Same columnar shape as SqliteStore.grid — no geometry on the wire.

        Deliberately does not ask PostGIS for the boundary. `ST_AsGeoJSON` on
        20,000 polygons is real server work to send the client something it can
        reconstruct from one prototype ring.
        """
        from core.store.sqlite import _Codes, _common_prefix, _r  # noqa: PLC0415
        rows = self._rows(
            "SELECT h3_index, lat, lon, zone::text AS zone, h_union, risk_score,"
            " population, confidence, governing_hazard, village_name"
            " FROM hex_features WHERE district = %s ORDER BY h3_index", (district,))
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
        rows = self._rows("SELECT *, ST_AsGeoJSON(geom) AS boundary_json"
                          " FROM hex_features WHERE h3_index = %s", (h3_index,))
        if not rows:
            return None
        r = rows[0]
        g = json.loads(r.pop("boundary_json")) if r.get("boundary_json") else None
        r.pop("geom", None)
        r["boundary"] = g["coordinates"][0] if g else None
        return r

    def villages(self, district: str) -> list[dict]:
        return self._rows("SELECT * FROM village_risk WHERE district = %s", (district,))

    def plan(self, district: str) -> list[dict]:
        return self._rows("SELECT * FROM relocation_priority WHERE district = %s"
                          " ORDER BY phase, priority", (district,))

    def sites(self, district: str, village: str | None = None) -> list[dict]:
        if village:
            return self._rows("SELECT * FROM candidate_site WHERE district = %s"
                              " AND lgd_village_code = %s ORDER BY rank",
                              (district, village))
        return self._rows("SELECT * FROM candidate_site WHERE district = %s ORDER BY rank",
                          (district,))

    def artefact(self, district: str, name: str):
        rows = self._rows("SELECT payload FROM artefact WHERE district = %s AND name = %s",
                          (district, name))
        return rows[0]["payload"] if rows else None

    def audit_tail(self, limit: int = 100) -> list[dict]:
        return self._rows("SELECT * FROM audit_log ORDER BY id DESC LIMIT %s", (limit,))

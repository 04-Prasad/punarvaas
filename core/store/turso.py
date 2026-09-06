from __future__ import annotations

import json
import os

import libsql

from core.store.sqlite import _Codes, _common_prefix, _r


class TursoStore:
    GRID_COLS = (
        "h3_index", "lat", "lon", "zone", "h_union", "risk_score",
        "population", "confidence", "governing_hazard", "village_name",
    )

    def __init__(self, url: str | None = None, auth_token: str | None = None):
        self.url = url or os.environ["TURSO_DATABASE_URL"]
        self.auth_token = auth_token or os.environ["TURSO_AUTH_TOKEN"]
        self.db = libsql.connect(
            database=self.url,
            auth_token=self.auth_token,
        )

    def migrate(self) -> None:
        return None

    def audit(self, actor: str, action: str, subject: str = "", detail: dict | None = None):
        self.db.execute(
            "INSERT INTO audit_log(actor, action, subject, detail) VALUES (?,?,?,?)",
            (actor, action, subject, json.dumps(detail or {}, separators=(",", ":"))),
        )

    def ingest_district(self, district: str) -> dict:
        raise RuntimeError("District ingestion is disabled on the Turso production backend.")

    @staticmethod
    def _rows(cursor) -> list[dict]:
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def districts(self) -> list[dict]:
        out = self._rows(
            self.db.execute("SELECT * FROM district ORDER BY pop_at_risk DESC")
        )
        for r in out:
            r["contains_synthetic"] = bool(r["contains_synthetic"])
        return out

    def zone_summary(self, district: str) -> list[dict]:
        return self._rows(
            self.db.execute(
                "SELECT zone, COUNT(*) AS cells, SUM(population) AS population,"
                " AVG(h_union) AS h_union_mean, MAX(h_union) AS h_union_max,"
                " AVG(confidence) AS confidence FROM hex_feature"
                " WHERE district = ? GROUP BY zone",
                (district,),
            )
        )

    def cells(self, district: str, bbox: tuple | None = None,
              zone: str | None = None, limit: int = 40_000) -> list[dict]:
        sql = (
            "SELECT h3_index, lat, lon, zone, h_union, risk_score, population,"
            " governing_hazard, confidence, village_name, boundary"
            " FROM hex_feature WHERE district = ?"
        )
        args: list = [district]

        if bbox:
            sql += " AND lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?"
            args += [bbox[0], bbox[2], bbox[1], bbox[3]]

        if zone:
            sql += " AND zone = ?"
            args.append(zone)

        sql += " LIMIT ?"
        args.append(int(limit))

        out = self._rows(self.db.execute(sql, tuple(args)))
        for r in out:
            r["boundary"] = json.loads(r["boundary"]) if r["boundary"] else None
        return out

    def grid(self, district: str) -> dict:
        result = self.db.execute(
            f"SELECT {', '.join(self.GRID_COLS)} FROM hex_feature"
            " WHERE district = ? ORDER BY rowid",
            (district,),
        )
        rows = self._rows(result)

        ids = [r["h3_index"] for r in rows]
        pfx = _common_prefix(ids)
        zones, hazards, villages = _Codes(), _Codes(), _Codes()

        return {
            "district": district,
            "n": len(rows),
            "id_prefix": pfx,
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
            "vocab": {
                "zone": zones.values,
                "governing_hazard": hazards.values,
                "village": villages.values,
            },
        }

    def cell(self, h3_index: str) -> dict | None:
        result = self.db.execute(
            "SELECT payload, boundary, district FROM hex_feature"
            " WHERE h3_index = ?",
            (h3_index,),
        )
        rows = self._rows(result)
        if not rows:
            return None

        r = rows[0]
        out = json.loads(r["payload"])
        out["boundary"] = json.loads(r["boundary"]) if r["boundary"] else None
        out["district"] = r["district"]
        return out

    def villages(self, district: str) -> list[dict]:
        result = self.db.execute(
            "SELECT payload FROM village_risk WHERE district = ?",
            (district,),
        )
        return [json.loads(r[0]) for r in result.fetchall()]

    def plan(self, district: str) -> list[dict]:
        result = self.db.execute(
            "SELECT payload FROM relocation_priority"
            " WHERE district = ? ORDER BY phase, priority",
            (district,),
        )
        return [json.loads(r[0]) for r in result.fetchall()]

    def sites(self, district: str, village: str | None = None) -> list[dict]:
        sql = "SELECT payload FROM candidate_site WHERE district = ?"
        args: list = [district]

        if village:
            sql += " AND lgd_village_code = ?"
            args.append(village)

        sql += " ORDER BY rank"
        result = self.db.execute(sql, tuple(args))
        return [json.loads(r[0]) for r in result.fetchall()]

    def artefact(self, district: str, name: str):
        result = self.db.execute(
            "SELECT payload FROM artefact WHERE district = ? AND name = ?",
            (district, name),
        )
        row = result.fetchone()
        if row is None:
            return None
        return json.loads(row[0])

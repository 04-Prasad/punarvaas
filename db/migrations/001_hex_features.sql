-- ════════════════════════════════════════════════════════════════════════════
-- PUNARVAAS · 001 · canonical analysis grid
-- Contract frozen in plan.md §8.1. Do not alter column names without a team
-- decision — six work streams read this table.
-- ════════════════════════════════════════════════════════════════════════════
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$ BEGIN
  CREATE TYPE zone_class AS ENUM ('RED','ORANGE','YELLOW','GREEN');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE priority_tier AS ENUM ('IMMEDIATE','SHORT_TERM','MEDIUM_TERM','MITIGATE');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── snapshots: every run is immutable and diffable (PS: "explain what changed")
CREATE TABLE IF NOT EXISTS snapshot (
  snapshot_id      TEXT PRIMARY KEY,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  district_code    TEXT NOT NULL,
  ruleset_version  TEXT NOT NULL,
  code_git_sha     TEXT,
  trigger          TEXT,              -- 'manual' | 'new_sentinel1_pass' | 'field_update'
  input_manifest   JSONB NOT NULL,    -- dataset -> {version, checksum, retrieved_at}
  contains_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
  notes            TEXT
);

-- ── the canonical cell table
CREATE TABLE IF NOT EXISTS hex_features (
  h3_index            TEXT NOT NULL,
  snapshot_id         TEXT NOT NULL REFERENCES snapshot(snapshot_id) ON DELETE CASCADE,
  h3_res              SMALLINT NOT NULL DEFAULT 10,
  h3_res8             TEXT,
  h3_res9             TEXT,

  -- administrative keys (D8: LGD is the primary admin key)
  lgd_state_code      TEXT,
  lgd_district_code   TEXT,
  lgd_block_code      TEXT,
  lgd_village_code    TEXT,
  district            TEXT,
  block               TEXT,
  village_name        TEXT,
  habitation_name     TEXT,
  geom                geometry(Polygon, 4326),
  centroid            geometry(Point, 4326),
  area_m2             REAL,

  -- ── terrain
  elevation_m         REAL,
  slope_deg           REAL,
  aspect_deg          REAL,
  curvature           REAL,
  twi                 REAL,   -- topographic wetness index
  hand_m              REAL,   -- height above nearest drainage
  relief_m            REAL,
  distance_to_stream_m REAL,

  -- ── hazard susceptibilities, all 0..1
  h_landslide         REAL,
  h_flood             REAL,
  h_erosion           REAL,
  h_cloudburst        REAL,
  h_seismic           REAL,
  h_glof              REAL,
  h_cyclone           REAL,
  h_surge             REAL,
  h_subsidence        REAL,

  -- ── hazard evidence
  insar_velocity_mm_yr REAL,          -- negative = subsiding
  events_per_decade    REAL,
  erosion_rate_m_yr    REAL,
  distance_to_bankline_m REAL,
  rain_1d_100yr_mm     REAL,          -- GEV return level
  pga_g                REAL,

  -- ── multi-hazard union
  h_union             REAL,
  hazard_count        SMALLINT,
  governing_hazard    TEXT,
  compound_bonus      REAL,

  -- ── exposure (dasymetric)
  population          REAL,
  households          REAL,
  buildings_count     INTEGER,
  built_area_m2       REAL,
  children_u6         REAL,
  elderly_60p         REAL,
  pwd_count           REAL,
  sc_st_population    REAL,
  critical_facilities JSONB,

  -- ── vulnerability sub-indices, 0..1
  v_structural        REAL,
  v_social            REAL,
  v_accessibility     REAL,
  v_isolation         REAL,
  v_index             REAL,

  -- ── risk
  risk_score          REAL,           -- 0..100, for ranking
  risk_ci_low         REAL,
  risk_ci_high        REAL,
  eap_annual          REAL,           -- expected annual population affected
  eal_annual_inr      REAL,           -- expected annual loss

  -- ── classification + provenance
  zone                zone_class,
  rule_id             TEXT,
  ruleset_version     TEXT,
  confidence          REAL,
  confidence_notes    JSONB,
  contributions       JSONB,          -- [{factor, pct, method}]
  field_verified      BOOLEAN NOT NULL DEFAULT FALSE,
  verified_at         TIMESTAMPTZ,
  verified_by         TEXT,
  is_synthetic        BOOLEAN NOT NULL DEFAULT FALSE,

  PRIMARY KEY (h3_index, snapshot_id)
);

CREATE INDEX IF NOT EXISTS ix_hex_geom      ON hex_features USING GIST (geom);
CREATE INDEX IF NOT EXISTS ix_hex_centroid  ON hex_features USING GIST (centroid);
CREATE INDEX IF NOT EXISTS ix_hex_village   ON hex_features (lgd_village_code, snapshot_id);
CREATE INDEX IF NOT EXISTS ix_hex_zone      ON hex_features (snapshot_id, zone);
CREATE INDEX IF NOT EXISTS ix_hex_risk      ON hex_features (snapshot_id, risk_score DESC);
CREATE INDEX IF NOT EXISTS ix_hex_res8      ON hex_features (h3_res8);

-- ════════════════════════════════════════════════════════════════════════════
-- PUNARVAAS · 002 · Engine 2 (sites), Engine 3 (capacity), Engine 3b (plan)
-- Contracts: plan.md §8.3 / §8.4 / §8.5
-- ════════════════════════════════════════════════════════════════════════════

-- ── Engine 2 output ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS candidate_site (
  site_id                 TEXT NOT NULL,
  snapshot_id             TEXT NOT NULL REFERENCES snapshot(snapshot_id) ON DELETE CASCADE,
  origin_lgd_village_code TEXT NOT NULL,
  geom                    geometry(Polygon, 4326),
  centroid                geometry(Point, 4326),
  h3_cells                TEXT[],
  area_ha                 REAL,
  usable_area_ha          REAL,
  distance_from_origin_km REAL,
  travel_time_min         REAL,
  elevation_m             REAL,
  mean_slope_deg          REAL,
  residual_hazard         REAL,          -- the site is not risk-free; say so
  suitability_score       REAL,          -- TOPSIS closeness 0..1
  rank                    INTEGER,
  criteria_scores         JSONB NOT NULL, -- {water, road, health, education, power,
                                          --  land, livelihood_continuity,
                                          --  social_disruption, expansion}
  weights_used            JSONB NOT NULL, -- AHP weights + CR
  accepted                BOOLEAN NOT NULL,
  reasons_accept          TEXT[],
  reasons_reject          TEXT[],         -- PS demands the "why not"
  land_ownership_class    TEXT,           -- govt_revenue | forest | private | unknown
  exclusions_triggered    TEXT[],
  is_synthetic            BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (site_id, snapshot_id)
);
CREATE INDEX IF NOT EXISTS ix_site_geom   ON candidate_site USING GIST (geom);
CREATE INDEX IF NOT EXISTS ix_site_origin ON candidate_site (snapshot_id, origin_lgd_village_code, rank);

-- ── Engine 3 output ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS capacity_result (
  site_id                 TEXT NOT NULL,
  snapshot_id             TEXT NOT NULL REFERENCES snapshot(snapshot_id) ON DELETE CASCADE,
  max_population          REAL,
  max_households          REAL,
  per_resource            JSONB NOT NULL, -- resource -> {capacity, norm, source, headroom}
  binding_constraint      TEXT NOT NULL,  -- Liebig's law: the single limiting resource
  gaps                    JSONB NOT NULL, -- [{resource, deficit, unit, unit_cost_inr,
                                          --   total_cost_inr, scheme, scheme_component}]
  capacity_after_gap_closure REAL,
  next_binding_constraint TEXT,
  total_gap_cost_inr      REAL,
  expansion_headroom_20yr REAL,
  PRIMARY KEY (site_id, snapshot_id)
);

-- ── Engine 3b output: the PS's exact 4-tier table ───────────────────────────
CREATE TABLE IF NOT EXISTS relocation_priority (
  snapshot_id             TEXT NOT NULL REFERENCES snapshot(snapshot_id) ON DELETE CASCADE,
  lgd_village_code        TEXT NOT NULL,
  habitation_name         TEXT,
  district                TEXT,
  risk_score              REAL,
  population              REAL,
  households              REAL,
  population_at_risk      REAL,          -- the "420 of 600" number
  households_at_risk      REAL,
  safe_site_available     TEXT,          -- yes | partial | no
  best_site_id            TEXT,
  site_capacity_persons   REAL,
  priority                priority_tier NOT NULL,
  recommended_action      TEXT NOT NULL,
  households_phase1       REAL,
  cost_relocate_inr       REAL,
  cost_mitigate_inr       REAL,
  eal_avoided_inr         REAL,
  bcr_relocate            REAL,
  bcr_mitigate            REAL,
  phase                   SMALLINT,      -- from the ILP/DP optimiser
  rationale               TEXT,
  PRIMARY KEY (snapshot_id, lgd_village_code)
);
CREATE INDEX IF NOT EXISTS ix_priority_rank ON relocation_priority (snapshot_id, risk_score DESC);

-- ── append-only, hash-chained audit log (governance requirement) ────────────
CREATE TABLE IF NOT EXISTS audit_log (
  seq        BIGSERIAL PRIMARY KEY,
  at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor      TEXT NOT NULL,
  role       TEXT NOT NULL,
  action     TEXT NOT NULL,
  target     TEXT,
  payload    JSONB,
  prev_hash  TEXT NOT NULL,
  hash       TEXT NOT NULL
);
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;

"""
PUNARVAAS · the store interface.

Deliberately small. Every method here answers a question some part of the product
actually asks; nothing is here speculatively. If a screen needs a new query, it
gets a named method with a docstring saying which screen, rather than the API
assembling SQL — otherwise the SQL ends up in six places and the audit trail
stops being complete.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Store(Protocol):
    # ── writes ──────────────────────────────────────────────────────────────
    def migrate(self) -> None:
        """Create tables and indexes. Idempotent."""

    def ingest_district(self, district: str) -> dict:
        """Load Engine 1 + Engine 2 artefacts for one district from Parquet/JSON."""

    def audit(self, actor: str, action: str, subject: str, detail: dict) -> None:
        """Append-only. Never updated, never deleted."""

    # ── reads ───────────────────────────────────────────────────────────────
    def districts(self) -> list[dict]:
        """Landing screen: one card per district with its headline numbers."""

    def zone_summary(self, district: str) -> list[dict]:
        """Risk screen: cells, area share, population and EAL per zone class."""

    def cells(self, district: str, bbox: tuple | None = None, zone: str | None = None,
              limit: int = 40_000) -> list[dict]:
        """Map layer. Slim columns only — the map does not need 70 fields."""

    def grid(self, district: str) -> dict:
        """Whole district, columnar, for the console's map.

        `cells()` returns one dict per cell with a GeoJSON ring, which is the
        right shape for a viewport query and the wrong shape for painting a whole
        district: 20,000 objects carrying 20,000 copies of the same 7-vertex
        polygon is 11 MB of JSON, and the browser spends longer parsing it than
        drawing it. This returns parallel arrays with the repeated strings
        dictionary-encoded, and no geometry at all — the console reconstructs
        every hexagon from one prototype ring, because on a single district's
        equal-area projection the cells are congruent.
        """

    def cell(self, h3_index: str) -> dict | None:
        """Every column for one cell, for the provenance card."""

    def villages(self, district: str) -> list[dict]:
        """The PS's sentence, per habitation."""

    def plan(self, district: str) -> list[dict]:
        """Relocation priority table with tier, BCR and phase."""

    def sites(self, district: str, village: str | None = None) -> list[dict]:
        """Candidate sites, ranked, with capacity and binding constraint."""

    def artefact(self, district: str, name: str) -> Any:
        """Raw JSON artefact: manifest, ahp, funnels, model card, gev."""

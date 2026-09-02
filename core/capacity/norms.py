"""
PUNARVAAS · Engine 3 — the norm ledger.

Carrying capacity is only meaningful against a stated standard. Every capacity
number this engine produces is `available ÷ norm`, and both the norm and its
citation travel with the answer, because "the site can hold 240 people" is
unfalsifiable while "the site can hold 240 people at 55 lpcd per Jal Jeevan
Mission, and 390 at 40 lpcd" is a decision a Collector can take.

Resources are deliberately heterogeneous — a volume, a distance, an area, a
count — which is exactly why the binding constraint has to be found rather than
averaged.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from core.config import NORMS, District, Norm


def _num(x) -> float | None:
    """JSON-safe number.

    `math.inf` is what "this resource does not limit the site" means internally,
    and `json.dumps` will happily write it as the bare token `Infinity` — which
    Python reads back and every other JSON parser on earth rejects, RFC 8259
    having no such literal. So an unbounded capacity crosses the serialisation
    boundary as `null` plus the `limiting: false` flag, and the reader is told
    which it is instead of inferring it from a magic number.
    """
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return round(f, 2) if math.isfinite(f) else None


@dataclass
class ResourceCapacity:
    resource: str
    label: str
    capacity_persons: float
    available: float
    unit: str
    norm_value: float
    norm_unit: str
    source: str
    headroom_persons: float = 0.0
    note: str = ""
    augmentable: bool = True

    @property
    def limiting(self) -> bool:
        """False when this resource imposes no ceiling at all."""
        return math.isfinite(float(self.capacity_persons))

    def as_dict(self) -> dict:
        return {"resource": self.resource, "label": self.label,
                "capacity_persons": _num(self.capacity_persons),
                "limiting": self.limiting,
                "available": _num(self.available), "unit": self.unit,
                "norm": f"{self.norm_value:g} {self.norm_unit}",
                "source": self.source,
                "headroom_persons": _num(self.headroom_persons),
                "augmentable": self.augmentable,
                "note": self.note}


def household_norm(d: District) -> Norm:
    """The household-size norm that applies to this district, source included.

    Returned as the whole Norm rather than a bare float because every consumer
    that reports the number also has to report where it came from, and a second
    copy of this key expression elsewhere would eventually disagree with this one.
    """
    key = "household_size_hill" if d.terrain == "hill" else "household_size_coastal"
    return NORMS[key]


def household_size(d: District) -> float:
    return float(household_norm(d).value)


def phc_norm(d: District) -> float:
    key = "phc_population_hill" if d.terrain == "hill" else "phc_population_plain"
    return float(NORMS[key].value)


# Unit costs for closing a gap. Sources are scheme SoRs and published unit
# costs; they are the numbers a district engineer will argue with, so they are
# in one visible table with the scheme that pays for each one.
UNIT_COST_INR = {
    "water_source_lpm":      45_000.0,    # per litre/min of augmented yield
    "water_storage_kl":      38_000.0,    # RCC OHT per kilolitre
    "pipeline_km":         1_150_000.0,
    "road_km":             6_500_000.0,   # PMGSY hill/plain average
    "classroom":           1_400_000.0,
    "subcentre":           8_500_000.0,
    "phc":                85_000_000.0,
    "power_kva":              18_000.0,
    "site_development_ha": 2_800_000.0,   # levelling, drainage, internal roads
    "dwelling":            1_200_000.0,
}

SCHEME_FOR_GAP = {
    "water":      ("Jal Jeevan Mission", "Retrofitting / new source augmentation"),
    "road":       ("PMGSY-IV", "New connectivity / upgradation"),
    "education":  ("Samagra Shiksha", "Additional classrooms"),
    "health":     ("National Health Mission", "New sub-centre / PHC upgradation"),
    "power":      ("RDSS", "Distribution transformer + LT line"),
    "land":       ("State rehabilitation package", "Site development"),
    "housing":    ("PMAY-G", "Unit assistance"),
    "sanitation": ("SBM-G Phase II", "Greywater management"),
}

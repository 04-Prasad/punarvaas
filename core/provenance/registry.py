"""
PUNARVAAS · provenance registry.

Every number on every screen must be traceable to a dataset with a name, a
vintage, a resolution and a source. The PS asks "which datasets, at what
resolution, from when?" — this class is the answer, and it is machine-readable
so the provenance card and the PDF are generated from it rather than hand-typed.

It also carries the honesty flag: if any input is synthetic, `contains_synthetic`
becomes True and every consumer is obliged to say so.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class DatasetRecord:
    name: str
    role: str                       # what it is used for
    vintage: str                    # "2011", "2024-07", "1990–2024"
    resolution: str                 # "30 m", "0.25°", "1:50,000", "village"
    source: str                     # portal / API / citation
    is_synthetic: bool = False
    licence: str = ""
    retrieved_at: str = ""
    checksum: str = ""
    notes: str = ""


@dataclass
class Manifest:
    district: str
    ruleset_version: str
    grid_backend: str
    grid_res: int
    datasets: list[DatasetRecord] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    code_git_sha: str = ""
    trigger: str = "manual"
    params: dict = field(default_factory=dict)

    def add(self, **kw) -> "Manifest":
        self.datasets.append(DatasetRecord(**kw))
        return self

    @property
    def contains_synthetic(self) -> bool:
        return any(d.is_synthetic for d in self.datasets)

    @property
    def synthetic_datasets(self) -> list[str]:
        return [d.name for d in self.datasets if d.is_synthetic]

    def snapshot_id(self) -> str:
        """Deterministic id from the inputs — same inputs, same id, so two runs
        are comparable and a diff means something really changed."""
        payload = json.dumps([asdict(d) for d in self.datasets], sort_keys=True) \
            + self.district + self.ruleset_version + json.dumps(self.params, sort_keys=True)
        h = hashlib.sha256(payload.encode()).hexdigest()[:12]
        return f"{self.district}-{datetime.now(timezone.utc):%Y%m%d}-{h}"

    def as_dict(self) -> dict:
        return {"district": self.district, "ruleset_version": self.ruleset_version,
                "grid": {"backend": self.grid_backend, "resolution": self.grid_res},
                "created_at": self.created_at, "trigger": self.trigger,
                "code_git_sha": self.code_git_sha, "params": self.params,
                "contains_synthetic": self.contains_synthetic,
                "synthetic_datasets": self.synthetic_datasets,
                "datasets": [asdict(d) for d in self.datasets]}

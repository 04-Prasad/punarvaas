"""
PUNARVAAS · the zoning rule engine.

Deliberately **zero machine learning**. A threshold that decides whether a
family must leave its home is not a statistical artefact — it is policy, and it
belongs to a named authority who signs it. So zoning lives in versioned YAML
that an SDMA can read, amend, and approve, and every classified cell records
which rule fired, with what inputs, and by what margin.

This is what lets us answer the judge question "who approved this threshold?"
with a file path and a version number instead of a shrug.

Security note: conditions are parsed with a restricted grammar
(`field op value`), never `eval()`. A ruleset file is configuration, and
configuration must not be able to execute code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

SEVERITY = {"GREEN": 0, "YELLOW": 1, "ORANGE": 2, "RED": 3}
_COND = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|==|!=|>|<)\s*(-?[\w.]+)\s*$")
_OPS = {">=": np.greater_equal, "<=": np.less_equal, ">": np.greater,
        "<": np.less, "==": np.equal, "!=": np.not_equal}


@dataclass
class Condition:
    raw: str
    field_name: str
    op: str
    value: float | str

    @classmethod
    def parse(cls, raw: str) -> "Condition":
        m = _COND.match(raw)
        if not m:
            raise ValueError(f"unparseable condition {raw!r} — grammar is 'field op value'")
        f, op, v = m.groups()
        try:
            val: float | str = float(v)
        except ValueError:
            val = v
        return cls(raw.strip(), f, op, val)

    def evaluate(self, df) -> np.ndarray:
        if self.field_name not in df.columns:
            raise KeyError(f"rule references unknown field {self.field_name!r}")
        col = df[self.field_name]
        if isinstance(self.value, str):
            return (_OPS[self.op](col.to_numpy(dtype=object), self.value)).astype(bool)
        return _OPS[self.op](col.to_numpy(float), self.value)

    def margin(self, actual: float) -> float:
        """Signed distance from the threshold. Negative = failed, and by how much.
        Shown in the provenance card so 'it just barely qualified' is visible."""
        if isinstance(self.value, str):
            return 0.0
        if self.op in (">=", ">"):
            return float(actual - self.value)
        if self.op in ("<=", "<"):
            return float(self.value - actual)
        return 0.0


@dataclass
class Rule:
    id: str
    label: str
    zone: str
    match: str = "all"                       # "all" | "any"
    conditions: list[Condition] = field(default_factory=list)
    action: str = ""
    rationale: str = ""

    @property
    def severity(self) -> int:
        return SEVERITY[self.zone]

    def evaluate(self, df) -> np.ndarray:
        if not self.conditions:
            return np.ones(len(df), bool)
        stack = [c.evaluate(df) for c in self.conditions]
        return np.logical_and.reduce(stack) if self.match == "all" \
            else np.logical_or.reduce(stack)


@dataclass
class RuleSet:
    version: str
    name: str
    applies_to: list[str]
    owner: str
    approved_by: str
    approved_at: str
    precedence: str
    rules: list[Rule]
    default_zone: str = "GREEN"
    notes: str = ""
    path: str = ""

    def approval(self) -> dict:
        # The ruleset path is reported relative to the repository root, never as
        # an absolute path: this dict is served over HTTP, and an absolute path
        # tells a caller the deployment's directory layout for no benefit.
        try:
            rel = str(Path(self.path).resolve()
                      .relative_to(Path(__file__).resolve().parents[2]))
        except (ValueError, OSError):
            rel = Path(self.path).name
        return {"ruleset_version": self.version, "owner": self.owner,
                "approved_by": self.approved_by, "approved_at": self.approved_at,
                "file": rel}


def load_ruleset(path: str | Path) -> RuleSet:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    rules = []
    for r in raw["rules"]:
        rules.append(Rule(id=r["id"], label=r["label"], zone=r["zone"],
                          match=r.get("match", "all"),
                          conditions=[Condition.parse(c) for c in r.get("conditions", [])],
                          action=r.get("action", ""), rationale=r.get("rationale", "")))
    ids = [r.id for r in rules]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate rule ids in ruleset")
    return RuleSet(version=raw["version"], name=raw["name"],
                   applies_to=raw.get("applies_to", []), owner=raw["owner"],
                   approved_by=raw.get("approved_by", raw["owner"]),
                   approved_at=raw.get("approved_at", ""),
                   precedence=raw.get("precedence", "highest_severity_wins"),
                   rules=rules, default_zone=raw.get("default_zone", "GREEN"),
                   notes=raw.get("notes", ""), path=str(path))


def classify(df, rs: RuleSet):
    """Vectorised classification.

    Returns (zone[], rule_id[], fired_mask{rule_id: bool[]}).
    Precedence `highest_severity_wins` means a cell that satisfies both a YELLOW
    and a RED rule is RED — the conservative direction, and the only defensible
    one when the consequence of under-calling is a death.
    """
    n = len(df)
    zone = np.array([rs.default_zone] * n, dtype=object)
    rule_id = np.array(["R-DEFAULT"] * n, dtype=object)
    sev = np.full(n, -1)
    fired: dict[str, np.ndarray] = {}

    order = sorted(rs.rules, key=lambda r: r.severity)          # low → high
    if rs.precedence == "first_match_wins":
        order = rs.rules

    for r in order:
        m = r.evaluate(df)
        fired[r.id] = m
        if rs.precedence == "first_match_wins":
            take = m & (sev < 0)
        else:
            take = m & (r.severity > sev)
        if take.any():
            zone[take] = r.zone
            rule_id[take] = r.id
            sev[take] = r.severity
    return zone, rule_id, fired


def explain_rule(df_row, rs: RuleSet, rule_id: str) -> dict:
    """Per-cell rule trace with actual values and margins — the provenance card's
    'rule' block (plan.md §8.2)."""
    r = next((x for x in rs.rules if x.id == rule_id), None)
    if r is None:
        return {"id": rule_id, "label": "no rule fired — default classification",
                "ruleset": rs.version, "conditions": []}
    conds = []
    for c in r.conditions:
        actual = df_row[c.field_name]
        a = float(actual) if not isinstance(c.value, str) else actual
        ok = bool(_OPS[c.op](np.array([a], dtype=object if isinstance(c.value, str) else float),
                            c.value)[0])
        conds.append({"expr": c.raw,
                      "actual": round(a, 4) if isinstance(a, float) else a,
                      "threshold": c.value,
                      "margin": round(c.margin(a), 4) if isinstance(c.value, float) else None,
                      "pass": ok})
    return {"id": r.id, "label": r.label, "zone": r.zone, "match": r.match,
            "ruleset": rs.version, "conditions": conds,
            "action": r.action, "rationale": r.rationale}

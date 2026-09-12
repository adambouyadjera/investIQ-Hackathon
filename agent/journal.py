"""The audit trail.

Every proposal, every veto and every fill lands here with the evidence that
produced it. This is what makes the desk explainable after the fact rather than
only at the moment of decision: a run's journal can reconstruct, for any trade,
the five contributions that summed to its score, the headlines behind the news
line, and every risk check the proposal passed on the way through.

Vetoes are kept, not discarded. A strategy's rejected proposals say as much
about it as its fills -- if the gate refused four fifths of what the desk
wanted to do, the equity curve belongs to the gate, not to the strategy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd


@dataclass
class JournalEntry:
    date: pd.Timestamp
    symbol: str
    stage: str        # "proposal" | "risk_gate" | "execution"
    outcome: str      # "proposed" | "vetoed" | "cancelled" | "filled"
    code: str
    detail: str
    proposal: object = None                     # decide.Proposal
    quantity: int = 0
    planned_loss: float = 0.0
    checks: Sequence[Tuple[str, bool, str]] = ()

    def to_dict(self, include_evidence: bool = True) -> dict:
        d = {
            "date": pd.Timestamp(self.date).strftime("%Y-%m-%d"),
            "symbol": self.symbol,
            "stage": self.stage,
            "outcome": self.outcome,
            "code": self.code,
            "detail": self.detail,
        }
        if self.quantity:
            d["quantity"] = self.quantity
            d["planned_loss"] = round(self.planned_loss, 2)
        if self.checks:
            d["checks"] = [
                {"name": n, "passed": p, "code": c} for n, p, c in self.checks
            ]
        if include_evidence and self.proposal is not None:
            p = self.proposal
            d["score"] = round(p.score, 4)
            d["regime"] = p.regime
            d["action"] = p.action
            d["rationale"] = p.rationale()
            d["evidence"] = [e.to_dict() for e in p.evidence]
            if p.news is not None:
                d["news"] = p.news.to_dict()
        return d


class Journal:
    def __init__(self) -> None:
        self.entries: List[JournalEntry] = []

    def record(self, entry: JournalEntry) -> None:
        self.entries.append(entry)

    def __len__(self) -> int:
        return len(self.entries)

    def by_outcome(self, outcome: str) -> List[JournalEntry]:
        return [e for e in self.entries if e.outcome == outcome]

    def for_symbol(self, symbol: str) -> List[JournalEntry]:
        return [e for e in self.entries if e.symbol == symbol]

    def summary(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self.entries:
            out[e.outcome] = out.get(e.outcome, 0) + 1
        return out

    def recent(self, n: int = 50, outcome: Optional[str] = None) -> List[dict]:
        pool = self.by_outcome(outcome) if outcome else self.entries
        return [e.to_dict() for e in pool[-n:]][::-1]

    def to_records(self, include_evidence: bool = True) -> List[dict]:
        return [e.to_dict(include_evidence) for e in self.entries]

    def write_jsonl(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for rec in self.to_records():
                fh.write(json.dumps(rec) + "\n")
        return path

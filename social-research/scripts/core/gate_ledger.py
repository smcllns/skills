"""Append-only gate ledger (JSONL) for social-research release gates.

Each gate writes one receipt line:

    {"gate": str, "status": "pass"|"fail"|"skip", "evidence_path": str, "reason": str}

Release contract: a missing receipt is treated as failure. A gate that never ran
is indistinguishable from one that ran and was skipped, so the validator blocks
release on either — that is the whole point of the ledger.

Producer CLI (for preflight / the agent to emit a receipt):
    python3 core/gate_ledger.py <ledger.jsonl> <gate> <pass|fail|skip> [--evidence P] [--reason R]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

VALID_STATUSES = ("pass", "fail", "skip")


def append_receipt(
    ledger_path: str | Path,
    gate: str,
    status: str,
    *,
    evidence_path: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Append one gate receipt to the ledger. Fails loud on an invalid status."""
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid gate status {status!r}; expected one of {VALID_STATUSES}")
    if not gate:
        raise ValueError("gate name is required")
    receipt = {"gate": gate, "status": status, "evidence_path": evidence_path, "reason": reason}
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(receipt, sort_keys=True) + "\n")
    return receipt


def read_receipts(ledger_path: str | Path) -> list[dict[str, Any]]:
    """Read all receipts in append order. Fails loud on a corrupt line."""
    path = Path(ledger_path)
    if not path.exists():
        return []
    receipts: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        receipts.append(json.loads(line))
    return receipts


def latest_by_gate(ledger_path: str | Path) -> dict[str, dict[str, Any]]:
    """Last receipt per gate — a gate re-run (append) supersedes its earlier line."""
    latest: dict[str, dict[str, Any]] = {}
    for receipt in read_receipts(ledger_path):
        latest[receipt["gate"]] = receipt
    return latest


def require_gates(ledger_path: str | Path, required_gates: list[str]) -> list[tuple[str, str]]:
    """Return (gate, problem) for every required gate missing or not 'pass'.

    Empty list = release allowed; non-empty = caller blocks release.
    """
    latest = latest_by_gate(ledger_path)
    problems: list[tuple[str, str]] = []
    for gate in required_gates:
        receipt = latest.get(gate)
        if receipt is None:
            problems.append((gate, "missing receipt (gate did not run)"))
        elif receipt["status"] != "pass":
            problems.append((gate, f"status={receipt['status']}: {receipt.get('reason', '')}".rstrip(": ")))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append a gate receipt to a social-research gate ledger.")
    parser.add_argument("ledger", type=Path)
    parser.add_argument("gate")
    parser.add_argument("status", choices=VALID_STATUSES)
    parser.add_argument("--evidence", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args(argv)
    receipt = append_receipt(args.ledger, args.gate, args.status, evidence_path=args.evidence, reason=args.reason)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

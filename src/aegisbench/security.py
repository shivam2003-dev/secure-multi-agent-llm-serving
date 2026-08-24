"""Statistical helpers for cache timing-isolation probes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def audit_timing_samples(path: str | Path) -> dict[str, Any]:
    cold: list[float] = []
    probe: list[float] = []
    cross_tenant_hits = 0
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
                group = sample["group"]
                latency = float(sample["ttft_ms"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid timing sample on line {line_number}") from exc
            if group == "cold":
                cold.append(latency)
            elif group == "cross_tenant_probe":
                probe.append(latency)
            else:
                raise ValueError(f"unknown group on line {line_number}: {group}")
            cross_tenant_hits += int(sample.get("cross_tenant_cache_hit", 0) or 0)

    return {
        "cold_samples": len(cold),
        "probe_samples": len(probe),
        "median_cold_ttft_ms": _median(cold),
        "median_probe_ttft_ms": _median(probe),
        "timing_attack_auc": _latency_auc(cold, probe),
        "cross_tenant_cache_hits": cross_tenant_hits,
        "pass": bool(
            cold and probe and cross_tenant_hits == 0 and _latency_auc(cold, probe) <= 0.60
        ),
    }


def _latency_auc(cold: list[float], probe: list[float]) -> float | None:
    """Return attacker AUC when a faster probe predicts a cache hit."""
    if not cold or not probe:
        return None
    wins = 0.0
    for probe_value in probe:
        for cold_value in cold:
            if probe_value < cold_value:
                wins += 1
            elif probe_value == cold_value:
                wins += 0.5
    auc = wins / (len(cold) * len(probe))
    return max(auc, 1.0 - auc)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2

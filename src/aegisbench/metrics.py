"""Metric definitions and aggregation for AegisBench result logs."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[rank]


def summarize(path: str | Path) -> dict[str, Any]:
    events = _read_events(path)
    successes = [event for event in events if event.get("success")]
    ttft = [_delta_ms(event, "start_s", "first_token_s") for event in successes]
    e2e = [_delta_ms(event, "start_s", "end_s") for event in successes]
    tpot = []
    for event in successes:
        tokens = int(event.get("output_tokens", 0) or 0)
        if tokens > 1 and event.get("first_token_s") is not None:
            tpot.append(
                (float(event["end_s"]) - float(event["first_token_s"])) * 1000 / (tokens - 1)
            )

    window_s = _window(successes)
    output_tokens = sum(int(event.get("output_tokens", 0) or 0) for event in successes)
    prompt_tokens = sum(int(event.get("prompt_tokens", 0) or 0) for event in successes)
    cached_tokens = sum(int(event.get("cache_hit_tokens", 0) or 0) for event in successes)
    proposed = sum(int(event.get("speculative_proposed", 0) or 0) for event in successes)
    accepted = sum(int(event.get("speculative_accepted", 0) or 0) for event in successes)

    workflows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tenants: dict[str, int] = defaultdict(int)
    for event in events:
        workflows[str(event.get("workflow_id"))].append(event)
        if event.get("success"):
            tenants[str(event.get("tenant_id"))] += 1
    workflow_latencies = []
    completed_workflows = 0
    for workflow_events in workflows.values():
        if workflow_events and all(event.get("success") for event in workflow_events):
            completed_workflows += 1
            start = min(float(event["arrival_s"]) for event in workflow_events)
            end = max(float(event["end_s"]) for event in workflow_events)
            workflow_latencies.append((end - start) * 1000)

    recovery = [
        float(event["fault_recovery_ms"])
        for event in events
        if event.get("fault_recovery_ms") is not None
    ]
    cross_tenant_hits = sum(int(event.get("cross_tenant_cache_hits", 0) or 0) for event in events)
    security_violations = sum(int(event.get("security_violations", 0) or 0) for event in events)

    return {
        "requests": {
            "total": len(events),
            "successful": len(successes),
            "success_rate": _ratio(len(successes), len(events)),
            "throughput_requests_s": _ratio(len(successes), window_s),
            "throughput_output_tokens_s": _ratio(output_tokens, window_s),
        },
        "latency_ms": {
            "ttft_p50": percentile(ttft, 0.50),
            "ttft_p95": percentile(ttft, 0.95),
            "ttft_p99": percentile(ttft, 0.99),
            "tpot_p50": percentile(tpot, 0.50),
            "tpot_p95": percentile(tpot, 0.95),
            "request_e2e_p95": percentile(e2e, 0.95),
            "workflow_e2e_p50": percentile(workflow_latencies, 0.50),
            "workflow_e2e_p95": percentile(workflow_latencies, 0.95),
            "workflow_e2e_p99": percentile(workflow_latencies, 0.99),
        },
        "workflows": {
            "total": len(workflows),
            "completed": completed_workflows,
            "completion_rate": _ratio(completed_workflows, len(workflows)),
        },
        "efficiency": {
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "kv_cache_hit_ratio": _ratio(cached_tokens, prompt_tokens),
            "speculative_acceptance_ratio": _ratio(accepted, proposed),
        },
        "resilience": {
            "recovery_events": len(recovery),
            "recovery_time_p95_ms": percentile(recovery, 0.95),
        },
        "isolation": {
            "cross_tenant_cache_hits": cross_tenant_hits,
            "security_violations": security_violations,
            "jain_fairness_index": _jain_index(list(tenants.values())),
        },
    }


def _read_events(path: str | Path) -> list[dict[str, Any]]:
    events = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number} of {path}") from exc
    return events


def _delta_ms(event: dict[str, Any], start: str, end: str) -> float:
    return (float(event[end]) - float(event[start])) * 1000


def _window(events: list[dict[str, Any]]) -> float:
    if not events:
        return 0.0
    return max(float(event["end_s"]) for event in events) - min(
        float(event["start_s"]) for event in events
    )


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _jain_index(values: list[int]) -> float | None:
    if not values:
        return None
    total = sum(values)
    squared = sum(value * value for value in values)
    return (total * total) / (len(values) * squared) if squared else None

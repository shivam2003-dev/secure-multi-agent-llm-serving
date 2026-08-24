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
    ttft = [
        _delta_ms(event, "start_s", "first_token_s")
        for event in successes
        if event.get("first_token_s") is not None
    ]
    e2e = [_delta_ms(event, "start_s", "end_s") for event in successes]
    admission_wait = [
        float(event["admission_wait_ms"])
        for event in events
        if event.get("admission_wait_ms") is not None
    ]
    tpot = []
    for event in successes:
        tokens = int(event.get("output_tokens") or 0)
        if tokens > 1 and event.get("first_token_s") is not None:
            tpot.append(
                (float(event["end_s"]) - float(event["first_token_s"])) * 1000 / (tokens - 1)
            )

    window_s = _window(events)
    observed_usage = [
        event
        for event in successes
        if event.get("prompt_tokens") is not None and event.get("output_tokens") is not None
    ]
    usage_complete = bool(successes) and len(observed_usage) == len(successes)
    observed_output_tokens = sum(int(event["output_tokens"]) for event in observed_usage)
    observed_prompt_tokens = sum(int(event["prompt_tokens"]) for event in observed_usage)
    cache_observations = [
        event
        for event in successes
        if event.get("cache_hit_tokens") is not None and event.get("prompt_tokens") is not None
    ]
    cached_tokens = sum(int(event["cache_hit_tokens"]) for event in cache_observations)
    cache_prompt_tokens = sum(int(event["prompt_tokens"]) for event in cache_observations)
    speculation_observations = [
        event
        for event in successes
        if event.get("speculative_proposed") is not None
        and event.get("speculative_accepted") is not None
    ]
    proposed = sum(int(event["speculative_proposed"]) for event in speculation_observations)
    accepted = sum(int(event["speculative_accepted"]) for event in speculation_observations)

    workflows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tenant_workflows: dict[str, set[str]] = defaultdict(set)
    tenant_output_tokens: dict[str, int] = defaultdict(int)
    for event in events:
        workflows[str(event.get("workflow_id"))].append(event)
        tenant = str(event.get("tenant_id"))
        tenant_workflows.setdefault(tenant, set())
        tenant_output_tokens.setdefault(tenant, 0)
        if event.get("success") and event.get("output_tokens") is not None:
            tenant_output_tokens[tenant] += int(event["output_tokens"])
    workflow_latencies = []
    completed_workflows = 0
    slo_evaluable = 0
    slo_satisfied = 0
    for workflow_id, workflow_events in workflows.items():
        complete = bool(workflow_events) and all(event.get("success") for event in workflow_events)
        if complete:
            completed_workflows += 1
            start = min(float(event["arrival_s"]) for event in workflow_events)
            end = max(float(event["end_s"]) for event in workflow_events)
            workflow_latencies.append((end - start) * 1000)
            tenant_workflows[str(workflow_events[0].get("tenant_id"))].add(workflow_id)
        evaluated, satisfied = _workflow_slo(workflow_events)
        slo_evaluable += int(evaluated)
        slo_satisfied += int(satisfied)

    recovery = [
        float(event["fault_recovery_ms"])
        for event in events
        if event.get("fault_recovery_ms") is not None
    ]
    cross_tenant_observations = [
        int(event["cross_tenant_cache_hits"])
        for event in events
        if event.get("cross_tenant_cache_hits") is not None
    ]
    security_observations = [
        int(event["security_violations"])
        for event in events
        if event.get("security_violations") is not None
    ]
    workflow_fairness = _jain_index(
        [len(tenant_workflows[tenant]) for tenant in sorted(tenant_workflows)]
    )
    token_fairness = _jain_index(
        [tenant_output_tokens[tenant] for tenant in sorted(tenant_output_tokens)]
    )

    return {
        "requests": {
            "total": len(events),
            "successful": len(successes),
            "success_rate": _ratio(len(successes), len(events)),
            "throughput_requests_s": _ratio(len(successes), window_s),
            "throughput_output_tokens_s": (
                _ratio(observed_output_tokens, window_s) if usage_complete else None
            ),
        },
        "latency_ms": {
            "ttft_p50": percentile(ttft, 0.50),
            "ttft_p95": percentile(ttft, 0.95),
            "ttft_p99": percentile(ttft, 0.99),
            "tpot_p50": percentile(tpot, 0.50),
            "tpot_p95": percentile(tpot, 0.95),
            "request_e2e_p95": percentile(e2e, 0.95),
            "admission_wait_p50": percentile(admission_wait, 0.50),
            "admission_wait_p95": percentile(admission_wait, 0.95),
            "workflow_e2e_p50": percentile(workflow_latencies, 0.50),
            "workflow_e2e_p95": percentile(workflow_latencies, 0.95),
            "workflow_e2e_p99": percentile(workflow_latencies, 0.99),
        },
        "workflows": {
            "total": len(workflows),
            "completed": completed_workflows,
            "completion_rate": _ratio(completed_workflows, len(workflows)),
            "slo_evaluable": slo_evaluable,
            "slo_evaluation_coverage": _ratio(slo_evaluable, len(workflows)),
            "slo_satisfied": slo_satisfied,
            "slo_attainment_rate": _ratio(slo_satisfied, len(workflows)),
            "slo_goodput_workflows_s": _ratio(slo_satisfied, window_s),
        },
        "efficiency": {
            "prompt_tokens": observed_prompt_tokens if usage_complete else None,
            "output_tokens": observed_output_tokens if usage_complete else None,
            "observed_prompt_tokens": observed_prompt_tokens,
            "observed_output_tokens": observed_output_tokens,
            "token_usage_coverage": _ratio(len(observed_usage), len(successes)),
            "kv_cache_hit_ratio": _ratio(cached_tokens, cache_prompt_tokens),
            "kv_cache_observation_coverage": _ratio(
                len(cache_observations), len(successes)
            ),
            "speculative_acceptance_ratio": _ratio(accepted, proposed),
            "speculation_observation_coverage": _ratio(
                len(speculation_observations), len(successes)
            ),
        },
        "resilience": {
            "recovery_events": len(recovery),
            "recovery_time_p95_ms": percentile(recovery, 0.95),
        },
        "isolation": {
            "cross_tenant_cache_hits": (
                sum(cross_tenant_observations) if cross_tenant_observations else None
            ),
            "cross_tenant_observation_coverage": _ratio(
                len(cross_tenant_observations), len(events)
            ),
            "security_violations": (
                sum(security_observations) if security_observations else None
            ),
            "security_observation_coverage": _ratio(len(security_observations), len(events)),
            "jain_fairness_index": workflow_fairness,
            "jain_workflow_completion_index": workflow_fairness,
            "jain_output_token_index": token_fairness,
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
        float(event["arrival_s"]) for event in events
    )


def _workflow_slo(events: list[dict[str, Any]]) -> tuple[bool, bool]:
    if not events:
        return (False, False)
    if not all(event.get("success") for event in events):
        return (True, False)
    start = min(float(event["arrival_s"]) for event in events)
    end = max(float(event["end_s"]) for event in events)
    deadline_values = [event.get("deadline_ms") for event in events]
    if any(value is None for value in deadline_values):
        return (False, False)
    workflow_pass = (end - start) * 1000 <= min(float(value) for value in deadline_values)
    for event in events:
        first_token = event.get("first_token_s")
        ttft_slo = event.get("ttft_slo_ms")
        tpot_slo = event.get("tpot_slo_ms")
        output_tokens = event.get("output_tokens")
        if first_token is None or ttft_slo is None or tpot_slo is None or output_tokens is None:
            return (False, False)
        ttft_ms = (float(first_token) - float(event["start_s"])) * 1000
        if ttft_ms > float(ttft_slo):
            workflow_pass = False
        if int(output_tokens) > 1:
            tpot_ms = (
                (float(event["end_s"]) - float(first_token))
                * 1000
                / (int(output_tokens) - 1)
            )
            if tpot_ms > float(tpot_slo):
                workflow_pass = False
    return (True, workflow_pass)


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _jain_index(values: list[int]) -> float | None:
    if not values:
        return None
    total = sum(values)
    squared = sum(value * value for value in values)
    return (total * total) / (len(values) * squared) if squared else None

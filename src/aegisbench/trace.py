"""Deterministic multi-agent workflow trace generation."""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from aegisbench.config import BenchmarkConfig


@dataclass(frozen=True)
class TraceRequest:
    request_id: str
    workflow_id: str
    tenant_id: str
    security_domain: str
    agent_id: str
    role: str
    dependencies: tuple[str, ...]
    arrival_s: float
    prompt_tokens: int
    output_tokens: int
    shared_prefix_tokens: int
    prefix_group: str
    deadline_ms: float


def generate_trace(config: BenchmarkConfig) -> list[TraceRequest]:
    rng = random.Random(config.seed)
    requests: list[TraceRequest] = []
    arrival_s = 0.0
    workflow_slo = float(config.metrics["slo"]["workflow_ms"])

    for workflow_index in range(config.workload.workflows):
        arrival_s += _next_interarrival(config, rng, workflow_index)
        workflow_id = f"wf-{workflow_index:06d}"
        tenant_id = _choose_tenant(config, rng)
        graph = _workflow_graph(config, workflow_id)
        for node_index, (agent_id, role, dependencies) in enumerate(graph):
            prompt_tokens = rng.randint(*config.workload.prompt_tokens)
            output_tokens = rng.randint(*config.workload.output_tokens)
            shared = int(prompt_tokens * config.workload.shared_prefix_ratio)
            requests.append(
                TraceRequest(
                    request_id=f"{workflow_id}-req-{node_index:03d}",
                    workflow_id=workflow_id,
                    tenant_id=tenant_id,
                    security_domain=tenant_id,
                    agent_id=agent_id,
                    role=role,
                    dependencies=tuple(dependencies),
                    arrival_s=round(arrival_s, 6),
                    prompt_tokens=prompt_tokens,
                    output_tokens=output_tokens,
                    shared_prefix_tokens=shared,
                    prefix_group=f"{config.workload.topology}:{role}",
                    deadline_ms=workflow_slo,
                )
            )
    return requests


def write_trace(requests: list[TraceRequest], output: str | Path) -> None:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for request in requests:
            record = asdict(request)
            record["dependencies"] = list(request.dependencies)
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def read_trace(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number} of {path}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"trace line {line_number} must be a JSON object")
            records.append(record)
    validate_trace(records)
    return records


def validate_trace(records: list[dict[str, Any]]) -> None:
    """Validate identity, DAG, tenant, and token invariants for a replay trace."""
    if not records:
        raise ValueError("trace must contain at least one request")
    required = {
        "request_id",
        "workflow_id",
        "tenant_id",
        "security_domain",
        "agent_id",
        "role",
        "dependencies",
        "arrival_s",
        "prompt_tokens",
        "output_tokens",
        "shared_prefix_tokens",
        "prefix_group",
        "deadline_ms",
    }
    by_id: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records, start=1):
        missing = sorted(required - record.keys())
        if missing:
            raise ValueError(f"trace record {index} is missing: {', '.join(missing)}")
        if not isinstance(record["request_id"], str) or not record["request_id"]:
            raise ValueError(f"trace record {index} has an invalid request_id")
        request_id = record["request_id"]
        if request_id in by_id:
            raise ValueError(f"duplicate request_id in trace: {request_id}")
        for field in (
            "workflow_id",
            "tenant_id",
            "security_domain",
            "agent_id",
            "role",
            "prefix_group",
        ):
            if not isinstance(record[field], str) or not record[field]:
                raise ValueError(f"{field} for {request_id} must be a non-empty string")
        dependencies = record["dependencies"]
        if not isinstance(dependencies, list) or any(
            not isinstance(value, str) or not value for value in dependencies
        ):
            raise ValueError(f"dependencies for {request_id} must be a list of IDs")
        if request_id in dependencies:
            raise ValueError(f"request {request_id} cannot depend on itself")
        if len(set(dependencies)) != len(dependencies):
            raise ValueError(f"dependencies for {request_id} must be unique")
        prompt_tokens = _trace_integer(record["prompt_tokens"], request_id, "prompt_tokens", 1)
        _trace_integer(record["output_tokens"], request_id, "output_tokens", 1)
        shared = _trace_integer(
            record["shared_prefix_tokens"], request_id, "shared_prefix_tokens", 0
        )
        if shared > prompt_tokens:
            raise ValueError(f"shared_prefix_tokens exceeds prompt_tokens for {request_id}")
        if (
            not isinstance(record["arrival_s"], (int, float))
            or isinstance(record["arrival_s"], bool)
            or not math.isfinite(float(record["arrival_s"]))
            or record["arrival_s"] < 0
        ):
            raise ValueError(f"arrival_s for {request_id} must be >= 0")
        if (
            not isinstance(record["deadline_ms"], (int, float))
            or isinstance(record["deadline_ms"], bool)
            or not math.isfinite(float(record["deadline_ms"]))
            or record["deadline_ms"] <= 0
        ):
            raise ValueError(f"deadline_ms for {request_id} must be > 0")
        by_id[request_id] = record

    for request_id, record in by_id.items():
        for dependency_id in record["dependencies"]:
            dependency = by_id.get(dependency_id)
            if dependency is None:
                raise ValueError(f"unknown dependency {dependency_id} for {request_id}")
            for field in ("workflow_id", "tenant_id", "security_domain"):
                if dependency[field] != record[field]:
                    raise ValueError(
                        f"dependency {dependency_id} crosses {field} boundary for {request_id}"
                    )

    state: dict[str, int] = {}

    def visit(request_id: str) -> None:
        if state.get(request_id) == 1:
            raise ValueError(f"cycle detected in trace at {request_id}")
        if state.get(request_id) == 2:
            return
        state[request_id] = 1
        for dependency_id in by_id[request_id]["dependencies"]:
            visit(dependency_id)
        state[request_id] = 2

    for request_id in by_id:
        visit(request_id)


def _trace_integer(value: Any, request_id: str, field: str, minimum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{field} for {request_id} must be an integer >= {minimum}")
    return value


def _next_interarrival(config: BenchmarkConfig, rng: random.Random, index: int) -> float:
    base = -math.log(max(1e-12, 1.0 - rng.random())) / config.workload.request_rate
    if config.workload.arrival_pattern == "bursty" and index % 8:
        return base * 0.08
    return base


def _choose_tenant(config: BenchmarkConfig, rng: random.Random) -> str:
    count = config.workload.tenants
    if config.workload.tenant_distribution == "uniform":
        index = rng.randrange(count)
    else:
        weights = [1.0 / (rank**1.2) for rank in range(1, count + 1)]
        index = rng.choices(range(count), weights=weights, k=1)[0]
    return f"tenant-{index + 1:03d}"


def _workflow_graph(
    config: BenchmarkConfig, workflow_id: str
) -> list[tuple[str, str, list[str]]]:
    def request_id(index: int) -> str:
        return f"{workflow_id}-req-{index:03d}"

    if config.workload.topology == "sequential":
        nodes = []
        for index in range(config.workload.agents):
            dependencies = [] if index == 0 else [request_id(index - 1)]
            nodes.append((f"agent-{index + 1}", "worker", dependencies))
        return nodes

    if config.workload.topology == "fan_out":
        nodes = [("supervisor", "supervisor", [])]
        for index in range(config.workload.agents - 2):
            nodes.append((f"worker-{index + 1}", "worker", [request_id(0)]))
        worker_ids = [request_id(index) for index in range(1, len(nodes))]
        nodes.append(("aggregator", "aggregator", worker_ids))
        return nodes

    nodes = []
    previous_round: list[str] = []
    for round_index in range(config.workload.debate_rounds):
        current_round: list[str] = []
        for agent_index in range(config.workload.agents):
            index = len(nodes)
            nodes.append(
                (
                    f"debater-{agent_index + 1}-round-{round_index + 1}",
                    "debater",
                    list(previous_round),
                )
            )
            current_round.append(request_id(index))
        previous_round = current_round
    nodes.append(("judge", "aggregator", previous_round))
    return nodes

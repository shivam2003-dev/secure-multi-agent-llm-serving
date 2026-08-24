"""Client-side admission policies for reproducible serving experiments.

The WCF implementation controls which dependency-ready request is admitted to a live
endpoint. It is deliberately not described as an engine-level batch scheduler: the serving
engine remains responsible for its internal iteration and batch composition.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from aegisbench.config import BenchmarkConfig


@dataclass(frozen=True)
class SchedulerDecision:
    endpoint: str
    policy: str
    score: float | None
    components: dict[str, float]
    predicted_cache_affinity: float


class AdmissionScheduler:
    """Work-conserving, priority-aware client admission across serving endpoints."""

    DEFAULT_WEIGHTS = {
        "criticality": 0.35,
        "tenant_deficit": 0.25,
        "cache_locality": 0.20,
        "service_cost": 0.08,
        "failure_risk": 0.07,
        "endpoint_load": 0.05,
    }

    def __init__(self, config: BenchmarkConfig, records: list[dict[str, Any]]) -> None:
        self.policy = str(config.mechanisms["resource_scheduling"]["policy"])
        self.endpoints = config.engine.endpoints
        self.capacity = int(config.mechanisms["batching"].get("client_max_concurrency", 32))
        self.weights = dict(self.DEFAULT_WEIGHTS)
        self.weights.update(config.mechanisms["resource_scheduling"].get("weights", {}))
        self.isolation = str(
            config.mechanisms["multi_tenancy_security"]["cache_isolation"]
        )
        self._records = {str(record["request_id"]): record for record in records}
        self._children = self._build_children(records)
        self._remaining_work = self._calculate_remaining_work()
        self._max_remaining = max(self._remaining_work.values(), default=1.0)
        self._max_cost = max((self._service_cost(record) for record in records), default=1.0)
        self._max_children = max((len(value) for value in self._children.values()), default=1)
        self._condition = asyncio.Condition()
        self._waiting: dict[str, dict[str, Any]] = {}
        self._active = 0
        self._endpoint_active: dict[str, int] = defaultdict(int)
        self._endpoint_attempts: dict[str, int] = defaultdict(int)
        self._endpoint_failures: dict[str, int] = defaultdict(int)
        self._tenant_service: dict[str, float] = defaultdict(float)
        self._resident_prefixes: dict[str, set[str]] = defaultdict(set)

    async def acquire(
        self, record: dict[str, Any], origin: float
    ) -> SchedulerDecision:
        """Wait until the policy selects this request and return its endpoint decision."""
        request_id = str(record["request_id"])
        async with self._condition:
            self._waiting[request_id] = record
            self._condition.notify_all()
            try:
                while True:
                    if self._active < self.capacity:
                        decision_id, decision = self.best_decision(time.monotonic() - origin)
                        if decision_id == request_id:
                            del self._waiting[request_id]
                            self._active += 1
                            self._endpoint_active[decision.endpoint] += 1
                            self._tenant_service[
                                str(record["tenant_id"])
                            ] += self._service_cost(record)
                            return decision
                    await self._condition.wait()
            except BaseException:
                self._waiting.pop(request_id, None)
                self._condition.notify_all()
                raise

    async def release(
        self,
        record: dict[str, Any],
        decision: SchedulerDecision,
        success: bool,
    ) -> None:
        """Release capacity and update only predictor state, never measured cache fields."""
        async with self._condition:
            self._active -= 1
            self._endpoint_active[decision.endpoint] -= 1
            self._endpoint_attempts[decision.endpoint] += 1
            if success:
                self._resident_prefixes[decision.endpoint].add(self._cache_key(record))
            else:
                self._endpoint_failures[decision.endpoint] += 1
            self._condition.notify_all()

    def best_decision(self, elapsed_s: float) -> tuple[str, SchedulerDecision]:
        """Return the highest-ranked waiting request and endpoint.

        This method is public to make policy behavior directly unit-testable. It requires at
        least one waiting record, which `acquire` guarantees.
        """
        if not self._waiting:
            raise RuntimeError("cannot rank an empty admission queue")

        if self.policy != "workflow_cache_fair":
            record = min(self._waiting.values(), key=lambda item: int(item["_sequence_index"]))
            endpoint = self._baseline_endpoint(record)
            return str(record["request_id"]), SchedulerDecision(
                endpoint=endpoint,
                policy=self.policy,
                score=None,
                components={},
                predicted_cache_affinity=self._cache_affinity(record, endpoint),
            )

        candidates: list[tuple[float, int, str, SchedulerDecision]] = []
        for record in self._waiting.values():
            for endpoint in self.endpoints:
                components = self._components(record, endpoint, elapsed_s)
                score = (
                    self.weights["criticality"] * components["criticality"]
                    + self.weights["tenant_deficit"] * components["tenant_deficit"]
                    + self.weights["cache_locality"] * components["cache_locality"]
                    - self.weights["service_cost"] * components["service_cost"]
                    - self.weights["failure_risk"] * components["failure_risk"]
                    - self.weights["endpoint_load"] * components["endpoint_load"]
                )
                decision = SchedulerDecision(
                    endpoint=endpoint,
                    policy=self.policy,
                    score=score,
                    components=components,
                    predicted_cache_affinity=components["cache_locality"],
                )
                candidates.append(
                    (
                        score,
                        -int(record["_sequence_index"]),
                        str(record["request_id"]),
                        decision,
                    )
                )
        _, _, request_id, decision = max(candidates, key=lambda item: (item[0], item[1]))
        return request_id, decision

    def add_waiting_for_test(self, record: dict[str, Any]) -> None:
        """Add a waiting record without touching async state for deterministic policy tests."""
        self._waiting[str(record["request_id"])] = record

    def _components(
        self, record: dict[str, Any], endpoint: str, elapsed_s: float
    ) -> dict[str, float]:
        request_id = str(record["request_id"])
        deadline_ms = max(float(record.get("deadline_ms", 1.0)), 1.0)
        workflow_age_s = max(0.0, elapsed_s - float(record["arrival_s"]))
        urgency = min(2.0, workflow_age_s * 1000 / deadline_ms)
        path = self._remaining_work[request_id] / max(self._max_remaining, 1.0)
        children = self._children.get(request_id, [])
        fanout = len(children) / max(self._max_children, 1)
        terminal = 1.0 if not children else 0.0
        criticality = 0.45 * path + 0.25 * urgency + 0.15 * fanout + 0.15 * terminal

        tenant = str(record["tenant_id"])
        max_service = max(self._tenant_service.values(), default=0.0)
        deficit = max(0.0, max_service - self._tenant_service[tenant])
        tenant_deficit = deficit / max(max_service, self._max_cost, 1.0)
        attempts = self._endpoint_attempts[endpoint]
        failure_risk = self._endpoint_failures[endpoint] / max(attempts, 1)
        per_endpoint_capacity = max(self.capacity / len(self.endpoints), 1.0)
        endpoint_load = min(1.0, self._endpoint_active[endpoint] / per_endpoint_capacity)
        return {
            "criticality": criticality,
            "tenant_deficit": tenant_deficit,
            "cache_locality": self._cache_affinity(record, endpoint),
            "service_cost": self._service_cost(record) / max(self._max_cost, 1.0),
            "failure_risk": failure_risk,
            "endpoint_load": endpoint_load,
        }

    def _baseline_endpoint(self, record: dict[str, Any]) -> str:
        if self.policy == "round_robin":
            return self.endpoints[int(record["_sequence_index"]) % len(self.endpoints)]
        key = str(record["tenant_id"])
        index = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % len(self.endpoints)
        return self.endpoints[index]

    def _cache_affinity(self, record: dict[str, Any], endpoint: str) -> float:
        if self._cache_key(record) not in self._resident_prefixes[endpoint]:
            return 0.0
        prompt_tokens = max(int(record["prompt_tokens"]), 1)
        return min(1.0, int(record["shared_prefix_tokens"]) / prompt_tokens)

    def _cache_key(self, record: dict[str, Any]) -> str:
        security_domain = "global" if self.isolation == "none" else str(
            record["security_domain"]
        )
        return f"{security_domain}:{record['prefix_group']}"

    @staticmethod
    def _service_cost(record: dict[str, Any]) -> float:
        return float(int(record["prompt_tokens"]) + int(record["output_tokens"]))

    @staticmethod
    def _build_children(records: list[dict[str, Any]]) -> dict[str, list[str]]:
        children: dict[str, list[str]] = defaultdict(list)
        for record in records:
            request_id = str(record["request_id"])
            children.setdefault(request_id, [])
            for dependency in record.get("dependencies", []):
                children[str(dependency)].append(request_id)
        return children

    def _calculate_remaining_work(self) -> dict[str, float]:
        memo: dict[str, float] = {}

        def visit(request_id: str, visiting: set[str]) -> float:
            if request_id in memo:
                return memo[request_id]
            if request_id in visiting:
                raise ValueError(f"cycle detected in trace at {request_id}")
            visiting.add(request_id)
            own = self._service_cost(self._records[request_id])
            descendants = [visit(child, visiting) for child in self._children[request_id]]
            visiting.remove(request_id)
            memo[request_id] = own + (max(descendants) if descendants else 0.0)
            return memo[request_id]

        for request_id in self._records:
            visit(request_id, set())
        return memo

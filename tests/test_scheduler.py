import asyncio
import copy
import time
from pathlib import Path

from aegisbench.config import BenchmarkConfig, load_config
from aegisbench.scheduler import AdmissionScheduler

ROOT = Path(__file__).resolve().parents[1]


def _record(
    request_id: str,
    tenant: str,
    sequence: int,
    prefix: str,
    shared: int = 50,
) -> dict:
    return {
        "request_id": request_id,
        "workflow_id": f"workflow-{request_id}",
        "tenant_id": tenant,
        "security_domain": tenant,
        "agent_id": "worker",
        "role": "worker",
        "dependencies": [],
        "arrival_s": 0.0,
        "prompt_tokens": 100,
        "output_tokens": 20,
        "shared_prefix_tokens": shared,
        "prefix_group": prefix,
        "deadline_ms": 1000,
        "_sequence_index": sequence,
    }


def _wcf_config(
    weights: dict[str, float] | None = None, capacity: int = 1
) -> BenchmarkConfig:
    base = load_config(ROOT / "configs" / "benchmark.factorial.yaml")
    raw = copy.deepcopy(base.raw)
    raw["engine"]["endpoints"] = ["http://worker-a:8000", "http://worker-b:8000"]
    raw["mechanisms"]["batching"]["client_max_concurrency"] = capacity
    if weights is not None:
        raw["mechanisms"]["resource_scheduling"]["weights"] = weights
    return BenchmarkConfig.from_mapping(raw)


def test_wcf_reuses_predicted_tenant_prefix_locality() -> None:
    warm = _record("warm", "tenant-1", 0, "tenant-1:worker")
    reuse = _record("reuse", "tenant-1", 1, "tenant-1:worker")
    scheduler = AdmissionScheduler(_wcf_config(), [warm, reuse])

    async def exercise() -> None:
        decision = await scheduler.acquire(warm, time.monotonic())
        await scheduler.release(warm, decision, True)
        scheduler.add_waiting_for_test(reuse)
        request_id, reuse_decision = scheduler.best_decision(0.2)
        assert request_id == "reuse"
        assert reuse_decision.endpoint == decision.endpoint
        assert reuse_decision.predicted_cache_affinity == 0.5

    asyncio.run(exercise())


def test_wcf_tenant_deficit_prioritizes_underserved_tenant() -> None:
    weights = {
        "criticality": 0,
        "tenant_deficit": 1,
        "cache_locality": 0,
        "service_cost": 0,
        "failure_risk": 0,
        "endpoint_load": 0,
    }
    served = _record("served", "tenant-1", 0, "served")
    tenant_one = _record("tenant-one", "tenant-1", 1, "one", shared=0)
    tenant_two = _record("tenant-two", "tenant-2", 2, "two", shared=0)
    scheduler = AdmissionScheduler(_wcf_config(weights), [served, tenant_one, tenant_two])

    async def exercise() -> None:
        decision = await scheduler.acquire(served, time.monotonic())
        await scheduler.release(served, decision, True)
        scheduler.add_waiting_for_test(tenant_one)
        scheduler.add_waiting_for_test(tenant_two)
        request_id, _ = scheduler.best_decision(0.2)
        assert request_id == "tenant-two"

    asyncio.run(exercise())


def test_wcf_reserves_fair_service_at_admission() -> None:
    weights = {
        "criticality": 0,
        "tenant_deficit": 1,
        "cache_locality": 0,
        "service_cost": 0,
        "failure_risk": 0,
        "endpoint_load": 0,
    }
    admitted = _record("admitted", "tenant-1", 0, "shared")
    tenant_one = _record("tenant-one", "tenant-1", 1, "shared")
    tenant_two = _record("tenant-two", "tenant-2", 2, "shared")
    scheduler = AdmissionScheduler(
        _wcf_config(weights, capacity=2), [admitted, tenant_one, tenant_two]
    )

    async def exercise() -> None:
        decision = await scheduler.acquire(admitted, time.monotonic())
        scheduler.add_waiting_for_test(tenant_one)
        scheduler.add_waiting_for_test(tenant_two)
        request_id, _ = scheduler.best_decision(0.2)
        assert request_id == "tenant-two"
        await scheduler.release(admitted, decision, True)

    asyncio.run(exercise())


def test_round_robin_endpoint_selection_is_stable() -> None:
    base = load_config(ROOT / "configs" / "benchmark.quick.yaml")
    raw = copy.deepcopy(base.raw)
    raw["engine"]["endpoints"] = ["http://worker-a:8000", "http://worker-b:8000"]
    raw["mechanisms"]["resource_scheduling"]["policy"] = "round_robin"
    config = BenchmarkConfig.from_mapping(raw)
    record = _record("r2", "tenant-1", 1, "prefix")
    scheduler = AdmissionScheduler(config, [record])
    scheduler.add_waiting_for_test(record)
    request_id, decision = scheduler.best_decision(0.0)
    assert request_id == "r2"
    assert decision.endpoint == "http://worker-b:8000"


def test_wcf_deadline_urgency_starts_at_workflow_arrival() -> None:
    record = _record("future", "tenant-1", 0, "shared")
    record["arrival_s"] = 10.0
    scheduler = AdmissionScheduler(_wcf_config(), [record])
    scheduler.add_waiting_for_test(record)
    _, decision = scheduler.best_decision(10.0)
    assert round(decision.components["criticality"], 6) == 0.6

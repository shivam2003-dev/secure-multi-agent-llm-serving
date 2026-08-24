from pathlib import Path

import pytest

from aegisbench.config import load_config
from aegisbench.trace import generate_trace, validate_trace

ROOT = Path(__file__).resolve().parents[1]


def test_trace_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="at least one request"):
        validate_trace([])


def test_trace_is_deterministic_and_preserves_fan_in() -> None:
    config = load_config(ROOT / "configs" / "benchmark.quick.yaml")
    first = generate_trace(config)
    second = generate_trace(config)
    assert first == second
    assert len(first) == config.workload.workflows * config.workload.agents

    workflow = [request for request in first if request.workflow_id == "wf-000000"]
    root = workflow[0]
    aggregator = workflow[-1]
    assert not root.dependencies
    assert aggregator.role == "aggregator"
    assert len(aggregator.dependencies) == config.workload.agents - 2
    assert all(request.security_domain == request.tenant_id for request in workflow)
    assert all(request.prefix_group.startswith("fan_out:") for request in workflow)
    assert all(request.tenant_id not in request.prefix_group for request in workflow)


def test_trace_rejects_cross_tenant_dependency() -> None:
    first = {
        "request_id": "a",
        "workflow_id": "w",
        "tenant_id": "t1",
        "security_domain": "t1",
        "agent_id": "a",
        "role": "worker",
        "dependencies": [],
        "arrival_s": 0.0,
        "prompt_tokens": 10,
        "output_tokens": 2,
        "shared_prefix_tokens": 5,
        "prefix_group": "p",
        "deadline_ms": 1000,
    }
    second = dict(first, request_id="b", tenant_id="t2", dependencies=["a"])
    with pytest.raises(ValueError, match="crosses tenant_id boundary"):
        validate_trace([first, second])


def test_trace_rejects_cycles() -> None:
    base = {
        "workflow_id": "w",
        "tenant_id": "t1",
        "security_domain": "t1",
        "agent_id": "a",
        "role": "worker",
        "arrival_s": 0.0,
        "prompt_tokens": 10,
        "output_tokens": 2,
        "shared_prefix_tokens": 5,
        "prefix_group": "p",
        "deadline_ms": 1000,
    }
    first = dict(base, request_id="a", dependencies=["b"])
    second = dict(base, request_id="b", dependencies=["a"])
    with pytest.raises(ValueError, match="cycle detected"):
        validate_trace([first, second])


def test_trace_rejects_non_finite_arrival() -> None:
    record = {
        "request_id": "a",
        "workflow_id": "w",
        "tenant_id": "t1",
        "security_domain": "t1",
        "agent_id": "a",
        "role": "worker",
        "dependencies": [],
        "arrival_s": float("nan"),
        "prompt_tokens": 10,
        "output_tokens": 2,
        "shared_prefix_tokens": 5,
        "prefix_group": "p",
        "deadline_ms": 1000,
    }
    with pytest.raises(ValueError, match="arrival_s"):
        validate_trace([record])

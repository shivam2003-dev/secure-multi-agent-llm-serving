from pathlib import Path

from aegisbench.config import load_config
from aegisbench.trace import generate_trace

ROOT = Path(__file__).resolve().parents[1]


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

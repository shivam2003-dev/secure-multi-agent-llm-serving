import asyncio
import copy
from pathlib import Path

import pytest

from aegisbench.config import BenchmarkConfig, load_config
from aegisbench.runner import _select_endpoint, run_trace

ROOT = Path(__file__).resolve().parents[1]


def test_round_robin_endpoint_selection_is_deterministic() -> None:
    base = load_config(ROOT / "configs" / "benchmark.quick.yaml")
    raw = copy.deepcopy(base.raw)
    raw["engine"]["endpoints"] = ["http://worker-a:8000", "http://worker-b:8000"]
    raw["mechanisms"]["resource_scheduling"]["policy"] = "round_robin"
    config = BenchmarkConfig.from_mapping(raw)
    assert _select_endpoint(config, {"_sequence_index": 0}) == "http://worker-a:8000"
    assert _select_endpoint(config, {"_sequence_index": 1}) == "http://worker-b:8000"
    assert _select_endpoint(config, {"_sequence_index": 2}) == "http://worker-a:8000"


def test_wcf_live_replay_requires_cluster_adapter(tmp_path) -> None:
    config = load_config(ROOT / "configs" / "benchmark.factorial.yaml")
    with pytest.raises(RuntimeError, match="engine scheduler adapter"):
        asyncio.run(run_trace(config, tmp_path / "missing.jsonl", tmp_path / "events.jsonl"))

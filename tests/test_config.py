import copy
from pathlib import Path

import pytest

from aegisbench.config import BenchmarkConfig, ConfigError, load_config

ROOT = Path(__file__).resolve().parents[1]


def test_quick_config_is_valid_and_stable() -> None:
    config = load_config(ROOT / "configs" / "benchmark.quick.yaml")
    assert config.name == "aegisserve-quickstart"
    assert config.workload.topology == "fan_out"
    assert len(config.digest) == 16
    assert config.digest == load_config(ROOT / "configs" / "benchmark.quick.yaml").digest


def test_missing_mechanism_is_rejected() -> None:
    config = load_config(ROOT / "configs" / "benchmark.quick.yaml")
    raw = dict(config.raw)
    raw["mechanisms"] = dict(raw["mechanisms"])
    del raw["mechanisms"]["failure_recovery"]
    with pytest.raises(ConfigError, match="failure_recovery"):
        BenchmarkConfig.from_mapping(raw)


def test_endpoint_credentials_are_rejected() -> None:
    config = load_config(ROOT / "configs" / "benchmark.quick.yaml")
    raw = copy.deepcopy(config.raw)
    raw["engine"]["endpoints"] = ["https://user:secret@example.test"]
    with pytest.raises(ConfigError, match="must not embed credentials"):
        BenchmarkConfig.from_mapping(raw)


@pytest.mark.parametrize(
    "endpoint",
    ["https://example.test?api_key=secret", "https://example.test#secret"],
)
def test_endpoint_query_and_fragment_are_rejected(endpoint: str) -> None:
    config = load_config(ROOT / "configs" / "benchmark.quick.yaml")
    raw = copy.deepcopy(config.raw)
    raw["engine"]["endpoints"] = [endpoint]
    with pytest.raises(ConfigError, match="query parameters or fragments"):
        BenchmarkConfig.from_mapping(raw)


def test_unknown_wcf_weight_is_rejected() -> None:
    config = load_config(ROOT / "configs" / "benchmark.factorial.yaml")
    raw = copy.deepcopy(config.raw)
    raw["mechanisms"]["resource_scheduling"]["weights"] = {"mystery": 1.0}
    with pytest.raises(ConfigError, match="unknown resource-scheduling weights"):
        BenchmarkConfig.from_mapping(raw)


def test_partial_zero_wcf_weight_keeps_other_defaults() -> None:
    config = load_config(ROOT / "configs" / "benchmark.factorial.yaml")
    raw = copy.deepcopy(config.raw)
    raw["mechanisms"]["resource_scheduling"]["weights"] = {"criticality": 0.0}
    BenchmarkConfig.from_mapping(raw)


def test_all_zero_wcf_weights_are_rejected() -> None:
    config = load_config(ROOT / "configs" / "benchmark.factorial.yaml")
    raw = copy.deepcopy(config.raw)
    keys = raw["mechanisms"]["resource_scheduling"]["weights"]
    raw["mechanisms"]["resource_scheduling"]["weights"] = dict.fromkeys(keys, 0.0)
    with pytest.raises(ConfigError, match="at least one"):
        BenchmarkConfig.from_mapping(raw)


def test_non_finite_wcf_weight_is_rejected() -> None:
    config = load_config(ROOT / "configs" / "benchmark.factorial.yaml")
    raw = copy.deepcopy(config.raw)
    raw["mechanisms"]["resource_scheduling"]["weights"] = {"criticality": float("nan")}
    with pytest.raises(ConfigError, match="must be finite"):
        BenchmarkConfig.from_mapping(raw)

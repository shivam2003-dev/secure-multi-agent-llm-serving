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

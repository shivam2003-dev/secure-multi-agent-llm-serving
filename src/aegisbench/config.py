"""Configuration loading and validation for reproducible benchmark runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when a benchmark configuration violates the schema."""


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{path} must be a mapping")
    return value


def _integer(value: Any, path: str, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ConfigError(f"{path} must be an integer >= {minimum}")
    return value


def _number(value: Any, path: str, minimum: float = 0.0, exclusive: bool = False) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"{path} must be a number")
    parsed = float(value)
    if (exclusive and parsed <= minimum) or (not exclusive and parsed < minimum):
        operator = ">" if exclusive else ">="
        raise ConfigError(f"{path} must be {operator} {minimum}")
    return parsed


def _choice(value: Any, path: str, choices: set[str]) -> str:
    if value not in choices:
        allowed = ", ".join(sorted(choices))
        raise ConfigError(f"{path} must be one of: {allowed}")
    return str(value)


@dataclass(frozen=True)
class EngineConfig:
    endpoints: tuple[str, ...]
    model: str
    timeout_s: float


@dataclass(frozen=True)
class WorkloadConfig:
    workflows: int
    topology: str
    agents: int
    debate_rounds: int
    tenants: int
    tenant_distribution: str
    arrival_pattern: str
    request_rate: float
    prompt_tokens: tuple[int, int]
    output_tokens: tuple[int, int]
    shared_prefix_ratio: float


@dataclass(frozen=True)
class BenchmarkConfig:
    name: str
    seed: int
    engine: EngineConfig
    workload: WorkloadConfig
    mechanisms: dict[str, Any]
    metrics: dict[str, Any]
    raw: dict[str, Any]

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> BenchmarkConfig:
        if raw.get("schema_version") != "1.0":
            raise ConfigError("schema_version must be '1.0'")

        benchmark = _mapping(raw.get("benchmark"), "benchmark")
        name = benchmark.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError("benchmark.name must be a non-empty string")
        seed = _integer(benchmark.get("seed", 2026), "benchmark.seed", minimum=0)

        engine_raw = _mapping(raw.get("engine"), "engine")
        endpoint_values = engine_raw.get("endpoints")
        if not isinstance(endpoint_values, list) or not endpoint_values:
            raise ConfigError("engine.endpoints must be a non-empty list")
        endpoints = tuple(str(item).rstrip("/") for item in endpoint_values)
        if any(not endpoint.startswith(("http://", "https://")) for endpoint in endpoints):
            raise ConfigError("each engine endpoint must start with http:// or https://")
        model = engine_raw.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ConfigError("engine.model must be a non-empty string")
        timeout_s = _number(engine_raw.get("timeout_s", 120), "engine.timeout_s", exclusive=True)

        workload_raw = _mapping(raw.get("workload"), "workload")
        workflows = _integer(workload_raw.get("workflows"), "workload.workflows")
        topology = _choice(
            workload_raw.get("topology"),
            "workload.topology",
            {"sequential", "fan_out", "debate"},
        )
        agents = _integer(workload_raw.get("agents"), "workload.agents", minimum=2)
        if topology == "fan_out" and agents < 3:
            raise ConfigError("workload.agents must be >= 3 for fan_out")
        debate_rounds = _integer(
            workload_raw.get("debate_rounds", 2), "workload.debate_rounds"
        )
        tenants = _integer(workload_raw.get("tenants"), "workload.tenants")
        tenant_distribution = _choice(
            workload_raw.get("tenant_distribution", "uniform"),
            "workload.tenant_distribution",
            {"uniform", "zipf"},
        )
        arrival_pattern = _choice(
            workload_raw.get("arrival_pattern", "poisson"),
            "workload.arrival_pattern",
            {"poisson", "bursty"},
        )
        request_rate = _number(
            workload_raw.get("request_rate"), "workload.request_rate", exclusive=True
        )
        prompt_tokens = _range(workload_raw.get("prompt_tokens"), "workload.prompt_tokens")
        output_tokens = _range(workload_raw.get("output_tokens"), "workload.output_tokens")
        shared_prefix_ratio = _number(
            workload_raw.get("shared_prefix_ratio", 0.5),
            "workload.shared_prefix_ratio",
        )
        if shared_prefix_ratio > 1:
            raise ConfigError("workload.shared_prefix_ratio must be <= 1")

        mechanisms = _mapping(raw.get("mechanisms"), "mechanisms")
        required_mechanisms = {
            "speculative_decoding",
            "batching",
            "kv_cache",
            "resource_scheduling",
            "failure_recovery",
            "multi_tenancy_security",
        }
        missing = sorted(required_mechanisms - mechanisms.keys())
        if missing:
            raise ConfigError(f"mechanisms is missing: {', '.join(missing)}")
        for mechanism in required_mechanisms:
            _mapping(mechanisms[mechanism], f"mechanisms.{mechanism}")

        isolation = mechanisms["multi_tenancy_security"].get("cache_isolation")
        _choice(
            isolation,
            "mechanisms.multi_tenancy_security.cache_isolation",
            {"none", "per_tenant", "per_tenant_salt"},
        )
        scheduler = mechanisms["resource_scheduling"].get("policy")
        _choice(
            scheduler,
            "mechanisms.resource_scheduling.policy",
            {"round_robin", "tenant_affinity", "workflow_cache_fair"},
        )

        metrics = _mapping(raw.get("metrics"), "metrics")
        slo = _mapping(metrics.get("slo"), "metrics.slo")
        _number(slo.get("ttft_ms"), "metrics.slo.ttft_ms", exclusive=True)
        _number(slo.get("tpot_ms"), "metrics.slo.tpot_ms", exclusive=True)
        _number(slo.get("workflow_ms"), "metrics.slo.workflow_ms", exclusive=True)

        return cls(
            name=name.strip(),
            seed=seed,
            engine=EngineConfig(endpoints=endpoints, model=model.strip(), timeout_s=timeout_s),
            workload=WorkloadConfig(
                workflows=workflows,
                topology=topology,
                agents=agents,
                debate_rounds=debate_rounds,
                tenants=tenants,
                tenant_distribution=tenant_distribution,
                arrival_pattern=arrival_pattern,
                request_rate=request_rate,
                prompt_tokens=prompt_tokens,
                output_tokens=output_tokens,
                shared_prefix_ratio=shared_prefix_ratio,
            ),
            mechanisms=mechanisms,
            metrics=metrics,
            raw=raw,
        )

    @property
    def digest(self) -> str:
        payload = json.dumps(self.raw, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()[:16]


def _range(value: Any, path: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ConfigError(f"{path} must be a two-item list")
    low = _integer(value[0], f"{path}[0]")
    high = _integer(value[1], f"{path}[1]")
    if low > high:
        raise ConfigError(f"{path}[0] must be <= {path}[1]")
    return (low, high)


def load_config(path: str | Path) -> BenchmarkConfig:
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration not found: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc
    return BenchmarkConfig.from_mapping(_mapping(raw, "root"))

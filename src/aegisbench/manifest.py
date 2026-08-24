"""Run-manifest generation without collecting credentials or prompt contents."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from aegisbench.config import BenchmarkConfig


def write_run_manifest(
    config: BenchmarkConfig,
    config_path: str | Path,
    trace_path: str | Path,
    events_path: str | Path,
    manifest_path: str | Path,
    started_at: datetime,
    completed_at: datetime,
    results: list[dict[str, Any]],
    run_id: str,
    time_scale: float = 1.0,
) -> dict[str, Any]:
    """Write a reviewable sidecar manifest for a completed live replay."""
    if time_scale <= 0:
        raise ValueError("time_scale must be > 0")
    if any(result.get("run_id") != run_id for result in results):
        raise ValueError("every event must carry the manifest run_id")
    trace = Path(trace_path)
    events = Path(events_path)
    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "started_at_utc": _utc(started_at),
        "completed_at_utc": _utc(completed_at),
        "duration_s": (completed_at - started_at).total_seconds(),
        "code": {
            "git_commit": _git(["rev-parse", "HEAD"]),
            "git_dirty": bool(_git(["status", "--porcelain"])),
            "aegisbench_version": _package_version(),
        },
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "configuration": {
            "path": str(Path(config_path)),
            "digest": config.digest,
            "benchmark": config.name,
            "seed": config.seed,
        },
        "trace": {
            "path": str(trace),
            "sha256": _sha256(trace),
            "requests": len(results),
        },
        "engine": {
            "model": config.engine.model,
            "endpoints": list(config.engine.endpoints),
        },
        "treatment": {
            "time_scale": time_scale,
            "scheduler_policy": config.mechanisms["resource_scheduling"]["policy"],
            "cache_isolation": config.mechanisms["multi_tenancy_security"][
                "cache_isolation"
            ],
            "speculative_decoding": _select(
                config.mechanisms["speculative_decoding"],
                "enabled",
                "method",
                "draft_model",
                "speculative_tokens",
            ),
            "batching": _select(
                config.mechanisms["batching"],
                "enabled",
                "mode",
                "client_max_concurrency",
                "max_num_batched_tokens",
            ),
            "kv_cache": _select(
                config.mechanisms["kv_cache"],
                "enabled",
                "prefix_caching",
                "tiers",
            ),
            "failure_recovery": _select(
                config.mechanisms["failure_recovery"],
                "enabled",
                "checkpoint",
                "fault_types",
            ),
        },
        "events": {
            "path": str(events),
            "sha256": _sha256(events),
            "total": len(results),
            "successful": sum(bool(result.get("success")) for result in results),
            "usage_reported": sum(bool(result.get("usage_reported")) for result in results),
            "cache_reported": sum(
                result.get("cache_hit_tokens") is not None for result in results
            ),
            "speculation_reported": sum(
                result.get("speculative_proposed") is not None
                and result.get("speculative_accepted") is not None
                for result in results
            ),
            "cross_tenant_reported": sum(
                result.get("cross_tenant_cache_hits") is not None for result in results
            ),
            "security_reported": sum(
                result.get("security_violations") is not None for result in results
            ),
        },
        "secret_policy": {
            "environment_values_recorded": False,
            "prompt_bodies_recorded": False,
        },
    }
    destination = Path(manifest_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def default_manifest_path(events_path: str | Path) -> Path:
    events = Path(events_path)
    stem = events.name.removesuffix(events.suffix)
    return events.with_name(f"{stem}.manifest.json")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(arguments: list[str]) -> str | None:
    completed = subprocess.run(
        ["git", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _package_version() -> str:
    try:
        return version("aegisbench")
    except PackageNotFoundError:
        return "uninstalled"


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _select(mapping: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: mapping[key] for key in keys if key in mapping}

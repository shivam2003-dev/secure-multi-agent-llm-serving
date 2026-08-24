"""OpenAI-compatible trace replay for live serving experiments."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from aegisbench.config import BenchmarkConfig
from aegisbench.scheduler import AdmissionScheduler, SchedulerDecision
from aegisbench.trace import read_trace


async def run_trace(
    config: BenchmarkConfig,
    trace_path: str | Path,
    output_path: str | Path,
    time_scale: float = 1.0,
    transport: httpx.AsyncBaseTransport | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Replay a trace while preserving DAG dependencies and relative arrivals."""
    if time_scale <= 0:
        raise ValueError("time_scale must be > 0")
    isolation = config.mechanisms["multi_tenancy_security"]["cache_isolation"]
    if isolation == "per_tenant_salt" and not os.getenv("AEGIS_CACHE_SALT_SECRET"):
        raise RuntimeError(
            "AEGIS_CACHE_SALT_SECRET is required when cache_isolation=per_tenant_salt"
        )
    records = read_trace(trace_path)
    active_run_id = run_id or str(uuid.uuid4())
    for sequence_index, record in enumerate(records):
        record["_sequence_index"] = sequence_index
    scheduler = AdmissionScheduler(config, records)
    done = {str(record["request_id"]): asyncio.Event() for record in records}
    outcomes: dict[str, bool] = {}
    origin = time.monotonic()
    api_key = os.getenv("AEGIS_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    timeout = httpx.Timeout(config.engine.timeout_s)

    async with httpx.AsyncClient(
        timeout=timeout,
        headers=headers,
        transport=transport,
    ) as client:
        tasks = [
            asyncio.create_task(
                _execute_record(
                    config,
                    client,
                    record,
                    scheduler,
                    done,
                    outcomes,
                    origin,
                    time_scale,
                    active_run_id,
                )
            )
            for record in records
        ]
        results = await asyncio.gather(*tasks)

    results.sort(key=lambda item: str(item["request_id"]))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, sort_keys=True) + "\n")
    return results


async def _execute_record(
    config: BenchmarkConfig,
    client: httpx.AsyncClient,
    record: dict[str, Any],
    scheduler: AdmissionScheduler,
    done: dict[str, asyncio.Event],
    outcomes: dict[str, bool],
    origin: float,
    time_scale: float,
    run_id: str,
) -> dict[str, Any]:
    request_id = str(record["request_id"])
    target_s = float(record["arrival_s"]) / time_scale
    await asyncio.sleep(max(0.0, origin + target_s - time.monotonic()))
    dependencies = [str(value) for value in record.get("dependencies", [])]
    await asyncio.gather(*(done[dependency].wait() for dependency in dependencies))
    if any(not outcomes.get(dependency, False) for dependency in dependencies):
        result = _failed_result(
            config,
            record,
            origin,
            time_scale,
            run_id,
            "dependency_failed",
        )
        outcomes[request_id] = False
        done[request_id].set()
        return result

    queued_at = time.monotonic()
    decision = await scheduler.acquire(record, origin)
    admission_wait_ms = (time.monotonic() - queued_at) * 1000
    try:
        result = await _call_endpoint(
            config,
            client,
            record,
            decision,
            admission_wait_ms,
            origin,
            time_scale,
            run_id,
        )
    except BaseException:
        await scheduler.release(record, decision, False)
        raise
    await scheduler.release(record, decision, bool(result["success"]))
    outcomes[request_id] = bool(result["success"])
    done[request_id].set()
    return result


async def _call_endpoint(
    config: BenchmarkConfig,
    client: httpx.AsyncClient,
    record: dict[str, Any],
    decision: SchedulerDecision,
    admission_wait_ms: float,
    origin: float,
    time_scale: float,
    run_id: str,
) -> dict[str, Any]:
    endpoint = decision.endpoint
    body = {
        "model": config.engine.model,
        "messages": _messages(record),
        "max_tokens": int(record["output_tokens"]),
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    cache_salt = _cache_salt(config, str(record["tenant_id"]))
    if cache_salt:
        body["cache_salt"] = cache_salt

    start_s = time.monotonic() - origin
    first_token_s: float | None = None
    output_tokens: int | None = None
    prompt_tokens: int | None = None
    cached_tokens: int | None = None
    usage_reported = False
    error: str | None = None
    success = False

    try:
        async with client.stream(
            "POST", f"{endpoint}/v1/chat/completions", json=body
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if _has_content(chunk) and first_token_s is None:
                    first_token_s = time.monotonic() - origin
                usage = chunk.get("usage") or {}
                if usage:
                    usage_reported = True
                    if usage.get("completion_tokens") is not None:
                        output_tokens = int(usage["completion_tokens"])
                    if usage.get("prompt_tokens") is not None:
                        prompt_tokens = int(usage["prompt_tokens"])
                    details = usage.get("prompt_tokens_details") or {}
                    if details.get("cached_tokens") is not None:
                        cached_tokens = int(details["cached_tokens"])
            success = True
    except (TimeoutError, httpx.HTTPError) as exc:
        error = f"{type(exc).__name__}: {exc}"

    end_s = time.monotonic() - origin
    if success and first_token_s is None:
        success = False
        error = "empty_stream: no text token was observed"

    return {
        "run_id": run_id,
        "config_digest": config.digest,
        "request_id": record["request_id"],
        "workflow_id": record["workflow_id"],
        "tenant_id": record["tenant_id"],
        "security_domain": record["security_domain"],
        "agent_id": record["agent_id"],
        "role": record["role"],
        "prefix_group": record["prefix_group"],
        "endpoint": endpoint,
        "arrival_s": float(record["arrival_s"]) / time_scale,
        "start_s": start_s,
        "first_token_s": first_token_s,
        "end_s": end_s,
        "deadline_ms": float(record["deadline_ms"]),
        "ttft_slo_ms": float(config.metrics["slo"]["ttft_ms"]),
        "tpot_slo_ms": float(config.metrics["slo"]["tpot_ms"]),
        "requested_prompt_tokens": int(record["prompt_tokens"]),
        "requested_output_tokens": int(record["output_tokens"]),
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "cache_hit_tokens": cached_tokens,
        "usage_reported": usage_reported,
        "scheduler_policy": decision.policy,
        "scheduler_score": decision.score,
        "scheduler_components": decision.components,
        "predicted_cache_affinity": decision.predicted_cache_affinity,
        "admission_wait_ms": admission_wait_ms,
        "speculative_proposed": None,
        "speculative_accepted": None,
        "fault_recovery_ms": None,
        "cross_tenant_cache_hits": None,
        "security_violations": None,
        "success": success,
        "error": error,
    }


def _cache_salt(config: BenchmarkConfig, tenant_id: str) -> str | None:
    isolation = config.mechanisms["multi_tenancy_security"]["cache_isolation"]
    if isolation != "per_tenant_salt":
        return None
    secret = os.getenv("AEGIS_CACHE_SALT_SECRET")
    if not secret:
        raise RuntimeError(
            "AEGIS_CACHE_SALT_SECRET is required when cache_isolation=per_tenant_salt"
        )
    return hmac.new(secret.encode(), tenant_id.encode(), hashlib.sha256).hexdigest()


def _messages(record: dict[str, Any]) -> list[dict[str, str]]:
    shared_count = max(1, int(record["shared_prefix_tokens"]))
    unique_count = max(1, int(record["prompt_tokens"]) - shared_count)
    shared = " ".join(f"policy{i % 64}" for i in range(shared_count))
    task_seed = int(hashlib.sha256(str(record["request_id"]).encode()).hexdigest()[:8], 16)
    unique = " ".join(f"task{(task_seed + i) % 4093}" for i in range(unique_count))
    return [
        {
            "role": "system",
            "content": f"You are {record['role']} in {record['prefix_group']}. {shared}",
        },
        {"role": "user", "content": f"Complete this deterministic benchmark task. {unique}"},
    ]


def _has_content(chunk: dict[str, Any]) -> bool:
    choices = chunk.get("choices") or []
    for choice in choices:
        delta = choice.get("delta") or {}
        if delta.get("content"):
            return True
    return False


def _failed_result(
    config: BenchmarkConfig,
    record: dict[str, Any],
    origin: float,
    time_scale: float,
    run_id: str,
    error: str,
) -> dict[str, Any]:
    now = time.monotonic() - origin
    return {
        "run_id": run_id,
        "config_digest": config.digest,
        "request_id": record["request_id"],
        "workflow_id": record["workflow_id"],
        "tenant_id": record["tenant_id"],
        "security_domain": record["security_domain"],
        "agent_id": record["agent_id"],
        "role": record["role"],
        "prefix_group": record["prefix_group"],
        "endpoint": None,
        "arrival_s": float(record["arrival_s"]) / time_scale,
        "start_s": now,
        "first_token_s": None,
        "end_s": now,
        "deadline_ms": float(record["deadline_ms"]),
        "ttft_slo_ms": float(config.metrics["slo"]["ttft_ms"]),
        "tpot_slo_ms": float(config.metrics["slo"]["tpot_ms"]),
        "requested_prompt_tokens": int(record["prompt_tokens"]),
        "requested_output_tokens": int(record["output_tokens"]),
        "prompt_tokens": 0,
        "output_tokens": 0,
        "cache_hit_tokens": 0,
        "usage_reported": False,
        "scheduler_policy": None,
        "scheduler_score": None,
        "scheduler_components": {},
        "predicted_cache_affinity": None,
        "admission_wait_ms": 0.0,
        "speculative_proposed": None,
        "speculative_accepted": None,
        "fault_recovery_ms": None,
        "cross_tenant_cache_hits": None,
        "security_violations": None,
        "success": False,
        "error": error,
    }

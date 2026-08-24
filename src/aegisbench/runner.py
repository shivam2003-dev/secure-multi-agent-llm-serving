"""OpenAI-compatible trace replay for live serving experiments."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from aegisbench.config import BenchmarkConfig
from aegisbench.trace import read_trace


async def run_trace(
    config: BenchmarkConfig,
    trace_path: str | Path,
    output_path: str | Path,
    time_scale: float = 1.0,
) -> list[dict[str, Any]]:
    """Replay a trace while preserving DAG dependencies and relative arrivals."""
    if time_scale <= 0:
        raise ValueError("time_scale must be > 0")
    policy = config.mechanisms["resource_scheduling"]["policy"]
    if policy == "workflow_cache_fair":
        raise RuntimeError(
            "workflow_cache_fair requires the planned engine scheduler adapter; "
            "use tenant_affinity or round_robin with the v0.1 client replay"
        )
    isolation = config.mechanisms["multi_tenancy_security"]["cache_isolation"]
    if isolation == "per_tenant_salt" and not os.getenv("AEGIS_CACHE_SALT_SECRET"):
        raise RuntimeError(
            "AEGIS_CACHE_SALT_SECRET is required when cache_isolation=per_tenant_salt"
        )
    records = read_trace(trace_path)
    for sequence_index, record in enumerate(records):
        record["_sequence_index"] = sequence_index
    concurrency = int(config.mechanisms["batching"].get("client_max_concurrency", 32))
    semaphore = asyncio.Semaphore(concurrency)
    done = {str(record["request_id"]): asyncio.Event() for record in records}
    outcomes: dict[str, bool] = {}
    origin = time.monotonic()
    api_key = os.getenv("AEGIS_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    timeout = httpx.Timeout(config.engine.timeout_s)

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        tasks = [
            asyncio.create_task(
                _execute_record(
                    config,
                    client,
                    record,
                    semaphore,
                    done,
                    outcomes,
                    origin,
                    time_scale,
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
    semaphore: asyncio.Semaphore,
    done: dict[str, asyncio.Event],
    outcomes: dict[str, bool],
    origin: float,
    time_scale: float,
) -> dict[str, Any]:
    request_id = str(record["request_id"])
    dependencies = [str(value) for value in record.get("dependencies", [])]
    await asyncio.gather(*(done[dependency].wait() for dependency in dependencies))
    if any(not outcomes.get(dependency, False) for dependency in dependencies):
        result = _failed_result(record, origin, time_scale, "dependency_failed")
        outcomes[request_id] = False
        done[request_id].set()
        return result

    target_s = float(record["arrival_s"]) / time_scale
    await asyncio.sleep(max(0.0, origin + target_s - time.monotonic()))
    async with semaphore:
        result = await _call_endpoint(config, client, record, origin, time_scale)
    outcomes[request_id] = bool(result["success"])
    done[request_id].set()
    return result


async def _call_endpoint(
    config: BenchmarkConfig,
    client: httpx.AsyncClient,
    record: dict[str, Any],
    origin: float,
    time_scale: float,
) -> dict[str, Any]:
    endpoint = _select_endpoint(config, record)
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
    output_tokens = 0
    prompt_tokens = 0
    cached_tokens = 0
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
                    output_tokens = int(
                        usage.get("completion_tokens", output_tokens) or output_tokens
                    )
                    prompt_tokens = int(usage.get("prompt_tokens", prompt_tokens) or prompt_tokens)
                    details = usage.get("prompt_tokens_details") or {}
                    cached_tokens = int(
                        details.get("cached_tokens", cached_tokens) or cached_tokens
                    )
            success = True
    except (TimeoutError, httpx.HTTPError) as exc:
        error = f"{type(exc).__name__}: {exc}"

    end_s = time.monotonic() - origin
    if success and first_token_s is None:
        first_token_s = end_s
    if success and output_tokens == 0:
        output_tokens = int(record["output_tokens"])
    if success and prompt_tokens == 0:
        prompt_tokens = int(record["prompt_tokens"])

    return {
        "request_id": record["request_id"],
        "workflow_id": record["workflow_id"],
        "tenant_id": record["tenant_id"],
        "endpoint": endpoint,
        "arrival_s": float(record["arrival_s"]) / time_scale,
        "start_s": start_s,
        "first_token_s": first_token_s,
        "end_s": end_s,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "cache_hit_tokens": cached_tokens,
        "speculative_proposed": None,
        "speculative_accepted": None,
        "fault_recovery_ms": None,
        "cross_tenant_cache_hits": 0,
        "security_violations": 0,
        "success": success,
        "error": error,
    }


def _select_endpoint(config: BenchmarkConfig, record: dict[str, Any]) -> str:
    endpoints = config.engine.endpoints
    policy = config.mechanisms["resource_scheduling"]["policy"]
    if policy == "round_robin":
        return endpoints[int(record["_sequence_index"]) % len(endpoints)]
    key = str(record["tenant_id"])
    index = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % len(endpoints)
    return endpoints[index]


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
    unique = " ".join(f"task{i % 257}" for i in range(unique_count))
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
    record: dict[str, Any], origin: float, time_scale: float, error: str
) -> dict[str, Any]:
    now = time.monotonic() - origin
    return {
        "request_id": record["request_id"],
        "workflow_id": record["workflow_id"],
        "tenant_id": record["tenant_id"],
        "arrival_s": float(record["arrival_s"]) / time_scale,
        "start_s": now,
        "first_token_s": None,
        "end_s": now,
        "prompt_tokens": 0,
        "output_tokens": 0,
        "cache_hit_tokens": 0,
        "fault_recovery_ms": None,
        "cross_tenant_cache_hits": 0,
        "security_violations": 0,
        "success": False,
        "error": error,
    }

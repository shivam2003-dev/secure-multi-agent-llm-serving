import asyncio
import copy
import json
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator, FormatChecker

from aegisbench.config import BenchmarkConfig, load_config
from aegisbench.runner import _messages, run_trace
from aegisbench.trace import generate_trace, write_trace

ROOT = Path(__file__).resolve().parents[1]


def test_wcf_live_replay_records_scheduler_and_observation_provenance(tmp_path) -> None:
    base = load_config(ROOT / "configs" / "benchmark.quick.yaml")
    raw = copy.deepcopy(base.raw)
    raw["workload"].update(
        {"workflows": 2, "topology": "sequential", "agents": 2, "request_rate": 1000}
    )
    raw["mechanisms"]["resource_scheduling"]["policy"] = "workflow_cache_fair"
    raw["mechanisms"]["multi_tenancy_security"]["cache_isolation"] = "per_tenant"
    config = BenchmarkConfig.from_mapping(raw)
    trace_path = tmp_path / "trace.jsonl"
    events_path = tmp_path / "events.jsonl"
    write_trace(generate_trace(config), trace_path)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        body = "\n".join(
            [
                'data: {"choices":[{"delta":{"content":"ok"}}]}',
                (
                    'data: {"choices":[],"usage":{"prompt_tokens":100,'
                    '"completion_tokens":4,"prompt_tokens_details":{"cached_tokens":20}}}'
                ),
                "data: [DONE]",
                "",
            ]
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    results = asyncio.run(
        run_trace(
            config,
            trace_path,
            events_path,
            time_scale=1000,
            transport=httpx.MockTransport(handler),
        )
    )
    assert len(results) == 4
    assert all(result["success"] for result in results)
    assert all(result["scheduler_policy"] == "workflow_cache_fair" for result in results)
    assert all(result["usage_reported"] for result in results)
    assert all(result["cache_hit_tokens"] == 20 for result in results)
    assert all(result["cross_tenant_cache_hits"] is None for result in results)
    persisted = [json.loads(line) for line in events_path.read_text().splitlines()]
    assert persisted == results
    schema = json.loads((ROOT / "schemas" / "event.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for event in persisted:
        validator.validate(event)


def test_synthetic_prompts_share_public_prefix_but_keep_tasks_distinct() -> None:
    base = {
        "role": "worker",
        "prefix_group": "fan_out:worker",
        "shared_prefix_tokens": 20,
        "prompt_tokens": 40,
    }
    first = _messages(dict(base, request_id="request-a"))
    second = _messages(dict(base, request_id="request-b"))
    assert first[0]["content"] == second[0]["content"]
    assert first[1]["content"] != second[1]["content"]


def test_dependency_failure_event_matches_schema(tmp_path) -> None:
    base = load_config(ROOT / "configs" / "benchmark.quick.yaml")
    raw = copy.deepcopy(base.raw)
    raw["workload"].update(
        {"workflows": 1, "topology": "sequential", "agents": 2, "request_rate": 1000}
    )
    raw["mechanisms"]["resource_scheduling"]["policy"] = "round_robin"
    raw["mechanisms"]["multi_tenancy_security"]["cache_isolation"] = "per_tenant"
    config = BenchmarkConfig.from_mapping(raw)
    trace_path = tmp_path / "trace.jsonl"
    events_path = tmp_path / "events.jsonl"
    write_trace(generate_trace(config), trace_path)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    results = asyncio.run(
        run_trace(
            config,
            trace_path,
            events_path,
            time_scale=1000,
            transport=httpx.MockTransport(handler),
        )
    )
    assert not any(result["success"] for result in results)
    assert any(result["error"] == "dependency_failed" for result in results)
    schema = json.loads((ROOT / "schemas" / "event.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for event in results:
        validator.validate(event)

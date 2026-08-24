import json

from aegisbench.metrics import summarize


def test_summary_includes_workflow_cache_recovery_and_isolation(tmp_path) -> None:
    events = [
        {
            "request_id": "r1",
            "workflow_id": "w1",
            "tenant_id": "t1",
            "arrival_s": 0.0,
            "start_s": 0.0,
            "first_token_s": 0.1,
            "end_s": 0.5,
            "prompt_tokens": 100,
            "output_tokens": 5,
            "cache_hit_tokens": 50,
            "speculative_proposed": 10,
            "speculative_accepted": 8,
            "fault_recovery_ms": None,
            "cross_tenant_cache_hits": 0,
            "security_violations": 0,
            "success": True,
        },
        {
            "request_id": "r2",
            "workflow_id": "w1",
            "tenant_id": "t1",
            "arrival_s": 0.0,
            "start_s": 0.5,
            "first_token_s": 0.7,
            "end_s": 1.0,
            "prompt_tokens": 100,
            "output_tokens": 4,
            "cache_hit_tokens": 100,
            "speculative_proposed": 10,
            "speculative_accepted": 7,
            "fault_recovery_ms": 120.0,
            "cross_tenant_cache_hits": 0,
            "security_violations": 0,
            "success": True,
        },
    ]
    path = tmp_path / "events.jsonl"
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    report = summarize(path)
    assert report["requests"]["success_rate"] == 1.0
    assert report["workflows"]["completion_rate"] == 1.0
    assert report["efficiency"]["kv_cache_hit_ratio"] == 0.75
    assert report["efficiency"]["speculative_acceptance_ratio"] == 0.75
    assert report["resilience"]["recovery_time_p95_ms"] == 120.0
    assert report["isolation"]["cross_tenant_cache_hits"] == 0

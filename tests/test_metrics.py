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
            "deadline_ms": 2000,
            "ttft_slo_ms": 300,
            "tpot_slo_ms": 200,
            "admission_wait_ms": 10,
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
            "deadline_ms": 2000,
            "ttft_slo_ms": 300,
            "tpot_slo_ms": 200,
            "admission_wait_ms": 20,
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
    assert report["workflows"]["slo_attainment_rate"] == 1.0
    assert report["workflows"]["slo_goodput_workflows_s"] == 1.0
    assert report["efficiency"]["kv_cache_hit_ratio"] == 0.75
    assert report["efficiency"]["speculative_acceptance_ratio"] == 0.75
    assert report["resilience"]["recovery_time_p95_ms"] == 120.0
    assert report["isolation"]["cross_tenant_cache_hits"] == 0
    assert report["isolation"]["cross_tenant_observation_coverage"] == 1.0


def test_summary_does_not_turn_unobserved_security_into_zero(tmp_path) -> None:
    event = {
        "request_id": "r1",
        "workflow_id": "w1",
        "tenant_id": "t1",
        "arrival_s": 0.0,
        "start_s": 0.0,
        "first_token_s": 0.1,
        "end_s": 0.2,
        "deadline_ms": 1000,
        "ttft_slo_ms": 200,
        "tpot_slo_ms": 100,
        "prompt_tokens": None,
        "output_tokens": None,
        "cache_hit_tokens": None,
        "admission_wait_ms": 0,
        "fault_recovery_ms": None,
        "cross_tenant_cache_hits": None,
        "security_violations": None,
        "success": True,
    }
    path = tmp_path / "unobserved.jsonl"
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    report = summarize(path)
    assert report["isolation"]["cross_tenant_cache_hits"] is None
    assert report["isolation"]["cross_tenant_observation_coverage"] == 0.0
    assert report["efficiency"]["token_usage_coverage"] == 0.0
    assert report["efficiency"]["prompt_tokens"] is None
    assert report["efficiency"]["output_tokens"] is None
    assert report["requests"]["throughput_output_tokens_s"] is None
    assert report["workflows"]["slo_evaluation_coverage"] == 0.0

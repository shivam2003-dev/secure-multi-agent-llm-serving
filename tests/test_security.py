import json

from aegisbench.security import audit_timing_samples


def test_timing_audit_passes_indistinguishable_isolated_samples(tmp_path) -> None:
    samples = []
    for value in [100, 102, 98, 101]:
        samples.append({"group": "cold", "ttft_ms": value})
    for value in [99, 103, 101, 98]:
        samples.append(
            {"group": "cross_tenant_probe", "ttft_ms": value, "cross_tenant_cache_hit": 0}
        )
    path = tmp_path / "samples.jsonl"
    path.write_text("".join(json.dumps(sample) + "\n" for sample in samples), encoding="utf-8")
    report = audit_timing_samples(path)
    assert report["pass"] is True
    assert report["cross_tenant_cache_hits"] == 0
    assert report["timing_attack_auc"] <= 0.60


def test_timing_audit_rejects_a_clear_side_channel(tmp_path) -> None:
    samples = [
        {"group": "cold", "ttft_ms": value} for value in [100, 105, 110]
    ] + [
        {"group": "cross_tenant_probe", "ttft_ms": value} for value in [20, 25, 30]
    ]
    path = tmp_path / "samples.jsonl"
    path.write_text("".join(json.dumps(sample) + "\n" for sample in samples), encoding="utf-8")
    report = audit_timing_samples(path)
    assert report["pass"] is False
    assert report["timing_attack_auc"] == 1.0

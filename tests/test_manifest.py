import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from aegisbench.config import load_config
from aegisbench.manifest import default_manifest_path, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_hashes_artifacts_without_secret_values(tmp_path, monkeypatch) -> None:
    config = load_config(ROOT / "configs" / "benchmark.quick.yaml")
    trace = tmp_path / "trace.jsonl"
    events = tmp_path / "events.jsonl"
    trace.write_text('{"request_id":"r1"}\n', encoding="utf-8")
    events.write_text('{"request_id":"r1","success":true}\n', encoding="utf-8")
    monkeypatch.setenv("AEGIS_API_KEY", "must-not-appear")
    monkeypatch.setenv("AEGIS_CACHE_SALT_SECRET", "also-must-not-appear")
    started = datetime(2026, 8, 25, tzinfo=UTC)
    destination = default_manifest_path(events)
    manifest = write_run_manifest(
        config,
        ROOT / "configs" / "benchmark.quick.yaml",
        trace,
        events,
        destination,
        started,
        started + timedelta(seconds=2),
        [
            {
                "run_id": "00000000-0000-4000-8000-000000000001",
                "success": True,
                "usage_reported": True,
            }
        ],
        "00000000-0000-4000-8000-000000000001",
        time_scale=0.25,
    )
    rendered = destination.read_text(encoding="utf-8")
    assert "must-not-appear" not in rendered
    assert manifest["duration_s"] == 2.0
    assert manifest["treatment"]["time_scale"] == 0.25
    assert manifest["events"]["cache_reported"] == 0
    assert len(manifest["events"]["sha256"]) == 64
    assert json.loads(rendered)["secret_policy"]["environment_values_recorded"] is False
    schema = json.loads((ROOT / "schemas" / "manifest.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)

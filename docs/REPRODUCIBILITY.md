# Reproducibility

## Required run bundle

Each reported point must archive:

```text
run-id/
  config.yaml
  manifest.json
  trace.jsonl
  client-events.jsonl
  engine-metrics.jsonl
  infrastructure-metrics.jsonl
  fault-events.jsonl          # fault treatments only
  summary.json
  stdout.log
  stderr.log
```

The manifest records UTC start/end time, Git revision and dirty state, config SHA-256,
container digests, serving engine and CUDA versions, exact model/tokenizer revisions,
precision/quantization, GPU model/count/memory, CPU/RAM, network topology, cloud region and
zones, scheduler placement, and all random seeds.

## Run order

1. Provision identical resources and verify clocks.
2. Capture the manifest before starting the server.
3. Start the engine and wait for health/readiness, not a fixed sleep.
4. Execute an unreported warm-up trace.
5. Reset prefix caches if the treatment starts cold.
6. Run one treatment and capture all telemetry.
7. Verify request counts and join coverage before teardown.
8. Randomize the next treatment; recreate the service where state cannot be reset reliably.

## Statistical reporting

- Use at least five independent repetitions for screening and ten for final tail results.
- Report median plus bootstrap 95% confidence intervals across runs.
- Report p50/p95/p99 within runs, but do not treat per-request samples as independent run
  replicates.
- Include failures and timeouts in completion/SLO denominators.
- Use paired seeds and traces for policy comparisons.
- Publish raw distributions for timing-security tests and include a positive control.

## Local artifact commands

```bash
uv sync --extra dev --extra paper
uv run aegisbench validate configs/benchmark.quick.yaml
uv run aegisbench generate configs/benchmark.quick.yaml --output results/trace.jsonl
uv run pytest
uv run --extra paper python scripts/build_whitepaper.py
```

## Claims policy

Use one of these labels for every result:

- **Measured**: backed by an archived run bundle and passing validity gates.
- **Derived**: calculated from measured fields with a published formula.
- **Simulated**: produced by an identified simulator and calibration source.
- **Hypothesis**: not yet tested.
- **Prior work**: attributed to the original source and experimental context.

Never describe a generated sample log as a measured serving result.

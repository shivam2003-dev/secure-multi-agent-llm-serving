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

The replay client automatically writes a sidecar manifest containing UTC start/end time,
run ID, Git revision and dirty state, AegisBench/Python/platform versions, config digest,
seed, treatment and time scale, endpoint/model identifiers, trace and event SHA-256 hashes,
and observation-coverage counts. It does not record environment values or prompt bodies.

The deployment adapter must augment the run bundle with container digests, serving engine,
CUDA and driver versions, exact model/tokenizer revisions, precision/quantization, GPU and
host inventory, network topology, cloud region/zones, and scheduler placement. The generated
manifest alone is not a complete cluster inventory.

## Run order

1. Provision identical resources and verify clocks.
2. Capture deployment inventory before starting the server.
3. Start the engine and wait for health/readiness, not a fixed sleep.
4. Execute an unreported warm-up trace.
5. Reset prefix caches if the treatment starts cold.
6. Run one treatment and capture all telemetry.
7. Finalize the hashed client manifest and verify request counts and join coverage.
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
uv sync --dev --extra paper
uv run aegisbench validate configs/benchmark.quick.yaml
uv run aegisbench generate configs/benchmark.quick.yaml --output results/trace.jsonl
uv run aegisbench run configs/benchmark.quick.yaml \
  --trace results/trace.jsonl --output results/events.jsonl
uv run aegisbench summarize results/events.jsonl --output results/summary.json
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

## Observation coverage

The OpenAI-compatible stream may omit token usage, cached-token details, or speculative
counters. AegisBench leaves absent fields as `null` and reports coverage for each derived
metric. A zero is a measured value; `null` is not observed. Isolation claims require the
separate controlled security probe and must not be inferred from ordinary client replay.

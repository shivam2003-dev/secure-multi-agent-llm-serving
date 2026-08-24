# Contributing

Thank you for improving AegisServe. The project welcomes reproducibility fixes, new serving
adapters, workload traces that can be redistributed safely, metric validation, and focused
research discussions.

## Set up

```bash
git clone https://github.com/shivam2003-dev/secure-multi-agent-llm-serving.git
cd secure-multi-agent-llm-serving
uv sync --extra dev --extra paper
uv run pytest
uv run ruff check .
```

## Before opening a pull request

1. Open or reference an issue for changes to metric definitions, event schemas, threat-model
   scope, or experimental methodology.
2. Add tests for behavior changes and keep deterministic seeds in fixtures.
3. Run config validation, lint, tests, and the white-paper build.
4. Explain the evidence boundary: measured, derived, simulated, hypothesis, or prior work.
5. Do not commit model credentials, cloud secrets, private prompts, customer traces, or
   generated results that cannot be audited.

## Research-result contributions

A result is reviewable only with the run bundle described in `docs/REPRODUCIBILITY.md`.
Include failed requests, exact versions, hardware/network inventory, seeds, cache reset and
warm-up policy, and raw client/engine/fault events. A screenshot or summary CSV alone is not
sufficient evidence.

Use synthetic data or data with explicit redistribution permission. If a trace cannot be
published, contribute the generator and distribution parameters instead.

## Code style

- Target Python 3.11 or newer.
- Keep core benchmark configuration declarative and deterministic.
- Prefer explicit units in names, such as `timeout_s` and `ttft_ms`.
- Preserve backward compatibility for JSONL fields or version the schema.
- Do not silently infer engine-level cache, batching, or recovery behavior from client time.

## Security

Do not open a public issue for a vulnerability that could expose tenant data or credentials.
Follow `SECURITY.md`.

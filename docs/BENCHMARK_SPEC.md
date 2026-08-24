# AegisBench benchmark specification

## 1. Goal

Measure the efficiency, isolation, fairness, and recoverability of distributed LLM serving
under multi-agent DAG workloads. A valid report must include user-visible workflow metrics;
request or token throughput alone is insufficient.

## 2. Experimental unit

The experimental unit is one independently provisioned run after warm-up. Repeat every
treatment at least five times with distinct recorded seeds. Randomize treatment order within
each hardware block. Do not reuse a warm prefix cache between treatments unless warm-cache
state is the controlled factor.

## 3. Workload families

| Family | DAG | Systems stress |
|---|---|---|
| Chain | `A -> B -> C -> ...` | critical path, state growth, session affinity |
| Supervisor | root -> parallel workers -> aggregator | burst amplification, fan-in tail |
| Debate | all-to-all rounds -> judge | repeated prefix reuse, synchronized bursts |

For each family, sweep prompt and output length, shared-prefix ratio, agent count, tenant
count, request rate, and arrival shape. Use trace replay for systems isolation and a real
task suite in a separate quality experiment. This prevents model nondeterminism from being
misread as scheduling behavior.

## 4. Required factors

### Speculative decoding

- Treatments: disabled; draft model with 3, 5, and 8 speculative tokens.
- Hold constant: target model, sampling parameters, prompt trace, batching cap.
- Report: accepted/proposed token ratio, target forward passes, TPOT, output tokens/s,
  workflow latency, and task-quality parity.
- Interpretation: an acceptance ratio without wall-clock improvement is not a win; draft
  execution can compete with target batches under high concurrency.

### Batching

- Treatments: concurrency 1, 8, 32, 128; fixed token budgets; continuous batching on/off.
- Report: queue delay, batch sequence count, batch tokens, TTFT, TPOT, GPU utilization,
  and SLO goodput.
- Check interaction with speculative decoding and long prefills.

### KV caching

- Treatments: disabled, local prefix cache, tenant-scoped cache, and remote tier.
- Prefix reuse: 0%, 25%, 50%, 75%, and 90% requested shared tokens.
- Report actual cached tokens, hit ratio, TTFT, evictions, recomputed tokens, transfer bytes,
  transfer latency, and peak HBM/host memory.
- A requested shared-prefix ratio is not evidence of a hit. Use engine counters.

### Resource scheduling

- Baselines: round robin, tenant affinity, cache affinity, shortest predicted remaining time.
- Reference treatment: Workflow-Cache-Fair client admission, with each score component
  recorded and individually ablated.
- Report workflow p50/p95/p99, request TTFT/TPOT, SLO goodput, cache hit ratio, utilization,
  and per-tenant Jain fairness.
- Run under uniform and Zipf tenants and include at least one noisy-neighbor tenant.

### Failure recovery

- Faults: process crash, GPU worker crash, node loss, and 100/500 ms network delay.
- Injection points: 25%, 50%, and 75% of prefill or decode progress.
- Treatments: recompute, metadata checkpoint, incremental KV checkpoint, KV replica.
- Report fault detection time, recovery time objective (RTO), lost/recomputed tokens,
  duplicate or missing output, request success, workflow completion, and post-fault SLO.
- A restarted replica is not a recovered workflow; verify the client-visible stream.

### Multi-tenancy and security

- Isolation treatments: global cache, per-tenant partition, keyed per-tenant salt.
- Probe: tenant A primes a secret prefix; tenant B issues controlled candidate prefixes.
- Report cross-tenant cache hits, TTFT distributions, attacker ROC AUC, cache-efficiency cost,
  authorization failures, and noisy-neighbor slowdown.
- Passing invariant: zero cross-tenant cache hits. Timing AUC must be near chance; the default
  automated gate is <= 0.60 with enough samples for a confidence interval.

## 5. Metrics and formulas

```text
TTFT = time(first streamed output) - time(request sent)
TPOT = (time(last output) - time(first output)) / (output tokens - 1)
workflow latency = max(node completion) - workflow arrival
SLO goodput = completed workflows meeting all declared SLOs / second
KV hit ratio = cached prompt tokens / prompt tokens
spec acceptance = accepted draft tokens / proposed draft tokens
Jain fairness = (sum tenant outcome)^2 / (N * sum tenant outcome^2)
```

With speculative decoding, streamed chunks may contain multiple tokens; TPOT and ITL are
therefore not interchangeable. Record the exact formula and measurement point. AegisBench
reports Jain fairness separately for completed workflows and observed output tokens; the
chosen tenant outcome must be named.

### Observation coverage

Derived metrics require the corresponding raw observation. If usage or engine cache fields
are omitted, the value is `null`, not zero, and the summary reports coverage. A workflow can
meet the full SLO only when it completes successfully and its workflow deadline, TTFT, and
TPOT constraints are evaluable. Failed workflows are known SLO failures; successful but
under-instrumented workflows are unevaluable and cannot count toward SLO goodput. Aggregate
token totals and token throughput remain `null` unless usage coverage is complete; separate
observed-token totals preserve the partial evidence.

## 6. Minimum experiment matrix

Use a fractional factorial screening study before focused sweeps. A naive full product of
all values above is too large and obscures interactions.

1. Screening: 2-level fractional factorial over speculation, batch budget, cache, scheduler,
   recovery, and isolation; at least five repetitions.
2. Interaction study: speculation x batching x prompt/output distribution.
3. Cache study: reuse x cache tier x tenant isolation x scheduler.
4. Failure study: fault type x injection phase x recovery mode.
5. Security study: isolation x tenant count x reuse x attacker rate.
6. End-to-end study: representative best safe policy against all baselines.

## 7. Baseline stack

Pin one serving engine for the mechanism ablations so implementation differences do not
confound the result. The initial reference is vLLM with an OpenAI-compatible endpoint and
Ray/Kubernetes for multi-node placement. Cross-engine comparison with SGLang is a separate
study and must use equivalent model weights, precision, kernels, request traces, and SLOs.

## 8. Result validity gates

A run is invalid if any of these are absent: run ID; config digest; code revision; model
revision; engine/container version; GPU and network inventory; raw client events; server
counters; fault timeline for fault runs; warm-up policy; seed; and metric observation
coverage. Trace and event hashes must match the manifest. Failed requests remain in the
denominator. Outliers may be explained but not silently deleted.

# Research plan

## Working title

**AegisServe: Secure and Efficient Multi-Agent LLM Inference in Distributed Clouds**

## Central research question

Can a tenant- and workflow-aware serving policy improve multi-agent workflow SLO goodput by
jointly managing batching, speculative decoding, and KV locality, without weakening tenant
isolation, fairness, or failure recovery?

## Hypotheses

### H1 - Workflow awareness

Under fan-out and debate workloads, WCF reduces p95 end-to-end workflow latency versus
round robin and cache-only affinity at equal hardware and request throughput.

### H2 - Optimization interaction

The benefit of speculative decoding depends on batch pressure and output length; a static
speculation setting is inferior to a load-aware setting for at least one workload regime.

### H3 - Secure cache reuse

Keyed tenant cache namespaces eliminate cross-tenant prefix hits and reduce timing attack
separability to near chance, with a measurable but bounded loss of cache efficiency relative
to global sharing.

### H4 - State-aware recovery

Incremental KV recovery lowers workflow recovery time and recomputation relative to full
prefill replay when the remaining decode is long enough to amortize checkpoint overhead.

### H5 - Joint policy

Optimizing token throughput alone produces more workflow SLO violations or worse tenant
fairness than a policy that includes critical-path slack and service deficit.

Every hypothesis is falsifiable. A negative result remains useful if the workload, system,
and power limits are reported.

## Research contributions

1. A workload model that preserves multi-agent DAG dependencies, synchronized bursts, and
   prompt-sharing structure.
2. A benchmark contract combining inference efficiency with security, fairness, and
   recovery rather than treating them as separate demonstrations.
3. The WCF scheduling policy and ablations of each score component.
4. A reproducible artifact with trace generation, live replay, fault/security protocols,
   raw event schemas, and publication-ready reporting.

## Evaluation phases

### Phase 1 - Single-node calibration

Validate client timestamps against engine metrics. Sweep prompt/output length, concurrency,
speculative tokens, and cache reuse on a 7B/8B model. Establish warm-up and sample sizes.

### Phase 2 - Distributed scheduling

Run two to eight GPU workers across at least two nodes. Compare round robin, tenant affinity,
cache affinity, shortest predicted remaining time, and WCF. Add network bandwidth/latency
as controlled variables.

### Phase 3 - Recovery

Inject process, worker, node, and network faults at recorded request phases. Compare full
recompute, metadata checkpoint, KV checkpoint, and replica treatments. Verify client-visible
stream correctness after every fault.

### Phase 4 - Isolation and interference

Run positive and negative timing controls, per-tenant salt/partition treatments, and a
noisy-neighbor tenant. Quantify both leakage reduction and performance cost.

### Phase 5 - Real task validation

Replay representative coding, retrieval, and deliberation workflows. Confirm that systems
treatments do not materially change task success or output distribution. Keep this separate
from deterministic systems traces.

## Baselines

- vLLM default/round-robin serving;
- continuous batching without workflow knowledge;
- cache-affinity scheduling inspired by distributed prefix reuse systems;
- prefill/decode disaggregation when supported;
- Ray Serve restart/replacement behavior for infrastructure recovery;
- global cache and strict per-tenant cache as security performance bounds.

## Scope control

The project is not a new foundation model, agent reasoning benchmark, cloud scheduler for
all workloads, or complete confidential-computing solution. The primary artifact is an
AI-systems serving benchmark plus one joint scheduling policy.

## Milestones

| Milestone | Exit criterion |
|---|---|
| M1 Artifact contract | schemas, trace generator, tests, documented metrics |
| M2 Live engine adapter | raw request and engine events join by request ID |
| M3 WCF prototype | all baseline policies and score ablations runnable |
| M4 Fault adapter | four fault types with exact injection/recovery timeline |
| M5 Security study | positive control works; isolated treatment passes gate |
| M6 Evaluation | repeated matrix, confidence intervals, no hidden exclusions |
| M7 Paper artifact | figures regenerate from raw logs and manifest |

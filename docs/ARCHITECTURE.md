# Architecture

## Design objective

AegisServe treats a multi-agent application as a tenant-owned directed acyclic graph (DAG)
of inference requests. Admission, scheduling, cache placement, and recovery operate on both
request-level and workflow-level state. This avoids equating maximum token throughput with
minimum end-to-end task latency.

## Logical components

### 1. Workflow admission controller

The controller accepts a DAG and attaches immutable metadata: workflow and tenant IDs,
security domain, dependencies, prompt/output budgets, deadline, and priority class. It
rejects malformed graphs and enforces per-tenant admission limits before GPU work begins.

### 2. Ready queue and WCF scheduler

Only nodes whose dependencies are complete enter the ready queue. The proposed
Workflow-Cache-Fair score is:

```text
score(r) = a * criticality(r)
         + b * tenant_deficit(r)
         + c * cache_locality(r)
         - d * predicted_service_time(r)
         - e * failure_risk(target)
```

The coefficients are configuration parameters, not learned constants. Criticality is
derived from remaining DAG slack. Tenant deficit implements weighted fair service. Cache
locality estimates avoided prefill tokens. Failure risk prevents state concentration in a
degraded fault domain.

### 3. Inference workers

Workers expose an OpenAI-compatible streaming API and may use vLLM, SGLang, or another
engine. The reference protocol records prefill and decode metrics separately. Prefill/decode
disaggregation is an experimental factor, not a required deployment shape.

### 4. Tenant-scoped KV manager

KV entries belong to a security domain. The strict policy uses an unpredictable keyed
tenant salt in the prefix-cache key. Public, explicitly shareable prefixes may use a
separate public domain, but private-to-public promotion is never automatic. Remote cache
movement must use authenticated encryption and integrity checks.

### 5. Recovery coordinator

The coordinator records request metadata and, for selected treatments, incremental KV
checkpoints. On failure it chooses one of three recovery modes: recompute the prompt,
restore a checkpoint, or resume from a replicated KV state. The result log records detection,
restart, first-token-after-recovery, duplicate-token, and workflow completion events.

### 6. Evidence plane

Client-observed timestamps are authoritative for TTFT and workflow latency. Engine metrics
provide batch, KV, and speculation details. Infrastructure telemetry supplies GPU, network,
and fault timing. Every event carries a run ID, config digest, workflow ID, tenant ID, and
request ID so these planes can be joined without inference.

## Trust boundaries

```mermaid
flowchart TB
  subgraph Tenant A
    A[Agent workflow A]
  end
  subgraph Tenant B
    B[Agent workflow B]
  end
  A --> GW[Authenticated gateway]
  B --> GW
  GW --> SCH[Policy and scheduler]
  SCH --> WA[Inference workers]
  WA --> KA[(KV domain A)]
  WA --> KB[(KV domain B)]
  KA -.- X{No cross-domain lookup}
  KB -.- X
  WA --> OBS[Append-only experiment log]
```

## v0.1 implementation boundary

The repository currently implements configuration, trace generation, DAG-aware client
replay with round-robin or tenant-affinity routing, metric aggregation, and timing-isolation
analysis. WCF engine admission, cache movement, and fault injection are specified interfaces
awaiting cluster adapters. This boundary is intentional: a local client cannot truthfully
claim GPU scheduler behavior or fault recovery without engine and infrastructure evidence.

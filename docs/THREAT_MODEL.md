# Threat model

## Assets

- private prompts, tool descriptions, retrieved context, and generated tokens;
- tenant identity, workflow topology, and timing metadata;
- KV blocks in GPU, host, and remote cache tiers;
- model weights, adapter identity, scheduler policy, and experiment integrity.

## Adversary

The primary adversary is an authenticated but malicious tenant sharing an inference service
with a victim. The adversary can issue adaptive prompts, measure its own response timing,
create bursty load, and observe its own API errors. It cannot read host memory directly,
administer the cluster, compromise the model provider, or defeat standard cryptography.

A second adversary is a compromised or faulty worker that returns stale, duplicated, or
misattributed state during recovery. The benchmark tests detection and containment; it does
not claim Byzantine consensus.

## In-scope risks

1. Cross-tenant prefix/KV reuse revealed directly or through timing.
2. Cache-key collision or missing tenant identity on one API path.
3. Tenant starvation and noisy-neighbor denial of service.
4. Plaintext or misrouted KV during node-to-node movement.
5. Stale KV restoration, duplicate tokens, or tenant mix-up after failure.
6. Secrets written to event logs, run manifests, traces, or repository history.

## Required controls

- authenticate every request and bind it to a server-derived tenant/security domain;
- derive cache namespaces from an unpredictable keyed tenant salt or use hard partitions;
- use authenticated encryption for remote KV and control-plane transport;
- include tenant, model, adapter, tokenizer, and cache-format identity in cache keys;
- enforce admission quotas and weighted fair service independently of client priority;
- validate checkpoint integrity and ownership before restore;
- redact prompts by default and record token counts or stable test identifiers instead;
- zero or cryptographically discard private cache material when its domain is destroyed.

## Explicitly out of scope for v0.1

- a malicious cloud/hypervisor administrator;
- physical attacks and GPU power/electromagnetic side channels;
- model-level prompt injection, unsafe tool use, and semantic data exfiltration;
- training-data extraction and model inversion;
- denial of service beyond configured admission capacity;
- formal verification of GPU kernels or collective communication libraries.

These exclusions must not be paraphrased as security guarantees. AegisServe evaluates a
specific shared-serving boundary.

## Security acceptance criteria

| Property | Evidence | Default gate |
|---|---|---|
| Cache separation | engine cached-token counters by tenant pair | 0 cross-tenant hits |
| Timing resistance | repeated cold/probe TTFT samples | attacker AUC <= 0.60 |
| Fair service | service share under a noisy tenant | policy target and Jain index reported |
| Recovery ownership | injected failure with tenant-tagged state | 0 misattributed restores |
| Transport | deployment and connection evidence | authenticated encryption enabled |
| Secret hygiene | repository/log scan | 0 committed credentials or prompt bodies |

The timing threshold is an engineering gate, not a proof of non-interference. Reports must
include sample size, confidence interval, network conditions, and the positive control that
demonstrates the probe can detect an intentionally global cache.

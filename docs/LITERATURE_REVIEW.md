# Literature review and positioning

This map separates established systems techniques from recent preprints and identifies the
specific question AegisServe still needs to test. Performance numbers belong to the cited
hardware, models, workloads, and baselines; they are not expected AegisServe results.

## Serving foundations

| Work | Main idea | Relevance to AegisServe |
|---|---|---|
| [Orca, OSDI 2022](https://www.usenix.org/conference/osdi22/presentation/yu) | iteration-level scheduling and selective batching | baseline for dynamic generative batching |
| [vLLM/PagedAttention, SOSP 2023](https://arxiv.org/abs/2309.06180) | paged KV memory and flexible sharing | reference engine and KV accounting foundation |
| [Speculative Decoding, ICML 2023](https://proceedings.mlr.press/v202/leviathan23a.html) | exact target sampling with draft proposals | mechanism and acceptance/latency interaction |
| [DistServe, OSDI 2024](https://arxiv.org/abs/2401.09670) | disaggregated prefill/decode goodput | phase-aware resource baseline |
| [Preble, 2024](https://arxiv.org/abs/2407.00023) | distributed prefix reuse plus load balance | cache-affinity scheduling baseline |
| [DejaVu, 2024](https://arxiv.org/abs/2403.01876) | KV streaming, swapping, and replication | stateful recovery baseline |
| [Llumnix, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/sun-biao) | live migration and dynamic rescheduling | multi-instance load/isolation baseline |
| [FastServe, NSDI 2026](https://www.usenix.org/conference/nsdi26/presentation/wu-bingyang) | token-level preemptive scheduling | latency-oriented scheduling baseline |

## Multi-agent serving

[Kairos](https://arxiv.org/abs/2508.06948) models multi-agent workflow information for
priority and memory-aware dispatch. Recent 2026 preprints move closer still:

- [SAGA](https://arxiv.org/abs/2605.00528) proposes workflow-atomic scheduling, agent
  execution graphs, affinity batching, and task-level fair share.
- [A Policy-Driven Runtime Layer for Agentic LLM Serving](https://arxiv.org/abs/2605.27744)
  proposes an agent-aware layer between frameworks and inference engines.
- [Cascade](https://arxiv.org/abs/2608.06557) jointly applies remaining SLO budget to
  scheduling and hierarchical KV management while considering fairness.

AegisServe therefore does not claim novelty for workflow awareness, cache-aware routing,
fair scheduling, or SLO-budget scheduling individually. Its narrower contribution target is
a compact open benchmark contract that tests their interactions with black-box KV isolation
and client-visible failure recovery, plus an executable, inspectable reference policy.

The repository must compare WCF against workflow-only, cache/load-only, fair-only, and simple
round-robin/affinity baselines. Otherwise a positive result cannot show which term adds value
relative to Kairos-, SAGA-, Cascade-, or conventional cache-aware behavior.

## KV security

The [vLLM prefix-cache design](https://docs.vllm.ai/en/latest/design/prefix_caching/) includes
cache salts as extra block identity and discusses cryptographic hashing for multi-tenant
risk. That is a design capability, not proof that every API entry point and external cache
connector preserves the namespace.

Two recent preprints sharpen the question:

- [SafeKV](https://arxiv.org/abs/2508.08438) proposes selective public/private sharing and
  reports both leakage mitigation and efficiency outcomes.
- [KVGov](https://arxiv.org/abs/2608.09225) proposes principal-keyed salting and governance
  across several timing-attack paths.

Because these are recent preprints, AegisServe treats their results as research context. Its
own security result requires a positive control, engine cached-token evidence, zero
cross-tenant hits, timing distributions, and an explicit attacker model.

## Production substrate

[Ray Serve architecture documentation](https://docs.ray.io/en/latest/serve/architecture.html)
describes replica and controller recovery and notes where transient state can be lost.
[vLLM distributed deployment documentation](https://docs.vllm.ai/en/latest/serving/data_parallel_deployment/)
describes multi-node data-parallel layouts and current queue-based internal balancing. These
are useful implementation substrates, but neither proves active multi-agent workflow
continuity after a fault.

## Research gap retained by this project

The defensible gap is not "no one has optimized LLM inference." It is:

> Can a compact reproducible artifact expose interactions among workflow scheduling, cache
> locality, tenant fairness, SLO goodput, isolation evidence, and client-visible recovery -
> and reject a performance win when observation coverage or a safety gate is missing?

This claim should be refreshed before paper submission because the serving literature is
moving quickly.

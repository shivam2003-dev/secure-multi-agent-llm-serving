# Results report template

## Answer first

State whether each hypothesis was supported, contradicted, or inconclusive. Include the
effect size and confidence interval, not only the winning treatment.

## System and workload

- Run IDs:
- Git revision / dirty state:
- Config digest:
- Engine/container/model revisions:
- Hardware and network:
- DAG family, tenants, arrivals, token distribution, reuse:
- Repetitions and seeds:

## Validity gates

| Gate | Status | Evidence path |
|---|---|---|
| Client/engine join coverage | | |
| Warm-up and cache-reset policy | | |
| Failed requests retained | | |
| Fault timeline captured | | |
| Positive timing control detects global cache | | |
| No secrets or private prompts in artifact | | |

## Efficiency and SLO results

| Treatment | Workflow p95 | TTFT p95 | TPOT p95 | SLO goodput | Output tok/s | GPU util |
|---|---:|---:|---:|---:|---:|---:|
| | | | | | | |

## KV and speculation

| Treatment | KV hit ratio | Evictions | Transfer GiB | Spec acceptance | Target steps saved |
|---|---:|---:|---:|---:|---:|
| | | | | | |

## Fairness and isolation

| Treatment | Jain fairness | Worst-tenant slowdown | Cross-tenant hits | Timing AUC |
|---|---:|---:|---:|---:|
| | | | | |

## Recovery

| Fault/treatment | Detection ms | RTO p95 ms | Recomputed tokens | Workflow completion |
|---|---:|---:|---:|---:|
| | | | | |

## Limitations and negative results

List unsupported model/engine combinations, failed validity gates, capacity boundaries,
measurement uncertainty, and treatments that did not help. Do not hide regressions behind
an aggregate mean.

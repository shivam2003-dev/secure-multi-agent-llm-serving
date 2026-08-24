# Security policy

## Supported versions

AegisServe is an early research prototype. Security fixes are applied to the current `main`
branch and the latest tagged release. No production-support claim is made.

## Reporting a vulnerability

Use the repository's private GitHub security advisory form:

https://github.com/shivam2003-dev/secure-multi-agent-llm-serving/security/advisories/new

Include the affected revision, configuration, impact, minimal reproduction, and whether the
issue can expose cross-tenant state. Do not include real prompts, API keys, cloud credentials,
or third-party tenant data. Please allow a reasonable remediation window before disclosure.

## Deployment warning

This repository is a benchmark and research prototype, not a hardened inference gateway.
The presence of tenant IDs or cache salts does not establish end-to-end isolation. A real
deployment must verify authentication, authorization, every cache entry path, transport
encryption, storage lifecycle, secret management, audit logging, and infrastructure policy.

Only run timing probes and fault injection against systems you own or are explicitly
authorized to test.

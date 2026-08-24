"""Command-line interface for AegisBench."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from aegisbench.config import ConfigError, load_config
from aegisbench.metrics import summarize
from aegisbench.runner import run_trace
from aegisbench.security import audit_timing_samples
from aegisbench.trace import generate_trace, write_trace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aegisbench",
        description="Secure multi-agent LLM serving benchmark",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a benchmark config")
    validate.add_argument("config", type=Path)

    generate = subparsers.add_parser("generate", help="generate a deterministic workflow trace")
    generate.add_argument("config", type=Path)
    generate.add_argument("--output", type=Path, required=True)

    run = subparsers.add_parser("run", help="replay a trace against OpenAI-compatible servers")
    run.add_argument("config", type=Path)
    run.add_argument("--trace", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--time-scale", type=float, default=1.0)

    summary = subparsers.add_parser("summarize", help="aggregate a JSONL event log")
    summary.add_argument("events", type=Path)
    summary.add_argument("--output", type=Path)

    security = subparsers.add_parser(
        "security-audit", help="evaluate cross-tenant cache timing samples"
    )
    security.add_argument("samples", type=Path)
    security.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            config = load_config(args.config)
            payload = {
                "valid": True,
                "name": config.name,
                "digest": config.digest,
                "topology": config.workload.topology,
            }
        elif args.command == "generate":
            config = load_config(args.config)
            trace = generate_trace(config)
            write_trace(trace, args.output)
            payload = {
                "generated": len(trace),
                "workflows": config.workload.workflows,
                "output": str(args.output),
                "config_digest": config.digest,
            }
        elif args.command == "run":
            config = load_config(args.config)
            results = asyncio.run(
                run_trace(config, args.trace, args.output, time_scale=args.time_scale)
            )
            payload = {
                "requests": len(results),
                "successful": sum(bool(result["success"]) for result in results),
                "output": str(args.output),
            }
        elif args.command == "summarize":
            payload = summarize(args.events)
        else:
            payload = audit_timing_samples(args.samples)
    except (ConfigError, OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    rendered = json.dumps(payload, indent=2, sort_keys=True)
    output = getattr(args, "output", None)
    if output and args.command in {"summarize", "security-audit"}:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)

#!/usr/bin/env python3
"""Minimal command-line client for the Distributed Job Engine.

Submits one job, then polls until it reaches a terminal state.

    python3 examples/client.py '{"task":"noop"}'
    python3 examples/client.py '{"task":"sleep","seconds":2}' --priority high
    python3 examples/client.py '{"task":"noop"}' --url http://127.0.0.1:8000/api/v1

Only `httpx` is required (it is already a project dependency). The script needs
no PYTHONPATH and does not import the engine itself.
"""

import argparse
import json
import sys
import time

import httpx

TERMINAL = {"completed", "failed", "cancelled", "dead_letter"}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Submit a job and wait for its result.")
    parser.add_argument("payload", help="job payload (string, usually JSON)")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000/api/v1",
        help="API base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--priority",
        default="normal",
        choices=["low", "normal", "high", "critical"],
        help="job priority (default: %(default)s)",
    )
    parser.add_argument("--timeout", type=int, help="per-job timeout in seconds")
    parser.add_argument("--max-retries", type=int, help="retry budget")
    parser.add_argument("--idempotency-key", help="deduplicate repeated submissions")
    parser.add_argument("--api-key", help="value for the configured API key header")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.2,
        help="seconds between status checks (default: %(default)s)",
    )
    parser.add_argument(
        "--max-wait",
        type=float,
        default=60.0,
        help="give up waiting after this many seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="submit and print the job id without polling",
    )
    return parser.parse_args(argv)


def headers(args):
    return {"X-API-Key": args.api_key} if args.api_key else {}


def main(argv=None) -> int:
    args = parse_args(argv)
    body = {"payload": args.payload, "priority": args.priority}
    if args.timeout is not None:
        body["timeout"] = args.timeout
    if args.max_retries is not None:
        body["max_retries"] = args.max_retries
    if args.idempotency_key is not None:
        body["idempotency_key"] = args.idempotency_key

    with httpx.Client(base_url=args.url, headers=headers(args), timeout=10.0) as client:
        response = client.post("/jobs", json=body)
        if response.status_code >= 400:
            print(f"submit failed: {response.status_code} {response.text}", file=sys.stderr)
            return 1

        job = response.json()
        job_id = job["job_id"]
        print(f"submitted {job_id} (status={job['status']})")

        if args.no_wait:
            return 0

        deadline = time.monotonic() + args.max_wait
        while time.monotonic() < deadline:
            current = client.get(f"/jobs/{job_id}")
            if current.status_code >= 400:
                print(f"poll failed: {current.status_code} {current.text}", file=sys.stderr)
                return 1

            job = current.json()
            if job["status"] in TERMINAL:
                print(json.dumps(job, indent=2))
                return 0 if job["status"] == "completed" else 2

            time.sleep(args.poll_interval)

    print(f"timed out waiting for {job_id}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())

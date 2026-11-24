"""Command-line entry point.

Installed as the ``job-engine`` console script:

    job-engine version
    job-engine serve --host 127.0.0.1 --port 8000
    job-engine worker --workers 4

``serve`` runs the HTTP API and, unless ``--no-workers`` is passed, the workers
in the same process. ``worker`` runs only the workers, which is how the API and
the execution layer are scaled apart.

All configuration still comes from environment variables (see ``src/config.py``);
the flags only override the bind address and the worker count.
"""

import argparse
import asyncio
import dataclasses
import signal
import sys

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job-engine",
        description="Async job engine: REST API, priority queue, asyncio workers.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the HTTP API")
    serve.add_argument("--host", help="bind address (default: API_HOST)")
    serve.add_argument("--port", type=int, help="bind port (default: API_PORT)")
    serve.add_argument(
        "--no-workers",
        action="store_true",
        help="serve HTTP only; run `job-engine worker` separately",
    )
    serve.add_argument(
        "--reload",
        action="store_true",
        help="auto-reload on source changes (development)",
    )

    worker = sub.add_parser("worker", help="run workers only, without the HTTP API")
    worker.add_argument(
        "--workers", type=int, help="number of worker coroutines (default: WORKER_COUNT)"
    )

    sub.add_parser("version", help="print the installed version")

    return parser


def _serve(args) -> int:
    import uvicorn

    from .config import JobEngineConfig
    from .main import app, configure_logging

    config = JobEngineConfig.from_env()
    if args.no_workers:
        config = dataclasses.replace(config, enable_workers=False)

    configure_logging(config)
    uvicorn.run(
        app,
        host=args.host or config.api_host,
        port=args.port or config.api_port,
        reload=args.reload,
        log_level=config.log_level.lower(),
    )
    return 0


def _run_worker(config) -> int:
    from .main import configure_logging
    from .services.database import DatabaseService
    from .services.job_processor import JobProcessor

    configure_logging(config)

    async def runner() -> None:
        db = DatabaseService(config)
        await db.initialize()

        processor = JobProcessor(config, db)
        await processor.start()

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:  # pragma: no cover - not on Windows
                pass

        try:
            await stop.wait()
        finally:
            await processor.stop()
            await db.close()

    asyncio.run(runner())
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "serve":
        return _serve(args)

    if args.command == "worker":
        from .config import JobEngineConfig

        config = JobEngineConfig.from_env()
        if args.workers is not None:
            if args.workers < 1:
                parser.error("--workers must be at least 1")
            config = dataclasses.replace(
                config, worker_count=args.workers, enable_workers=True
            )
        return _run_worker(config)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())

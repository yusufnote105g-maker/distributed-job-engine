"""Command-line entry point.

Installed as the ``job-engine`` console script:

    job-engine version
    job-engine serve --host 127.0.0.1 --port 8000

All configuration still comes from environment variables (see ``src/config.py``);
the flags only override the bind address.
"""

import argparse
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

    serve = sub.add_parser("serve", help="start the HTTP API (and in-process workers)")
    serve.add_argument("--host", help="bind address (default: API_HOST)")
    serve.add_argument("--port", type=int, help="bind port (default: API_PORT)")
    serve.add_argument(
        "--reload", action="store_true", help="auto-reload on source changes (development)"
    )

    sub.add_parser("version", help="print the installed version")

    return parser


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
        import uvicorn

        from .config import JobEngineConfig
        from .main import app, configure_logging

        config = JobEngineConfig.from_env()
        configure_logging(config)
        uvicorn.run(
            app,
            host=args.host or config.api_host,
            port=args.port or config.api_port,
            reload=args.reload,
            log_level=config.log_level.lower(),
        )
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())

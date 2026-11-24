"""CLI argument surface for the split API/worker deployment."""

import pytest

from src.cli import build_parser


def test_serve_defaults():
    args = build_parser().parse_args(["serve"])
    assert args.command == "serve"
    assert args.host is None
    assert args.port is None
    assert args.no_workers is False


def test_serve_no_workers_flag():
    args = build_parser().parse_args(["serve", "--no-workers", "--port", "9000"])
    assert args.no_workers is True
    assert args.port == 9000


def test_worker_command_defaults_to_configured_count():
    args = build_parser().parse_args(["worker"])
    assert args.command == "worker"
    assert args.workers is None


def test_worker_command_accepts_count():
    args = build_parser().parse_args(["worker", "--workers", "3"])
    assert args.workers == 3


def test_worker_rejects_non_positive_count(capsys):
    from src.cli import main

    with pytest.raises(SystemExit):
        main(["worker", "--workers", "0"])
    assert "--workers must be at least 1" in capsys.readouterr().err

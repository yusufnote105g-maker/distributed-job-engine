"""Packaging metadata and CLI entry point must stay consistent."""

import tomllib
from pathlib import Path

import src

ROOT = Path(__file__).resolve().parents[1]


def read_pyproject() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_pyproject_version_matches_package_version():
    data = read_pyproject()
    assert data["project"]["version"] == src.__version__


def test_app_version_matches_package_version():
    from src.main import VERSION

    assert VERSION == src.__version__


def test_cli_reports_the_same_version(capsys):
    from src.cli import main

    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == src.__version__


def test_cli_without_command_prints_help(capsys):
    from src.cli import main

    assert main([]) == 0
    out = capsys.readouterr().out
    assert "serve" in out
    assert "version" in out


def test_console_script_is_declared():
    data = read_pyproject()
    assert data["project"]["scripts"]["job-engine"] == (
        "distributed_job_engine.cli:main"
    )

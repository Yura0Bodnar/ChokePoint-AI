"""Prints the golden-set score tables at the end of the pytest run.

Tests append ``Report`` objects (via the ``eval_reports`` fixture); the hook below
renders them in the terminal summary, so the table is visible with a plain
``pytest tests/eval/`` — no ``-s`` needed.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def eval_reports(pytestconfig: pytest.Config) -> list[object]:
    reports: list[object] = []
    pytestconfig._eval_reports = reports  # type: ignore[attr-defined]  # read by the hook below
    return reports


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    reports = getattr(config, "_eval_reports", None)
    if not reports:
        return
    terminalreporter.section("extraction quality (golden set)")
    for report in reports:
        for line in report.render().splitlines():  # type: ignore[attr-defined]
            terminalreporter.write_line(line)
        terminalreporter.write_line("")

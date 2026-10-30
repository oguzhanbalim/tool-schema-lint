from __future__ import annotations

from typing import Any

import pytest

from tool_schema_lint.loader import LoadedFile, _add
from tool_schema_lint.model import Finding, Options
from tool_schema_lint.rules import Linter

GOOD_DESCRIPTION = (
    "Returns the balance of one account. Use this tool when the user asks how much money an "
    "account holds. It does not list transactions."
)


def make_tool(**overrides: Any) -> dict[str, Any]:
    tool: dict[str, Any] = {
        "name": "get_account_balance",
        "description": GOOD_DESCRIPTION,
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account number on the statement."}
            },
            "required": ["account_id"],
        },
    }
    tool.update(overrides)
    return tool


def run_lint(*tools: dict[str, Any], **options: Any) -> list[Finding]:
    from pathlib import Path

    loaded = LoadedFile(path=Path("mem.json"), kind="json", document=list(tools))
    for index, tool in enumerate(tools):
        _add(loaded, tool, f"/{index}")
    return Linter("mem.json", loaded.tools, Options(**options)).run()


@pytest.fixture
def lint():
    return run_lint


@pytest.fixture
def tool():
    return make_tool

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tool_schema_lint.cli import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, main
from tool_schema_lint.loader import load_python

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_good_example_passes(capsys):
    assert main([str(EXAMPLES / "good_tools.json"), "--fail-on", "info"]) == EXIT_OK
    assert "skipped server tools" in capsys.readouterr().out


def test_bad_example_fails(capsys):
    assert main([str(EXAMPLES / "bad_tools.json")]) == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "TS101 error" in out
    assert "TS401 warning" in out


def test_json_output_is_stable_for_ci(capsys):
    assert main([str(EXAMPLES / "bad_tools.json"), "--format", "json"]) == EXIT_FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == 1
    assert payload["tools"] == 3
    first = payload["findings"][0]
    assert set(first) == {
        "rule", "severity", "title", "path", "tool", "pointer", "line", "message", "fixable",
        "source",
    }  # fmt: skip


def test_fail_on_levels(tmp_path, tool):
    path = tmp_path / "tools.json"
    path.write_text(json.dumps([tool(description="Returns data. It is fast. It is cached.")]))
    assert main([str(path)]) == EXIT_OK
    assert main([str(path), "--fail-on", "info"]) == EXIT_FINDINGS
    assert main([str(path), "--fail-on", "never"]) == EXIT_OK


def test_select_and_ignore(capsys):
    path = str(EXAMPLES / "bad_tools.json")
    main([path, "--select", "TS302", "--format", "json"])
    assert {f["rule"] for f in json.loads(capsys.readouterr().out)["findings"]} == {"TS302"}
    main([path, "--ignore", "TS302", "--format", "json"])
    assert "TS302" not in {f["rule"] for f in json.loads(capsys.readouterr().out)["findings"]}


def test_unknown_rule_is_a_usage_error(capsys):
    assert main([str(EXAMPLES / "bad_tools.json"), "--ignore", "TS999"]) == EXIT_USAGE
    assert "TS999" in capsys.readouterr().err


def test_bad_input_is_a_usage_error(tmp_path, capsys):
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    assert main([str(path)]) == EXIT_USAGE
    assert "invalid JSON" in capsys.readouterr().err


def test_fix_applies_only_mechanical_changes(tmp_path, capsys):
    path = tmp_path / "bad.json"
    shutil.copy(EXAMPLES / "bad_tools.json", path)
    main([str(path), "--fix"])
    assert "applied 5 fixes" in capsys.readouterr().out
    tools = json.loads(path.read_text())["tools"]

    lookup = tools[0]["input_schema"]
    assert lookup["additionalProperties"] is False
    assert lookup["properties"]["address"]["additionalProperties"] is False
    assert lookup["required"] == ["data", "email"]  # deduplicated; the bad name is left for a human
    assert lookup["properties"]["metadata"]["additionalProperties"] is True  # not flipped
    assert tools[1]["input_schema"]["type"] == "object"
    assert tools[2]["input_schema"]["properties"]["color"]["enum"] == ["red", "green", 7]
    # Prose is never touched, and non-strict tools get no additionalProperties.
    assert tools[0]["description"] == "Gets customer."
    assert "additionalProperties" not in tools[2]["input_schema"]


def test_fix_is_idempotent(tmp_path, capsys):
    path = tmp_path / "bad.json"
    shutil.copy(EXAMPLES / "bad_tools.json", path)
    main([str(path), "--fix"])
    once = path.read_text()
    capsys.readouterr()
    main([str(path), "--fix"])
    assert path.read_text() == once
    assert "applied" not in capsys.readouterr().out


def test_fix_does_not_rewrite_python(tmp_path, capsys):
    path = tmp_path / "tools.py"
    shutil.copy(EXAMPLES / "tools_in_python.py", path)
    before = path.read_text()
    main([str(path), "--fix"])
    assert path.read_text() == before
    assert "does not rewrite Python" in capsys.readouterr().out


def test_python_is_read_not_executed(tmp_path):
    marker = tmp_path / "ran"
    path = tmp_path / "tools.py"
    path.write_text(
        f"open({str(marker)!r}, 'w').close()\n"
        "PREFIX = 'Returns'\n"
        "TOOLS = [{'name': 'get_x', 'description': PREFIX + ' x.',\n"
        "          'input_schema': {'type': 'object', 'properties': {}}}]\n"
    )
    loaded = load_python(path)
    assert not marker.exists()
    assert loaded.tools[0].description == "Returns x."
    assert loaded.tools[0].line == 3


def test_python_non_literal_tool_is_reported_not_guessed(tmp_path):
    path = tmp_path / "tools.py"
    path.write_text(
        "def build(): ...\n"
        "TOOLS = [{'name': 'get_x', 'description': build(), 'input_schema': {}}]\n"
    )
    loaded = load_python(path)
    assert loaded.tools == []
    assert "not a static literal" in loaded.notes[0]


def test_python_finds_tools_inline_in_a_call(tmp_path):
    path = tmp_path / "app.py"
    path.write_text(
        "client.messages.create(tools=[{'name': 'get_x', 'input_schema': {'type': 'object'}}])\n"
    )
    assert [t.name for t in load_python(path).tools] == ["get_x"]


def test_python_unrelated_function_key_is_not_a_tool(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("ROUTES = {'function': 'home', 'name': 'x'}\n")
    assert load_python(path).tools == []


@pytest.mark.parametrize("args", [["--list-rules"]])
def test_list_rules_marks_opinions(args, capsys):
    assert main(args) == EXIT_OK
    out = capsys.readouterr().out
    assert "[opinion]" in out
    assert "TS101" in out

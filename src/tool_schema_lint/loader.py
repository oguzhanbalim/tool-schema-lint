"""Load tool definitions from JSON files and, without executing them, from Python files."""

from __future__ import annotations

import ast
import contextlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import Tool


class LoadError(Exception):
    """The file could not be read as tool definitions."""


@dataclass
class LoadedFile:
    path: Path
    kind: str  # "json" or "python"
    document: Any = None  # parsed JSON, mutated in place by fixes
    tools: list[Tool] = field(default_factory=list)
    skipped_server_tools: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _is_tool_shape(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    if isinstance(obj.get("function"), dict):
        return "name" in obj["function"]
    return "name" in obj and ("input_schema" in obj or "parameters" in obj or "description" in obj)


def _is_server_tool(obj: dict[str, Any]) -> bool:
    """Date-versioned entries such as `web_search_20260209` carry no user schema."""
    kind = obj.get("type")
    return isinstance(kind, str) and kind not in ("custom", "function")


def _add(loaded: LoadedFile, obj: dict[str, Any], pointer: str, line: int | None = None) -> None:
    if _is_server_tool(obj):
        loaded.skipped_server_tools.append(str(obj.get("name") or obj.get("type")))
        return
    if isinstance(obj.get("function"), dict):  # {"type": "function", "function": {...}}
        obj = obj["function"]
        pointer += "/function"
    schema_key = (
        "parameters" if "parameters" in obj and "input_schema" not in obj else "input_schema"
    )
    loaded.tools.append(Tool(raw=obj, pointer=pointer, line=line, schema_key=schema_key))


def load_json(path: Path) -> LoadedFile:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise LoadError(f"{path}: cannot read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LoadError(f"{path}: invalid JSON: {exc}") from exc

    loaded = LoadedFile(path=path, kind="json", document=document)
    if isinstance(document, list):
        entries, base = document, ""
    elif isinstance(document, dict) and isinstance(document.get("tools"), list):
        entries, base = document["tools"], "/tools"
    elif _is_tool_shape(document):
        _add(loaded, document, "")
        return loaded
    else:
        raise LoadError(f"{path}: expected a tool, a list of tools, or an object with `tools`")

    for index, entry in enumerate(entries):
        if isinstance(entry, dict):
            _add(loaded, entry, f"{base}/{index}")
        else:
            loaded.notes.append(f"{base}/{index}: entry is not an object; skipped")
    return loaded


class _NotStatic(Exception):
    pass


def _static_eval(node: ast.AST, env: dict[str, Any]) -> Any:
    """Evaluate literals, known module-level names and `+` on them. Nothing else runs."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List | ast.Tuple):
        return [_static_eval(item, env) for item in node.elts]
    if isinstance(node, ast.Dict):
        result: dict[Any, Any] = {}
        for key, value in zip(node.keys, node.values, strict=True):
            if key is None:  # {**spread}
                spread = _static_eval(value, env)
                if not isinstance(spread, dict):
                    raise _NotStatic
                result.update(spread)
            else:
                result[_static_eval(key, env)] = _static_eval(value, env)
        return result
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        try:
            return _static_eval(node.left, env) + _static_eval(node.right, env)
        except TypeError as exc:
            raise _NotStatic from exc
    raise _NotStatic


def _looks_like_tool_literal(node: ast.Dict) -> bool:
    keys = {key.value for key in node.keys if isinstance(key, ast.Constant)}
    return "function" in keys or (
        "name" in keys and ("input_schema" in keys or "parameters" in keys)
    )


def load_python(path: Path) -> LoadedFile:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError) as exc:
        raise LoadError(f"{path}: cannot read: {exc}") from exc
    except SyntaxError as exc:
        raise LoadError(f"{path}: invalid Python: {exc}") from exc

    loaded = LoadedFile(path=path, kind="python")
    env: dict[str, Any] = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target, value = statement.targets[0], statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            target, value = statement.target, statement.value
        else:
            continue
        if isinstance(target, ast.Name):
            with contextlib.suppress(_NotStatic):
                env[target.id] = _static_eval(value, env)

    inner: set[int] = set()  # dicts nested in a tool already claimed
    for node in ast.walk(tree):  # breadth-first: outer dicts are seen before inner ones
        if (
            not isinstance(node, ast.Dict)
            or id(node) in inner
            or not _looks_like_tool_literal(node)
        ):
            continue
        inner.update(id(child) for child in ast.walk(node) if child is not node)
        try:
            value = _static_eval(node, env)
        except _NotStatic:
            loaded.notes.append(f"line {node.lineno}: tool is not a static literal; skipped")
            continue
        if not _is_tool_shape(value):
            continue
        _add(loaded, value, f"line:{node.lineno}", line=node.lineno)
    loaded.tools.sort(key=lambda tool: tool.line or 0)
    return loaded


def load(path: Path) -> LoadedFile:
    if path.suffix == ".py":
        return load_python(path)
    return load_json(path)

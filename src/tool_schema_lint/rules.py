"""The rules. Each `check_*` appends findings for one concern."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from .model import (
    DOCS_DEFINE,
    DOCS_LIMITS,
    LOCAL_AUDIT,
    LOCAL_CONCEPTS,
    OPINION,
    Finding,
    Options,
    Rule,
    Tool,
)

_RULES = [
    # Structure: applies to every user-defined tool.
    Rule("TS001", "error", "tool name missing or invalid", DOCS_DEFINE),
    Rule("TS002", "error", "input schema missing or not an object schema", LOCAL_CONCEPTS),
    Rule("TS003", "error", "duplicate tool name", DOCS_DEFINE),
    Rule("TS004", "error", "`required` malformed or names an undeclared property", LOCAL_CONCEPTS),
    Rule("TS005", "warning", "duplicate entries in `required`", OPINION),
    # Strict mode: applies when `strict: true`, or to every tool with --assume-strict.
    Rule("TS101", "error", "strict: object without `additionalProperties: false`", LOCAL_CONCEPTS),
    Rule("TS102", "error", "strict: `additionalProperties` set to something else", LOCAL_CONCEPTS),
    Rule("TS103", "error", "strict: unsupported constraint keyword", LOCAL_CONCEPTS),
    Rule("TS104", "error", "strict: recursive schema", LOCAL_CONCEPTS),
    Rule("TS105", "error", "strict: external `$ref`", DOCS_LIMITS),
    Rule("TS106", "warning", "strict: string format outside the supported list", LOCAL_CONCEPTS),
    Rule("TS107", "warning", "strict: regex feature that is not supported", DOCS_LIMITS),
    Rule("TS108", "warning", "strict: per-request complexity limit exceeded", DOCS_LIMITS),
    Rule("TS109", "error", "strict: enum with complex values", DOCS_LIMITS),
    Rule("TS110", "error", "strict: `allOf` combined with `$ref`", DOCS_LIMITS),
    # Descriptions.
    Rule("TS201", "error", "tool has no description", LOCAL_CONCEPTS),
    Rule("TS202", "warning", "tool description under 3 sentences", DOCS_DEFINE),
    Rule("TS203", "warning", "tool description is vague", OPINION),
    Rule("TS204", "info", "tool description does not say when to call it", LOCAL_CONCEPTS),
    Rule("TS205", "warning", "parameter has no description", LOCAL_CONCEPTS),
    Rule("TS206", "info", "description steers with shouting", LOCAL_AUDIT),
    Rule("TS207", "warning", "parameter description restates its name", OPINION),
    # Names.
    Rule("TS301", "warning", "ambiguous parameter name", OPINION),
    Rule("TS302", "warning", "vague tool name", LOCAL_CONCEPTS),
    # Overlap.
    Rule("TS401", "warning", "two tools overlap", LOCAL_AUDIT),
    # Enums.
    Rule("TS501", "warning", "oversized enum", OPINION),
    Rule("TS502", "warning", "duplicate enum values", OPINION),
    Rule("TS503", "error", "enum value does not match the declared type", OPINION),
    Rule("TS504", "warning", "description lists choices but there is no enum", LOCAL_CONCEPTS),
    Rule("TS505", "info", "parameter name suggests a fixed set of values", OPINION),
    # Tool set.
    Rule("TS601", "info", "more than 30 always-loaded tools", LOCAL_AUDIT),
]
RULES: dict[str, Rule] = {rule.id: rule for rule in _RULES}

NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
UNSUPPORTED_KEYWORDS = (
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "maxItems",
    "uniqueItems",
)
SUPPORTED_FORMATS = {
    "date-time",
    "time",
    "date",
    "duration",
    "email",
    "hostname",
    "uri",
    "ipv4",
    "ipv6",
    "uuid",
}
UNSUPPORTED_REGEX = (
    (re.compile(r"\\[1-9]"), "backreference"),
    (re.compile(r"\(\?<?[=!]"), "lookaround"),
    (re.compile(r"\\[bB]"), "word boundary"),
)
MAX_STRICT_TOOLS = 20
MAX_OPTIONAL_PARAMS = 24
MAX_UNION_PARAMS = 16
MAX_ALWAYS_LOADED_TOOLS = 30

VAGUE_TOOL_NAMES = {
    "action", "call", "data", "do", "do_it", "do_stuff", "execute", "get", "handle", "helper",
    "invoke", "main", "misc", "process", "run", "test", "tool", "update", "util", "utils",
}  # fmt: skip
AMBIGUOUS_PARAM_NAMES = {
    "arg", "args", "data", "foo", "info", "input", "item", "misc", "obj", "object", "opts",
    "options", "param", "params", "payload", "stuff", "temp", "thing", "tmp", "val", "value", "x",
}  # fmt: skip
ENUM_LIKE_NAMES = {
    "direction", "level", "mode", "order", "priority", "severity", "sort_order", "state",
    "status", "unit", "units",
}  # fmt: skip
VAGUE_PHRASES = re.compile(
    r"\b(does stuff|does things|helper (function|tool)|utility (function|tool)|"
    r"handles? (things|stuff|data|requests)|various|miscellaneous|general purpose|"
    r"general-purpose|todo|tbd)\b",
    re.IGNORECASE,
)
WHEN_TO_USE = re.compile(
    r"\b(use (this|it)?\s*(tool\s*)?(when|to|for|if)|call (this|it)?\s*(tool\s*)?(when|to|for|if)|"
    r"when the user|if the user|should be used|do not use|don't use|use only)\b",
    re.IGNORECASE,
)
SHOUTING = re.compile(r"\b(CRITICAL|IMPORTANT|YOU MUST|MUST ALWAYS|ALWAYS USE|NEVER USE)\b")
CHOICE_PATTERNS = (
    re.compile(r"\b(one of|possible values?|valid values?|allowed values?|options are)\b", re.I),
    re.compile(r"\beither\s+['\"`]?[\w-]+['\"`]?\s+or\s+['\"`]?[\w-]+", re.I),
    re.compile(r"['\"`][\w-]+['\"`]\s*(,\s*['\"`][\w-]+['\"`]\s*,?\s*)*(or|and)\s*['\"`][\w-]+"),
    re.compile(r"\b\w+\|\w+(\|\w+)*\b"),
)
SENTENCE_END = re.compile(r"[.!?](\s|$)")
ABBREVIATION = re.compile(r"\b(e\.g\.|i\.e\.|etc\.|vs\.)", re.IGNORECASE)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "given", "has", "if", "in",
    "is", "it", "its", "of", "on", "or", "that", "the", "this", "to", "tool", "use", "used",
    "when", "with", "you", "your",
}  # fmt: skip
# Verbs that read as the same action to a model choosing between tools.
SYNONYMS = {
    "fetch": "get", "retrieve": "get", "lookup": "get", "read": "get", "load": "get",
    "find": "search", "query": "search", "locate": "search",
    "add": "create", "insert": "create", "new": "create", "make": "create",
    "remove": "delete", "destroy": "delete", "drop": "delete",
    "edit": "update", "modify": "update", "change": "update", "patch": "update",
    "post": "send", "dispatch": "send",
}  # fmt: skip
PY_TYPE = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


@dataclass
class Node:
    """One sub-schema, with where it sits and which property it describes (if any)."""

    schema: dict[str, Any]
    pointer: str
    param: str | None = None


def walk(schema: Any, pointer: str, param: str | None = None) -> Iterator[Node]:
    if not isinstance(schema, dict):
        return
    yield Node(schema, pointer, param)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, sub in properties.items():
            yield from walk(sub, f"{pointer}/properties/{name}", name)
    for key in ("$defs", "$def", "definitions"):
        defs = schema.get(key)
        if isinstance(defs, dict):
            for name, sub in defs.items():
                yield from walk(sub, f"{pointer}/{key}/{name}")
    for key in ("anyOf", "allOf", "oneOf", "prefixItems"):
        branches = schema.get(key)
        if isinstance(branches, list):
            for index, sub in enumerate(branches):
                yield from walk(sub, f"{pointer}/{key}/{index}", param)
    for key in ("items", "additionalProperties", "not"):
        yield from walk(schema.get(key), f"{pointer}/{key}", param)


class Linter:
    def __init__(self, path: str, tools: list[Tool], options: Options) -> None:
        self.path = path
        self.tools = tools
        self.options = options
        self.findings: list[Finding] = []

    def report(self, rule_id: str, tool: Tool, pointer: str, message: str, fix=None) -> None:
        self.findings.append(
            Finding(
                rule=RULES[rule_id],
                path=self.path,
                tool=tool.name or "<unnamed>",
                pointer=pointer,
                message=message,
                line=tool.line,
                fix=fix,
            )
        )

    def run(self) -> list[Finding]:
        for tool in self.tools:
            schema_pointer = f"{tool.pointer}/{tool.schema_key}"
            self.check_structure(tool, schema_pointer)
            nodes = list(walk(tool.schema, schema_pointer))
            self.check_required(tool, nodes)
            if tool.strict or self.options.assume_strict:
                self.check_strict(tool, nodes)
            self.check_tool_description(tool)
            self.check_parameters(tool, nodes)
            self.check_enums(tool, nodes)
        self.check_tool_set()
        self.check_overlap()
        return self.findings

    def check_structure(self, tool: Tool, schema_pointer: str) -> None:
        if not tool.name:
            self.report("TS001", tool, tool.pointer, "tool has no `name`")
        elif not NAME_RE.fullmatch(tool.name):
            self.report(
                "TS001", tool, f"{tool.pointer}/name",
                f"name {tool.name!r} does not match ^[a-zA-Z0-9_-]{{1,128}}$",
            )  # fmt: skip
        schema = tool.schema
        if not isinstance(schema, dict):
            self.report("TS002", tool, schema_pointer, f"`{tool.schema_key}` is missing")
        elif "type" not in schema:
            fix = None
            if "properties" in schema:

                def fix() -> None:
                    schema["type"] = "object"

            self.report("TS002", tool, schema_pointer, "root schema has no `type`", fix)
        elif schema["type"] != "object":
            self.report(
                "TS002", tool, f"{schema_pointer}/type",
                f"root schema type is {schema['type']!r}, expected 'object'",
            )  # fmt: skip
        if tool.name and VAGUE_TOOL_NAMES.intersection({tool.name.lower()}):
            self.report(
                "TS302", tool, f"{tool.pointer}/name",
                f"{tool.name!r} does not say what the tool acts on",
            )  # fmt: skip

    def check_required(self, tool: Tool, nodes: list[Node]) -> None:
        for node in nodes:
            required = node.schema.get("required")
            if required is None:
                continue
            pointer = f"{node.pointer}/required"
            if not isinstance(required, list) or not all(isinstance(r, str) for r in required):
                self.report("TS004", tool, pointer, "`required` must be a list of strings")
                continue
            properties = node.schema.get("properties")
            declared = set(properties) if isinstance(properties, dict) else set()
            for name in required:
                if name not in declared:
                    self.report(
                        "TS004", tool, pointer,
                        f"`required` names {name!r}, which is not in `properties`",
                    )  # fmt: skip
            duplicates = sorted(k for k, n in Counter(required).items() if n > 1)
            if duplicates:

                def fix(schema: dict[str, Any] = node.schema) -> None:
                    schema["required"] = list(dict.fromkeys(schema["required"]))

                self.report(
                    "TS005", tool, pointer, f"listed more than once: {', '.join(duplicates)}", fix
                )

    def check_strict(self, tool: Tool, nodes: list[Node]) -> None:
        for node in nodes:
            schema = node.schema
            if self._is_object(schema):
                self._check_additional_properties(tool, node)
            for keyword in UNSUPPORTED_KEYWORDS:
                if keyword in schema:
                    self.report(
                        "TS103", tool, f"{node.pointer}/{keyword}",
                        f"`{keyword}` is not supported; an SDK helper may strip it, a raw "
                        "request gets a 400",
                    )  # fmt: skip
            min_items = schema.get("minItems")
            if isinstance(min_items, int) and min_items not in (0, 1):
                self.report(
                    "TS103", tool, f"{node.pointer}/minItems",
                    f"`minItems` is {min_items}; only 0 and 1 are supported",
                )  # fmt: skip
            fmt = schema.get("format")
            if isinstance(fmt, str) and fmt not in SUPPORTED_FORMATS:
                self.report(
                    "TS106", tool, f"{node.pointer}/format",
                    f"format {fmt!r} is not in the supported list",
                )  # fmt: skip
            pattern = schema.get("pattern")
            if isinstance(pattern, str):
                for regex, label in UNSUPPORTED_REGEX:
                    if regex.search(pattern):
                        self.report(
                            "TS107", tool, f"{node.pointer}/pattern",
                            f"pattern uses a {label}: {pattern!r}",
                        )  # fmt: skip
            enum = schema.get("enum")
            if isinstance(enum, list) and any(isinstance(v, dict | list) for v in enum):
                self.report(
                    "TS109", tool, f"{node.pointer}/enum",
                    "enum values must be strings, numbers, booleans or nulls",
                )  # fmt: skip
            ref = schema.get("$ref")
            if isinstance(ref, str) and not ref.startswith("#"):
                self.report("TS105", tool, f"{node.pointer}/$ref", f"external $ref: {ref}")
            if isinstance(schema.get("allOf"), list) and any(
                isinstance(branch, dict) and "$ref" in branch for branch in schema["allOf"]
            ):
                self.report("TS110", tool, f"{node.pointer}/allOf", "`allOf` with `$ref`")
        if isinstance(tool.schema, dict):
            for ref in self._recursive_refs(tool.schema):
                self.report(
                    "TS104", tool, f"{tool.pointer}/{tool.schema_key}", f"{ref} refers to itself"
                )

    def _check_additional_properties(self, tool: Tool, node: Node) -> None:
        schema = node.schema
        if "additionalProperties" not in schema:

            def fix() -> None:
                schema["additionalProperties"] = False

            self.report(
                "TS101", tool, node.pointer, "object has no `additionalProperties: false`", fix
            )
        elif schema["additionalProperties"] is not False:
            # Not fixable: flipping this changes what the tool accepts.
            self.report(
                "TS102", tool, f"{node.pointer}/additionalProperties",
                f"must be false, found {json.dumps(schema['additionalProperties'])}",
            )  # fmt: skip

    @staticmethod
    def _is_object(schema: dict[str, Any]) -> bool:
        kind = schema.get("type")
        if kind == "object" or (isinstance(kind, list) and "object" in kind):
            return True
        return kind is None and "properties" in schema

    @staticmethod
    def _recursive_refs(root: dict[str, Any]) -> list[str]:
        """Local `$ref` targets from which the same target can be reached again."""

        def refs_in(value: Any) -> Iterator[str]:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "$ref" and isinstance(item, str):
                        yield item
                    else:
                        yield from refs_in(item)
            elif isinstance(value, list):
                for item in value:
                    yield from refs_in(item)

        def resolve(ref: str) -> Any:
            if ref == "#":
                return root
            current: Any = root
            for part in ref.removeprefix("#/").split("/"):
                if not isinstance(current, dict) or part not in current:
                    return None
                current = current[part]
            return current

        recursive = []
        for start in sorted({r for r in refs_in(root) if r.startswith("#")}):
            seen: set[str] = set()
            stack = list(refs_in(resolve(start)))
            while stack:
                ref = stack.pop()
                if ref == start:
                    recursive.append(start)
                    break
                if ref not in seen and ref.startswith("#"):
                    seen.add(ref)
                    stack.extend(refs_in(resolve(ref)))
        return recursive

    def check_tool_description(self, tool: Tool) -> None:
        pointer = f"{tool.pointer}/description"
        description = (tool.description or "").strip()
        if not description:
            self.report("TS201", tool, pointer, "tool has no description")
            return
        sentences = len(SENTENCE_END.findall(ABBREVIATION.sub("", description)))
        if not re.search(r"[.!?]\s*$", description):
            sentences += 1
        if sentences < 3:
            self.report(
                "TS202", tool, pointer,
                f"{sentences} sentence(s); the docs ask for at least 3-4 covering what, when, "
                "and caveats",
            )  # fmt: skip
        words = tokens(description)
        if VAGUE_PHRASES.search(description) or (words and words <= tokens(tool.name)):
            self.report("TS203", tool, pointer, f"vague: {description[:60]!r}")
        if not WHEN_TO_USE.search(description):
            self.report("TS204", tool, pointer, "add when to call it, and when not to")
        if SHOUTING.search(description):
            self.report("TS206", tool, pointer, "use plain 'Use this tool when ...' instead")

    def check_parameters(self, tool: Tool, nodes: list[Node]) -> None:
        for node in nodes:
            # Only the property itself, not its anyOf branches or array items.
            if not node.param or not node.pointer.endswith(f"/properties/{node.param}"):
                continue
            description = node.schema.get("description")
            if not isinstance(description, str) or not description.strip():
                self.report("TS205", tool, node.pointer, f"{node.param!r} has no description")
            else:
                words = tokens(description)
                if words and words <= tokens(node.param) | {"value", "parameter"}:
                    self.report(
                        "TS207", tool, f"{node.pointer}/description",
                        f"{description!r} adds nothing to the name {node.param!r}",
                    )  # fmt: skip
            if node.param.lower() in AMBIGUOUS_PARAM_NAMES:
                self.report(
                    "TS301", tool, node.pointer,
                    f"{node.param!r} does not say what the value is",
                )  # fmt: skip

    def check_enums(self, tool: Tool, nodes: list[Node]) -> None:
        for node in nodes:
            schema = node.schema
            enum = schema.get("enum")
            kind = schema.get("type")
            if isinstance(enum, list):
                self._check_enum_values(tool, node, enum, kind)
            elif kind == "string" and "const" not in schema and node.param:
                description = schema.get("description")
                if isinstance(description, str) and any(
                    pattern.search(description) for pattern in CHOICE_PATTERNS
                ):
                    self.report(
                        "TS504", tool, node.pointer,
                        f"{node.param!r} is described as a fixed choice: {description[:70]!r}",
                    )  # fmt: skip
                elif node.param.lower() in ENUM_LIKE_NAMES:
                    self.report(
                        "TS505", tool, node.pointer, f"{node.param!r} is a free-form string"
                    )

    def _check_enum_values(self, tool: Tool, node: Node, enum: list[Any], kind: Any) -> None:
        pointer = f"{node.pointer}/enum"
        if len(enum) > self.options.max_enum:
            self.report(
                "TS501", tool, pointer,
                f"{len(enum)} values (limit {self.options.max_enum}); these are sent on every "
                "request. Consider a search parameter or a lookup tool",
            )  # fmt: skip
        unique = list(dict.fromkeys(v for v in enum if not isinstance(v, dict | list)))
        if len(unique) < sum(not isinstance(v, dict | list) for v in enum):

            def fix(schema: dict[str, Any] = node.schema) -> None:
                schema["enum"] = list(dict.fromkeys(schema["enum"]))

            self.report("TS502", tool, pointer, "enum repeats a value", fix)
        expected = PY_TYPE.get(kind) if isinstance(kind, str) else None
        if expected is None:
            return
        for value in enum:
            mismatch = not isinstance(value, expected) or (
                kind in ("integer", "number") and isinstance(value, bool)
            )
            if mismatch:
                self.report("TS503", tool, pointer, f"{value!r} is not of declared type {kind!r}")

    def check_tool_set(self) -> None:
        strict = [t for t in self.tools if t.strict or self.options.assume_strict]
        if self.tools and len(self.tools) > MAX_ALWAYS_LOADED_TOOLS:
            self.report(
                "TS601", self.tools[0], "",
                f"{len(self.tools)} tools; past a few dozen, use tool search or deferred loading",
            )  # fmt: skip
        names = Counter(t.name for t in self.tools if t.name)
        for tool in self.tools:
            if names.get(tool.name, 0) > 1:
                self.report("TS003", tool, f"{tool.pointer}/name", f"{tool.name!r} is repeated")
        if not strict:
            return
        optional = unions = 0
        for tool in strict:
            for node in walk(tool.schema, ""):
                properties = node.schema.get("properties")
                if isinstance(properties, dict):
                    required = node.schema.get("required")
                    listed = set(required) if isinstance(required, list) else set()
                    optional += sum(name not in listed for name in properties)
                if node.param and (
                    "anyOf" in node.schema or isinstance(node.schema.get("type"), list)
                ):
                    unions += 1
        for count, limit, label in (
            (len(strict), MAX_STRICT_TOOLS, "strict tools"),
            (optional, MAX_OPTIONAL_PARAMS, "optional parameters across strict tools"),
            (unions, MAX_UNION_PARAMS, "union-typed parameters across strict tools"),
        ):
            if count > limit:
                self.report(
                    "TS108", strict[0], "",
                    f"{count} {label}; the limit is {limit} per request (assumes this file is "
                    "one request's tool list)",
                )  # fmt: skip

    def check_overlap(self) -> None:
        for left, right in combinations(self.tools, 2):
            if not (left.name and right.name) or left.name == right.name:
                continue
            score, shared = similarity(left, right)
            if score >= self.options.overlap_threshold:
                self.report(
                    "TS401", right, right.pointer,
                    f"overlaps {left.name!r} (score {score:.2f}, shared: "
                    f"{', '.join(sorted(shared)[:6])}); merge them or state the boundary in both",
                )  # fmt: skip


def tokens(text: str) -> set[str]:
    """Lowercase word stems with stopwords removed and action synonyms folded."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    out = set()
    for word in re.findall(r"[a-z0-9]+", spaced.lower()):
        if word in STOPWORDS:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        out.add(SYNONYMS.get(word, word))
    return out


def _params(tool: Tool) -> set[str]:
    schema = tool.schema
    properties = schema.get("properties") if isinstance(schema, dict) else None
    return tokens(" ".join(properties)) if isinstance(properties, dict) else set()


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def similarity(left: Tool, right: Tool) -> tuple[float, set[str]]:
    """Weighted overlap of names, descriptions and parameter names. A heuristic, not semantics."""
    names = tokens(left.name), tokens(right.name)
    descriptions = tokens(left.description or ""), tokens(right.description or "")
    params = _params(left), _params(right)
    score = 0.5 * _jaccard(*names) + 0.3 * _jaccard(*descriptions) + 0.2 * _jaccard(*params)
    shared = (names[0] & names[1]) | (descriptions[0] & descriptions[1]) | (params[0] & params[1])
    return score, shared

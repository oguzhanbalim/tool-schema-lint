"""Core data types: tools, rules and findings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

SEVERITIES = ("info", "warning", "error")

# Where a rule comes from. Every rule names one of these so that a reader can
# tell an API fact from a style opinion.
LOCAL_CONCEPTS = "claude-api skill: shared/tool-use-concepts.md"
LOCAL_AUDIT = "claude-api skill: shared/prompt-audit.md, Group 3"
DOCS_DEFINE = "docs: agents-and-tools/tool-use/define-tools (read 2026-10-30)"
DOCS_LIMITS = "docs: build-with-claude/structured-outputs#json-schema-limitations (read 2026-10-30)"
OPINION = "opinion"


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str
    title: str
    source: str


@dataclass
class Tool:
    """A user-defined tool, normalised across the shapes the loader accepts."""

    raw: dict[str, Any]  # the object holding name/description/schema; mutated by fixes
    pointer: str  # JSON pointer to `raw` within the file
    line: int | None = None  # source line, for Python inputs
    schema_key: str = "input_schema"

    @property
    def name(self) -> str:
        value = self.raw.get("name")
        return value if isinstance(value, str) else ""

    @property
    def description(self) -> str | None:
        value = self.raw.get("description")
        return value if isinstance(value, str) else None

    @property
    def schema(self) -> Any:
        return self.raw.get(self.schema_key)

    @property
    def strict(self) -> bool:
        return self.raw.get("strict") is True


@dataclass
class Finding:
    rule: Rule
    path: str
    tool: str
    pointer: str
    message: str
    line: int | None = None
    fix: Callable[[], None] | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule.id,
            "severity": self.rule.severity,
            "title": self.rule.title,
            "path": self.path,
            "tool": self.tool,
            "pointer": self.pointer,
            "line": self.line,
            "message": self.message,
            "fixable": self.fix is not None,
            "source": self.rule.source,
        }


@dataclass
class Options:
    assume_strict: bool = False
    max_enum: int = 50
    overlap_threshold: float = 0.55

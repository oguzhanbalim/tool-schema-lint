"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .loader import LoadedFile, LoadError, load
from .model import SEVERITIES, Finding, Options
from .rules import RULES, Linter

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tool-schema-lint",
        description="Lint LLM tool definitions in JSON files or Python dict literals.",
    )
    parser.add_argument("paths", nargs="*", type=Path, help="JSON or .py files")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--fix", action="store_true", help="apply safe mechanical fixes (JSON only)"
    )
    parser.add_argument(
        "--assume-strict", action="store_true", help="check every tool as if `strict: true`"
    )
    parser.add_argument("--select", default="", help="comma-separated rule IDs to run")
    parser.add_argument("--ignore", default="", help="comma-separated rule IDs to skip")
    parser.add_argument(
        "--fail-on",
        choices=(*SEVERITIES, "never"),
        default="error",
        help="lowest severity that makes the exit code 1 (default: error)",
    )
    parser.add_argument("--max-enum", type=int, default=50, help="TS501 limit (default: 50)")
    parser.add_argument(
        "--overlap-threshold", type=float, default=0.55, help="TS401 score (default: 0.55)"
    )
    parser.add_argument("--list-rules", action="store_true", help="print the rules and exit")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def _ids(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def lint_file(loaded: LoadedFile, options: Options) -> list[Finding]:
    return Linter(str(loaded.path), loaded.tools, options).run()


def _filter(findings: list[Finding], select: set[str], ignore: set[str]) -> list[Finding]:
    return [f for f in findings if (not select or f.rule.id in select) and f.rule.id not in ignore]


def write_fixed(loaded: LoadedFile) -> None:
    text = loaded.path.read_text(encoding="utf-8")
    match = re.search(r"^[\[{]\s*\n([ \t]+)\S", text)
    indent = match.group(1) if match else 2
    loaded.path.write_text(
        json.dumps(loaded.document, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def print_rules() -> None:
    for rule in RULES.values():
        print(f"{rule.id}  {rule.severity:<7}  {rule.title}  [{rule.source}]")


def print_text(findings: list[Finding], loaded_files: list[LoadedFile], fixed: int) -> None:
    for finding in findings:
        location = f"{finding.path}:{finding.line}" if finding.line else finding.path
        mark = " [fixable]" if finding.fix else ""
        print(
            f"{location}: {finding.rule.id} {finding.rule.severity}: "
            f"{finding.tool}: {finding.message}{mark}"
        )
        print(f"    at {finding.pointer or '/'}")
    for loaded in loaded_files:
        for note in loaded.notes:
            print(f"{loaded.path}: note: {note}")
        if loaded.skipped_server_tools:
            names = ", ".join(loaded.skipped_server_tools)
            print(f"{loaded.path}: note: skipped server tools with built-in schemas: {names}")
    counts = Counter(f.rule.severity for f in findings)
    tools = sum(len(loaded.tools) for loaded in loaded_files)
    summary = ", ".join(f"{counts[s]} {s}" for s in reversed(SEVERITIES))
    fixable = sum(f.fix is not None for f in findings)
    print(f"{tools} tools in {len(loaded_files)} files: {summary}, {fixable} fixable")
    if fixed:
        print(f"applied {fixed} fixes")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_rules:
        print_rules()
        return EXIT_OK
    if not args.paths:
        parser.print_usage(sys.stderr)
        return EXIT_USAGE
    select, ignore = _ids(args.select), _ids(args.ignore)
    unknown = (select | ignore) - set(RULES)
    if unknown:
        print(f"unknown rule IDs: {', '.join(sorted(unknown))}", file=sys.stderr)
        return EXIT_USAGE

    options = Options(
        assume_strict=args.assume_strict,
        max_enum=args.max_enum,
        overlap_threshold=args.overlap_threshold,
    )
    loaded_files: list[LoadedFile] = []
    findings: list[Finding] = []
    fixed = 0
    for path in args.paths:
        try:
            loaded = load(path)
        except LoadError as exc:
            print(exc, file=sys.stderr)
            return EXIT_USAGE
        file_findings = _filter(lint_file(loaded, options), select, ignore)
        if args.fix:
            fixes = [f.fix for f in file_findings if f.fix]
            if fixes and loaded.kind == "json":
                for fix in fixes:
                    fix()
                fixed += len(fixes)
                write_fixed(loaded)
                file_findings = _filter(lint_file(loaded, options), select, ignore)
            elif fixes:
                loaded.notes.append(
                    f"--fix does not rewrite Python; {len(fixes)} fixes not applied"
                )
        loaded_files.append(loaded)
        findings.extend(file_findings)

    if args.format == "json":
        payload = {
            "version": 1,
            "tools": sum(len(loaded.tools) for loaded in loaded_files),
            "fixed": fixed,
            "summary": dict(Counter(f.rule.severity for f in findings)),
            "findings": [f.to_dict() for f in findings],
            "notes": [f"{loaded.path}: {note}" for loaded in loaded_files for note in loaded.notes],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_text(findings, loaded_files, fixed)

    if args.fail_on == "never":
        return EXIT_OK
    threshold = SEVERITIES.index(args.fail_on)
    failed = any(SEVERITIES.index(f.rule.severity) >= threshold for f in findings)
    return EXIT_FINDINGS if failed else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

# tool-schema-lint

Your tool definitions are prompts with a schema attached. Lint them like code.

A tool with a one-line description, a `data` parameter and `strict: true` on a schema the API will reject is easy to ship and awkward to debug, because the failure shows up as a 400 or as a model picking the wrong tool. This reads tool definitions from JSON or Python dict literals and reports those problems with rule IDs, without calling a model.

No dependencies, no API key, no network. Not affiliated with Anthropic.

## Quickstart

```sh
pip install -e .
tool-schema-lint examples/bad_tools.json
```

A filtered run, so this README stays short (the example file produces 25 findings in full):

```text
$ tool-schema-lint examples/bad_tools.json --select TS101,TS102,TS103,TS401,TS504
examples/bad_tools.json: TS101 error: lookup_customer: object has no `additionalProperties: false` [fixable]
    at /tools/0/input_schema
examples/bad_tools.json: TS103 error: lookup_customer: `minimum` is not supported; an SDK helper may strip it, a raw request gets a 400
    at /tools/0/input_schema/properties/age/minimum
examples/bad_tools.json: TS101 error: lookup_customer: object has no `additionalProperties: false` [fixable]
    at /tools/0/input_schema/properties/address
examples/bad_tools.json: TS102 error: lookup_customer: must be false, found true
    at /tools/0/input_schema/properties/metadata/additionalProperties
examples/bad_tools.json: TS504 warning: run: 'sort' is described as a fixed choice: "Sort direction, either 'asc' or 'desc'."
    at /tools/2/input_schema/properties/sort
examples/bad_tools.json: TS401 warning: fetch_customer: overlaps 'lookup_customer' (score 0.75, shared: customer, data, get); merge them or state the boundary in both
    at /tools/1
3 tools in 1 files: 4 error, 2 warning, 0 info, 2 fixable
```

A clean file, with a server tool correctly left alone:

```text
$ tool-schema-lint examples/good_tools.json --fail-on info
examples/good_tools.json: note: skipped server tools with built-in schemas: web_search
2 tools in 1 files: 0 error, 0 warning, 0 info, 0 fixable
```

Python files are parsed with `ast` and never executed. Module-level constants and string `+` are resolved; anything else is skipped with a note rather than guessed.

```text
$ tool-schema-lint examples/tools_in_python.py --select TS101
examples/tools_in_python.py:6: TS101 error: get_invoice: object has no `additionalProperties: false` [fixable]
    at line:6/input_schema
1 tools in 1 files: 1 error, 0 warning, 0 info, 1 fixable
```

## `--fix`

Fixes only what has one correct answer: adding `additionalProperties: false` to objects in a tool already marked strict, adding a missing root `type: object`, and removing duplicates from `required` and `enum`. It does not flip `additionalProperties: true`, delete unsupported keywords, rename anything or write prose, because those change what the tool means. JSON only; Python is reported but not rewritten.

```text
$ tool-schema-lint tools.json --fix --select TS002,TS005,TS101,TS502
3 tools in 1 files: 0 error, 0 warning, 0 info, 0 fixable
applied 5 fixes
```

## CI

Exit code is 0 when clean, 1 when a finding reaches `--fail-on` (default `error`), 2 for bad input.

```text
$ tool-schema-lint examples/bad_tools.json --select TS302 --format json --fail-on never
{
  "version": 1,
  "tools": 3,
  "fixed": 0,
  "summary": {
    "warning": 1
  },
  "findings": [
    {
      "rule": "TS302",
      "severity": "warning",
      "title": "vague tool name",
      "path": "examples/bad_tools.json",
      "tool": "run",
      "pointer": "/tools/2/name",
      "line": null,
      "message": "'run' does not say what the tool acts on",
      "fixable": false,
      "source": "claude-api skill: shared/tool-use-concepts.md"
    }
  ],
  "notes": []
}
```

`--assume-strict` checks every tool as if `strict: true` were set, which answers "what breaks if I turn it on".

## Rules

Each rule names its source, so an API fact can be told apart from a style opinion. `claude-api skill` means the reference files bundled with Claude Code 2.1.309; `docs` means platform.claude.com pages read on 2026-10-30. Those facts can change; rules were written against that date.

```text
$ tool-schema-lint --list-rules
TS001  error    tool name missing or invalid  [docs: agents-and-tools/tool-use/define-tools (read 2026-10-30)]
TS002  error    input schema missing or not an object schema  [claude-api skill: shared/tool-use-concepts.md]
TS003  error    duplicate tool name  [docs: agents-and-tools/tool-use/define-tools (read 2026-10-30)]
TS004  error    `required` malformed or names an undeclared property  [claude-api skill: shared/tool-use-concepts.md]
TS005  warning  duplicate entries in `required`  [opinion]
TS101  error    strict: object without `additionalProperties: false`  [claude-api skill: shared/tool-use-concepts.md]
TS102  error    strict: `additionalProperties` set to something else  [claude-api skill: shared/tool-use-concepts.md]
TS103  error    strict: unsupported constraint keyword  [claude-api skill: shared/tool-use-concepts.md]
TS104  error    strict: recursive schema  [claude-api skill: shared/tool-use-concepts.md]
TS105  error    strict: external `$ref`  [docs: build-with-claude/structured-outputs#json-schema-limitations (read 2026-10-30)]
TS106  warning  strict: string format outside the supported list  [claude-api skill: shared/tool-use-concepts.md]
TS107  warning  strict: regex feature that is not supported  [docs: build-with-claude/structured-outputs#json-schema-limitations (read 2026-10-30)]
TS108  warning  strict: per-request complexity limit exceeded  [docs: build-with-claude/structured-outputs#json-schema-limitations (read 2026-10-30)]
TS109  error    strict: enum with complex values  [docs: build-with-claude/structured-outputs#json-schema-limitations (read 2026-10-30)]
TS110  error    strict: `allOf` combined with `$ref`  [docs: build-with-claude/structured-outputs#json-schema-limitations (read 2026-10-30)]
TS201  error    tool has no description  [claude-api skill: shared/tool-use-concepts.md]
TS202  warning  tool description under 3 sentences  [docs: agents-and-tools/tool-use/define-tools (read 2026-10-30)]
TS203  warning  tool description is vague  [opinion]
TS204  info     tool description does not say when to call it  [claude-api skill: shared/tool-use-concepts.md]
TS205  warning  parameter has no description  [claude-api skill: shared/tool-use-concepts.md]
TS206  info     description steers with shouting  [claude-api skill: shared/prompt-audit.md, Group 3]
TS207  warning  parameter description restates its name  [opinion]
TS301  warning  ambiguous parameter name  [opinion]
TS302  warning  vague tool name  [claude-api skill: shared/tool-use-concepts.md]
TS401  warning  two tools overlap  [claude-api skill: shared/prompt-audit.md, Group 3]
TS501  warning  oversized enum  [opinion]
TS502  warning  duplicate enum values  [opinion]
TS503  error    enum value does not match the declared type  [opinion]
TS504  warning  description lists choices but there is no enum  [claude-api skill: shared/tool-use-concepts.md]
TS505  info     parameter name suggests a fixed set of values  [opinion]
TS601  info     more than 30 always-loaded tools  [claude-api skill: shared/prompt-audit.md, Group 3]
```

One strict-mode rule is deliberately absent: the API does not require every property to be listed in `required`. Its own strict examples leave properties optional. What it limits is the count, which TS108 checks (20 strict tools, 24 optional parameters, 16 union-typed parameters per request).

## Limits

- Strict-mode rules follow the Messages API. Other providers have different rules, and a schema that passes here is not checked against them. The `{"type": "function", "function": {...}}` wrapper and `parameters` key are read so that shared definitions can be linted, nothing more.
- Nothing here has been run against the live API. Rules come from documentation, not from observed 400s.
- TS401 is a weighted token overlap of names, descriptions and parameter names with a small synonym table, tuned by hand on my own examples. It has no notion of meaning: it will miss two tools that overlap in different words and flag two that share vocabulary but have a stated boundary. Raise `--overlap-threshold` if it is noisy.
- Description rules (TS202 to TS204, TS504) are regexes over English. TS202 counts sentence punctuation, so it can miscount.
- Overlap, duplicates and TS108 treat one file as one request's tool list.
- `--fix` re-serialises the whole JSON file with consistent indentation, so inline arrays expand and the diff can be larger than the fix.
- Tools built at runtime, by decorators or from Pydantic models, are not seen. Dump them to JSON first.

Tests: `57 passed in 0.06s` (self-written fixtures). About 984 lines of source.

## License

MIT

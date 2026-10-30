"""One behaviour per rule: it fires on the bad shape and stays quiet on the good one."""

from __future__ import annotations

from tool_schema_lint.rules import RULES


def ids(findings):
    return {f.rule.id for f in findings}


def schema(**extra):
    return {"type": "object", "properties": {}, **extra}


def strict_with(prop, **options):
    return {
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"thing_count": {"description": "How many to return.", **prop}},
            "required": ["thing_count"],
            "additionalProperties": False,
        },
        **options,
    }


def test_good_tool_is_clean(lint, tool):
    assert lint(tool()) == []


def test_every_rule_names_a_source():
    assert all(rule.source for rule in RULES.values())


def test_ts001_invalid_and_missing_name(lint, tool):
    assert "TS001" in ids(lint(tool(name="has space")))
    bad = tool()
    del bad["name"]
    assert "TS001" in ids(lint(bad))


def test_ts002_schema_shapes(lint, tool):
    missing = tool()
    del missing["input_schema"]
    assert "TS002" in ids(lint(missing))
    assert "TS002" in ids(lint(tool(input_schema={"type": "array"})))
    assert "TS002" in ids(lint(tool(input_schema={"properties": {}})))


def test_ts003_duplicate_names(lint, tool):
    assert "TS003" in ids(lint(tool(), tool()))


def test_ts004_required_problems(lint, tool):
    assert "TS004" in ids(lint(tool(input_schema=schema(required=["ghost"]))))
    assert "TS004" in ids(lint(tool(input_schema=schema(required="ghost"))))


def test_ts005_duplicate_required(lint, tool):
    s = {
        "type": "object",
        "properties": {"account_id": {"type": "string", "description": "Account on statement."}},
        "required": ["account_id", "account_id"],
    }
    assert "TS005" in ids(lint(tool(input_schema=s)))


def test_strict_rules_only_apply_to_strict_tools(lint, tool):
    assert "TS101" not in ids(lint(tool()))
    assert "TS101" in ids(lint(tool(strict=True)))
    assert "TS101" in ids(lint(tool(), assume_strict=True))


def test_optional_properties_are_allowed_in_strict(lint, tool):
    # The docs' own strict examples leave properties out of `required`.
    s = {
        "type": "object",
        "properties": {
            "account_id": {"type": "string", "description": "Account on statement."},
            "currency_code": {"type": "string", "description": "ISO code of the currency."},
        },
        "required": ["account_id"],
        "additionalProperties": False,
    }
    assert lint(tool(strict=True, input_schema=s)) == []


def test_ts101_reaches_nested_objects(lint, tool):
    s = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "items_list": {
                "type": "array",
                "description": "Rows to insert.",
                "items": {"type": "object", "properties": {}},
            }
        },
    }
    found = [f for f in lint(tool(strict=True, input_schema=s)) if f.rule.id == "TS101"]
    assert [f.pointer for f in found] == ["/0/input_schema/properties/items_list/items"]


def test_ts102_true_and_schema(lint, tool):
    s = schema(additionalProperties=True)
    found = [f for f in lint(tool(strict=True, input_schema=s)) if f.rule.id == "TS102"]
    assert found and found[0].fix is None


def test_ts103_unsupported_constraints(lint, tool):
    assert "TS103" in ids(lint(tool(**strict_with({"type": "integer", "minimum": 1}))))
    assert "TS103" in ids(lint(tool(**strict_with({"type": "string", "maxLength": 3}))))
    assert "TS103" in ids(lint(tool(**strict_with({"type": "array", "minItems": 2}))))
    assert "TS103" not in ids(lint(tool(**strict_with({"type": "array", "minItems": 1}))))


def test_ts104_recursive_ref(lint, tool):
    s = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"root_node": {"$ref": "#/$defs/node", "description": "Tree root."}},
        "$defs": {
            "node": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"child": {"$ref": "#/$defs/node", "description": "Next node."}},
            }
        },
    }
    assert "TS104" in ids(lint(tool(strict=True, input_schema=s)))


def test_ts104_non_recursive_ref_is_fine(lint, tool):
    s = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"home": {"$ref": "#/$defs/place", "description": "Home address."}},
        "$defs": {"place": {"type": "object", "additionalProperties": False, "properties": {}}},
    }
    assert "TS104" not in ids(lint(tool(strict=True, input_schema=s)))


def test_ts105_external_ref(lint, tool):
    assert "TS105" in ids(lint(tool(**strict_with({"$ref": "http://example.test/s.json"}))))


def test_ts106_format(lint, tool):
    assert "TS106" in ids(lint(tool(**strict_with({"type": "string", "format": "phone"}))))
    assert "TS106" not in ids(lint(tool(**strict_with({"type": "string", "format": "uuid"}))))


def test_ts107_regex(lint, tool):
    assert "TS107" in ids(lint(tool(**strict_with({"type": "string", "pattern": r"(?=a)b"}))))
    assert "TS107" in ids(lint(tool(**strict_with({"type": "string", "pattern": r"\bword"}))))
    assert "TS107" not in ids(lint(tool(**strict_with({"type": "string", "pattern": r"^\d+$"}))))


def test_ts108_counts_optional_parameters_across_tools(lint, tool):
    props = {f"field_{i}": {"type": "string", "description": "A named field."} for i in range(25)}
    s = {"type": "object", "properties": props, "additionalProperties": False}
    found = [f for f in lint(tool(strict=True, input_schema=s)) if f.rule.id == "TS108"]
    assert len(found) == 1
    assert "25 optional" in found[0].message


def test_ts108_counts_strict_tools(lint, tool):
    tools = [tool(name=f"get_widget_{i}", strict=True) for i in range(21)]
    found = lint(*tools, overlap_threshold=2.0)
    assert any(f.rule.id == "TS108" and "21 strict tools" in f.message for f in found)


def test_ts109_complex_enum(lint, tool):
    assert "TS109" in ids(lint(tool(**strict_with({"enum": [{"a": 1}]}))))


def test_ts110_allof_ref(lint, tool):
    assert "TS110" in ids(lint(tool(**strict_with({"allOf": [{"$ref": "#/$defs/a"}]}))))


def test_ts201_no_description(lint, tool):
    assert "TS201" in ids(lint(tool(description="")))


def test_ts202_short_description(lint, tool):
    assert "TS202" in ids(lint(tool(description="Returns the balance. It is a number.")))
    assert "TS202" not in ids(lint(tool()))


def test_ts202_abbreviations_are_not_sentences(lint, tool):
    assert "TS202" in ids(lint(tool(description="Find e.g. a thing, i.e. one thing, etc. here")))


def test_ts203_vague(lint, tool):
    assert "TS203" in ids(lint(tool(description="Helper function for various things.")))
    assert "TS203" in ids(lint(tool(description="Get account balance.")))


def test_ts204_when_to_use(lint, tool):
    assert "TS204" in ids(lint(tool(description="Returns data. It is fast. It is cached.")))
    assert "TS204" not in ids(lint(tool()))


def test_ts205_and_ts207_parameter_descriptions(lint, tool):
    s = {
        "type": "object",
        "properties": {
            "account_id": {"type": "string"},
            "region": {"type": "string", "description": "region"},
        },
    }
    assert {"TS205", "TS207"} <= ids(lint(tool(input_schema=s)))


def test_ts205_ignores_anyof_branches(lint, tool):
    s = {
        "type": "object",
        "properties": {
            "account_id": {
                "description": "Account number on the statement.",
                "anyOf": [{"type": "string"}, {"type": "null"}],
            }
        },
    }
    assert "TS205" not in ids(lint(tool(input_schema=s)))


def test_ts206_shouting(lint, tool):
    text = "CRITICAL: YOU MUST use this tool when asked. It is good. It returns a value."
    assert "TS206" in ids(lint(tool(description=text)))


def test_ts301_ambiguous_param(lint, tool):
    s = {"type": "object", "properties": {"data": {"type": "string", "description": "Row data."}}}
    assert "TS301" in ids(lint(tool(input_schema=s)))


def test_ts302_vague_tool_name(lint, tool):
    assert "TS302" in ids(lint(tool(name="run")))
    assert "TS302" not in ids(lint(tool(name="run_sql_query")))


def test_ts401_overlap_through_synonyms(lint, tool):
    pair = lint(
        tool(name="fetch_invoice", description="Gets one invoice by number. Use when asked."),
        tool(name="retrieve_invoice", description="Gets an invoice by its number. Use when asked."),
    )
    assert "TS401" in ids(pair)


def test_ts401_distinct_tools_do_not_overlap(lint, tool):
    pair = lint(tool(name="get_invoice"), tool(name="cancel_shipment"))
    assert "TS401" not in ids(pair)


def test_ts401_threshold_is_configurable(lint, tool):
    pair = (tool(name="fetch_invoice"), tool(name="retrieve_invoice"))
    assert "TS401" not in ids(lint(*pair, overlap_threshold=1.1))


def test_ts501_oversized_enum(lint, tool):
    values = [f"v{i}" for i in range(51)]
    s = {
        "type": "object",
        "properties": {"region": {"type": "string", "description": "Target.", "enum": values}},
    }
    assert "TS501" in ids(lint(tool(input_schema=s)))
    assert "TS501" not in ids(lint(tool(input_schema=s), max_enum=100))


def test_ts502_ts503_enum_values(lint, tool):
    s = {
        "type": "object",
        "properties": {
            "region": {"type": "string", "description": "Target.", "enum": ["a", "a", 3]},
            "size_code": {"type": "integer", "description": "Target.", "enum": [True, 1]},
        },
    }
    found = lint(tool(input_schema=s))
    assert {"TS502", "TS503"} <= ids(found)
    assert sum(f.rule.id == "TS503" for f in found) == 2


def test_ts504_description_lists_choices(lint, tool):
    for text in (
        "One of: fast, slow.",
        "Either 'asc' or 'desc'.",
        "Must be 'a', 'b', or 'c'.",
        "Sort key: name|date|size.",
    ):
        s = {"type": "object", "properties": {"sorting": {"type": "string", "description": text}}}
        assert "TS504" in ids(lint(tool(input_schema=s))), text


def test_ts504_quiet_with_enum_or_prose(lint, tool):
    with_enum = {"type": "string", "enum": ["a", "b"], "description": "Either 'a' or 'b'."}
    prose = {"type": "string", "description": "Name of the city."}
    for prop in (with_enum, prose):
        s = {"type": "object", "properties": {"sorting": prop}}
        assert "TS504" not in ids(lint(tool(input_schema=s)))


def test_ts505_enum_like_name(lint, tool):
    s = {"type": "object", "properties": {"status": {"type": "string", "description": "Filter."}}}
    assert "TS505" in ids(lint(tool(input_schema=s)))


def test_ts601_many_tools(lint, tool):
    tools = [tool(name=f"get_widget_{i}") for i in range(31)]
    assert "TS601" in ids(lint(*tools, overlap_threshold=2.0))


def test_function_wrapped_shape_uses_parameters(lint):
    wrapped = {
        "type": "function",
        "function": {
            "name": "get_account_balance",
            "description": "Returns one balance. Use when asked. It lists nothing else.",
            "strict": True,
            "parameters": {"type": "object", "properties": {}},
        },
    }
    found = lint(wrapped)
    assert [f.pointer for f in found if f.rule.id == "TS101"] == ["/0/function/parameters"]


def test_server_tools_are_skipped(lint):
    assert lint({"type": "web_search_20260209", "name": "web_search"}) == []

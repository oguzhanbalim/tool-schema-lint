"""Tool definitions in Python. The linter reads this file with `ast`; it never runs it."""

SHARED_NOTE = "Returns nothing about payment."

TOOLS = [
    {
        "name": "get_invoice",
        "description": "Returns one invoice. " + SHARED_NOTE,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"invoice_id": {"type": "string", "description": "Invoice number."}},
            "required": ["invoice_id"],
        },
    },
]

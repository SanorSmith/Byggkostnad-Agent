# TODO — Sanor rewrites this before the interview
"""Tool schemas sent to Claude.

The description strings are the routing logic: they are the only thing the
model reads when deciding which tool answers a question. Nothing else in
the codebase imports from this file except tools.py, so it can be
rewritten freely as long as the tool names and parameter names stay.
"""

from typing import Any

COST_CLASSES = ["TOTAL", "MATERIAL", "ARBL", "MASK", "TRANS", "OMK", "ETTILLFEM", "BYGGKOST"]
BUILDING_TYPES = ["FLERBO", "GRUPPSMÅ", "JORDBRUK"]

QUERY_PRICE_INDEX: dict[str, Any] = {
    "name": "query_price_index",
    "description": (
        "Look up exact monthly values of SCB's construction cost index "
        "(Byggkostnadsindex, BKI) and get the change between two months, computed "
        "exactly. Use this for any question that needs a number: an index level, a "
        "rise or fall, a percentage change, a comparison between periods. Never "
        "estimate numbers from documents; call this tool. "
        "Series available: residential buildings, monthly, 1968=100 (table FPIBOM, "
        "building_type FLERBO = multi-dwelling buildings / flerbostadshus, "
        "GRUPPSMÅ = group-built small houses / gruppbyggda småhus) and agricultural "
        "buildings, monthly, 2015=100 (table FPIJBM15, building_type JORDBRUK). "
        "Cost classes: TOTAL = total index (use this when the user says 'the index'), "
        "MATERIAL = building materials, ARBL = wages, MASK = machinery, TRANS = "
        "transport, fuel and electricity, OMK = overheads, ETTILLFEM = contractor's "
        "costs, BYGGKOST = client's (byggherre) costs. "
        "If the user says 'residential' without a type, use FLERBO, the headline "
        "series SCB reports. Returns ordered rows plus first, last, absolute_change "
        "and percent_change."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cost_class": {"type": "string", "enum": COST_CLASSES},
            "from_date": {
                "type": "string",
                "description": "Start month, YYYY-MM-DD (day is ignored).",
            },
            "to_date": {
                "type": "string",
                "description": "End month, YYYY-MM-DD. Omit for the latest available month.",
            },
            "building_type": {
                "type": "string",
                "enum": BUILDING_TYPES,
                "description": "Omit to get every building type that has this cost class.",
            },
        },
        "required": ["cost_class", "from_date"],
        "additionalProperties": False,
    },
}

SEARCH_DOCS: dict[str, Any] = {
    "name": "search_docs",
    "description": (
        "Semantic search over SCB's documentation for the construction cost index: "
        "what the index measures and includes, the cost classes and their weights, "
        "how it is constructed, methodology changes, and the monthly statistical "
        "news releases that explain why costs moved (e.g. steel, timber, energy). "
        "Use this for definitions and for explanations of why the index changed. "
        "The documents are in Swedish; searching in Swedish terms often works "
        "better (e.g. 'byggherrekostnader', 'armeringsstål 2022'). Do not read "
        "index values out of these documents to answer numeric questions; use "
        "query_price_index for numbers."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for."},
            "k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

TOOL_SCHEMAS: list[dict[str, Any]] = [QUERY_PRICE_INDEX, SEARCH_DOCS]

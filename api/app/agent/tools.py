"""Tool registry: name -> callable. Inputs are validated before any query runs."""

from collections.abc import Callable
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.queries.price_index import query_price_index
from app.retrieval.search import search_docs

CostClass = Literal["TOTAL", "MATERIAL", "ARBL", "MASK", "TRANS", "OMK", "ETTILLFEM", "BYGGKOST"]
BuildingType = Literal["FLERBO", "GRUPPSMÅ", "JORDBRUK"]


class PriceIndexInput(BaseModel):
    cost_class: CostClass
    from_date: date
    to_date: date | None = None
    building_type: BuildingType | None = None


class SearchDocsInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    k: int = Field(default=5, ge=1, le=10)


def _price_index_tool(**kwargs: Any) -> dict[str, Any]:
    args = PriceIndexInput(**kwargs)
    return query_price_index(args.cost_class, args.from_date, args.to_date, args.building_type)


def _search_docs_tool(**kwargs: Any) -> dict[str, Any]:
    args = SearchDocsInput(**kwargs)
    return {"query": args.query, "hits": search_docs(args.query, args.k)}


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "query_price_index": _price_index_tool,
    "search_docs": _search_docs_tool,
}


def run_tool(name: str, tool_input: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Run a tool. Returns (output, is_error); bad input becomes an error result
    the model can read and correct, not an exception."""
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}, True
    try:
        return fn(**tool_input), False
    except ValidationError as exc:
        return {"error": "Invalid arguments", "details": exc.errors(include_url=False)}, True

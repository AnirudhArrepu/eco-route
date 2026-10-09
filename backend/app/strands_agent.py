import json
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.integrations import search_places


class ParsedIntent(BaseModel):
    operation: Literal["add_destination", "replan", "create_schedule", "clarify"]
    destination_query: str | None = None
    budget_inr: int | None = Field(default=None, gt=0)
    clarification_needed: bool = False
    clarification_question: str | None = None


def interpret_with_strands(text: str, timezone: str = "UTC", bias: list[float] | None = None) -> dict:
    if not settings.bedrock_model_id:
        raise HTTPException(503, "BEDROCK_MODEL_ID is required for Strands")
    if not settings.aws_integrations_enabled or not settings.location_index_name:
        raise HTTPException(503, "Amazon Location place search must be configured for the Strands agent")

    try:
        from strands import Agent, tool
        tool_calls = 0

        @tool
        def search_places_tool(query: str) -> dict:
            """Search Amazon Location for real candidate places. This does not verify stock or price."""
            nonlocal tool_calls
            tool_calls += 1
            if tool_calls > settings.strands_max_tool_calls:
                raise RuntimeError("Strands place-search tool-call limit exceeded")
            return {"places": search_places(query, bias, 10)}

        agent = Agent(
            model=settings.bedrock_model_id,
            tools=[search_places_tool],
            callback_handler=None,
            structured_output_model=ParsedIntent,
            system_prompt=(
                "Interpret schedule requests and use search_places_tool for destination discovery. "
                "Never claim inventory, price, opening hours, or emissions unless returned by a tool. "
                "Do not modify a schedule or approve proposals. End with one JSON object containing "
                "operation, destination_query, budget_inr, clarification_needed, clarification_question. "
                "Allowed operation values are add_destination, replan, create_schedule, clarify."
            ),
        )
        result = agent(f"Timezone: {timezone}\nUser request: {text}")
        structured = getattr(result, "structured_output", None)
        if isinstance(structured, ParsedIntent):
            return structured.model_dump()
        rendered = str(result)
        parsed_text = rendered[rendered.find("{") : rendered.rfind("}") + 1]
        parsed = ParsedIntent.model_validate(json.loads(parsed_text))
        return parsed.model_dump()
    except HTTPException:
        raise
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(502, "Strands returned an invalid structured intent") from exc
    except Exception as exc:
        raise HTTPException(502, "Strands request failed") from exc

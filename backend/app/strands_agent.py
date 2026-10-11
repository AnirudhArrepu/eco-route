import json
import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.integrations import search_places

logger = logging.getLogger(__name__)


class ParsedIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["add_destination", "replan", "create_schedule", "clarify"]
    destination_query: str | None = None
    budget_inr: int | None = Field(default=None, gt=0)
    clarification_needed: bool = False
    clarification_question: str | None = None


class ExtractedTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=128)
    destination_query: str = Field(min_length=2, max_length=300)
    type: Literal["errand", "appointment"] = "errand"
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    latest_start: str | None = None
    latest_end: str | None = None
    fixed_start: str | None = None


class ExtractedTaskList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[ExtractedTask] = Field(max_length=12)
    clarification_question: str | None = None


class ReplanInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updates: dict[str, dict[str, Any]] = Field(default_factory=dict)
    stop_order: list[str] | None = None
    optimize_route: bool = False
    clarification_question: str | None = None


def _configured_model():
    if not settings.mantle_enabled:
        raise HTTPException(503, "OPENAI_API_KEY and OPENAI_BASE_URL are required for the Strands agent")
    if not settings.bedrock_model_id:
        raise HTTPException(503, "BEDROCK_MODEL_ID is required for the Strands agent")
    try:
        from strands.models.openai import OpenAIModel
    except ImportError as exc:
        raise HTTPException(503, "The Strands Agents SDK is not installed") from exc

    return OpenAIModel(
        model_id=settings.bedrock_model_id,
        client_args={
            "api_key": settings.openai_api_key.get_secret_value(),
            "base_url": settings.openai_base_url,
            "project": settings.openai_project_id or None,
            "timeout": 25,
            "max_retries": 1,
        },
        params={"temperature": 0, "max_tokens": 1600},
    )


def _run_agent(prompt: str, system_prompt: str, output_model: type[BaseModel], tools: list | None = None):
    try:
        from strands import Agent
    except ImportError as exc:
        raise HTTPException(503, "The Strands Agents SDK is not installed") from exc

    phase = "agent_setup"
    try:
        agent = Agent(
            model=_configured_model(),
            tools=tools or [],
            callback_handler=None,
            structured_output_model=output_model,
            system_prompt=system_prompt,
        )
        phase = "model_inference"
        result = agent(prompt)
        phase = "structured_output_validation"
        structured = getattr(result, "structured_output", None)
        if isinstance(structured, output_model):
            return structured
        if isinstance(structured, dict):
            return output_model.model_validate(structured)
        rendered = str(result)
        return output_model.model_validate_json(rendered)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Strands structured request failed: output=%s phase=%s type=%s",
            output_model.__name__,
            phase,
            type(exc).__name__,
        )
        raise HTTPException(502, "The Strands agent could not interpret this request. No plan changes were made.") from exc


def _place_search_tool(bias: list[float] | None):
    if not settings.aws_integrations_enabled or not settings.location_index_name:
        return None
    try:
        from strands import tool
    except ImportError as exc:
        raise HTTPException(503, "The Strands Agents SDK is not installed") from exc

    @tool
    def search_places_tool(query: str) -> dict:
        """Find real candidate places; place results do not verify price or availability."""
        return {"places": search_places(query, bias, 10)}

    return search_places_tool


def interpret_with_strands(
    text: str,
    timezone: str = "UTC",
    bias: list[float] | None = None,
    schedule_context: dict | None = None,
) -> dict:
    tools = [tool for tool in [_place_search_tool(bias)] if tool]
    parsed = _run_agent(
        prompt=json.dumps({
            "timezone": timezone,
            "current_schedule": schedule_context or {},
            "user_request": text,
        }, ensure_ascii=False),
        system_prompt=(
            "Interpret the user's natural-language request for EcoRoute. Return one structured intent. "
            "Choose add_destination for a new place to visit, including requests that say 'also', 'and', "
            "or 'add'. Choose replan only when the user wants to change an existing stop or route. Use "
            "the schedule context to distinguish a new stop from a change to a stop already on the plan. "
            "For a request to be at or arrive at an existing stop by a time, choose replan. For a moved "
            "or rescheduled appointment, choose replan. Never ask for a city when the schedule provides "
            "one. Do not claim to have changed or saved the plan."
        ),
        output_model=ParsedIntent,
        tools=tools,
    )
    return {**parsed.model_dump(), "intent_source": "strands_agent"}


def extract_tasks_with_strands(text: str, plan_date: str, timezone: str = "UTC") -> dict:
    parsed = _run_agent(
        prompt=json.dumps({
            "plan_date": str(plan_date),
            "timezone": timezone,
            "user_request": text,
        }, ensure_ascii=False),
        system_prompt=(
            "Extract every distinct place the user intends to visit from their natural-language request. "
            "Return a separate task for each errand or appointment, even when errands and appointments "
            "are combined in one sentence or joined by 'and' or 'also'. Preserve the user's task identity "
            "in title (for example 'Pharmacy' or 'Dentist appointment') and provide a concise place-search "
            "query in destination_query. Set type to appointment whenever the user says they have an "
            "appointment, even when no time is stated; otherwise use errand. A request to 'have a dentist "
            "appointment' is a destination task even if no appointment time is stated. Do not invent "
            "durations or times. For a stated exact "
            "appointment time, set fixed_start to an ISO datetime with the schedule date and timezone offset. "
            "For 'be at', 'arrive at', or 'reach' a place by a time, set latest_start. For a task that must "
            "be completed by a time, set latest_end. Never treat arrival deadlines as completion deadlines. "
            "For an omitted year/date, use plan_date. Use the supplied timezone for local times. Ask one "
            "short clarification only when the user did not specify any actionable places."
        ),
        output_model=ExtractedTaskList,
    )

    tasks = []
    for task in parsed.tasks:
        values = task.model_dump()
        for field in ("latest_start", "latest_end", "fixed_start"):
            value = values[field]
            if value is None:
                continue
            try:
                parsed_time = datetime.fromisoformat(value)
            except ValueError as exc:
                raise HTTPException(502, f"Strands returned an invalid {field} timestamp") from exc
            if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
                raise HTTPException(502, f"Strands returned a {field} timestamp without a timezone offset")
            values[field] = parsed_time.isoformat()
        values["title"] = values["title"].strip()
        values["destination_query"] = values["destination_query"].strip()
        if not values["title"] or len(values["destination_query"]) < 2:
            raise HTTPException(502, "Strands returned a task without a usable title or place query")
        tasks.append(values)

    question = parsed.clarification_question
    if not tasks and not question:
        question = "What places or appointments should I include?"
    return {
        "tasks": tasks,
        "clarification_question": question,
        "extraction_source": "strands_agent",
        "fallback_reason": None,
    }


def parse_replan_with_strands(
    text: str,
    stops: list[dict],
    timezone: str,
    schedule_context: dict | None = None,
) -> dict:
    stop_context = [{
        key: stop.get(key) for key in (
            "id", "title", "type", "duration_minutes", "earliest_start",
            "latest_start", "latest_end", "fixed_start", "priority", "mandatory",
        )
    } for stop in stops]
    parsed = _run_agent(
        prompt=json.dumps({
            "timezone": timezone,
            "schedule": schedule_context or {},
            "stops": stop_context,
            "user_request": text,
        }, ensure_ascii=False),
        system_prompt=(
            "Interpret the user's natural-language request to change an existing EcoRoute itinerary. "
            "Return only updates keyed by the exact existing stop IDs. A request to be at or arrive at "
            "a stop by a time sets latest_start. An exact appointment time, or an appointment that has "
            "moved/rescheduled to a specific time, sets fixed_start. Do not confuse 'by' deadlines with "
            "fixed appointment times. Resolve times to ISO datetimes with the schedule date and timezone "
            "offset. For 'extend/increase by N minutes', add N to the current duration; when the user says "
            "make it N minutes, use N as the total. Preserve all other stop constraints by omitting fields "
            "that are not requested. For an explicit stop order include every stop ID exactly once. Set "
            "optimize_route for a general request to optimize/reorder. If a stop name is ambiguous, missing, "
            "or the requested change is unclear, return no updates and ask one short clarification. Never "
            "claim the plan has been saved or approved."
        ),
        output_model=ReplanInterpretation,
    )

    allowed_fields = {
        "duration_minutes", "earliest_start", "latest_start", "latest_end",
        "fixed_start", "priority", "mandatory",
    }
    known_ids = {stop["id"] for stop in stops}
    for stop_id, updates in parsed.updates.items():
        if stop_id not in known_ids:
            raise HTTPException(502, "Strands referenced a stop that is not in the active plan")
        for field, value in updates.items():
            if field not in allowed_fields:
                raise HTTPException(502, "Strands returned an unsupported plan change")
            if field in {"duration_minutes", "priority"}:
                if not isinstance(value, int) or isinstance(value, bool):
                    raise HTTPException(502, f"Strands returned an invalid {field}")
                limit = (1, 1440) if field == "duration_minutes" else (1, 5)
                if not limit[0] <= value <= limit[1]:
                    raise HTTPException(502, f"Strands returned an out-of-range {field}")
            elif field == "mandatory" and not isinstance(value, bool):
                raise HTTPException(502, "Strands returned an invalid mandatory value")
            elif field in {"earliest_start", "latest_start", "latest_end", "fixed_start"}:
                if not isinstance(value, str):
                    raise HTTPException(502, f"Strands returned an invalid {field}")
                try:
                    parsed_time = datetime.fromisoformat(value)
                except ValueError as exc:
                    raise HTTPException(502, f"Strands returned an invalid {field} timestamp") from exc
                if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
                    raise HTTPException(502, f"Strands returned a {field} timestamp without a timezone offset")

    if parsed.stop_order is not None and (
        len(parsed.stop_order) != len(known_ids) or set(parsed.stop_order) != known_ids
    ):
        raise HTTPException(502, "Strands returned an invalid stop order")
    if parsed.updates and parsed.clarification_question:
        raise HTTPException(502, "Strands returned both a plan change and a clarification request")
    if not parsed.updates and parsed.stop_order is None and not parsed.optimize_route and not parsed.clarification_question:
        parsed.clarification_question = "What would you like me to change in this plan?"

    return {
        **parsed.model_dump(),
        "source": "strands_agent",
        "fallback_reason": None,
    }

import boto3
import json
import logging
from botocore.config import Config
from app.config import settings
from app.planner import MockTravelProvider, Leg
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def _json_object_from_response(raw):
    """Decode the JSON object returned by OpenAI compatible Mantle chat completions."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        raw = "".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in raw)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Mantle response did not contain text")
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(candidate[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Mantle response was not a JSON object")
    return parsed

class AmazonLocation:
    def __init__(self):
        self.client = boto3.client("location", region_name=settings.aws_region, config=Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 2}))
    def search(self, text, bias=None, max_results=10):
        args={"IndexName":settings.location_index_name,"Text":text,"MaxResults":min(max(1,max_results),20)}
        if bias: args["BiasPosition"]=bias
        out=self.client.search_place_index_for_text(**args)
        rows=[]
        for item in out.get("Results",[]):
            p=item.get("Place",{}); point=p.get("Geometry",{}).get("Point")
            if point:
                rows.append({"id":item.get("PlaceId"),"title":p.get("Label",text),"label":p.get("Label"),"longitude":point[0],"latitude":point[1],"categories":p.get("Categories",[])})
        return rows
    def route(self,a,b,mode="Walking"):
        out=self.client.calculate_route(CalculatorName=settings.location_route_calculator_name,DeparturePosition=[a["longitude"],a["latitude"]],DestinationPosition=[b["longitude"],b["latitude"]],TravelMode=mode,IncludeLegGeometry=False)
        s=out.get("Summary",{})
        return Leg(float(s.get("DurationSeconds",0))/60,float(s.get("Distance",0)))

class TravelProvider:
    def __init__(self):
        self.mock=MockTravelProvider()
        self.aws=AmazonLocation() if settings.aws_integrations_enabled else None
    def leg(self,a,b,mode="Walking"):
        if settings.aws_integrations_enabled:
            if not settings.location_route_calculator_name:
                raise RuntimeError("LOCATION_ROUTE_CALCULATOR_NAME is required when AWS integrations are enabled")
            return self.aws.route(a,b,mode)
        if settings.environment == "production":
            raise RuntimeError("Live Amazon Location routing must be configured in production")
        return self.mock.leg(a,b,mode)

def search_places(text,bias=None,max_results=10):
    if not settings.aws_integrations_enabled:
        return []
    if not settings.location_index_name:
        raise HTTPException(503,"LOCATION_INDEX_NAME is required when AWS integrations are enabled")
    try:
        return AmazonLocation().search(text,bias,max_results)
    except Exception as exc:
        raise HTTPException(502,"Amazon Location place search failed") from exc

def search_places_on_route(text, start_location, end_location, mode="Walking", max_results=5):
    """Rank real place matches by the extra routed distance they add to a trip."""
    if not settings.aws_integrations_enabled:
        return []
    midpoint = [
        (start_location["longitude"] + end_location["longitude"]) / 2,
        (start_location["latitude"] + end_location["latitude"]) / 2,
    ]
    candidates = search_places(text, midpoint, max_results)
    if not candidates:
        return []
    provider = TravelProvider()
    try:
        direct_km = provider.leg(start_location, end_location, mode).distance_km
        ranked = []
        for place in candidates:
            place_location = {"latitude": place["latitude"], "longitude": place["longitude"]}
            to_place = provider.leg(start_location, place_location, mode).distance_km
            from_place = provider.leg(place_location, end_location, mode).distance_km
            route_km = to_place + from_place
            ranked.append({**place, "route_km": round(route_km, 2),
                           "detour_km": round(max(0.0, route_km - direct_km), 2)})
        ranked.sort(key=lambda place: (place["detour_km"], place["route_km"], place["label"] or ""))
        for index, place in enumerate(ranked):
            place["route_rank"] = index + 1
        return ranked
    except Exception as exc:
        logger.error("Amazon Location route-aware place ranking failed: type=%s", type(exc).__name__)
        raise HTTPException(502, "Could not compare place candidates against the planned route") from exc

def _explicit_add_destination(text):
    """Return a destination when the user clearly asks to add or visit one."""
    import re

    patterns = (
        r"^\s*(?:(?:and|also)\s+)?(?:i\s+)?(?:also\s+)?(?:need|want)\s+to\s+(?:go\s+to|visit|stop\s+by)\s+(.+?)\s*[?.!]*\s*$",
        r"^\s*(?:(?:and|also)\s+)?(?:please\s+)?(?:add|include|visit|go\s+to|stop\s+by)\s+(?:another\s+stop\s+(?:at|for)\s+)?(.+?)\s*[?.!]*\s*$",
    )
    for pattern in patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            query = re.sub(r"^(?:the|a|an)\s+", "", match.group(1).strip(), flags=re.IGNORECASE)
            if query:
                return query
    return None


def _explicit_replan_for_current_stop(text, schedule_context):
    """Recognize a change to a named stop in the active schedule before place discovery."""
    import re

    stops = (schedule_context or {}).get("stops", [])
    normalized = text.casefold()
    mentions_stop = False
    for stop in stops:
        labels = (stop.get("title"), stop.get("location", {}).get("label") if isinstance(stop.get("location"), dict) else None)
        for label in labels:
            if label and len(label.strip()) >= 3 and re.search(rf"(?<!\w){re.escape(label.strip().casefold())}(?!\w)", normalized):
                mentions_stop = True
                break
        if mentions_stop:
            break
    if not mentions_stop:
        return False
    has_time_or_change = re.search(
        r"\b(?:by|before|after|at)\s+(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)\b|"
        r"\b(?:move|change|shift|reschedule|delay|advance|extend|shorten|earlier|later|running late|be at|arrive)\b",
        normalized,
    )
    is_place_search = re.search(r"\b(?:find|search for|look for|locate|another|new)\b", normalized)
    return bool(has_time_or_change and not is_place_search)


def _local_parse_intent(text, timezone="UTC", schedule_context=None, fallback_reason=None):
    """Small explicit-phrase fallback used only when Mantle cannot answer."""
    import re
    if _explicit_replan_for_current_stop(text, schedule_context):
        return {"operation":"replan","destination_query":None,"clarification_needed":False,
                "clarification_question":None,"intent_source":"local_fallback","fallback_reason":fallback_reason}
    explicit_query = _explicit_add_destination(text) if schedule_context else None
    if explicit_query:
        return {"operation":"add_destination","destination_query":explicit_query,"budget_inr":None,
                "clarification_needed":False,"clarification_question":None,
                "intent_source":"local_fallback","fallback_reason":fallback_reason}
    low=text.lower().strip()
    if not low:
        return {"operation":"clarify","destination_query":None,"clarification_needed":True,
                "clarification_question":"What would you like to plan or change?","intent_source":"local_fallback",
                "fallback_reason":fallback_reason}
    if any(x in low for x in ("replan","reschedule","meeting moved","meeting extended","running late")) or re.search(r"\b(meeting|appointment|class|call)\b.*\b(extended|moved|rescheduled|running late|changed)\b",low):
        return {"operation":"replan","destination_query":None,"clarification_needed":False,
                "clarification_question":None,"intent_source":"local_fallback","fallback_reason":fallback_reason}
    if any(x in low for x in ("create a schedule","plan my day","make a schedule","schedule for tomorrow","schedule for today")):
        return {"operation":"create_schedule","destination_query":None,"clarification_needed":False,
                "clarification_question":None,"intent_source":"local_fallback","fallback_reason":fallback_reason}
    query=text
    search_match=re.match(r"^\s*(?:please\s+)?(?:find|search\s+for|look\s+for|locate)\s+(.+?)\s*[?.!]*\s*$",text,re.IGNORECASE)
    if search_match:
        query=search_match.group(1)
    return {"operation":"add_destination","destination_query":query,"budget_inr":None,
            "clarification_needed":False,"clarification_question":None,
            "intent_source":"local_fallback","fallback_reason":fallback_reason}


def parse_intent(text, timezone="UTC", schedule_context=None):
    if _explicit_replan_for_current_stop(text, schedule_context):
        return {"operation":"replan","destination_query":None,"clarification_needed":False,
                "clarification_question":None,"intent_source":"existing_schedule_stop"}
    explicit_query = _explicit_add_destination(text) if schedule_context else None
    if explicit_query:
        return {"operation":"add_destination","destination_query":explicit_query,"budget_inr":None,
                "clarification_needed":False,"clarification_question":None,
                "intent_source":"schedule_context"}
    if settings.mantle_enabled:
        from app.strands_agent import ParsedIntent

        try:
            from openai import OpenAI

            client=OpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                base_url=settings.openai_base_url,
                project=settings.openai_project_id or None,
                timeout=20,
                max_retries=1,
            )
            prompt=("Return one JSON object only with keys operation,destination_query,budget_inr,"
                    "clarification_needed,clarification_question. Allowed operation: add_destination,"
                    "replan,create_schedule,clarify. Preserve the user's destination wording. Never invent "
                    "inventory, prices, opening hours, or travel facts. Ask for clarification when required. "
                    "When the user explicitly says find, search for, look for, or locate a place or service, "
                    "choose add_destination. A request such as 'Find a pharmacy near Chennai Central' is "
                    "already clear; do not ask whether they want a list or directions. Clarify only when "
                    "the place or requested action is genuinely missing or ambiguous. When a user says they "
                    "also need to go to, visit, or add a place, choose add_destination. If a current schedule "
                    "area is provided, use it to resolve a missing city; do not ask the user for a city or "
                    "location. The place search will be biased to the schedule start location. "
                    f"Timezone={timezone}. Schedule context={json.dumps(schedule_context or {}, ensure_ascii=False)}. "
                    f"User request={text}")
            response=client.chat.completions.create(
                model=settings.bedrock_model_id or "openai.gpt-oss-safeguard-20b",
                messages=[{"role":"user","content":prompt}],
                temperature=0,
                response_format={"type":"json_object"},
            )
        except Exception as exc:
            logger.error(
                "Mantle intent request failed: type=%s module=%s status=%s request_id=%s",
                type(exc).__name__,
                getattr(exc, "name", None),
                getattr(exc, "status_code", None),
                getattr(exc, "request_id", None),
            )
            return _local_parse_intent(text,timezone,schedule_context,"mantle_request_failed")

        try:
            choices = getattr(response, "choices", None) or []
            if not choices:
                raise ValueError("response contained no choices")
            message = getattr(choices[0], "message", None)
            raw = getattr(message, "content", None)
            if not isinstance(raw, str) or not raw.strip():
                refusal = bool(getattr(message, "refusal", None))
                raise ValueError(f"response content was empty (refusal={refusal})")

            # Some compatible endpoints wrap JSON in a markdown fence or short prose.
            # Accept the first complete JSON object while still validating its schema.
            candidate = raw.strip()
            try:
                parsed = ParsedIntent.model_validate_json(candidate)
            except Exception:
                start = candidate.find("{")
                end = candidate.rfind("}")
                if start < 0 or end <= start:
                    raise
                parsed = ParsedIntent.model_validate(json.loads(candidate[start : end + 1]))
            if parsed.clarification_needed:
                import re

                search_match = re.match(
                    r"^\s*(?:please\s+)?(?:find|search\s+for|look\s+for|locate)\s+(?:(?:a|an|the)\s+)?(.+?)\s*[?.!]*\s*$",
                    text,
                    re.IGNORECASE,
                )
                if search_match and len(search_match.group(1).split()) >= 2:
                    parsed = ParsedIntent(
                        operation="add_destination",
                        destination_query=search_match.group(1),
                        budget_inr=parsed.budget_inr,
                        clarification_needed=False,
                        clarification_question=None,
                    )
            return {**parsed.model_dump(),"intent_source":"mantle"}
        except Exception as exc:
            logger.error(
                "Mantle intent response invalid: type=%s finish_reason=%s request_id=%s",
                type(exc).__name__,
                getattr(choices[0], "finish_reason", None) if choices else None,
                getattr(response, "_request_id", None),
            )
            return _local_parse_intent(text,timezone,schedule_context,"mantle_response_invalid")
    if settings.aws_integrations_enabled and settings.bedrock_model_id:
        raise HTTPException(503, "Configure OPENAI_API_KEY and OPENAI_BASE_URL for Bedrock Mantle inference")
    import re
    low=text.lower().strip()
    if not low:
        return {"operation":"clarify","destination_query":None,"clarification_needed":True,"clarification_question":"What would you like to plan or change?"}
    if any(x in low for x in ("replan","reschedule","meeting moved","meeting extended","running late")) or re.search(r"\b(meeting|appointment|class|call)\b.*\b(extended|moved|rescheduled|running late|changed)\b",low):
        return {"operation":"replan","destination_query":None,"clarification_needed":False,"clarification_question":None}
    if any(x in low for x in ("create a schedule","plan my day","make a schedule","schedule for tomorrow","schedule for today")):
        return {"operation":"create_schedule","destination_query":None,"clarification_needed":False,"clarification_question":None}
    budget_match=re.search(r"(?:under|below|maximum|max(?:imum)?(?: of)?|budget(?: of)?)\s*(?:₹|rs\.?\s*)?([\d,]+)",text,re.IGNORECASE)
    query=text
    if budget_match:
        query=(text[:budget_match.start()] + text[budget_match.end():]).strip(" ,.;")
    return {"operation":"add_destination","destination_query":query,"budget_inr":int(budget_match.group(1).replace(",","")) if budget_match else None,"clarification_needed":False,"clarification_question":None,"verification_note":"Place search does not verify product stock or price."}

def extract_tasks(text, plan_date, timezone="UTC"):
    """Turn a new-plan request into distinct errands with explicit constraints only."""
    from datetime import date
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    from pydantic import BaseModel, Field, ValidationError

    class Task(BaseModel):
        title: str = Field(min_length=1, max_length=128)
        destination_query: str = Field(min_length=2, max_length=300)
        duration_minutes: int | None = Field(default=None, ge=1, le=1440)
        deadline: str | None = None
        fixed_time: str | None = None

    class TaskList(BaseModel):
        tasks: list[Task] = Field(max_length=12)
        clarification_question: str | None = None

    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(422, "Unknown timezone") from exc
    date_value = plan_date if isinstance(plan_date, date) else date.fromisoformat(str(plan_date))

    def explicit_deadline():
        import re
        match = re.search(r"\b(?:before|by|no later than)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.I)
        if not match:
            return None
        hour = int(match.group(1)) % 12
        if match.group(3).lower() == "pm":
            hour += 12
        local_time = __import__("datetime").time(hour, int(match.group(2) or 0), tzinfo=zone)
        return __import__("datetime").datetime.combine(date_value, local_time).isoformat()

    def local_fallback():
        # Keep basic coordinated errands usable when Mantle returns non-JSON or is unavailable.
        import re
        cleaned = re.sub(r"^\s*(?:i\s+)?(?:need|want)\s+to\s+(?:visit|go to|stop by)\s+", "", text, flags=re.I)
        cleaned = re.sub(r"^\s*(?:i need to|i want to|please|can you help me|help me)\s+", "", cleaned, flags=re.I)
        cleaned = re.sub(r"^(?:visit|go to|stop by|pick up from|pick up|buy from|buy|get to)\s+", "", cleaned, flags=re.I)
        parts = re.split(r"\s*,\s*|\s+and\s+", cleaned, flags=re.I)
        duration_match = re.search(r"\b(?:for|about|around)\s+(\d{1,3})\s*(?:minutes?|mins?)\b", text, re.I)
        deadline = explicit_deadline()
        tasks = []
        for part in parts:
            query = re.sub(r"\b(?:before|by|no later than)\b.*$", "", part, flags=re.I).strip(" .?!")
            query = re.sub(r"^(?:the|a|an)\s+", "", query, flags=re.I)
            if query:
                title = query[:1].upper() + query[1:]
                tasks.append(Task(title=title, destination_query=query,
                                  duration_minutes=int(duration_match.group(1)) if duration_match else None,
                                  deadline=deadline))
        return TaskList(tasks=tasks[:12], clarification_question=None if tasks else "What places or errands should I include?")

    if settings.mantle_enabled:
        extraction_source = "mantle"
        fallback_reason = None
        phase = "request"
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key.get_secret_value(), base_url=settings.openai_base_url,
                            project=settings.openai_project_id or None, timeout=20, max_retries=1)
            response = client.chat.completions.create(
                model=settings.bedrock_model_id or "openai.gpt-oss-safeguard-20b",
                messages=[
                    {"role":"system","content":(
                        "Extract distinct errands and appointments from the user's request. "
                        "Return exactly one JSON object and no other text, with this shape: "
                        '{"tasks":[{"title":"Grocery store","destination_query":"grocery store","duration_minutes":null}],"clarification_question":null}. '
                        "Split coordinated places into separate tasks. Preserve the destination wording for place search. "
                        "Do not invent destinations or durations. Use null for a duration unless the user states one. "
                        "If there are no actionable destinations, return an empty tasks array and ask one short clarification."
                    )},
                    {"role":"user","content":json.dumps({"plan_date":date_value.isoformat(),"timezone":timezone,"request":text},ensure_ascii=False)},
                ], temperature=0, max_tokens=800,
                response_format={"type":"json_object"},
            )
            phase = "response parsing"
            choices = getattr(response, "choices", None) or []
            if not choices:
                raise ValueError("Mantle response contained no choices")
            message = getattr(choices[0], "message", None)
            data = _json_object_from_response(getattr(message, "content", None))
            if "tasks" not in data:
                data["tasks"] = data.get("errands", data.get("destinations", data.get("places", [])))
            if isinstance(data.get("tasks"), dict):
                data["tasks"] = [data["tasks"]]
            if not isinstance(data.get("tasks"), list):
                raise ValueError("Mantle task list was not an array")
            normalized_tasks = []
            for item in data["tasks"]:
                if isinstance(item, str):
                    item = {"title": item, "destination_query": item}
                if not isinstance(item, dict):
                    raise ValueError("Mantle returned a task with an unsupported shape")
                query = next((item.get(key) for key in ("destination_query", "search_query", "place_query", "query", "destination", "place", "name", "title") if item.get(key)), None)
                if isinstance(query, dict):
                    query = query.get("label") or query.get("name") or query.get("title")
                title = item.get("title") or item.get("name") or query
                normalized_tasks.append({
                    "title": title,
                    "destination_query": query,
                    "duration_minutes": item.get("duration_minutes", item.get("duration")),
                    "deadline": item.get("deadline", item.get("latest_end")),
                    "fixed_time": item.get("fixed_time", item.get("fixed_start")),
                })
            data["tasks"] = normalized_tasks
            if "clarification_question" not in data:
                data["clarification_question"] = data.get("question")
            parsed = TaskList.model_validate(data)
        except Exception as exc:
            request_id=getattr(locals().get("response"),"_request_id",None)
            logger.error("Mantle task extraction failed: phase=%s type=%s status=%s request_id=%s",phase,type(exc).__name__,getattr(exc,"status_code",None),request_id)
            parsed=local_fallback()
            extraction_source="local_fallback"
            fallback_reason="mantle_request_failed" if phase == "request" else "mantle_response_invalid"
    else:
        parsed = local_fallback()
        extraction_source = "local_fallback"
        fallback_reason = "mantle_not_configured"

    output = []
    for task in parsed.tasks:
        def local_iso(value):
            if not value:
                return None
            try:
                parsed_time = __import__("datetime").datetime.fromisoformat(value)
                if parsed_time.tzinfo is None:
                    parsed_time = parsed_time.replace(tzinfo=zone)
                return parsed_time.isoformat()
            except (TypeError, ValueError):
                return None
        output.append({"title":task.title.strip(), "destination_query":task.destination_query.strip(),
                       "duration_minutes":task.duration_minutes, "latest_end":local_iso(task.deadline) or explicit_deadline(),
                       "fixed_start":local_iso(task.fixed_time)})
    return {"tasks":output, "clarification_question":parsed.clarification_question,
            "extraction_source":extraction_source, "fallback_reason":fallback_reason}

def infer_replan_updates(text, stops):
    """Extract only explicit duration extensions that can be tied to one stop."""
    import re

    match=re.search(r"\b(?:extended|increased|lengthened|longer|add(?:ed)?)\s+(?:by\s+)?(\d+)\s*(?:minutes?|mins?)\b",text,re.IGNORECASE)
    if not match:
        return {}
    minutes=int(match.group(1))
    if minutes <= 0:
        return {}
    normalized=text.casefold()
    matched=[stop for stop in stops if stop.get("title") and stop["title"].casefold() in normalized]
    if not matched and re.search(r"\b(meeting|appointment|class|call)\b",normalized):
        matched=[stop for stop in stops if any(term in f"{stop.get('type','')} {stop.get('title','')}".casefold() for term in ("meeting","appointment","class","call"))]
    if not matched and re.search(r"\b(meeting|appointment|class|call)\b",normalized):
        fixed=[stop for stop in stops if stop.get("fixed_start")]
        if len(fixed)==1:
            matched=fixed
    if len(matched)!=1:
        return {}
    stop=matched[0]
    return {stop["id"]:{"duration_minutes":int(stop["duration_minutes"])+minutes}}


def _local_replan_fallback(text, stops, timezone, schedule_context, reason):
    """Safely handle common, explicit changes if Mantle is unavailable or malformed."""
    import re
    from datetime import datetime, time
    from zoneinfo import ZoneInfo

    normalized=text.casefold()
    matches=[]
    for stop in stops:
        labels=[stop.get("title")]
        location=stop.get("location")
        if isinstance(location,dict):
            labels.append(location.get("label"))
        if any(label and len(label.strip()) >= 3 and re.search(rf"(?<!\w){re.escape(label.strip().casefold())}(?!\w)",normalized) for label in labels):
            matches.append(stop)
    duration_updates=infer_replan_updates(text,stops)
    if duration_updates:
        return {"updates":duration_updates,"stop_order":None,"optimize_route":False,"clarification_question":None,
                "source":"local_fallback","fallback_reason":reason}

    time_match=re.search(r"\b(?:by|before|no later than|at)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",text,re.I)
    if time_match and len(matches)==1:
        hour=int(time_match.group(1))
        if not 1 <= hour <= 12:
            return {"updates":{},"stop_order":None,"optimize_route":False,
                    "clarification_question":"What time should I use? Please include a time from 1 to 12 with am or pm.",
                    "source":"local_fallback","fallback_reason":reason}
        hour%=12
        if time_match.group(3).lower()=="pm":
            hour+=12
        zone=ZoneInfo(timezone)
        plan_date=datetime.fromisoformat(schedule_context["date"]).date()
        requested=datetime.combine(plan_date,time(hour,int(time_match.group(2) or 0),tzinfo=zone)).isoformat()
        return {"updates":{matches[0]["id"]:{"latest_start":requested}},"stop_order":None,"optimize_route":False,
                "clarification_question":None,"source":"local_fallback","fallback_reason":reason}
    if any(word in normalized for word in ("optimize", "shortest route", "more efficient", "less driving", "reduce distance")):
        return {"updates":{},"stop_order":None,"optimize_route":True,"clarification_question":None,
                "source":"local_fallback","fallback_reason":reason}
    return {"updates":{},"stop_order":None,"optimize_route":False,
            "clarification_question":"I couldn’t safely identify the change. Name the stop and its new time or duration, or ask me to optimize the route.",
            "source":"local_fallback","fallback_reason":reason}


def parse_replan_request(text, stops, timezone="UTC", schedule_context=None):
    """Translate a natural-language itinerary change into explicit, validated stop updates."""
    # Do not let a well-formed but empty Mantle response discard a clear named deadline.
    # E.g. "need to be at pharmacy by 5pm" is a deterministic latest_start update.
    explicit = _local_replan_fallback(text, stops, timezone, schedule_context, "explicit_request")
    if explicit["updates"]:
        explicit["source"] = "explicit_rule"
        return explicit
    if not settings.mantle_enabled:
        return _local_replan_fallback(text,stops,timezone,schedule_context,"mantle_not_configured")

    allowed_fields = {"duration_minutes", "earliest_start", "latest_start", "latest_end", "fixed_start", "priority", "mandatory"}
    stop_context = [{key: stop.get(key) for key in (
        "id", "title", "type", "duration_minutes", "earliest_start", "latest_start", "latest_end", "fixed_start", "priority", "mandatory"
    )} for stop in stops]
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key.get_secret_value(), base_url=settings.openai_base_url,
                        project=settings.openai_project_id or None, timeout=20, max_retries=1)
        response = client.chat.completions.create(
            model=settings.bedrock_model_id or "openai.gpt-oss-safeguard-20b",
            messages=[
                {"role": "system", "content": (
                    "Parse the user's requested changes to an existing itinerary. Return JSON only with shape "
                    '{"updates":{"existing-stop-id":{"duration_minutes":45,"fixed_start":"2026-10-11T16:00:00+05:30"}},"stop_order":null,"optimize_route":false,"clarification_question":null}. '
                    "Only use existing stop IDs supplied in context. Supported fields: duration_minutes (integer minutes), "
                    "earliest_start, latest_start, latest_end, fixed_start (ISO datetime including timezone offset), priority (1-5), "
                    "mandatory (boolean). For 'add/extend by N minutes', add N to the stop's current duration; for 'make it N minutes', "
                    "use N as the new total. A request to be at or arrive at a stop 'by' a time means set latest_start to that time; "
                    "do not treat it as a new destination or as a fixed appointment unless the user says the time is exact. "
                    "Return only fields the user explicitly asks to change; never invent values. "
                    "Resolve relative dates and times using the schedule date and timezone. If the request is ambiguous, refers to "
                    "an unknown or non-unique stop, or asks for a change outside supported fields, return no updates and ask one "
                    "short clarification. For an explicit requested visit order, return stop_order containing every existing stop ID "
                    "exactly once. For a request to optimize/reorder the route without a specified order, return empty updates, "
                    "stop_order null and optimize_route true; the planner will optimize the itinerary. For a vague request such as "
                    "'replan it' or 'change my plan', ask what should change. Do not claim the plan has already changed."
                )},
                {"role": "user", "content": json.dumps({"timezone": timezone, "schedule": schedule_context or {}, "stops": stop_context, "request": text}, ensure_ascii=False)},
            ], temperature=0, max_tokens=800, response_format={"type": "json_object"},
        )
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ValueError("Mantle response contained no choices")
        parsed = _json_object_from_response(getattr(getattr(choices[0], "message", None), "content", None))
        if not isinstance(parsed, dict) or not isinstance(parsed.get("updates", {}), dict):
            raise ValueError("Mantle returned an invalid replan structure")
        known_ids = {stop["id"] for stop in stops}
        validated = {}
        for stop_id, updates in parsed.get("updates", {}).items():
            if stop_id not in known_ids or not isinstance(updates, dict):
                raise ValueError("Mantle referenced an unknown stop")
            clean = {}
            for field, value in updates.items():
                if field not in allowed_fields:
                    raise ValueError("Mantle returned an unsupported stop field")
                if field == "duration_minutes":
                    value = int(value)
                    if not 1 <= value <= 1440:
                        raise ValueError("duration_minutes is outside the supported range")
                elif field == "priority":
                    value = int(value)
                    if not 1 <= value <= 5:
                        raise ValueError("priority is outside the supported range")
                elif field == "mandatory" and not isinstance(value, bool):
                    raise ValueError("mandatory must be a boolean")
                elif field in {"earliest_start", "latest_start", "latest_end", "fixed_start"}:
                    from datetime import datetime
                    parsed_time = datetime.fromisoformat(value)
                    if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
                        raise ValueError("requested schedule times must include a timezone offset")
                clean[field] = value
            if clean:
                validated[stop_id] = clean
        question = parsed.get("clarification_question")
        if question is not None and not isinstance(question, str):
            raise ValueError("clarification_question must be text or null")
        stop_order = parsed.get("stop_order")
        if stop_order is not None and (not isinstance(stop_order, list) or len(stop_order) != len(known_ids) or set(stop_order) != known_ids):
            raise ValueError("Mantle returned an invalid requested stop order")
        optimize_route = parsed.get("optimize_route", False)
        if not isinstance(optimize_route, bool):
            raise ValueError("optimize_route must be a boolean")
        return {"updates": validated, "stop_order": stop_order, "optimize_route": optimize_route, "clarification_question": question, "source": "mantle"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Mantle replan parsing failed: type=%s status=%s request_id=%s", type(exc).__name__, getattr(exc, "status_code", None), getattr(locals().get("response"), "_request_id", None))
        return _local_replan_fallback(text,stops,timezone,schedule_context,"mantle_response_or_request_failed")

import boto3
import json
import logging
from botocore.config import Config
from app.config import settings
from app.planner import MockTravelProvider, Leg
from fastapi import HTTPException

logger = logging.getLogger(__name__)

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

def parse_intent(text, timezone="UTC"):
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
                    "the place or requested action is genuinely missing or ambiguous. "
                    f"Timezone={timezone}. User request={text}")
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
            raise HTTPException(502, "Bedrock Mantle intent request failed") from exc

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
            return parsed.model_dump()
        except Exception as exc:
            logger.error(
                "Mantle intent response invalid: type=%s finish_reason=%s request_id=%s",
                type(exc).__name__,
                getattr(choices[0], "finish_reason", None) if choices else None,
                getattr(response, "_request_id", None),
            )
            raise HTTPException(502, "Bedrock Mantle returned an invalid intent response") from exc
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
    if settings.mantle_enabled:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key.get_secret_value(), base_url=settings.openai_base_url,
                            project=settings.openai_project_id or None, timeout=20, max_retries=1)
            prompt = (
                "Extract distinct real-world errands and appointments from the user's new-day planning request. "
                "Return JSON only: {tasks:[{title,destination_query,duration_minutes,deadline,fixed_time}],clarification_question}. "
                "Use one task per distinct place/action; split coordinated errands such as grocery store and pharmacy. "
                "Preserve destination wording so it can be searched. Never invent a place, deadline, appointment, or duration. "
                "duration_minutes is null unless explicitly stated. deadline and fixed_time are null unless explicitly stated; "
                "otherwise return local ISO datetime with the supplied timezone offset. If the request has no actionable "
                "destination tasks, return an empty tasks array and a concise clarification_question. "
                f"Plan date={date_value.isoformat()}, timezone={timezone}, UTC offset on plan date={date_value and __import__('datetime').datetime.combine(date_value, __import__('datetime').time(12), zone).utcoffset()}. "
                f"Request={text}"
            )
            response = client.chat.completions.create(
                model=settings.bedrock_model_id or "openai.gpt-oss-safeguard-20b",
                messages=[{"role":"user","content":prompt}], temperature=0,
                response_format={"type":"json_object"},
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            parsed = TaskList.model_validate(data)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Mantle task extraction failed: type=%s status=%s request_id=%s", type(exc).__name__, getattr(exc,"status_code",None), getattr(locals().get("response"),"_request_id",None))
            raise HTTPException(502, "Bedrock Mantle task extraction failed") from exc
    else:
        # Local fallback supports straightforward coordinated lists; Mantle handles richer phrasing.
        import re
        cleaned = re.sub(r"^\s*(?:i need to|i want to|please|can you help me|help me)\s+", "", text, flags=re.I)
        cleaned = re.sub(r"^(?:visit|go to|stop by|pick up from|pick up|buy from|buy|get to)\s+", "", cleaned, flags=re.I)
        parts = re.split(r"\s*,\s*|\s+and\s+", cleaned, flags=re.I)
        time_match = re.search(r"\b(?:before|by|no later than)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.I)
        duration_match = re.search(r"\b(?:for|about|around)\s+(\d{1,3})\s*(?:minutes?|mins?)\b", text, re.I)
        deadline = None
        if time_match:
            hour = int(time_match.group(1)) % 12
            if time_match.group(3).lower() == "pm":
                hour += 12
            deadline = __import__("datetime").datetime.combine(
                date_value, __import__("datetime").time(hour, int(time_match.group(2) or 0), tzinfo=zone)
            ).isoformat()
        tasks = []
        for part in parts:
            query = re.sub(r"\b(?:before|by|no later than)\b.*$", "", part, flags=re.I).strip(" .?!")
            query = re.sub(r"^(?:the|a|an)\s+", "", query, flags=re.I)
            if query:
                title = query[:1].upper() + query[1:]
                tasks.append(Task(title=title, destination_query=query,
                                  duration_minutes=int(duration_match.group(1)) if duration_match else None,
                                  deadline=deadline))
        parsed = TaskList(tasks=tasks[:12], clarification_question=None if tasks else "What places or errands should I include?")

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
                       "duration_minutes":task.duration_minutes, "latest_end":local_iso(task.deadline),
                       "fixed_start":local_iso(task.fixed_time)})
    return {"tasks":output, "clarification_question":parsed.clarification_question}

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

import boto3
from botocore.config import Config
from app.config import settings
from app.planner import MockTravelProvider, Leg
from fastapi import HTTPException

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
                    f"Timezone={timezone}. User request={text}")
            response=client.chat.completions.create(
                model=settings.bedrock_model_id or "openai.gpt-oss-safeguard-20b",
                messages=[{"role":"user","content":prompt}],
                temperature=0,
                response_format={"type":"json_object"},
            )
            import json
            from pydantic import ValidationError
            from app.strands_agent import ParsedIntent
            raw=response.choices[0].message.content or ""
            parsed=ParsedIntent.model_validate_json(raw)
            return parsed.model_dump()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502,"Bedrock Mantle returned an invalid intent response") from exc
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

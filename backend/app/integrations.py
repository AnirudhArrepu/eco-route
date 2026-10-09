import boto3
from app.config import settings
from app.planner import MockTravelProvider, Leg

class AmazonLocation:
    def __init__(self):
        self.client = boto3.client("geo", region_name=settings.aws_region)
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
        self.aws=AmazonLocation() if settings.aws_integrations_enabled and settings.location_route_calculator_name else None
    def leg(self,a,b,mode="Walking"):
        return self.aws.route(a,b,mode) if self.aws else self.mock.leg(a,b,mode)

def search_places(text,bias=None,max_results=10):
    if not (settings.aws_integrations_enabled and settings.location_index_name): return []
    return AmazonLocation().search(text,bias,max_results)

def parse_intent(text, timezone="UTC"):
    if settings.aws_integrations_enabled and settings.bedrock_model_id:
        client=boto3.client("bedrock-runtime",region_name=settings.aws_region)
        prompt=("Return JSON only with keys operation,destination_query,clarification_needed,clarification_question. "
                "Allowed operation: add_destination,replan,create_schedule,clarify. Never invent inventory or prices. "
                f"Timezone={timezone}. User request={text}")
        response=client.converse(modelId=settings.bedrock_model_id,messages=[{"role":"user","content":[{"text":prompt}]}],inferenceConfig={"temperature":0,"maxTokens":500})
        content=response["output"]["message"]["content"]
        raw="".join(x.get("text","") for x in content)
        import json
        return json.loads(raw[raw.find("{"):raw.rfind("}")+1])
    low=text.lower()
    op="replan" if any(x in low for x in ("replan","reschedule","meeting moved")) else "create_schedule" if "create a schedule" in low else "add_destination"
    return {"operation":op,"destination_query":text,"clarification_needed":False,"clarification_question":None}

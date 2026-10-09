from datetime import datetime, timezone
from app.planner import plan, MockTravelProvider, optimize_schedule, Leg

def dt(h,m=0): return datetime(2026,10,9,h,m,tzinfo=timezone.utc)
def stop(i,lat,lon,d=20,fixed=None):
    return {"id":i,"title":i,"type":"errand","location":{"id":i,"latitude":lat,"longitude":lon},"duration_minutes":d,"fixed_start":fixed.isoformat() if fixed else None,"mandatory":True}
def req(existing,candidates):
    return {"start_at":dt(9),"end_at":dt(19),"start_location":{"latitude":13.0,"longitude":80.2},"end_location":{"latitude":13.0,"longitude":80.2},"existing_stops":existing,"candidate_stops":candidates,"constraints":[{"type":"preserve_fixed_appointments","hardness":"hard"}],"max_candidate_evaluations":500}
def test_add_stop():
    result=plan(req([stop("meeting",13.01,80.21,60,dt(10))],[stop("shop",13.02,80.22)]),MockTravelProvider())
    assert result["feasible"]
    assert "shop" in [s["id"] for s in result["stops"]]
def test_empty_schedule_is_feasible():
    result=plan(req([],[]),MockTravelProvider())
    assert result["feasible"]

def test_fixed_start_outside_latest_window_is_infeasible():
    item=stop("fixed",13.0,80.2,30,dt(10))
    item["latest_start"] = dt(9, 30).isoformat()
    result=plan(req([item],[]),MockTravelProvider())
    assert not result["feasible"]
    assert any(x["constraint_type"]=="time_window" for x in result["conflicts"])

def test_max_travel_constraint_includes_return_leg():
    request=req([], [stop("shop",13.02,80.22)])
    request["constraints"]=[{"type":"max_travel_minutes","hardness":"hard","parameters":{"minutes":1}}]
    result=plan(request,MockTravelProvider())
    assert not result["feasible"]

def test_naive_stop_time_is_rejected_for_aware_schedule():
    item=stop("shop",13.0,80.2)
    item["earliest_start"]="2026-10-09T10:00:00"
    result=plan(req([item],[]),MockTravelProvider())
    assert not result["feasible"]
    assert any(x["constraint_type"]=="invalid_input" for x in result["conflicts"])

def test_candidate_evaluation_limit_zero_returns_structured_conflict():
    request=req([], [stop("shop",13.02,80.22)])
    request["max_candidate_evaluations"]=0
    result=plan(request,MockTravelProvider())
    assert not result["feasible"]
    assert result["conflicts"][0]["constraint_type"]=="candidate_limit"

def test_new_schedule_optimizer_returns_timed_order_and_respects_deadline():
    first=stop("late-shop",13.03,80.23,20)
    first["latest_start"] = dt(11).isoformat()
    second=stop("early-meeting",13.01,80.21,30)
    second["latest_end"] = dt(10,30).isoformat()
    request=req([first,second],[])
    result=optimize_schedule(request,MockTravelProvider())
    assert result["feasible"]
    assert [item["id"] for item in result["stops"]][0] == "early-meeting"
    timeline=result["metrics"]["after"]["timeline"]
    assert timeline[0]["start_at"] <= timeline[0]["end_at"]
    assert result["metrics"]["after"]["return_arrival_at"]

def test_schedule_optimizer_reports_infeasible_deadline():
    item=stop("impossible",13.02,80.22,60)
    item["latest_end"] = dt(9,1).isoformat()
    result=optimize_schedule(req([item],[]),MockTravelProvider())
    assert not result["feasible"]
    assert any(conflict["constraint_type"] in {"latest_end","schedule_horizon"} for conflict in result["conflicts"])

def test_schedule_optimizer_caches_route_legs_across_orders():
    class CountingProvider:
        def __init__(self): self.calls=[]
        def leg(self,a,b,mode="Walking"):
            key=(a["latitude"],a["longitude"],b["latitude"],b["longitude"],mode)
            self.calls.append(key)
            return Leg(1,1)
    provider=CountingProvider()
    request=req([stop("a",13.01,80.21),stop("b",13.02,80.22),stop("c",13.03,80.23)],[])
    result=optimize_schedule(request,provider)
    assert result["feasible"]
    assert len(provider.calls)==len(set(provider.calls))

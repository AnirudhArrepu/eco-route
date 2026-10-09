from datetime import datetime, timezone
from app.planner import plan, MockTravelProvider

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

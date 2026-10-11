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


def test_schedule_optimizer_prioritizes_shorter_route_for_climate_goal():
    class TradeoffProvider:
        def leg(self, origin, destination, mode="Walking"):
            route = (origin["latitude"], destination["latitude"])
            distances = {(0, 1): 1, (1, 2): 1, (2, 3): 1, (0, 2): 2, (2, 1): 2, (1, 3): 1,
                         (0, 3): 1, (1, 0): 1, (2, 0): 2}
            minutes = {(0, 1): 60, (1, 2): 60, (2, 3): 60, (0, 2): 1, (2, 1): 1, (1, 3): 1,
                       (0, 3): 1, (1, 0): 1, (2, 0): 1}
            return Leg(minutes.get(route, 1), distances.get(route, 1))

    first, second = stop("first", 1, 0), stop("second", 2, 0)
    request = req([first, second], [])
    request["start_location"] = {"latitude": 0, "longitude": 0}
    request["end_location"] = {"latitude": 3, "longitude": 0}

    result = optimize_schedule(request, TradeoffProvider())

    assert result["feasible"]
    assert [item["id"] for item in result["stops"]] == ["first", "second"]
    assert result["metrics"]["after"]["distance_km"] == 3
    assert result["metrics"]["objective"] == "minimum feasible route distance"


def test_distance_savings_estimates_co2_using_selected_travel_mode():
    from app.planner import calculate_distance_savings

    request = req([], [])
    request["start_location"] = {"latitude": 0, "longitude": 0}
    request["end_location"] = {"latitude": 0, "longitude": 0}
    provider = MockTravelProvider()
    stop_item = stop("errand", 1, 0, 10)
    stop_item["location"] = {"latitude": 1, "longitude": 0}

    car = calculate_distance_savings([stop_item], request, provider, "Car", planned_km=10)
    walking = calculate_distance_savings([stop_item], request, provider, "Walking", planned_km=10)

    assert car["estimated_co2_saved_kg"] == round(car["saved_km"] * 0.140, 3)
    assert car["co2_factor_source_url"].startswith("https://")
    assert walking["estimated_co2_saved_kg"] == 0
    scenario = walking["public_transport_scenario"]
    assert scenario["distance_km"] == 10
    assert scenario["estimated_car_co2_kg"] == 1.4
    assert scenario["estimated_public_transport_co2e_kg"] == 0.6
    assert scenario["estimated_co2e_saved_kg"] == 0.8
    assert "not a public-transport route" in scenario["warning"]
    assert calculate_distance_savings([stop_item], request, provider, "Walking", None)["public_transport_scenario"] is None


def test_schedule_optimizer_improves_orders_with_more_than_eight_stops():
    input_stops = [stop(f"s{index}", index / 1000, 0, 1) for index in [5, 9, 4, 8, 3, 7, 2, 6, 1]]
    request = req(input_stops, [])
    request["start_location"] = {"latitude": 0, "longitude": 0}
    request["end_location"] = {"latitude": 0, "longitude": 0}

    baseline = plan(request, MockTravelProvider())
    result = optimize_schedule(request, MockTravelProvider())

    assert result["feasible"]
    assert result["search_truncated"] is True
    assert result["evaluated_orders"] > 1
    assert result["metrics"]["after"]["distance_km"] < baseline["metrics"]["after"]["distance_km"]

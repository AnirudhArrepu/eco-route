from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import radians, sin, cos, asin, sqrt
from typing import Any

@dataclass
class Leg:
    minutes: float
    distance_km: float

class MockTravelProvider:
    SPEED = {"Walking": 4.5, "Bicycle": 15.0, "Car": 25.0}
    def leg(self, a: dict, b: dict, mode: str = "Walking") -> Leg:
        lat1, lon1 = radians(float(a["latitude"])), radians(float(a["longitude"]))
        lat2, lon2 = radians(float(b["latitude"])), radians(float(b["longitude"]))
        h = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
        km = 6371 * 2 * asin(sqrt(h)) * 1.25
        return Leg(km / self.SPEED.get(mode, 4.5) * 60 + (2 if km else 0), km)

def loc(stop):
    return stop["location"]

def validate(stops, start_at, end_at, start_location, end_location, provider, mode, constraints):
    conflicts, timing = [], []
    current_time, current_loc = start_at, start_location
    ids = [s["id"] for s in stops]
    for c in constraints:
        if c["type"] == "precedence" and c.get("hardness", "hard") == "hard":
            before, after = c.get("parameters", {}).get("before"), c.get("parameters", {}).get("after")
            if before in ids and after in ids and ids.index(before) >= ids.index(after):
                conflicts.append({"constraint_type":"precedence","reason":f"{before} must precede {after}"})
    for s in stops:
        leg = provider.leg(current_loc, loc(s), mode)
        arrival = current_time + timedelta(minutes=leg.minutes)
        start = max(arrival, datetime.fromisoformat(s["earliest_start"]) if s.get("earliest_start") else arrival)
        fixed = datetime.fromisoformat(s["fixed_start"]) if s.get("fixed_start") else None
        if fixed:
            if arrival > fixed:
                conflicts.append({"constraint_type":"fixed_appointment","stop_id":s["id"],"reason":"Cannot arrive before fixed appointment"})
            start = fixed
        if s.get("latest_start") and start > datetime.fromisoformat(s["latest_start"]):
            conflicts.append({"constraint_type":"time_window","stop_id":s["id"],"reason":"Latest start exceeded"})
        finish = start + timedelta(minutes=s["duration_minutes"])
        if s.get("latest_end") and finish > datetime.fromisoformat(s["latest_end"]):
            conflicts.append({"constraint_type":"latest_end","stop_id":s["id"],"reason":"Latest end exceeded"})
        oh = s.get("opening_hours") or {}
        if oh.get("open") and oh.get("close"):
            day = start.date()
            op = datetime.fromisoformat(f"{day}T{oh['open']}:00").replace(tzinfo=start.tzinfo)
            cl = datetime.fromisoformat(f"{day}T{oh['close']}:00").replace(tzinfo=start.tzinfo)
            if start < op or finish > cl:
                conflicts.append({"constraint_type":"opening_hours","stop_id":s["id"],"reason":"Visit does not fit opening hours"})
        if start < start_at or finish > end_at:
            conflicts.append({"constraint_type":"schedule_horizon","stop_id":s["id"],"reason":"Stop outside schedule horizon"})
        timing.append({"arrival":arrival,"start":start,"end":finish,"travel":leg.minutes,"distance":leg.distance_km,"wait":max(0,(start-arrival).total_seconds()/60)})
        current_time, current_loc = finish, loc(s)
    final_leg = provider.leg(current_loc, end_location, mode)
    if current_time + timedelta(minutes=final_leg.minutes) > end_at:
        conflicts.append({"constraint_type":"schedule_horizon","reason":"End journey exceeds schedule horizon"})
    return not conflicts, conflicts, timing

def metrics(stops, req, provider, mode):
    ok, conflicts, timing = validate(stops, req["start_at"], req["end_at"], req["start_location"], req["end_location"], provider, mode, req["constraints"])
    # include final return leg in route totals
    last_loc = loc(stops[-1]) if stops else req["start_location"]
    endleg = provider.leg(last_loc, req["end_location"], mode)
    travel = sum(x["travel"] for x in timing) + endleg.minutes
    distance = sum(x["distance"] for x in timing) + endleg.distance_km
    return {"feasible":ok,"travel_minutes":round(travel,2),"distance_km":round(distance,2),"waiting_minutes":round(sum(x["wait"] for x in timing),2),"stop_count":len(stops)}, conflicts

def plan(req, provider=None, mode="Walking"):
    provider = provider or MockTravelProvider()
    existing = req["existing_stops"]
    before, before_conflicts = metrics(existing, req, provider, mode)
    if not before["feasible"]:
        return {"feasible":False,"stops":existing,"metrics":{"before":before,"after":None},"conflicts":before_conflicts,"explanation_facts":["The existing schedule violates one or more hard constraints."]}
    candidates, evals = [], 0
    destinations = req.get("candidate_stops", [])
    if not destinations:
        candidates.append(existing)
        if req.get("allow_reordering_flexible_stops", False):
            flexible = [i for i,s in enumerate(existing) if not s.get("fixed_start")]
            for a,b in zip(flexible, flexible[1:]):
                if evals >= req.get("max_candidate_evaluations", 500): break
                alt = list(existing); alt[a],alt[b] = alt[b],alt[a]; candidates.append(alt); evals += 1
    else:
        limit = req.get("max_candidate_evaluations", 500)
        for d in destinations:
            for i in range(len(existing)+1):
                if evals >= limit: break
                alt=list(existing); alt.insert(i,d); candidates.append(alt); evals+=1
            if evals >= limit: break
    valid = []
    weights = req.get("weights", {"travel_time":5,"distance":1,"disruption":4})
    for candidate in candidates:
        after, conflicts = metrics(candidate, req, provider, mode)
        if not after["feasible"]: continue
        original_ids=[s["id"] for s in existing]
        proposed_common=[s["id"] for s in candidate if s["id"] in original_ids]
        disruption=sum(a!=b for a,b in zip(original_ids,proposed_common))
        score = weights.get("travel_time",5)*after["travel_minutes"]/max(60,before["travel_minutes"]) + weights.get("distance",1)*after["distance_km"]/max(10,before["distance_km"]) + weights.get("disruption",4)*disruption/max(1,len(existing))
        valid.append((score,candidate,after))
    if not valid:
        return {"feasible":False,"stops":existing,"metrics":{"before":before,"after":None},"conflicts":[{"constraint_type":"no_feasible_candidate","reason":"No candidate plan satisfies hard constraints"}],"explanation_facts":["Try another destination or adjust a user-approved constraint."]}
    valid.sort(key=lambda x:x[0])
    score, best, after=valid[0]
    return {"feasible":True,"stops":best,"metrics":{"before":before,"after":after,"score":score},"conflicts":[],"explanation_facts":[f"Travel time changes by {after['travel_minutes']-before['travel_minutes']:+.1f} minutes.","All configured hard constraints passed validation."]}
